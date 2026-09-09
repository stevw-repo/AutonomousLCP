"""Provider-disabled source-neutral semantic-evaluation contract proof."""

from __future__ import annotations

import copy
import gc
import pickle
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import asklegal_processing.evaluation as compact_evaluation
import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_processing.evaluation import (
    EvaluationContractError,
    OpaqueEvaluationReference,
    SourceNeutralEvaluationRequest,
    SourceNeutralEvaluationResult,
    SourceNeutralValidationOutcome,
    SourceNeutralValidationSnapshot,
    SourceNeutralValidatorBinding,
    bind_source_neutral_validator,
    evaluate_source_neutral_contract,
    load_source_neutral_evaluation_request,
    replay_source_neutral_evaluation,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures/hk_v1_golden_suite.json"


def _raw_fixture() -> bytes:
    """Read only the checked-in small synthetic contract fixture."""
    return FIXTURE_PATH.read_bytes()


def _request() -> SourceNeutralEvaluationRequest:
    """Load one exact source-neutral fixture request."""
    return load_source_neutral_evaluation_request(_raw_fixture())


def _reseal(document: dict[str, JsonValue]) -> bytes:
    """Canonicalize a hostile local fixture variant with its stated digest."""
    projection = dict(document)
    projection.pop("fingerprint")
    document["fingerprint"] = (
        f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    )
    return canonicalize(checked_json_value(document))


def _request_with_truth(*indexes: int) -> SourceNeutralEvaluationRequest:
    """Reseal one local fixture variant whose requested opaque truth refs exist."""
    document = parse_json_bytes(_raw_fixture(), max_bytes=100_000)
    assert isinstance(document, dict)
    cases = document["cases"]
    assert isinstance(cases, list)
    for index in indexes:
        case = cases[index]
        assert isinstance(case, dict)
        case["reference_truth"] = {
            "adjudicated_truth_ref": {
                "ref_id": f"truth_local_{index:03d}",
                "fingerprint": f"sha256:{'a' * 64}",
            },
            "task_specific_facts_ref": {
                "ref_id": f"facts_local_{index:03d}",
                "fingerprint": f"sha256:{'b' * 64}",
            },
        }
    return load_source_neutral_evaluation_request(_reseal(document))


def _outcome(snapshot: SourceNeutralValidationSnapshot) -> SourceNeutralValidationOutcome:
    """Return exactly the opaque callback facts supplied by a frozen snapshot."""
    return SourceNeutralValidationOutcome(
        snapshot.case_id,
        snapshot.decision_output_ref,
        snapshot.challenge_output_ref,
        accepted=True,
    )


def test_source_neutral_fixture_has_complete_required_material_and_language_slices() -> None:
    """The small local fixture accounts for every required slice without claiming V1 truth."""
    request = _request()

    assert {case.material for case in request.cases} == {"GAZETTE", "LEGISLATION", "CASES", "HKEX"}
    assert {case.language_slice for case in request.cases} == {
        "EN",
        "ZH_HANT",
        "BILINGUAL",
        "CROSS_LANGUAGE",
    }


def test_missing_protected_truth_never_calls_validator_or_reports_pass() -> None:
    """Missing truth ends in exact NOT_EVALUATED accounting before any callback."""
    invocations: list[str] = []

    def validator(snapshot: SourceNeutralValidationSnapshot) -> SourceNeutralValidationOutcome:
        invocations.append(snapshot.case_id)
        return _outcome(snapshot)

    result = evaluate_source_neutral_contract(_request(), validator)

    assert invocations == []
    assert result.state == "NOT_EVALUATED"
    assert result.passed is False
    assert tuple(case.state for case in result.case_results) == ("NOT_EVALUATED",) * 4
    assert result.failure_codes == (
        "PROTECTED_REFERENCE_TRUTH_MISSING",
        "PROVIDER_DISABLED",
        "TASK_SPECIFIC_FACTS_MISSING",
    )
    assert replay_source_neutral_evaluation(_request(), result) is result


def test_snapshots_all_cases_before_a_validator_can_mutate_the_live_request() -> None:
    """A callback cannot alter later-case accounting after the full primitive snapshot."""
    request = _request_with_truth(0)

    def validator(snapshot: SourceNeutralValidationSnapshot) -> SourceNeutralValidationOutcome:
        object.__setattr__(request, "cases", ())
        return _outcome(snapshot)

    binding = bind_source_neutral_validator(request.cases[0].validator_ref, validator)
    result = evaluate_source_neutral_contract(request, binding)

    assert len(result.case_results) == 4
    assert result.case_results[0].state == "CONTRACT_BOUND"
    assert tuple(case.state for case in result.case_results[1:]) == ("NOT_EVALUATED",) * 3
    assert result.passed is False
    assert result.failure_codes == (
        "PROTECTED_REFERENCE_TRUTH_MISSING",
        "PROVIDER_DISABLED",
        "TASK_SPECIFIC_FACTS_MISSING",
    )


def test_validator_mismatch_and_ordinary_error_are_accounted_without_false_pass() -> None:
    """Mismatched or failed callbacks produce one deterministic result per supplied case."""
    request = _request_with_truth(0)
    first = request.cases[0]

    def validator(snapshot: SourceNeutralValidationSnapshot) -> SourceNeutralValidationOutcome:
        return SourceNeutralValidationOutcome(
            snapshot.case_id,
            snapshot.challenge_output_ref,
            snapshot.decision_output_ref,
            accepted=True,
        )

    binding = bind_source_neutral_validator(first.validator_ref, validator)
    result = evaluate_source_neutral_contract(request, binding)

    assert tuple(case.state for case in result.case_results) == (
        "CONTRACT_INVALID",
        "NOT_EVALUATED",
        "NOT_EVALUATED",
        "NOT_EVALUATED",
    )
    assert result.passed is False
    assert result.failure_codes == (
        "PROTECTED_REFERENCE_TRUTH_MISSING",
        "PROVIDER_DISABLED",
        "TASK_SPECIFIC_FACTS_MISSING",
        "VALIDATOR_OUTCOME_MISMATCH",
    )

    def failing_validator(
        snapshot: SourceNeutralValidationSnapshot,
    ) -> SourceNeutralValidationOutcome:
        del snapshot
        message = "ordinary test failure"
        error = RuntimeError(message)
        raise error

    binding = bind_source_neutral_validator(first.validator_ref, failing_validator)
    result = evaluate_source_neutral_contract(request, binding)
    assert result.case_results[0].state == "VALIDATOR_FAILURE"
    assert "VALIDATOR_FAILURE" in result.case_results[0].reason_codes


def test_base_exception_from_validator_is_not_converted_into_a_result() -> None:
    """Fatal control flow is never caught or mislabeled as an ordinary evaluation result."""
    request = _request_with_truth(0)

    def validator(snapshot: SourceNeutralValidationSnapshot) -> SourceNeutralValidationOutcome:
        del snapshot
        raise KeyboardInterrupt

    binding = bind_source_neutral_validator(request.cases[0].validator_ref, validator)
    with pytest.raises(KeyboardInterrupt):
        evaluate_source_neutral_contract(request, binding)


def test_loader_rejects_noncanonical_profile_fingerprint_and_incomplete_case_coverage() -> None:
    """Profile fingerprints and the complete local accounting matrix are strict contract facts."""
    document = parse_json_bytes(_raw_fixture(), max_bytes=100_000)
    assert isinstance(document, dict)
    document["semantic_profile_fingerprint"] = "sha256:" + "A" * 64
    with pytest.raises(EvaluationContractError, match="PROFILE_FINGERPRINT_INVALID"):
        load_source_neutral_evaluation_request(_reseal(document))

    document = parse_json_bytes(_raw_fixture(), max_bytes=100_000)
    assert isinstance(document, dict)
    cases = document["cases"]
    assert isinstance(cases, list)
    document["cases"] = cases[:3]
    with pytest.raises(EvaluationContractError, match="CASE_COVERAGE_INCOMPLETE"):
        load_source_neutral_evaluation_request(_reseal(document))


def test_direct_subclass_and_mutated_container_cannot_enter_callback_accounting() -> None:
    """Only exact immutable request/case/reference values enter the callback boundary."""
    request = _request()

    class _RequestSubclass(SourceNeutralEvaluationRequest):
        pass

    evil_request = object.__new__(_RequestSubclass)
    for name in (
        "revision",
        "semantic_profile_fingerprint",
        "serving_profile_fingerprint",
        "cases",
        "fingerprint",
    ):
        object.__setattr__(evil_request, name, getattr(request, name))
    with pytest.raises(EvaluationContractError, match="REQUEST_INVALID"):
        evaluate_source_neutral_contract(evil_request, None)

    class _StringSubclass(str):
        __slots__ = ()

    request = _request()
    object.__setattr__(
        request,
        "semantic_profile_fingerprint",
        _StringSubclass(request.semantic_profile_fingerprint),
    )
    with pytest.raises(EvaluationContractError, match="PROFILE_FINGERPRINT_INVALID"):
        evaluate_source_neutral_contract(request, None)

    request = _request()
    case = request.cases[0]
    object.__setattr__(case, "evidence_refs", [*case.evidence_refs])
    with pytest.raises(EvaluationContractError, match="CASE_INVALID"):
        evaluate_source_neutral_contract(request, None)


def test_factory_result_replay_rejects_direct_replace_copy_pickle_and_mutation() -> None:
    """Only the exact factory result and original canonical projection can replay."""
    result = evaluate_source_neutral_contract(_request(), None)
    assert replay_source_neutral_evaluation(_request(), result) is result

    with pytest.raises(EvaluationContractError, match="RESULT_NONTRANSFERABLE"):
        copy.copy(result)
    with pytest.raises(EvaluationContractError, match="RESULT_NONTRANSFERABLE"):
        copy.deepcopy(result)
    with pytest.raises(EvaluationContractError, match="RESULT_NONTRANSFERABLE"):
        pickle.dumps(result)
    with pytest.raises(TypeError):
        replace(result)

    original_cases = result.case_results
    object.__setattr__(result, "case_results", ())
    with pytest.raises(EvaluationContractError, match="RESULT_FACTORY_REQUIRED"):
        replay_source_neutral_evaluation(_request(), result)
    object.__setattr__(result, "case_results", original_cases)
    with pytest.raises(EvaluationContractError, match="RESULT_FACTORY_REQUIRED"):
        replay_source_neutral_evaluation(_request(), result)

    result = evaluate_source_neutral_contract(_request(), None)
    object.__setattr__(result, "case_results", [*result.case_results])
    with pytest.raises(EvaluationContractError, match="RESULT_FACTORY_REQUIRED"):
        replay_source_neutral_evaluation(_request(), result)


def test_direct_result_shell_is_not_factory_issued() -> None:
    """A field-for-field direct shell cannot borrow issuance from a genuine result."""
    genuine = evaluate_source_neutral_contract(_request(), None)
    shell = object.__new__(type(genuine))
    for name in (
        "request_fingerprint",
        "state",
        "case_results",
        "failure_codes",
        "passed",
        "fingerprint",
        "issuance",
    ):
        object.__setattr__(shell, name, getattr(genuine, name))
    with pytest.raises(EvaluationContractError, match="RESULT_FACTORY_REQUIRED"):
        replay_source_neutral_evaluation(_request(), shell)


def test_direct_material_subclass_and_unhashable_value_close_before_any_callback() -> None:
    """Caller scalars cannot execute hash/equality code while a request is being detached."""
    request = _request()
    case = request.cases[0]
    calls: list[str] = []

    class _MaterialSubclass(str):
        __slots__ = ()

        def __hash__(self) -> int:
            calls.append("hash")
            return super().__hash__()

    object.__setattr__(case, "material", _MaterialSubclass(case.material))
    with pytest.raises(EvaluationContractError, match="CASE_INVALID"):
        evaluate_source_neutral_contract(request, None)
    assert calls == []

    request = _request()
    object.__setattr__(request.cases[0], "material", [])
    with pytest.raises(EvaluationContractError, match="CASE_INVALID"):
        evaluate_source_neutral_contract(request, None)


def test_malformed_exact_validator_outcome_is_accounted_and_later_cases_remain_visible() -> None:
    """Outcome validation faults close only their case and preserve complete accounting."""
    request = _request_with_truth(0)

    def validator(snapshot: SourceNeutralValidationSnapshot) -> SourceNeutralValidationOutcome:
        return SourceNeutralValidationOutcome(
            snapshot.case_id,
            OpaqueEvaluationReference("INVALID", snapshot.decision_output_ref.fingerprint),
            snapshot.challenge_output_ref,
            accepted=True,
        )

    binding = bind_source_neutral_validator(request.cases[0].validator_ref, validator)
    result = evaluate_source_neutral_contract(request, binding)

    assert len(result.case_results) == 4
    assert result.case_results[0].state == "CONTRACT_INVALID"
    assert "VALIDATOR_OUTCOME_INVALID" in result.case_results[0].reason_codes
    assert tuple(case.state for case in result.case_results[1:]) == ("NOT_EVALUATED",) * 3


def test_replay_rejects_equal_nested_replacement_and_equal_scalar_subclass() -> None:
    """Factory issuance binds nested result identities and exact scalar types, not just values."""
    result = evaluate_source_neutral_contract(_request(), None)
    case_results = (replace(result.case_results[0]), *result.case_results[1:])
    object.__setattr__(result, "case_results", case_results)
    with pytest.raises(EvaluationContractError, match="RESULT_FACTORY_REQUIRED"):
        replay_source_neutral_evaluation(_request(), result)

    result = evaluate_source_neutral_contract(_request(), None)

    class _FingerprintSubclass(str):
        __slots__ = ()

    object.__setattr__(result, "fingerprint", _FingerprintSubclass(result.fingerprint))
    with pytest.raises(EvaluationContractError, match="RESULT_FACTORY_REQUIRED"):
        replay_source_neutral_evaluation(_request(), result)


def test_loader_rejects_opaque_id_reuse_across_evidence_and_task_roles() -> None:
    """One opaque ID may not denote different facts across contract roles."""
    document = parse_json_bytes(_raw_fixture(), max_bytes=100_000)
    assert isinstance(document, dict)
    cases = document["cases"]
    assert isinstance(cases, list)
    case = cases[0]
    assert isinstance(case, dict)
    refs = case["evidence_refs"]
    assert isinstance(refs, list)
    evidence = refs[0]
    assert isinstance(evidence, dict)
    task_ref = case["decision_task_ref"]
    assert isinstance(task_ref, dict)
    task_ref["ref_id"] = evidence["ref_id"]
    with pytest.raises(EvaluationContractError, match="REFERENCE_ID_REUSED"):
        load_source_neutral_evaluation_request(_reseal(document))


def test_unbound_validator_cannot_produce_contract_bound() -> None:
    """An arbitrary callable is not evidence that the opaque validator reference executed."""
    result = evaluate_source_neutral_contract(_request_with_truth(0), _outcome)

    assert result.case_results[0].state == "CONTRACT_INVALID"
    assert "VALIDATOR_UNBOUND" in result.case_results[0].reason_codes


def test_issued_result_registry_discards_dead_result_entries() -> None:
    """Weak cleanup removes dead factory entries instead of retaining projections."""
    module_values = vars(compact_evaluation)
    registry = module_values["_ISSUED_RESULTS"]
    registry.clear()
    result = evaluate_source_neutral_contract(_request(), None)
    assert len(registry) == 1
    del result
    gc.collect()
    assert registry == {}


def test_issued_validator_registry_discards_dead_binding_entries() -> None:
    """Weak cleanup also releases the process-local validator authority."""
    module_values = vars(compact_evaluation)
    registry = module_values["_ISSUED_VALIDATORS"]
    registry.clear()
    binding = bind_source_neutral_validator(_request().cases[0].validator_ref, _outcome)
    assert len(registry) == 1
    del binding
    gc.collect()
    assert registry == {}


def test_callback_receives_a_disposable_snapshot_and_cannot_rebind_request_facts() -> None:
    """Callback mutations cannot alter retained grading or the captured request fingerprint."""
    request = _request_with_truth(0)
    original_fingerprint = request.fingerprint
    original_case_id = request.cases[0].case_id

    def validator(snapshot: SourceNeutralValidationSnapshot) -> SourceNeutralValidationOutcome:
        object.__setattr__(snapshot, "case_id", "mutated_case_000")
        object.__setattr__(
            snapshot,
            "decision_output_ref",
            OpaqueEvaluationReference("mutated_output_000", f"sha256:{'c' * 64}"),
        )
        object.__setattr__(request, "fingerprint", f"sha256:{'d' * 64}")
        return _outcome(snapshot)

    binding = bind_source_neutral_validator(request.cases[0].validator_ref, validator)
    result = evaluate_source_neutral_contract(request, binding)

    assert result.request_fingerprint == original_fingerprint
    assert result.case_results[0].case_id == original_case_id
    assert result.case_results[0].state == "CONTRACT_INVALID"
    assert "VALIDATOR_OUTCOME_INVALID" in result.case_results[0].reason_codes


def test_registry_retains_exact_nested_result_authority_without_retaining_outer_result() -> None:
    """Replay authority must hold exact nested objects, never recyclable numeric addresses."""
    module_values = vars(compact_evaluation)
    registry = module_values["_ISSUED_RESULTS"]
    registry.clear()
    result = evaluate_source_neutral_contract(_request(), None)
    issuance = result.issuance
    assert issuance is not None
    facts = registry[issuance]

    assert facts.case_results is result.case_results
    assert facts.failure_codes is result.failure_codes

    replacement = tuple(replace(case_result) for case_result in result.case_results)
    object.__setattr__(result, "case_results", replacement)
    gc.collect()
    assert facts.case_results is not replacement
    with pytest.raises(EvaluationContractError, match="RESULT_FACTORY_REQUIRED"):
        replay_source_neutral_evaluation(_request(), result)


def test_uninitialized_public_shells_close_without_raw_attribute_errors() -> None:
    """Exact-class shells are contract failures, never uncontained attribute access."""
    request_shell = object.__new__(SourceNeutralEvaluationRequest)
    with pytest.raises(EvaluationContractError, match="REQUEST_INVALID"):
        evaluate_source_neutral_contract(request_shell, None)

    result_shell = object.__new__(SourceNeutralEvaluationResult)
    with pytest.raises(EvaluationContractError, match="RESULT_FACTORY_REQUIRED"):
        replay_source_neutral_evaluation(_request(), result_shell)

    request = _request_with_truth(0)
    binding_shell = object.__new__(SourceNeutralValidatorBinding)
    result = evaluate_source_neutral_contract(request, binding_shell)
    assert result.case_results[0].state == "CONTRACT_INVALID"
    assert "VALIDATOR_UNBOUND" in result.case_results[0].reason_codes

    reference_shell = object.__new__(OpaqueEvaluationReference)
    with pytest.raises(EvaluationContractError, match="VALIDATOR_BINDING_INVALID"):
        bind_source_neutral_validator(reference_shell, _outcome)


def test_replay_closes_when_an_issued_nested_result_loses_a_required_slot() -> None:
    """A malformed issued nested result must not leak raw attribute access."""
    request = _request()
    result = evaluate_source_neutral_contract(request, None)
    object.__delattr__(result.case_results[0], "reason_codes")

    with pytest.raises(EvaluationContractError, match="RESULT_FACTORY_REQUIRED"):
        replay_source_neutral_evaluation(request, result)


def test_validator_binding_is_nontransferable_and_outcome_shell_is_accounted() -> None:
    """Local binding authority cannot transfer, and a direct outcome shell closes one case."""
    request = _request_with_truth(0)

    def malformed_outcome(
        snapshot: SourceNeutralValidationSnapshot,
    ) -> SourceNeutralValidationOutcome:
        del snapshot
        return object.__new__(SourceNeutralValidationOutcome)

    binding = bind_source_neutral_validator(request.cases[0].validator_ref, malformed_outcome)
    with pytest.raises(EvaluationContractError, match="VALIDATOR_NONTRANSFERABLE"):
        copy.copy(binding)
    with pytest.raises(EvaluationContractError, match="VALIDATOR_NONTRANSFERABLE"):
        copy.deepcopy(binding)
    with pytest.raises(EvaluationContractError, match="VALIDATOR_NONTRANSFERABLE"):
        pickle.dumps(binding)

    result = evaluate_source_neutral_contract(request, binding)
    assert result.case_results[0].state == "CONTRACT_INVALID"
    assert "VALIDATOR_OUTCOME_INVALID" in result.case_results[0].reason_codes
