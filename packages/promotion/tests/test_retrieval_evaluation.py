"""Synthetic-only regression tests for Plan 6 Task 4A retrieval mechanics.

These tests deliberately prove evaluator control flow, not retrieval quality,
provider behavior, ranking truth, or V1 admission.
"""

from __future__ import annotations

import copy
import math
import pickle
from dataclasses import replace
from hashlib import sha256

import pytest
from asklegal_promotion import retrieval
from asklegal_promotion.builder import freeze_embedding_profile
from asklegal_promotion.model import (
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingProfileInput,
    EmbeddingReceipt,
    EmbeddingRequest,
    TargetDefinition,
)
from asklegal_promotion.retrieval import (
    AdmissionState,
    EvaluationState,
    HKV1RetrievalEvaluationResult,
    RetrievalContractError,
    RetrievalGoldenCase,
    RetrievalWitness,
    RetrievedTargetRecord,
    ServingPayload,
    SyntheticRetrievalSnapshot,
    assert_retrieval_evaluation_result,
    freeze_synthetic_retrieval_snapshot,
    run_retrieval_evaluation,
    run_synthetic_retrieval_contract,
)


def _fingerprint(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _profile() -> EmbeddingProfile:
    return freeze_embedding_profile(
        EmbeddingProfileInput(
            provider="AZURE_OPENAI",
            resource_class="SYNTHETIC",
            geography_class="SYNTHETIC",
            deployment_name="synthetic-embedding-v1",
            model_id="synthetic-model-v1",
            model_version="1.0.0",
            api_contract="2026-08-01",
            tokenizer="synthetic-tokenizer-v1",
            dimensions=3,
            encoding="FLOAT32",
            normalization="UNIT_LENGTH",
            metric="cosine",
            max_input_tokens=2048,
            cost_limit_microunits=1000,
            expires_at="2099-01-01T00:00:00Z",
            allowed_environments=("LOCAL_SYNTHETIC",),
        )
    )


def _payload(*, text: str = "Synthetic legal text") -> ServingPayload:
    return ServingPayload(
        text=text,
        country="HK",
        jurisdiction="HKSAR",
        material_type="SYNTHETIC",
        source="LOCAL_SYNTHETIC",
        authority_note="SYNTHETIC TEST WITNESS ONLY",
    )


def _request(profile_id: str, *, case_id: str = "RET-001") -> EmbeddingRequest:
    return EmbeddingRequest(
        request_id=f"req_{case_id}",
        record_id=f"qry_{case_id}",
        serving_payload_fingerprint=_fingerprint(case_id.encode()),
        text="synthetic query",
        text_fingerprint=_fingerprint(b"synthetic query"),
        token_count=0,
        profile_id=profile_id,
        batch_id="synthetic-retrieval-contract",
        batch_position=0,
        cache_key=_fingerprint(f"cache:{case_id}".encode()),
    )


def _case(profile_id: str) -> RetrievalGoldenCase:
    expected = RetrievalWitness("rec_expected", _payload(), expected=True)
    alternative = RetrievalWitness(
        "rec_alternative", _payload(text="Other synthetic text"), expected=False
    )
    return RetrievalGoldenCase(
        case_id="RET-001",
        language_slice="EN",
        embedding_request=_request(profile_id),
        witnesses=(expected, alternative),
        top_k=2,
    )


def _snapshot() -> SyntheticRetrievalSnapshot:
    profile = _profile()
    return freeze_synthetic_retrieval_snapshot(
        profile,
        TargetDefinition(
            "asklegal-local-synthetic-retrieval",
            _fingerprint(b"target-state"),
            3,
            "cosine",
            "synthetic-v1",
        ),
        (_case(profile.profile_id),),
    )


class _ScriptedEmbedding:
    synthetic_retrieval_contract = True

    def __init__(
        self, *, vector: tuple[float, ...] = (0.1, 0.2, 0.3), error: BaseException | None = None
    ) -> None:
        self.vector = vector
        self.error = error
        self.calls: list[EmbeddingRequest] = []

    def embed(self, profile: object, request: EmbeddingRequest) -> EmbeddedVector:
        del profile
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return EmbeddedVector(
            self.vector,
            EmbeddingReceipt(
                "emc_synthetic",
                request.request_id,
                "synthetic-request",
                len(self.vector),
                _fingerprint(b"synthetic-vector"),
                0,
                0,
                "SUCCEEDED",
            ),
        )


class _ScriptedQuery:
    synthetic_retrieval_contract = True

    def __init__(
        self,
        results: tuple[RetrievedTargetRecord, ...],
        *,
        error: BaseException | None = None,
    ) -> None:
        self.results = results
        self.error = error
        self.calls: list[tuple[str, tuple[float, ...], int]] = []

    def query(
        self, name: str, vector: tuple[float, ...], top_k: int
    ) -> tuple[RetrievedTargetRecord, ...]:
        self.calls.append((name, vector, top_k))
        if self.error is not None:
            raise self.error
        return self.results


class _MalformedEmbedding:
    """Returns an exact-class shell with no dataclass fields."""

    synthetic_retrieval_contract = True

    def embed(self, profile: object, request: EmbeddingRequest) -> EmbeddedVector:
        del profile, request
        return object.__new__(EmbeddedVector)


class _MarkerMutatingEmbedding(_ScriptedEmbedding):
    """Attempts to erase public cases while the synthetic marker is read."""

    def __init__(self, snapshot: SyntheticRetrievalSnapshot) -> None:
        super().__init__()
        self._snapshot = snapshot

    @property
    def synthetic_retrieval_contract(self) -> bool:
        object.__setattr__(self._snapshot, "cases", ())
        return True


class _QueryMutatingTarget(_ScriptedQuery):
    """Attempts to rewrite the public expected payload before grading."""

    def __init__(self, snapshot: SyntheticRetrievalSnapshot) -> None:
        super().__init__(())
        self._snapshot = snapshot

    def query(
        self, name: str, vector: tuple[float, ...], top_k: int
    ) -> tuple[RetrievedTargetRecord, ...]:
        del name, vector, top_k
        case = self._snapshot.cases[0]
        replacement = replace(case.witnesses[0], payload=_payload(text="attacker-selected payload"))
        object.__setattr__(
            self._snapshot,
            "cases",
            (replace(case, witnesses=(replacement, case.witnesses[1])),),
        )
        return (RetrievedTargetRecord("rec_expected", 0.9, replacement.payload),)


def _expected_result(*, score: float = 0.9) -> RetrievedTargetRecord:
    return RetrievedTargetRecord("rec_expected", score, _payload())


def test_synthetic_contract_calls_embedding_and_query_and_never_admits() -> None:
    """Only an injected scripted query may establish synthetic evaluator mechanics."""
    snapshot = _snapshot()
    embeddings = _ScriptedEmbedding()
    target = _ScriptedQuery((_expected_result(),))

    result = run_synthetic_retrieval_contract(snapshot, embeddings, target)

    assert result.state is EvaluationState.SYNTHETIC_CONTRACT_PASSED
    assert result.admission_state is AdmissionState.NOT_ADMITTED
    assert result.case_results[0].failure_code is None
    assert result.case_results[0].returned_record_ids == ("rec_expected",)
    assert len(embeddings.calls) == 1
    assert target.calls == [("asklegal-local-synthetic-retrieval", (0.1, 0.2, 0.3), 2)]


def test_provider_disabled_entrypoint_never_calls_ports_without_truth_or_authority() -> None:
    """The admission entrypoint must fail closed before either injected port runs."""
    snapshot = _snapshot()
    embeddings = _ScriptedEmbedding()
    target = _ScriptedQuery((_expected_result(),))

    result = run_retrieval_evaluation(snapshot, embeddings, target)

    assert result.state is EvaluationState.NOT_EVALUATED
    assert result.admission_state is AdmissionState.NOT_ADMITTED
    assert result.failure_codes == ("AUTHENTIC_TRUTH_OR_AUTHORITY_MISSING",)
    assert embeddings.calls == []
    assert target.calls == []


def test_marker_callback_cannot_erase_private_case_accounting_or_create_zero_case_pass() -> None:
    """C1: every case is captured before a callback-capable marker is read."""
    snapshot = _snapshot()

    result = run_synthetic_retrieval_contract(
        snapshot, _MarkerMutatingEmbedding(snapshot), _ScriptedQuery((_expected_result(),))
    )

    assert result.state is EvaluationState.SYNTHETIC_CONTRACT_PASSED
    assert len(result.case_results) == 1
    assert result.case_results[0].case_id == "RET-001"


def test_query_callback_cannot_rewrite_private_expected_payload_or_create_pass() -> None:
    """C1: grading reads detached expected witnesses, never callback-mutated public data."""
    snapshot = _snapshot()

    result = run_synthetic_retrieval_contract(
        snapshot, _ScriptedEmbedding(), _QueryMutatingTarget(snapshot)
    )

    assert result.state is EvaluationState.SYNTHETIC_CONTRACT_FAILED
    assert result.case_results[0].failure_code == "RESULT_METADATA_INVALID"


def test_result_binds_private_snapshot_and_rejects_forged_or_mutated_evidence() -> None:
    """I1: result evidence cannot borrow identity or become string-admitted by mutation."""
    first = run_synthetic_retrieval_contract(
        _snapshot(), _ScriptedEmbedding(), _ScriptedQuery((_expected_result(),))
    )
    # A separately issued target proves that result evidence binds its full input.
    profile = _profile()
    second = run_synthetic_retrieval_contract(
        freeze_synthetic_retrieval_snapshot(
            profile,
            TargetDefinition("other-target", _fingerprint(b"other"), 3, "cosine", "other"),
            (_case(profile.profile_id),),
        ),
        _ScriptedEmbedding(),
        _ScriptedQuery((_expected_result(),)),
    )

    assert first.fingerprint != second.fingerprint
    assert_retrieval_evaluation_result(first)
    with pytest.raises(RetrievalContractError, match="RESULT_UNISSUED"):
        assert_retrieval_evaluation_result(replace(first))
    object.__setattr__(first, "admission_state", "ADMITTED")
    with pytest.raises(RetrievalContractError, match="RESULT_UNISSUED"):
        assert_retrieval_evaluation_result(first)


def test_result_assertion_consumes_live_object_and_returns_detached_not_admitted_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C1: a post-projection mutation cannot leak through the verifier's return value."""
    issued = run_synthetic_retrieval_contract(
        _snapshot(), _ScriptedEmbedding(), _ScriptedQuery((_expected_result(),))
    )
    projection_function: object = retrieval.__dict__["_result_projection"]
    assert callable(projection_function)

    def mutate_after_projection(value: HKV1RetrievalEvaluationResult) -> bytes:
        projection = projection_function(value)
        assert type(projection) is bytes
        object.__setattr__(value, "admission_state", "ADMITTED")
        return projection

    monkeypatch.setattr(retrieval, "_result_projection", mutate_after_projection)
    verified = assert_retrieval_evaluation_result(issued)

    assert verified is not issued
    assert verified.admission_state is AdmissionState.NOT_ADMITTED
    with pytest.raises(RetrievalContractError, match="RESULT_UNISSUED"):
        assert_retrieval_evaluation_result(issued)


def test_result_factory_rejects_direct_replace_copy_pickle_subclass_and_all_mutation() -> None:
    """I1: no public projection can acquire evaluator-result identity or admission."""
    issued = run_synthetic_retrieval_contract(
        _snapshot(), _ScriptedEmbedding(), _ScriptedQuery((_expected_result(),))
    )
    direct = HKV1RetrievalEvaluationResult(
        issued.state,
        issued.admission_state,
        issued.snapshot_canonical_bytes,
        issued.snapshot_fingerprint,
        issued.profile_fingerprint,
        issued.target_name,
        issued.target_state_fingerprint,
        issued.target_dimensions,
        issued.target_metric,
        issued.target_namespace,
        issued.case_results,
        issued.failure_codes,
        issued.fingerprint,
    )

    class _Subclass(HKV1RetrievalEvaluationResult):
        pass

    forged = object.__new__(_Subclass)
    for result in (
        object.__new__(HKV1RetrievalEvaluationResult),
        direct,
        replace(issued),
        copy.copy(issued),
        copy.deepcopy(issued),
        forged,
    ):
        with pytest.raises(RetrievalContractError, match="RESULT_UNISSUED"):
            assert_retrieval_evaluation_result(result)
    with pytest.raises(TypeError, match="RESULT_NONTRANSFERABLE"):
        pickle.dumps(issued)

    object.__setattr__(issued, "state", EvaluationState.NOT_EVALUATED)
    with pytest.raises(RetrievalContractError, match="RESULT_UNISSUED"):
        assert_retrieval_evaluation_result(issued)


def test_exact_class_uninitialized_port_values_become_failed_cases_not_attribute_errors() -> None:
    """I2: malformed exact-class shells stay within ordinary evaluator accounting."""
    malformed_record = object.__new__(RetrievedTargetRecord)

    vector_result = run_synthetic_retrieval_contract(
        _snapshot(), _MalformedEmbedding(), _ScriptedQuery(())
    )
    record_result = run_synthetic_retrieval_contract(
        _snapshot(), _ScriptedEmbedding(), _ScriptedQuery((malformed_record,))
    )

    assert vector_result.state is EvaluationState.SYNTHETIC_CONTRACT_FAILED
    assert vector_result.case_results[0].failure_code == "EMBEDDING_RESULT_INVALID"
    assert record_result.state is EvaluationState.SYNTHETIC_CONTRACT_FAILED
    assert record_result.case_results[0].failure_code == "RESULT_RETURN_INVALID"


def test_result_keeps_only_true_expected_witnesses_and_complete_unknown_reply_evidence() -> None:
    """I1: expected labels and failed valid reply facts stay exact and fingerprint-bound."""
    passed = run_synthetic_retrieval_contract(
        _snapshot(), _ScriptedEmbedding(), _ScriptedQuery((_expected_result(),))
    )
    unknown_a = run_synthetic_retrieval_contract(
        _snapshot(),
        _ScriptedEmbedding(),
        _ScriptedQuery((RetrievedTargetRecord("unknown_a", 0.9, _payload(text="A")),)),
    )
    unknown_b = run_synthetic_retrieval_contract(
        _snapshot(),
        _ScriptedEmbedding(),
        _ScriptedQuery((RetrievedTargetRecord("unknown_b", 0.8, _payload(text="B")),)),
    )

    assert passed.case_results[0].expected_record_ids == ("rec_expected",)
    assert unknown_a.case_results[0].returned_record_ids == ("unknown_a",)
    assert unknown_a.case_results[0].returned_scores == (0.9,)
    assert unknown_a.fingerprint != unknown_b.fingerprint


def test_result_keeps_complete_overlimit_reply_evidence_and_distinguishes_it() -> None:
    """I1: exceeding top-k remains failed while every valid reply item is retained."""
    common = (
        _expected_result(),
        RetrievedTargetRecord("rec_alternative", 0.8, _payload(text="Other synthetic text")),
    )
    first = run_synthetic_retrieval_contract(
        _snapshot(),
        _ScriptedEmbedding(),
        _ScriptedQuery((*common, RetrievedTargetRecord("overlimit_a", 0.7, _payload(text="A")))),
    )
    second = run_synthetic_retrieval_contract(
        _snapshot(),
        _ScriptedEmbedding(),
        _ScriptedQuery((*common, RetrievedTargetRecord("overlimit_b", 0.6, _payload(text="B")))),
    )

    assert first.case_results[0].failure_code == "RESULT_LIMIT_EXCEEDED"
    assert first.case_results[0].returned_record_ids == (
        "rec_expected",
        "rec_alternative",
        "overlimit_a",
    )
    assert len(first.case_results[0].returned_payload_fingerprints) == 3
    assert first.fingerprint != second.fingerprint


@pytest.mark.parametrize(
    ("results", "failure"),
    [
        ((), "EXPECTED_RECORD_NOT_IN_TOP_RESULTS"),
        ((RetrievedTargetRecord("rec_unknown", 0.9, _payload()),), "RETURNED_RECORD_UNKNOWN"),
        ((_expected_result(), _expected_result(score=0.8)), "RETURNED_RECORD_DUPLICATE"),
        ((_expected_result(score=float("nan")),), "RESULT_SCORE_INVALID"),
        (
            (
                _expected_result(score=0.8),
                RetrievedTargetRecord(
                    "rec_alternative", 0.9, _payload(text="Other synthetic text")
                ),
            ),
            "RESULT_ORDER_INVALID",
        ),
        (
            (
                _expected_result(),
                RetrievedTargetRecord(
                    "rec_alternative", 0.8, _payload(text="Other synthetic text")
                ),
                _expected_result(score=0.7),
            ),
            "RESULT_LIMIT_EXCEEDED",
        ),
        (
            (RetrievedTargetRecord("rec_expected", 0.9, _payload(text="tampered")),),
            "RESULT_METADATA_INVALID",
        ),
    ],
)
def test_synthetic_contract_fails_closed_for_invalid_query_witnesses(
    results: tuple[RetrievedTargetRecord, ...], failure: str
) -> None:
    """Each malformed reply becomes a visible synthetic contract failure, never a pass."""
    snapshot = _snapshot()
    result = run_synthetic_retrieval_contract(
        snapshot, _ScriptedEmbedding(), _ScriptedQuery(results)
    )

    assert result.state is EvaluationState.SYNTHETIC_CONTRACT_FAILED
    assert result.admission_state is AdmissionState.NOT_ADMITTED
    assert result.case_results[0].failure_code == failure


def test_synthetic_contract_rejects_wrong_embedding_dimensions_before_query() -> None:
    """A vector of the wrong width cannot be sent into the scripted target."""
    embeddings = _ScriptedEmbedding(vector=(0.1, 0.2))
    target = _ScriptedQuery((_expected_result(),))

    result = run_synthetic_retrieval_contract(_snapshot(), embeddings, target)

    assert result.state is EvaluationState.SYNTHETIC_CONTRACT_FAILED
    assert result.case_results[0].failure_code == "RESULT_DIMENSIONS_INVALID"
    assert len(embeddings.calls) == 1
    assert target.calls == []


def test_synthetic_contract_contains_ordinary_port_errors_but_reraises_base_exception() -> None:
    """Normal faults are evidence; control-flow exceptions are never converted to a pass."""
    normal = run_synthetic_retrieval_contract(
        _snapshot(), _ScriptedEmbedding(error=RuntimeError("ordinary")), _ScriptedQuery(())
    )
    assert normal.state is EvaluationState.SYNTHETIC_CONTRACT_FAILED
    assert normal.case_results[0].failure_code == "EMBEDDING_FAILED"

    with pytest.raises(KeyboardInterrupt):
        run_synthetic_retrieval_contract(
            _snapshot(), _ScriptedEmbedding(error=KeyboardInterrupt()), _ScriptedQuery(())
        )


def test_synthetic_contract_refuses_unmarked_ports_without_calling_them() -> None:
    """A provider-shaped object needs an explicit synthetic-only marker before invocation."""
    embeddings = _ScriptedEmbedding()
    target = _ScriptedQuery((_expected_result(),))
    embeddings.synthetic_retrieval_contract = False
    target.synthetic_retrieval_contract = False

    result = run_synthetic_retrieval_contract(_snapshot(), embeddings, target)

    assert result.state is EvaluationState.SYNTHETIC_CONTRACT_FAILED
    assert result.failure_codes == ("SYNTHETIC_PORT_NOT_ALLOWED",)
    assert embeddings.calls == []
    assert target.calls == []


def test_snapshot_factory_replay_is_canonical_and_direct_or_copied_values_are_unissued() -> None:
    """Only factory-issued process-local snapshots may reach either evaluator path."""
    snapshot = _snapshot()
    replay = _snapshot()
    assert snapshot.fingerprint == replay.fingerprint
    assert snapshot.canonical_bytes == replay.canonical_bytes
    direct = SyntheticRetrievalSnapshot(
        snapshot.profile,
        snapshot.target_name,
        snapshot.target_state_fingerprint,
        snapshot.target_dimensions,
        snapshot.target_metric,
        snapshot.target_namespace,
        snapshot.cases,
        snapshot.canonical_bytes,
        snapshot.fingerprint,
    )

    embeddings = _ScriptedEmbedding()
    target = _ScriptedQuery((_expected_result(),))
    for forged in (
        object.__new__(SyntheticRetrievalSnapshot),
        direct,
        replace(snapshot),
        copy.copy(snapshot),
        copy.deepcopy(snapshot),
    ):
        with pytest.raises(RetrievalContractError, match="SNAPSHOT_UNISSUED"):
            run_synthetic_retrieval_contract(forged, embeddings, target)
    with pytest.raises(TypeError, match="SNAPSHOT_NONTRANSFERABLE"):
        pickle.dumps(snapshot)
    assert embeddings.calls == []
    assert target.calls == []


def test_snapshot_detects_mutation_and_subclass_before_ports_are_called() -> None:
    """Restoring apparent field equality cannot borrow an issued snapshot witness."""
    snapshot = _snapshot()
    object.__setattr__(snapshot, "target_name", "tampered")
    with pytest.raises(RetrievalContractError, match="SNAPSHOT_UNISSUED"):
        run_synthetic_retrieval_contract(snapshot, _ScriptedEmbedding(), _ScriptedQuery(()))
    object.__setattr__(snapshot, "target_name", "asklegal-local-synthetic-retrieval")
    with pytest.raises(RetrievalContractError, match="SNAPSHOT_UNISSUED"):
        run_synthetic_retrieval_contract(snapshot, _ScriptedEmbedding(), _ScriptedQuery(()))

    class _Subclass(type(snapshot)):
        pass

    forged = object.__new__(_Subclass)
    with pytest.raises(RetrievalContractError, match="SNAPSHOT_UNISSUED"):
        run_synthetic_retrieval_contract(forged, _ScriptedEmbedding(), _ScriptedQuery(()))


def test_direct_case_validation_rejects_missing_extra_duplicate_and_noncanonical_inputs() -> None:
    """Factory accounting is closed before any scripted provider-like call."""
    profile = _profile()
    target = TargetDefinition("target", _fingerprint(b"state"), 3, "cosine", "ns")
    case = _case(profile.profile_id)
    invalid_cases = (
        (),
        (case, case),
        (replace(case, case_id=" RET-001"),),
        (replace(case, witnesses=()),),
        (replace(case, witnesses=(case.witnesses[0], case.witnesses[0])),),
        (replace(case, top_k=True),),
        (replace(case, language_slice="FR"),),
        (replace(case, embedding_request=replace(case.embedding_request, profile_id="other")),),
    )
    for cases in invalid_cases:
        with pytest.raises(RetrievalContractError):
            freeze_synthetic_retrieval_snapshot(profile, target, cases)


def test_result_fingerprint_and_case_accounting_are_exact_and_no_false_pass_is_possible() -> None:
    """One failed case changes the whole synthetic result and cannot be relabelled as a pass."""
    passed = run_synthetic_retrieval_contract(
        _snapshot(), _ScriptedEmbedding(), _ScriptedQuery((_expected_result(),))
    )
    failed = run_synthetic_retrieval_contract(_snapshot(), _ScriptedEmbedding(), _ScriptedQuery(()))

    assert len(passed.case_results) == 1
    assert len(failed.case_results) == 1
    assert passed.fingerprint != failed.fingerprint
    assert failed.state is not EvaluationState.SYNTHETIC_CONTRACT_PASSED
    assert not math.isnan(float(len(failed.failure_codes)))
