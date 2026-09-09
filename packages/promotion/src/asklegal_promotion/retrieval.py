"""Synthetic-only top-results evaluator mechanics for Plan 6 Task 4A.

This module deliberately has no production adapter, provider configuration, or
Pinecone integration.  It proves that an injected scripted query result is
checked faithfully; it never claims that its vectors, ordering, witnesses, or
results are retrieval-quality evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Never, Protocol, TypeGuard
from weakref import ref

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .builder import serving_metadata_fingerprint, verify_embedding_profile
from .model import (
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingReceipt,
    EmbeddingRequest,
    TargetDefinition,
)
from .ports import EmbeddingPort

_LANGUAGE_SLICES = frozenset({"EN", "ZH_HANT", "BILINGUAL", "CROSS_LANGUAGE"})
_FINGERPRINT_PREFIX = "sha256:"
_MAX_TOP_K = 100


class RetrievalContractError(RuntimeError):
    """One closed Task 4A local-contract failure."""


class EvaluationState(StrEnum):
    """Closed evaluator-only result states; none is a V1 admission state."""

    NOT_EVALUATED = "NOT_EVALUATED"
    SYNTHETIC_CONTRACT_FAILED = "SYNTHETIC_CONTRACT_FAILED"
    SYNTHETIC_CONTRACT_PASSED = "SYNTHETIC_CONTRACT_PASSED"


class AdmissionState(StrEnum):
    """Task 4A cannot issue capability or V1 admission."""

    NOT_ADMITTED = "NOT_ADMITTED"


@dataclass(frozen=True, slots=True)
class ServingPayload:
    """The exact six-field payload used to recompute a returned witness hash."""

    text: str
    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str


@dataclass(frozen=True, slots=True)
class RetrievalWitness:
    """One synthetic allowed query result, independently marked expected or not."""

    record_id: str
    payload: ServingPayload
    expected: bool


@dataclass(frozen=True, slots=True)
class RetrievedTargetRecord:
    """One injected query result; its payload fingerprint is always recomputed."""

    record_id: str
    score: float
    payload: ServingPayload


@dataclass(frozen=True, slots=True)
class RetrievalGoldenCase:
    """One synthetic evaluator input, never authentic V1 golden evidence."""

    case_id: str
    language_slice: str
    embedding_request: EmbeddingRequest
    witnesses: tuple[RetrievalWitness, ...]
    top_k: int


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class SyntheticRetrievalSnapshot:
    """Factory-issued private snapshot whose authority is process-local only."""

    profile: EmbeddingProfile
    target_name: str
    target_state_fingerprint: str
    target_dimensions: int
    target_metric: str
    target_namespace: str
    cases: tuple[RetrievalGoldenCase, ...]
    canonical_bytes: bytes
    fingerprint: str

    def __copy__(self) -> SyntheticRetrievalSnapshot:
        """Return an ordinary unissued projection."""
        return object.__new__(type(self))

    def __deepcopy__(self, memo: dict[int, object]) -> SyntheticRetrievalSnapshot:
        """Deep copies are intentionally ordinary unissued projections."""
        del memo
        return object.__new__(type(self))

    def __reduce__(self) -> Never:
        """Do not let an issued snapshot transfer process-local authority."""
        _assert_issued_snapshot(self)
        message = "SNAPSHOT_NONTRANSFERABLE"
        raise TypeError(message)


@dataclass(frozen=True, slots=True)
class RetrievalGoldenCaseResult:
    """One exact mechanical outcome of an injected scripted query."""

    case_id: str
    query_request_fingerprint: str
    expected_record_ids: tuple[str, ...]
    expected_payload_fingerprints: tuple[str, ...]
    returned_record_ids: tuple[str, ...]
    returned_scores: tuple[float, ...]
    returned_payload_fingerprints: tuple[str, ...]
    failure_code: str | None


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class HKV1RetrievalEvaluationResult:
    """A local result that remains explicitly not admitted in every state."""

    state: EvaluationState
    admission_state: AdmissionState
    snapshot_canonical_bytes: bytes
    snapshot_fingerprint: str
    profile_fingerprint: str
    target_name: str
    target_state_fingerprint: str
    target_dimensions: int
    target_metric: str
    target_namespace: str
    case_results: tuple[RetrievalGoldenCaseResult, ...]
    failure_codes: tuple[str, ...]
    fingerprint: str

    def __copy__(self) -> HKV1RetrievalEvaluationResult:
        """Return an ordinary unissued projection."""
        return object.__new__(type(self))

    def __deepcopy__(self, memo: dict[int, object]) -> HKV1RetrievalEvaluationResult:
        """Deep copies are intentionally ordinary unissued projections."""
        del memo
        return object.__new__(type(self))

    def __reduce__(self) -> Never:
        """Do not transfer evaluator-result authority through pickle."""
        assert_retrieval_evaluation_result(self)
        message = "RESULT_NONTRANSFERABLE"
        raise TypeError(message)


@dataclass(frozen=True, slots=True)
class _PrivateSnapshot:
    """Detached primitives captured before any marker or port callback."""

    profile: EmbeddingProfile
    target_name: str
    target_state_fingerprint: str
    target_dimensions: int
    target_metric: str
    target_namespace: str
    cases: tuple[RetrievalGoldenCase, ...]
    canonical_bytes: bytes
    fingerprint: str


class RetrievalQueryPort(Protocol):
    """Evaluator-only injected vector-query boundary; no serving adapter implements it yet."""

    def query(
        self, name: str, vector: tuple[float, ...], top_k: int
    ) -> tuple[RetrievedTargetRecord, ...]:
        """Return one ordered synthetic witness list for the exact injected vector."""
        ...


@dataclass(frozen=True, slots=True)
class _IssuedSnapshot:
    fingerprint: str
    projection: bytes
    private: _PrivateSnapshot


_ISSUED: dict[int, tuple[ref[SyntheticRetrievalSnapshot], _IssuedSnapshot]] = {}


@dataclass(frozen=True, slots=True)
class _IssuedResult:
    fingerprint: str
    projection: bytes
    private: _PrivateResult


@dataclass(frozen=True, slots=True)
class _PrivateCaseResult:
    """Detached, complete per-case result facts owned only by the registry."""

    case_id: str
    query_request_fingerprint: str
    expected_record_ids: tuple[str, ...]
    expected_payload_fingerprints: tuple[str, ...]
    returned_record_ids: tuple[str, ...]
    returned_scores: tuple[float, ...]
    returned_payload_fingerprints: tuple[str, ...]
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class _PrivateResult:
    """The immutable result facts from which every public result is rebuilt."""

    state: EvaluationState
    snapshot_canonical_bytes: bytes
    snapshot_fingerprint: str
    profile_fingerprint: str
    target_name: str
    target_state_fingerprint: str
    target_dimensions: int
    target_metric: str
    target_namespace: str
    case_results: tuple[_PrivateCaseResult, ...]
    failure_codes: tuple[str, ...]


_ISSUED_RESULTS: dict[int, tuple[ref[HKV1RetrievalEvaluationResult], _IssuedResult]] = {}


def _fail(code: str) -> Never:
    raise RetrievalContractError(code)


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        _fail(code)
    return value


def _identifier(value: object, code: str) -> str:
    result = _text(value, code)
    if any(character.isspace() for character in result):
        _fail(code)
    return result


def _fingerprint(raw: bytes) -> str:
    return f"{_FINGERPRINT_PREFIX}{sha256(raw).hexdigest()}"


def _object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    """Narrow only a concrete tuple whose elements remain untrusted objects."""
    return type(value) is tuple


def _payload_document(payload: ServingPayload) -> dict[str, str]:
    if type(payload) is not ServingPayload:
        _fail("RESULT_METADATA_INVALID")
    return {
        "authority_note": _text(payload.authority_note, "RESULT_METADATA_INVALID"),
        "country": _text(payload.country, "RESULT_METADATA_INVALID"),
        "jurisdiction": _text(payload.jurisdiction, "RESULT_METADATA_INVALID"),
        "source": _text(payload.source, "RESULT_METADATA_INVALID"),
        "text": _text(payload.text, "RESULT_METADATA_INVALID"),
        "type": _text(payload.material_type, "RESULT_METADATA_INVALID"),
    }


def _payload_fingerprint(payload: ServingPayload) -> str:
    try:
        return serving_metadata_fingerprint(_payload_document(payload))
    except RetrievalContractError:
        raise
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        _fail("RESULT_METADATA_INVALID")


def _profile_document(profile: EmbeddingProfile) -> dict[str, object]:
    if type(profile) is not EmbeddingProfile:
        _fail("SNAPSHOT_UNISSUED")
    try:
        verify_embedding_profile(profile)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        _fail("SNAPSHOT_UNISSUED")
    return {
        "allowed_environments": list(profile.allowed_environments),
        "api_contract": profile.api_contract,
        "cost_limit_microunits": profile.cost_limit_microunits,
        "deployment_name": profile.deployment_name,
        "dimensions": profile.dimensions,
        "encoding": profile.encoding,
        "expires_at": profile.expires_at,
        "geography_class": profile.geography_class,
        "max_input_tokens": profile.max_input_tokens,
        "metric": profile.metric,
        "model_id": profile.model_id,
        "model_version": profile.model_version,
        "normalization": profile.normalization,
        "profile_fingerprint": profile.profile_fingerprint,
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "resource_class": profile.resource_class,
        "stateful_features": profile.stateful_features,
        "tokenizer": profile.tokenizer,
    }


def _request_document(request: EmbeddingRequest, profile_id: str) -> dict[str, object]:
    if type(request) is not EmbeddingRequest:
        _fail("CASE_REQUEST_INVALID")
    if request.profile_id != profile_id:
        _fail("CASE_REQUEST_INVALID")
    if (
        type(request.token_count) is not int
        or request.token_count < 0
        or type(request.batch_position) is not int
        or request.batch_position < 0
    ):
        _fail("CASE_REQUEST_INVALID")
    return {
        "batch_id": _identifier(request.batch_id, "CASE_REQUEST_INVALID"),
        "batch_position": request.batch_position,
        "cache_key": _text(request.cache_key, "CASE_REQUEST_INVALID"),
        "profile_id": _identifier(request.profile_id, "CASE_REQUEST_INVALID"),
        "record_id": _identifier(request.record_id, "CASE_REQUEST_INVALID"),
        "request_id": _identifier(request.request_id, "CASE_REQUEST_INVALID"),
        "serving_payload_fingerprint": _text(
            request.serving_payload_fingerprint, "CASE_REQUEST_INVALID"
        ),
        "text": _text(request.text, "CASE_REQUEST_INVALID"),
        "text_fingerprint": _text(request.text_fingerprint, "CASE_REQUEST_INVALID"),
        "token_count": request.token_count,
    }


def _case_document(case: RetrievalGoldenCase, profile_id: str) -> dict[str, object]:
    if type(case) is not RetrievalGoldenCase:
        _fail("CASE_INVALID")
    if case.language_slice not in _LANGUAGE_SLICES:
        _fail("CASE_LANGUAGE_INVALID")
    if type(case.top_k) is not int or not 1 <= case.top_k <= _MAX_TOP_K:
        _fail("CASE_TOP_K_INVALID")
    if type(case.witnesses) is not tuple or not case.witnesses:
        _fail("CASE_WITNESS_INVALID")
    witnesses: list[dict[str, object]] = []
    identifiers: set[str] = set()
    expected_count = 0
    for witness in case.witnesses:
        if type(witness) is not RetrievalWitness or type(witness.expected) is not bool:
            _fail("CASE_WITNESS_INVALID")
        identifier = _identifier(witness.record_id, "CASE_WITNESS_INVALID")
        if identifier in identifiers:
            _fail("CASE_WITNESS_INVALID")
        identifiers.add(identifier)
        if witness.expected:
            expected_count += 1
        witnesses.append(
            {
                "expected": witness.expected,
                "payload_fingerprint": _payload_fingerprint(witness.payload),
                "record_id": identifier,
            }
        )
    if expected_count == 0:
        _fail("CASE_WITNESS_INVALID")
    return {
        "case_id": _identifier(case.case_id, "CASE_INVALID"),
        "embedding_request": _request_document(case.embedding_request, profile_id),
        "language_slice": case.language_slice,
        "top_k": case.top_k,
        "witnesses": witnesses,
    }


def _snapshot_projection(snapshot: SyntheticRetrievalSnapshot) -> bytes:
    if type(snapshot) is not SyntheticRetrievalSnapshot:
        _fail("SNAPSHOT_UNISSUED")
    profile = _profile_document(snapshot.profile)
    if (
        type(snapshot.target_dimensions) is not int
        or snapshot.target_dimensions != snapshot.profile.dimensions
        or _text(snapshot.target_metric, "SNAPSHOT_UNISSUED") != snapshot.profile.metric
    ):
        _fail("SNAPSHOT_UNISSUED")
    cases = [_case_document(case, snapshot.profile.profile_id) for case in snapshot.cases]
    case_ids = [_identifier(case.case_id, "SNAPSHOT_UNISSUED") for case in snapshot.cases]
    if not cases or case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
        _fail("SNAPSHOT_UNISSUED")
    return canonicalize(
        checked_json_value(
            {
                "cases": cases,
                "profile": profile,
                "target": {
                    "dimensions": snapshot.target_dimensions,
                    "metric": _text(snapshot.target_metric, "SNAPSHOT_UNISSUED"),
                    "name": _identifier(snapshot.target_name, "SNAPSHOT_UNISSUED"),
                    "namespace": _text(snapshot.target_namespace, "SNAPSHOT_UNISSUED"),
                    "state_fingerprint": _text(
                        snapshot.target_state_fingerprint, "SNAPSHOT_UNISSUED"
                    ),
                },
                "type": "asklegal.synthetic-retrieval-evaluator.v1",
            }
        )
    )


def _copy_profile(profile: EmbeddingProfile) -> EmbeddingProfile:
    """Detach every profile primitive from a callback-visible public object."""
    return EmbeddingProfile(
        profile.profile_id,
        profile.profile_fingerprint,
        profile.provider,
        profile.resource_class,
        profile.geography_class,
        profile.deployment_name,
        profile.model_id,
        profile.model_version,
        profile.api_contract,
        profile.tokenizer,
        profile.dimensions,
        profile.encoding,
        profile.normalization,
        profile.metric,
        profile.max_input_tokens,
        profile.cost_limit_microunits,
        profile.expires_at,
        tuple(profile.allowed_environments),
        profile.stateful_features,
    )


def _copy_case(case: RetrievalGoldenCase) -> RetrievalGoldenCase:
    """Detach each request, witness, expected flag, and six-field payload."""
    request = case.embedding_request
    copied_request = EmbeddingRequest(
        request.request_id,
        request.record_id,
        request.serving_payload_fingerprint,
        request.text,
        request.text_fingerprint,
        request.token_count,
        request.profile_id,
        request.batch_id,
        request.batch_position,
        request.cache_key,
    )
    witnesses = tuple(
        RetrievalWitness(
            witness.record_id,
            ServingPayload(
                witness.payload.text,
                witness.payload.country,
                witness.payload.jurisdiction,
                witness.payload.material_type,
                witness.payload.source,
                witness.payload.authority_note,
            ),
            witness.expected,
        )
        for witness in case.witnesses
    )
    return RetrievalGoldenCase(
        case.case_id, case.language_slice, copied_request, witnesses, case.top_k
    )


def _private_snapshot(snapshot: SyntheticRetrievalSnapshot, projection: bytes) -> _PrivateSnapshot:
    """Capture the entire validated public input before any callback can run."""
    return _PrivateSnapshot(
        _copy_profile(snapshot.profile),
        snapshot.target_name,
        snapshot.target_state_fingerprint,
        snapshot.target_dimensions,
        snapshot.target_metric,
        snapshot.target_namespace,
        tuple(_copy_case(case) for case in snapshot.cases),
        bytes(projection),
        _fingerprint(projection),
    )


def _assert_issued_snapshot(snapshot: object) -> _PrivateSnapshot:
    if type(snapshot) is not SyntheticRetrievalSnapshot:
        _fail("SNAPSHOT_UNISSUED")
    entry = _ISSUED.pop(id(snapshot), None)
    if entry is None or entry[0]() is not snapshot:
        _fail("SNAPSHOT_UNISSUED")
    try:
        projection = _snapshot_projection(snapshot)
    except RetrievalContractError:
        raise
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        _fail("SNAPSHOT_UNISSUED")
    record = entry[1]
    if record.projection != projection or record.fingerprint != snapshot.fingerprint:
        _fail("SNAPSHOT_UNISSUED")
    if _fingerprint(projection) != snapshot.fingerprint or snapshot.canonical_bytes != projection:
        _fail("SNAPSHOT_UNISSUED")
    if entry[0]() is not snapshot or id(snapshot) in _ISSUED:
        _fail("SNAPSHOT_UNISSUED")
    _ISSUED[id(snapshot)] = entry
    return entry[1].private


def freeze_synthetic_retrieval_snapshot(
    profile: EmbeddingProfile,
    target: TargetDefinition,
    cases: tuple[RetrievalGoldenCase, ...],
) -> SyntheticRetrievalSnapshot:
    """Freeze exact synthetic witnesses for evaluator mechanics only."""
    if type(target) is not TargetDefinition or type(cases) is not tuple:
        _fail("SNAPSHOT_INVALID")
    profile_document = _profile_document(profile)
    if (
        type(target.dimensions) is not int
        or target.dimensions != profile.dimensions
        or target.metric != profile.metric
    ):
        _fail("SNAPSHOT_INVALID")
    case_documents = [_case_document(case, profile.profile_id) for case in cases]
    case_ids = [_identifier(case.case_id, "SNAPSHOT_INVALID") for case in cases]
    if not case_documents or case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
        _fail("SNAPSHOT_INVALID")
    projection = canonicalize(
        checked_json_value(
            {
                "cases": case_documents,
                "profile": profile_document,
                "target": {
                    "dimensions": target.dimensions,
                    "metric": _text(target.metric, "SNAPSHOT_INVALID"),
                    "name": _identifier(target.name, "SNAPSHOT_INVALID"),
                    "namespace": _text(target.namespace, "SNAPSHOT_INVALID"),
                    "state_fingerprint": _text(target.state_fingerprint, "SNAPSHOT_INVALID"),
                },
                "type": "asklegal.synthetic-retrieval-evaluator.v1",
            }
        )
    )
    fingerprint = _fingerprint(projection)
    snapshot = SyntheticRetrievalSnapshot(
        profile,
        target.name,
        target.state_fingerprint,
        target.dimensions,
        target.metric,
        target.namespace,
        cases,
        projection,
        fingerprint,
    )
    key = id(snapshot)

    def cleanup(stored: ref[SyntheticRetrievalSnapshot], key: int = key) -> None:
        if _ISSUED.get(key, (None, None))[0] is stored:
            _ISSUED.pop(key, None)

    private = _private_snapshot(snapshot, projection)
    _ISSUED[key] = (ref(snapshot, cleanup), _IssuedSnapshot(fingerprint, projection, private))
    return snapshot


def _case_result(
    case: RetrievalGoldenCase,
    returned_record_ids: tuple[str, ...],
    returned_scores: tuple[float, ...],
    returned_payload_fingerprints: tuple[str, ...],
    failure_code: str | None,
) -> RetrievalGoldenCaseResult:
    """Project only primitives captured from the detached case and query reply."""
    request = _request_document(case.embedding_request, case.embedding_request.profile_id)
    expected_record_ids = tuple(witness.record_id for witness in case.witnesses if witness.expected)
    expected_payload_fingerprints = tuple(
        _payload_fingerprint(witness.payload) for witness in case.witnesses if witness.expected
    )
    return RetrievalGoldenCaseResult(
        case.case_id,
        _fingerprint(canonicalize(checked_json_value(request))),
        expected_record_ids,
        expected_payload_fingerprints,
        returned_record_ids,
        returned_scores,
        returned_payload_fingerprints,
        failure_code,
    )


def _result_projection(result: HKV1RetrievalEvaluationResult) -> bytes:
    """Rebuild every result-bound primitive; do not trust its public fields."""
    if (
        type(result) is not HKV1RetrievalEvaluationResult
        or type(result.state) is not EvaluationState
        or type(result.admission_state) is not AdmissionState
        or result.admission_state is not AdmissionState.NOT_ADMITTED
        or type(result.snapshot_canonical_bytes) is not bytes
        or type(result.snapshot_fingerprint) is not str
        or type(result.profile_fingerprint) is not str
        or type(result.target_dimensions) is not int
        or type(result.case_results) is not tuple
        or type(result.failure_codes) is not tuple
    ):
        _fail("RESULT_UNISSUED")
    try:
        case_results: list[dict[str, object]] = []
        for case in result.case_results:
            if type(case) is not RetrievalGoldenCaseResult:
                _fail("RESULT_UNISSUED")
            if (
                type(case.returned_record_ids) is not tuple
                or type(case.returned_scores) is not tuple
                or type(case.returned_payload_fingerprints) is not tuple
                or len(case.returned_record_ids) != len(case.returned_scores)
                or len(case.returned_record_ids) != len(case.returned_payload_fingerprints)
                or type(case.expected_record_ids) is not tuple
                or type(case.expected_payload_fingerprints) is not tuple
                or len(case.expected_record_ids) != len(case.expected_payload_fingerprints)
                or (case.failure_code is not None and type(case.failure_code) is not str)
            ):
                _fail("RESULT_UNISSUED")
            case_results.append(
                {
                    "case_id": _identifier(case.case_id, "RESULT_UNISSUED"),
                    "expected_payload_fingerprints": [
                        _text(value, "RESULT_UNISSUED")
                        for value in case.expected_payload_fingerprints
                    ],
                    "expected_record_ids": [
                        _identifier(value, "RESULT_UNISSUED") for value in case.expected_record_ids
                    ],
                    "failure_code": case.failure_code,
                    "query_request_fingerprint": _text(
                        case.query_request_fingerprint, "RESULT_UNISSUED"
                    ),
                    "returned_payload_fingerprints": [
                        _text(value, "RESULT_UNISSUED")
                        for value in case.returned_payload_fingerprints
                    ],
                    "returned_record_ids": [
                        _identifier(value, "RESULT_UNISSUED") for value in case.returned_record_ids
                    ],
                    "returned_scores": [
                        score
                        if type(score) is float and math.isfinite(score)
                        else _fail("RESULT_UNISSUED")
                        for score in case.returned_scores
                    ],
                }
            )
        failure_codes = tuple(
            sorted(
                {case.failure_code for case in result.case_results if case.failure_code is not None}
            )
        )
        if result.failure_codes != failure_codes:
            _fail("RESULT_UNISSUED")
        return canonicalize(
            checked_json_value(
                {
                    "admission_state": result.admission_state.value,
                    "case_results": case_results,
                    "failure_codes": list(result.failure_codes),
                    "profile_fingerprint": _text(result.profile_fingerprint, "RESULT_UNISSUED"),
                    "snapshot_canonical_bytes": result.snapshot_canonical_bytes.hex(),
                    "snapshot_fingerprint": _text(result.snapshot_fingerprint, "RESULT_UNISSUED"),
                    "state": result.state.value,
                    "target": {
                        "dimensions": result.target_dimensions,
                        "metric": _text(result.target_metric, "RESULT_UNISSUED"),
                        "name": _identifier(result.target_name, "RESULT_UNISSUED"),
                        "namespace": _text(result.target_namespace, "RESULT_UNISSUED"),
                        "state_fingerprint": _text(
                            result.target_state_fingerprint, "RESULT_UNISSUED"
                        ),
                    },
                    "type": "asklegal.synthetic-retrieval-evaluation-result.v1",
                }
            )
        )
    except RetrievalContractError:
        raise
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        _fail("RESULT_UNISSUED")


def assert_retrieval_evaluation_result(
    result: object,
) -> HKV1RetrievalEvaluationResult:
    """Consume a live issued shell and return only detached registry-owned facts."""
    if type(result) is not HKV1RetrievalEvaluationResult:
        _fail("RESULT_UNISSUED")
    entry = _ISSUED_RESULTS.pop(id(result), None)
    if entry is None or entry[0]() is not result:
        _fail("RESULT_UNISSUED")
    try:
        projection = _result_projection(result)
    except RetrievalContractError:
        raise
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        _fail("RESULT_UNISSUED")
    record = entry[1]
    if record.projection != projection or record.fingerprint != result.fingerprint:
        _fail("RESULT_UNISSUED")
    if entry[0]() is not result or id(result) in _ISSUED_RESULTS:
        _fail("RESULT_UNISSUED")
    return _issue_result(record.private)


def _private_case_result(result: RetrievalGoldenCaseResult) -> _PrivateCaseResult:
    """Copy every already-normalized public case fact into registry ownership."""
    return _PrivateCaseResult(
        result.case_id,
        result.query_request_fingerprint,
        tuple(result.expected_record_ids),
        tuple(result.expected_payload_fingerprints),
        tuple(result.returned_record_ids),
        tuple(result.returned_scores),
        tuple(result.returned_payload_fingerprints),
        result.failure_code,
    )


def _public_case_result(result: _PrivateCaseResult) -> RetrievalGoldenCaseResult:
    """Reconstruct a new non-shared public case result from private facts."""
    return RetrievalGoldenCaseResult(
        result.case_id,
        result.query_request_fingerprint,
        tuple(result.expected_record_ids),
        tuple(result.expected_payload_fingerprints),
        tuple(result.returned_record_ids),
        tuple(result.returned_scores),
        tuple(result.returned_payload_fingerprints),
        result.failure_code,
    )


def _public_result(result: _PrivateResult, fingerprint: str) -> HKV1RetrievalEvaluationResult:
    """Build a fresh public shell; it never shares a registry-owned result object."""
    return HKV1RetrievalEvaluationResult(
        result.state,
        AdmissionState.NOT_ADMITTED,
        bytes(result.snapshot_canonical_bytes),
        result.snapshot_fingerprint,
        result.profile_fingerprint,
        result.target_name,
        result.target_state_fingerprint,
        result.target_dimensions,
        result.target_metric,
        result.target_namespace,
        tuple(_public_case_result(case) for case in result.case_results),
        tuple(result.failure_codes),
        fingerprint,
    )


def _issue_result(private: _PrivateResult) -> HKV1RetrievalEvaluationResult:
    """Issue one new, weakly tracked public shell from complete private facts."""
    provisional = _public_result(private, "")
    projection = _result_projection(provisional)
    result = _public_result(private, _fingerprint(projection))
    key = id(result)

    def cleanup(stored: ref[HKV1RetrievalEvaluationResult], key: int = key) -> None:
        if _ISSUED_RESULTS.get(key, (None, None))[0] is stored:
            _ISSUED_RESULTS.pop(key, None)

    _ISSUED_RESULTS[key] = (
        ref(result, cleanup),
        _IssuedResult(result.fingerprint, projection, private),
    )
    return result


def _result(
    state: EvaluationState,
    case_results: tuple[RetrievalGoldenCaseResult, ...],
    frozen: _PrivateSnapshot,
) -> HKV1RetrievalEvaluationResult:
    failure_codes = tuple(
        sorted({result.failure_code for result in case_results if result.failure_code is not None})
    )
    private = _PrivateResult(
        state,
        bytes(frozen.canonical_bytes),
        frozen.fingerprint,
        frozen.profile.profile_fingerprint,
        frozen.target_name,
        frozen.target_state_fingerprint,
        frozen.target_dimensions,
        frozen.target_metric,
        frozen.target_namespace,
        tuple(_private_case_result(result) for result in case_results),
        failure_codes,
    )
    return _issue_result(private)


def _vector_or_failure(value: object, dimensions: int, request_id: str) -> tuple[float, ...] | str:
    try:
        if type(value) is not EmbeddedVector or type(value.receipt) is not EmbeddingReceipt:
            return "EMBEDDING_RESULT_INVALID"
        receipt = value.receipt
        if type(value.values) is not tuple or len(value.values) != dimensions:
            return "RESULT_DIMENSIONS_INVALID"
        if any(type(number) is not float or not math.isfinite(number) for number in value.values):
            return "RESULT_DIMENSIONS_INVALID"
        if receipt.request_id != request_id or receipt.dimensions != dimensions:
            return "EMBEDDING_RESULT_INVALID"
        return tuple(value.values)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        return "EMBEDDING_RESULT_INVALID"


@dataclass(frozen=True, slots=True)
class _CapturedReturnedRecord:
    """One safely normalized actual reply item, retained before semantic grading."""

    record_id: str
    score: float
    payload_fingerprint: str


def _capture_returned_record(
    result: object,
) -> _CapturedReturnedRecord | str:
    """Detach a valid actual item before it can be rejected semantically."""
    try:
        if type(result) is not RetrievedTargetRecord:
            return "RESULT_RETURN_INVALID"
        if type(result.score) is not float or not math.isfinite(result.score):
            return "RESULT_SCORE_INVALID"
        return _CapturedReturnedRecord(
            _identifier(result.record_id, "RESULT_RETURN_INVALID"),
            result.score,
            _payload_fingerprint(result.payload),
        )
    except RetrievalContractError as error:
        return str(error)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        return "RESULT_RETURN_INVALID"


def _records_or_failure(
    results: object, case: RetrievalGoldenCase
) -> tuple[tuple[str, ...], tuple[float, ...], tuple[str, ...], str | None]:
    if not _object_tuple(results):
        return (), (), (), "RESULT_RETURN_INVALID"
    captured, capture_failure = _capture_reply(results)
    identifiers = tuple(record.record_id for record in captured)
    scores = tuple(record.score for record in captured)
    payload_fingerprints = tuple(record.payload_fingerprint for record in captured)
    return (
        identifiers,
        scores,
        payload_fingerprints,
        _reply_failure(captured, len(results), capture_failure, case),
    )


def _capture_reply(
    results: tuple[object, ...],
) -> tuple[tuple[_CapturedReturnedRecord, ...], str | None]:
    """Capture all valid returned primitives before any semantic reply decision."""
    captured: list[_CapturedReturnedRecord] = []
    capture_failure: str | None = None
    for result in results:
        record = _capture_returned_record(result)
        if isinstance(record, str):
            if capture_failure is None:
                capture_failure = record
        else:
            captured.append(record)
    return tuple(captured), capture_failure


def _reply_failure(
    captured: tuple[_CapturedReturnedRecord, ...],
    result_count: int,
    capture_failure: str | None,
    case: RetrievalGoldenCase,
) -> str | None:
    """Grade detached actual facts after their complete valid projection is retained."""
    if result_count > case.top_k:
        return "RESULT_LIMIT_EXCEEDED"
    if capture_failure is not None:
        return capture_failure
    return _semantic_reply_failure(captured, case)


def _semantic_reply_failure(
    captured: tuple[_CapturedReturnedRecord, ...], case: RetrievalGoldenCase
) -> str | None:
    """Check ordering, witnesses, and expected membership after full capture."""
    witnesses = {witness.record_id: witness for witness in case.witnesses}
    previous_score: float | None = None
    expected_seen = False
    seen: set[str] = set()
    for record in captured:
        if record.record_id in seen:
            return "RETURNED_RECORD_DUPLICATE"
        seen.add(record.record_id)
        if previous_score is not None and previous_score < record.score:
            return "RESULT_ORDER_INVALID"
        previous_score = record.score
        witness = witnesses.get(record.record_id)
        if witness is None:
            return "RETURNED_RECORD_UNKNOWN"
        if record.payload_fingerprint != _payload_fingerprint(witness.payload):
            return "RESULT_METADATA_INVALID"
        expected_seen = expected_seen or witness.expected
    if not expected_seen:
        return "EXPECTED_RECORD_NOT_IN_TOP_RESULTS"
    return None


def run_synthetic_retrieval_contract(
    snapshot: object,
    embeddings: EmbeddingPort,
    target: RetrievalQueryPort,
) -> HKV1RetrievalEvaluationResult:
    """Execute only synthetic witnesses through injected ports, never an admission path."""
    frozen = _assert_issued_snapshot(snapshot)
    try:
        ports_allowed = (
            getattr(embeddings, "synthetic_retrieval_contract", False) is True
            and getattr(target, "synthetic_retrieval_contract", False) is True
        )
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        ports_allowed = False
    if not ports_allowed:
        return _result(
            EvaluationState.SYNTHETIC_CONTRACT_FAILED,
            tuple(
                _case_result(case, (), (), (), "SYNTHETIC_PORT_NOT_ALLOWED")
                for case in frozen.cases
            ),
            frozen,
        )
    case_results: list[RetrievalGoldenCaseResult] = []
    for case in frozen.cases:
        request = _copy_case(case).embedding_request
        try:
            embedded = embeddings.embed(_copy_profile(frozen.profile), request)
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            case_results.append(_case_result(case, (), (), (), "EMBEDDING_FAILED"))
            continue
        vector = _vector_or_failure(embedded, frozen.target_dimensions, request.request_id)
        if isinstance(vector, str):
            case_results.append(_case_result(case, (), (), (), vector))
            continue
        try:
            returned = target.query(frozen.target_name, vector, case.top_k)
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            case_results.append(_case_result(case, (), (), (), "QUERY_FAILED"))
            continue
        identifiers, scores, payload_fingerprints, failure = _records_or_failure(returned, case)
        case_results.append(_case_result(case, identifiers, scores, payload_fingerprints, failure))
    outcomes = tuple(case_results)
    state = (
        EvaluationState.SYNTHETIC_CONTRACT_PASSED
        if outcomes and all(result.failure_code is None for result in outcomes)
        else EvaluationState.SYNTHETIC_CONTRACT_FAILED
    )
    return _result(state, outcomes, frozen)


def run_retrieval_evaluation(
    snapshot: object,
    embeddings: EmbeddingPort,
    target: RetrievalQueryPort,
) -> HKV1RetrievalEvaluationResult:
    """Fail closed: Task 4A cannot invoke providers or issue an admitted evaluation."""
    del embeddings, target
    frozen = _assert_issued_snapshot(snapshot)
    results = tuple(
        _case_result(case, (), (), (), "AUTHENTIC_TRUTH_OR_AUTHORITY_MISSING")
        for case in frozen.cases
    )
    return _result(EvaluationState.NOT_EVALUATED, results, frozen)
