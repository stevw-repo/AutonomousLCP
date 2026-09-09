"""Provider-disabled, source-neutral semantic-evaluation contracts.

This module deliberately does not invoke a model, tokenizer, source, or target.
It records whether immutable inputs are sufficient for a later evaluator without
mistaking local contract coverage for a semantic or provider evaluation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Literal, Never, Protocol
from weakref import ref

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .model import ProcessingError

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_REFERENCE_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_MATERIALS = frozenset({"GAZETTE", "LEGISLATION", "CASES", "HKEX"})
_LANGUAGE_SLICES = frozenset({"EN", "ZH_HANT", "BILINGUAL", "CROSS_LANGUAGE"})
_REQUEST_KEYS = frozenset(
    {
        "schema_id",
        "schema_version",
        "revision",
        "semantic_profile_fingerprint",
        "serving_profile_fingerprint",
        "cases",
        "fingerprint",
    }
)
_CASE_KEYS = frozenset(
    {
        "case_id",
        "material",
        "language_slice",
        "evidence_refs",
        "decision_task_ref",
        "challenge_task_ref",
        "validator_ref",
        "decision_output_ref",
        "challenge_output_ref",
        "reference_truth",
    }
)
_REFERENCE_KEYS = frozenset({"ref_id", "fingerprint"})
_TRUTH_KEYS = frozenset({"adjudicated_truth_ref", "task_specific_facts_ref"})
_CASE_NON_EVIDENCE_REF_COUNT = 5

type Material = Literal["GAZETTE", "LEGISLATION", "CASES", "HKEX"]
type LanguageSlice = Literal["EN", "ZH_HANT", "BILINGUAL", "CROSS_LANGUAGE"]


class EvaluationContractError(ProcessingError):
    """One closed failure in the local source-neutral evaluator contract."""


def _fail(code: str) -> Never:
    raise EvaluationContractError(code)


def _fingerprint(value: object, code: str) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        _fail(code)
    return value


def _text(value: object, code: str) -> str:
    """Capture only an exact primitive before inspecting its content."""
    if type(value) is not str:
        _fail(code)
    return value


def _attribute(value: object, name: str, code: str) -> object:
    """Read one exact-class slot without leaking an incomplete shell error."""
    try:
        return getattr(value, name)
    except AttributeError:
        _fail(code)


def _reference_id(value: object, code: str) -> str:
    if type(value) is not str or _REFERENCE_ID.fullmatch(value) is None:
        _fail(code)
    return value


def _version(value: object, code: str) -> str:
    if type(value) is not str or _VERSION.fullmatch(value) is None:
        _fail(code)
    return value


def _material(value: object) -> Material:
    """Narrow an already exact primitive without hashing caller-owned data."""
    text = _text(value, "CASE_INVALID")
    if text == "GAZETTE":
        return "GAZETTE"
    if text == "LEGISLATION":
        return "LEGISLATION"
    if text == "CASES":
        return "CASES"
    if text == "HKEX":
        return "HKEX"
    _fail("CASE_INVALID")


def _language_slice(value: object) -> LanguageSlice:
    """Narrow an already exact primitive without hashing caller-owned data."""
    text = _text(value, "CASE_INVALID")
    if text == "EN":
        return "EN"
    if text == "ZH_HANT":
        return "ZH_HANT"
    if text == "BILINGUAL":
        return "BILINGUAL"
    if text == "CROSS_LANGUAGE":
        return "CROSS_LANGUAGE"
    _fail("CASE_INVALID")


@dataclass(frozen=True, slots=True)
class OpaqueEvaluationReference:
    """An exact opaque pointer; its content is intentionally unavailable here."""

    ref_id: str
    fingerprint: str

    def validate(self) -> None:
        """Require exact primitive identity and lower-case content digest."""
        _reference_id(self.ref_id, "REFERENCE_INVALID")
        _fingerprint(self.fingerprint, "REFERENCE_FINGERPRINT_INVALID")


@dataclass(frozen=True, slots=True)
class SourceNeutralReferenceTruth:
    """Pointers to later protected truth, never substituted with invented facts."""

    adjudicated_truth_ref: OpaqueEvaluationReference | None
    task_specific_facts_ref: OpaqueEvaluationReference | None

    def available(self) -> bool:
        """Return true only for both exact required opaque truth references."""
        self.validate()
        return self.adjudicated_truth_ref is not None and self.task_specific_facts_ref is not None

    def validate(self) -> None:
        """Reject partial or substituted reference values before callbacks."""
        for item in (self.adjudicated_truth_ref, self.task_specific_facts_ref):
            if item is not None and type(item) is not OpaqueEvaluationReference:
                _fail("REFERENCE_TRUTH_INVALID")
            if item is not None:
                item.validate()


@dataclass(frozen=True, slots=True)
class SourceNeutralEvaluationCase:
    """One fully accounted local case with opaque evidence/task/output bindings."""

    case_id: str
    material: Material
    language_slice: LanguageSlice
    evidence_refs: tuple[OpaqueEvaluationReference, ...]
    decision_task_ref: OpaqueEvaluationReference
    challenge_task_ref: OpaqueEvaluationReference
    validator_ref: OpaqueEvaluationReference
    decision_output_ref: OpaqueEvaluationReference
    challenge_output_ref: OpaqueEvaluationReference
    reference_truth: SourceNeutralReferenceTruth

    def validate(self) -> None:
        """Close the complete opaque projection before any evaluator callback."""
        _validate_global_reference_inventory((_snapshot_case(self),))


@dataclass(frozen=True, slots=True)
class SourceNeutralEvaluationRequest:
    """A canonical request that binds profiles only by opaque exact fingerprint."""

    revision: str
    semantic_profile_fingerprint: str
    serving_profile_fingerprint: str
    cases: tuple[SourceNeutralEvaluationCase, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SourceNeutralValidationSnapshot:
    """Detached primitive snapshot made for a validator after all cases are frozen."""

    case_id: str
    material: Material
    language_slice: LanguageSlice
    evidence_refs: tuple[OpaqueEvaluationReference, ...]
    decision_task_ref: OpaqueEvaluationReference
    challenge_task_ref: OpaqueEvaluationReference
    validator_ref: OpaqueEvaluationReference
    decision_output_ref: OpaqueEvaluationReference
    challenge_output_ref: OpaqueEvaluationReference
    adjudicated_truth_ref: OpaqueEvaluationReference | None
    task_specific_facts_ref: OpaqueEvaluationReference | None


@dataclass(frozen=True, slots=True)
class _CapturedRequest:
    """Private retained request facts, never exposed to a validator callback."""

    fingerprint: str
    snapshots: tuple[SourceNeutralValidationSnapshot, ...]


@dataclass(frozen=True, slots=True)
class SourceNeutralValidationOutcome:
    """A validator's opaque output identity check, without legal-content facts."""

    case_id: str
    decision_output_ref: OpaqueEvaluationReference
    challenge_output_ref: OpaqueEvaluationReference
    accepted: bool


class SourceNeutralValidator(Protocol):
    """A future task-specific validator called only when its truth is present."""

    def __call__(self, snapshot: SourceNeutralValidationSnapshot) -> SourceNeutralValidationOutcome:
        """Validate one fully detached source-neutral snapshot."""
        ...


@dataclass(frozen=True, slots=True, eq=False)
class _ValidatorIssuance:
    """Identity-only local witness for one validator/reference binding."""


@dataclass(frozen=True, slots=True, weakref_slot=True, init=False, eq=False)
class SourceNeutralValidatorBinding:
    """Factory-issued proof that one callback owns one opaque validator reference."""

    issuance: _ValidatorIssuance | None = field(repr=False, compare=False)

    def __reduce__(self) -> Never:
        """Keep callback authority process-local and non-transferable."""
        _fail("VALIDATOR_NONTRANSFERABLE")


@dataclass(frozen=True, slots=True)
class SourceNeutralCaseResult:
    """One accounted result which intentionally never states semantic PASS."""

    case_id: str
    state: Literal["NOT_EVALUATED", "CONTRACT_BOUND", "CONTRACT_INVALID", "VALIDATOR_FAILURE"]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True, eq=False)
class _ResultIssuance:
    """Identity-only private witness for one process-local result issuance."""

    projection: bytes


@dataclass(frozen=True, slots=True)
class _IssuedResultFacts:
    """The factory's exact original output identity and immutable projection."""

    projection: bytes
    result_reference: ref[SourceNeutralEvaluationResult]
    request_fingerprint: str
    state: str
    case_results: tuple[SourceNeutralCaseResult, ...]
    failure_codes: tuple[str, ...]
    passed: bool
    fingerprint: str
    issuance_projection: bytes


@dataclass(frozen=True, slots=True)
class _IssuedValidatorFacts:
    """The exact callback object and opaque reference bound at issuance."""

    ref_id: str
    fingerprint: str
    callback: SourceNeutralValidator
    binding_reference: ref[SourceNeutralValidatorBinding]


@dataclass(frozen=True, slots=True, weakref_slot=True, init=False, eq=False)
class SourceNeutralEvaluationResult:
    """Factory-issued local contract evidence; it is never a provider evaluation."""

    request_fingerprint: str
    state: Literal["NOT_EVALUATED"]
    case_results: tuple[SourceNeutralCaseResult, ...]
    failure_codes: tuple[str, ...]
    passed: Literal[False]
    fingerprint: str
    issuance: _ResultIssuance | None = field(repr=False, compare=False)

    def __reduce__(self) -> Never:
        """Prevent copy, deepcopy, and pickle from transferring local issuance."""
        _fail("RESULT_NONTRANSFERABLE")


_ISSUED_RESULTS: dict[_ResultIssuance, _IssuedResultFacts] = {}
_ISSUED_VALIDATORS: dict[_ValidatorIssuance, _IssuedValidatorFacts] = {}


def _reference_projection(value: OpaqueEvaluationReference | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"fingerprint": value.fingerprint, "ref_id": value.ref_id}


def _case_projection(
    value: SourceNeutralEvaluationCase | SourceNeutralValidationSnapshot,
) -> dict[str, object]:
    if isinstance(value, SourceNeutralEvaluationCase):
        adjudicated_truth_ref = value.reference_truth.adjudicated_truth_ref
        task_specific_facts_ref = value.reference_truth.task_specific_facts_ref
    else:
        adjudicated_truth_ref = value.adjudicated_truth_ref
        task_specific_facts_ref = value.task_specific_facts_ref
    return {
        "case_id": value.case_id,
        "challenge_output_ref": _reference_projection(value.challenge_output_ref),
        "challenge_task_ref": _reference_projection(value.challenge_task_ref),
        "decision_output_ref": _reference_projection(value.decision_output_ref),
        "decision_task_ref": _reference_projection(value.decision_task_ref),
        "evidence_refs": [_reference_projection(item) for item in value.evidence_refs],
        "language_slice": value.language_slice,
        "material": value.material,
        "reference_truth": {
            "adjudicated_truth_ref": _reference_projection(adjudicated_truth_ref),
            "task_specific_facts_ref": _reference_projection(task_specific_facts_ref),
        },
        "validator_ref": _reference_projection(value.validator_ref),
    }


def _request_projection(
    revision: str,
    semantic_profile_fingerprint: str,
    serving_profile_fingerprint: str,
    cases: tuple[SourceNeutralEvaluationCase, ...] | tuple[SourceNeutralValidationSnapshot, ...],
) -> bytes:
    return canonicalize(
        checked_json_value(
            {
                "cases": [_case_projection(item) for item in cases],
                "revision": revision,
                "schema_id": "asklegal.hk-v1-source-neutral-evaluation-request",
                "schema_version": "1.0.0",
                "semantic_profile_fingerprint": semantic_profile_fingerprint,
                "serving_profile_fingerprint": serving_profile_fingerprint,
            }
        )
    )


def _capture_reference(value: object, code: str) -> OpaqueEvaluationReference:
    """Detach one opaque reference before regex or equality work begins."""
    if type(value) is not OpaqueEvaluationReference:
        _fail(code)
    ref_id = _reference_id(_attribute(value, "ref_id", code), code)
    fingerprint = _fingerprint(_attribute(value, "fingerprint", code), code)
    return OpaqueEvaluationReference(ref_id, fingerprint)


def _capture_optional_reference(value: object, code: str) -> OpaqueEvaluationReference | None:
    """Detach one optional opaque reference without accepting a substitute type."""
    if value is None:
        return None
    return _capture_reference(value, code)


def _capture_truth(
    value: object,
) -> tuple[OpaqueEvaluationReference | None, OpaqueEvaluationReference | None]:
    """Detach protected truth as references only; this contract cannot inspect facts."""
    if type(value) is not SourceNeutralReferenceTruth:
        _fail("REFERENCE_TRUTH_INVALID")
    return (
        _capture_optional_reference(
            _attribute(value, "adjudicated_truth_ref", "REFERENCE_TRUTH_INVALID"),
            "REFERENCE_TRUTH_INVALID",
        ),
        _capture_optional_reference(
            _attribute(value, "task_specific_facts_ref", "REFERENCE_TRUTH_INVALID"),
            "REFERENCE_TRUTH_INVALID",
        ),
    )


def _snapshot_case(value: SourceNeutralEvaluationCase) -> SourceNeutralValidationSnapshot:
    """Capture every caller-owned case value before any aggregate operation."""
    if type(value) is not SourceNeutralEvaluationCase:
        _fail("CASE_INVALID")
    try:
        case_id_value = value.case_id
        material_value = value.material
        language_slice_value = value.language_slice
        evidence_value = value.evidence_refs
        decision_task_value = value.decision_task_ref
        challenge_task_value = value.challenge_task_ref
        validator_value = value.validator_ref
        decision_output_value = value.decision_output_ref
        challenge_output_value = value.challenge_output_ref
        truth_value = value.reference_truth
    except AttributeError:
        _fail("CASE_INVALID")
    case_id = _reference_id(case_id_value, "CASE_INVALID")
    material = _material(material_value)
    language_slice = _language_slice(language_slice_value)
    if type(evidence_value) is not tuple or not evidence_value:
        _fail("CASE_INVALID")
    evidence_refs = tuple(_capture_reference(item, "CASE_INVALID") for item in evidence_value)
    decision_task_ref = _capture_reference(decision_task_value, "CASE_INVALID")
    challenge_task_ref = _capture_reference(challenge_task_value, "CASE_INVALID")
    validator_ref = _capture_reference(validator_value, "CASE_INVALID")
    decision_output_ref = _capture_reference(decision_output_value, "CASE_INVALID")
    challenge_output_ref = _capture_reference(challenge_output_value, "CASE_INVALID")
    adjudicated_truth_ref, task_specific_facts_ref = _capture_truth(truth_value)
    return SourceNeutralValidationSnapshot(
        case_id,
        material,
        language_slice,
        evidence_refs,
        decision_task_ref,
        challenge_task_ref,
        validator_ref,
        decision_output_ref,
        challenge_output_ref,
        adjudicated_truth_ref,
        task_specific_facts_ref,
    )


def _references(value: SourceNeutralValidationSnapshot) -> tuple[OpaqueEvaluationReference, ...]:
    """Return every opaque identifier role, including optional protected truth."""
    truth = tuple(
        item
        for item in (value.adjudicated_truth_ref, value.task_specific_facts_ref)
        if item is not None
    )
    return (
        *value.evidence_refs,
        value.decision_task_ref,
        value.challenge_task_ref,
        value.validator_ref,
        value.decision_output_ref,
        value.challenge_output_ref,
        *truth,
    )


def _validate_global_reference_inventory(
    snapshots: tuple[SourceNeutralValidationSnapshot, ...],
) -> None:
    """Use one globally unique opaque-ID namespace for all contract roles."""
    seen: set[str] = set()
    for snapshot in snapshots:
        for reference in _references(snapshot):
            if reference.ref_id in seen:
                _fail("REFERENCE_ID_REUSED")
            seen.add(reference.ref_id)


def _snapshot_request(
    value: SourceNeutralEvaluationRequest,
) -> _CapturedRequest:
    if type(value) is not SourceNeutralEvaluationRequest:
        _fail("REQUEST_INVALID")
    try:
        cases_value = value.cases
        revision_value = value.revision
        semantic_profile_value = value.semantic_profile_fingerprint
        serving_profile_value = value.serving_profile_fingerprint
        fingerprint_value = value.fingerprint
    except AttributeError:
        _fail("REQUEST_INVALID")
    if type(cases_value) is not tuple:
        _fail("REQUEST_INVALID")
    revision = _text(revision_value, "REQUEST_INVALID")
    semantic_profile_fingerprint = _text(semantic_profile_value, "PROFILE_FINGERPRINT_INVALID")
    serving_profile_fingerprint = _text(serving_profile_value, "PROFILE_FINGERPRINT_INVALID")
    fingerprint = _text(fingerprint_value, "REQUEST_FINGERPRINT_MISMATCH")
    if not cases_value:
        _fail("REQUEST_INVALID")
    snapshots = tuple(_snapshot_case(item) for item in cases_value)
    _version(revision, "REQUEST_INVALID")
    _fingerprint(semantic_profile_fingerprint, "PROFILE_FINGERPRINT_INVALID")
    _fingerprint(serving_profile_fingerprint, "PROFILE_FINGERPRINT_INVALID")
    _fingerprint(fingerprint, "REQUEST_FINGERPRINT_MISMATCH")
    _validate_global_reference_inventory(snapshots)
    case_ids = tuple(item.case_id for item in snapshots)
    if case_ids != tuple(sorted(case_ids)) or len(set(case_ids)) != len(case_ids):
        _fail("CASE_ACCOUNTING_INVALID")
    if (
        frozenset(item.material for item in snapshots) != _MATERIALS
        or frozenset(item.language_slice for item in snapshots) != _LANGUAGE_SLICES
    ):
        _fail("CASE_COVERAGE_INCOMPLETE")
    projection = _request_projection(
        revision,
        semantic_profile_fingerprint,
        serving_profile_fingerprint,
        snapshots,
    )
    expected = f"sha256:{sha256(projection).hexdigest()}"
    if fingerprint != expected:
        _fail("REQUEST_FINGERPRINT_MISMATCH")
    return _CapturedRequest(fingerprint, snapshots)


def _object(value: JsonValue | None, code: str) -> dict[str, JsonValue]:
    if type(value) is not dict:
        _fail(code)
    return value


def _keys(value: dict[str, JsonValue], expected: frozenset[str], code: str) -> None:
    if frozenset(value) != expected:
        _fail(code)


def _parse_reference(value: JsonValue | None, code: str) -> OpaqueEvaluationReference:
    raw = _object(value, code)
    _keys(raw, _REFERENCE_KEYS, code)
    return OpaqueEvaluationReference(
        _reference_id(raw.get("ref_id"), code), _fingerprint(raw.get("fingerprint"), code)
    )


def _parse_truth(value: JsonValue | None) -> SourceNeutralReferenceTruth:
    raw = _object(value, "REFERENCE_TRUTH_INVALID")
    _keys(raw, _TRUTH_KEYS, "REFERENCE_TRUTH_INVALID")
    truth = raw.get("adjudicated_truth_ref")
    facts = raw.get("task_specific_facts_ref")
    return SourceNeutralReferenceTruth(
        None if truth is None else _parse_reference(truth, "REFERENCE_TRUTH_INVALID"),
        None if facts is None else _parse_reference(facts, "REFERENCE_TRUTH_INVALID"),
    )


def _parse_case(value: JsonValue) -> SourceNeutralEvaluationCase:
    raw = _object(value, "CASE_INVALID")
    _keys(raw, _CASE_KEYS, "CASE_INVALID")
    evidence = raw.get("evidence_refs")
    if type(evidence) is not list or not evidence:
        _fail("CASE_INVALID")
    return SourceNeutralEvaluationCase(
        _reference_id(raw.get("case_id"), "CASE_INVALID"),
        _material(raw.get("material")),
        _language_slice(raw.get("language_slice")),
        tuple(_parse_reference(item, "CASE_INVALID") for item in evidence),
        _parse_reference(raw.get("decision_task_ref"), "CASE_INVALID"),
        _parse_reference(raw.get("challenge_task_ref"), "CASE_INVALID"),
        _parse_reference(raw.get("validator_ref"), "CASE_INVALID"),
        _parse_reference(raw.get("decision_output_ref"), "CASE_INVALID"),
        _parse_reference(raw.get("challenge_output_ref"), "CASE_INVALID"),
        _parse_truth(raw.get("reference_truth")),
    )


def load_source_neutral_evaluation_request(raw: bytes) -> SourceNeutralEvaluationRequest:
    """Decode one small canonical source-neutral fixture with no external reads."""
    if type(raw) is not bytes or not raw:
        _fail("REQUEST_DOCUMENT_INVALID")
    try:
        parsed = parse_json_bytes(raw, max_bytes=2_000_000)
    except ContractViolation:
        _fail("REQUEST_DOCUMENT_INVALID")
    document = _object(parsed, "REQUEST_DOCUMENT_INVALID")
    _keys(document, _REQUEST_KEYS, "REQUEST_DOCUMENT_INVALID")
    if (
        document.get("schema_id") != "asklegal.hk-v1-source-neutral-evaluation-request"
        or document.get("schema_version") != "1.0.0"
    ):
        _fail("REQUEST_DOCUMENT_INVALID")
    cases = document.get("cases")
    if type(cases) is not list or not cases:
        _fail("REQUEST_DOCUMENT_INVALID")
    projection = dict(document)
    supplied = _fingerprint(projection.pop("fingerprint", None), "REQUEST_FINGERPRINT_MISMATCH")
    expected = f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"
    if supplied != expected:
        _fail("REQUEST_FINGERPRINT_MISMATCH")
    request = SourceNeutralEvaluationRequest(
        _version(document.get("revision"), "REQUEST_DOCUMENT_INVALID"),
        _fingerprint(document.get("semantic_profile_fingerprint"), "PROFILE_FINGERPRINT_INVALID"),
        _fingerprint(document.get("serving_profile_fingerprint"), "PROFILE_FINGERPRINT_INVALID"),
        tuple(_parse_case(item) for item in cases),
        supplied,
    )
    _snapshot_request(request)
    return request


def _snapshot_has_truth(value: SourceNeutralValidationSnapshot) -> bool:
    return value.adjudicated_truth_ref is not None and value.task_specific_facts_ref is not None


def _validator_snapshot(value: SourceNeutralValidationSnapshot) -> SourceNeutralValidationSnapshot:
    """Give a validator its own disposable copy of retained accounting facts."""
    return SourceNeutralValidationSnapshot(
        value.case_id,
        value.material,
        value.language_slice,
        tuple(_capture_reference(item, "CASE_INVALID") for item in value.evidence_refs),
        _capture_reference(value.decision_task_ref, "CASE_INVALID"),
        _capture_reference(value.challenge_task_ref, "CASE_INVALID"),
        _capture_reference(value.validator_ref, "CASE_INVALID"),
        _capture_reference(value.decision_output_ref, "CASE_INVALID"),
        _capture_reference(value.challenge_output_ref, "CASE_INVALID"),
        _capture_optional_reference(value.adjudicated_truth_ref, "REFERENCE_TRUTH_INVALID"),
        _capture_optional_reference(value.task_specific_facts_ref, "REFERENCE_TRUTH_INVALID"),
    )


def _not_evaluated_result(value: SourceNeutralValidationSnapshot) -> SourceNeutralCaseResult:
    reasons = ["PROVIDER_DISABLED"]
    if value.adjudicated_truth_ref is None:
        reasons.append("PROTECTED_REFERENCE_TRUTH_MISSING")
    if value.task_specific_facts_ref is None:
        reasons.append("TASK_SPECIFIC_FACTS_MISSING")
    return SourceNeutralCaseResult(value.case_id, "NOT_EVALUATED", tuple(sorted(reasons)))


def _outcome_matches(snapshot: SourceNeutralValidationSnapshot, value: object) -> tuple[bool, str]:
    if type(value) is not SourceNeutralValidationOutcome:
        return False, "VALIDATOR_OUTCOME_INVALID"
    try:
        case_id = value.case_id
        decision_output_ref = value.decision_output_ref
        challenge_output_ref = value.challenge_output_ref
        accepted = value.accepted
    except AttributeError:
        return False, "VALIDATOR_OUTCOME_INVALID"
    if (
        type(case_id) is not str
        or case_id != snapshot.case_id
        or type(decision_output_ref) is not OpaqueEvaluationReference
        or type(challenge_output_ref) is not OpaqueEvaluationReference
        or type(accepted) is not bool
    ):
        return False, "VALIDATOR_OUTCOME_INVALID"
    decision_output_ref.validate()
    challenge_output_ref.validate()
    if (
        decision_output_ref != snapshot.decision_output_ref
        or challenge_output_ref != snapshot.challenge_output_ref
    ):
        return False, "VALIDATOR_OUTCOME_MISMATCH"
    if not accepted:
        return False, "VALIDATOR_REJECTED"
    return True, ""


def bind_source_neutral_validator(
    validator_ref: OpaqueEvaluationReference, validator: SourceNeutralValidator
) -> SourceNeutralValidatorBinding:
    """Issue process-local authority for one exact callback/reference pair."""
    reference = _capture_reference(validator_ref, "VALIDATOR_BINDING_INVALID")
    if not callable(validator):
        _fail("VALIDATOR_BINDING_INVALID")
    issuance = _ValidatorIssuance()
    binding = object.__new__(SourceNeutralValidatorBinding)
    object.__setattr__(binding, "issuance", issuance)
    _ISSUED_VALIDATORS[issuance] = _IssuedValidatorFacts(
        reference.ref_id,
        reference.fingerprint,
        validator,
        ref(binding, lambda _dead: _discard_dead_validator(issuance)),
    )
    return binding


def _bound_callback(
    value: object | None, snapshot: SourceNeutralValidationSnapshot
) -> SourceNeutralValidator | None:
    """Resolve only a factory-issued callback that exactly owns this validator ID."""
    if type(value) is not SourceNeutralValidatorBinding:
        return None
    try:
        issuance = value.issuance
    except AttributeError:
        return None
    if type(issuance) is not _ValidatorIssuance:
        return None
    facts = _ISSUED_VALIDATORS.get(issuance)
    if facts is None or facts.binding_reference() is not value:
        return None
    if (
        facts.ref_id != snapshot.validator_ref.ref_id
        or facts.fingerprint != snapshot.validator_ref.fingerprint
    ):
        return None
    return facts.callback


def _call_validator(
    callback: SourceNeutralValidator,
    callback_snapshot: SourceNeutralValidationSnapshot,
    grading_snapshot: SourceNeutralValidationSnapshot,
) -> tuple[bool, str]:
    """Call with a disposable copy and grade only against private retained facts."""
    try:
        outcome = callback(callback_snapshot)
    except BaseException as error:
        if isinstance(error, Exception):
            return False, "VALIDATOR_FAILURE"
        raise
    try:
        return _outcome_matches(grading_snapshot, outcome)
    except BaseException as error:
        if isinstance(error, Exception):
            return False, "VALIDATOR_OUTCOME_INVALID"
        raise


def _result_projection(
    request_fingerprint: str,
    case_results: tuple[SourceNeutralCaseResult, ...],
    failure_codes: tuple[str, ...],
) -> bytes:
    return canonicalize(
        checked_json_value(
            {
                "case_results": [
                    {
                        "case_id": item.case_id,
                        "reason_codes": list(item.reason_codes),
                        "state": item.state,
                    }
                    for item in case_results
                ],
                "failure_codes": list(failure_codes),
                "passed": False,
                "request_fingerprint": request_fingerprint,
                "state": "NOT_EVALUATED",
                "type": "asklegal.source-neutral-evaluation-result.public.v1",
            }
        )
    )


def _discard_dead_result(issuance: _ResultIssuance) -> None:
    """Release registry facts as soon as the associated public result dies."""
    _ISSUED_RESULTS.pop(issuance, None)


def _discard_dead_validator(issuance: _ValidatorIssuance) -> None:
    """Release a callback binding when its corresponding local authority dies."""
    _ISSUED_VALIDATORS.pop(issuance, None)


def _result_has_safe_shape(value: SourceNeutralEvaluationResult) -> bool:
    """Narrow containers before walking a possibly tampered public result."""
    try:
        request_fingerprint = value.request_fingerprint
        state = value.state
        case_results = value.case_results
        failure_codes = value.failure_codes
        passed = value.passed
        fingerprint = value.fingerprint
    except AttributeError:
        return False
    if (
        type(request_fingerprint) is not str
        or type(state) is not str
        or type(case_results) is not tuple
        or type(failure_codes) is not tuple
        or type(passed) is not bool
        or type(fingerprint) is not str
    ):
        return False
    for case_result in case_results:
        if type(case_result) is not SourceNeutralCaseResult:
            return False
        try:
            case_id = case_result.case_id
            case_state = case_result.state
            reason_codes = case_result.reason_codes
        except AttributeError:
            return False
        if (
            type(case_id) is not str
            or type(case_state) is not str
            or type(reason_codes) is not tuple
        ):
            return False
    return True


def _issue_result(
    request_fingerprint: str, case_results: tuple[SourceNeutralCaseResult, ...]
) -> SourceNeutralEvaluationResult:
    failure_codes = tuple(
        sorted(
            {code for item in case_results for code in item.reason_codes} | {"PROVIDER_DISABLED"}
        )
    )
    projection = _result_projection(request_fingerprint, case_results, failure_codes)
    issuance = _ResultIssuance(projection)
    result = object.__new__(SourceNeutralEvaluationResult)
    object.__setattr__(result, "request_fingerprint", request_fingerprint)
    object.__setattr__(result, "state", "NOT_EVALUATED")
    object.__setattr__(result, "case_results", case_results)
    object.__setattr__(result, "failure_codes", failure_codes)
    object.__setattr__(result, "passed", False)
    object.__setattr__(result, "fingerprint", f"sha256:{sha256(projection).hexdigest()}")
    object.__setattr__(result, "issuance", issuance)
    _ISSUED_RESULTS[issuance] = _IssuedResultFacts(
        projection,
        ref(result, lambda _dead: _discard_dead_result(issuance)),
        request_fingerprint,
        result.state,
        case_results,
        failure_codes,
        result.passed,
        result.fingerprint,
        issuance.projection,
    )
    return result


def evaluate_source_neutral_contract(
    request: SourceNeutralEvaluationRequest,
    validator: SourceNeutralValidatorBinding | object | None,
) -> SourceNeutralEvaluationResult:
    """Account for every supplied case without a provider call or semantic PASS."""
    captured_request = _snapshot_request(request)
    results: list[SourceNeutralCaseResult] = []
    for snapshot in captured_request.snapshots:
        if not _snapshot_has_truth(snapshot):
            results.append(_not_evaluated_result(snapshot))
            continue
        callback = _bound_callback(validator, snapshot)
        if callback is None:
            reason = "VALIDATOR_UNAVAILABLE" if validator is None else "VALIDATOR_UNBOUND"
            results.append(
                SourceNeutralCaseResult(
                    snapshot.case_id,
                    "CONTRACT_INVALID",
                    ("PROVIDER_DISABLED", reason),
                )
            )
            continue
        matches, reason = _call_validator(callback, _validator_snapshot(snapshot), snapshot)
        if reason == "VALIDATOR_FAILURE":
            results.append(
                SourceNeutralCaseResult(
                    snapshot.case_id,
                    "VALIDATOR_FAILURE",
                    ("PROVIDER_DISABLED", "VALIDATOR_FAILURE"),
                )
            )
            continue
        if not matches:
            results.append(
                SourceNeutralCaseResult(
                    snapshot.case_id, "CONTRACT_INVALID", ("PROVIDER_DISABLED", reason)
                )
            )
            continue
        results.append(
            SourceNeutralCaseResult(snapshot.case_id, "CONTRACT_BOUND", ("PROVIDER_DISABLED",))
        )
    return _issue_result(captured_request.fingerprint, tuple(results))


def replay_source_neutral_evaluation(
    request: SourceNeutralEvaluationRequest, result: SourceNeutralEvaluationResult
) -> SourceNeutralEvaluationResult:
    """Require the exact factory-issued result and original complete projection."""
    captured_request = _snapshot_request(request)
    issuance = _result_issuance(result)
    if type(result) is not SourceNeutralEvaluationResult or type(issuance) is not _ResultIssuance:
        _fail("RESULT_FACTORY_REQUIRED")
    facts = _ISSUED_RESULTS.pop(issuance, None)
    if facts is None or facts.result_reference() is not result:
        _fail("RESULT_FACTORY_REQUIRED")
    if not _result_has_safe_shape(result):
        _fail("RESULT_FACTORY_REQUIRED")
    if (
        result.request_fingerprint is not facts.request_fingerprint
        or result.state is not facts.state
        or result.case_results is not facts.case_results
        or result.failure_codes is not facts.failure_codes
        or result.passed is not facts.passed
        or result.fingerprint is not facts.fingerprint
        or issuance.projection is not facts.issuance_projection
    ):
        _fail("RESULT_FACTORY_REQUIRED")
    if (
        result.request_fingerprint != captured_request.fingerprint
        or result.state != "NOT_EVALUATED"
        or result.passed is not False
        or result.failure_codes != tuple(sorted(set(result.failure_codes)))
        or any(type(item) is not SourceNeutralCaseResult for item in result.case_results)
    ):
        _fail("RESULT_FACTORY_REQUIRED")
    try:
        projection = _result_projection(
            result.request_fingerprint, result.case_results, result.failure_codes
        )
    except Exception as error:
        code = "RESULT_FACTORY_REQUIRED"
        raise EvaluationContractError(code) from error
    if (
        projection != facts.projection
        or issuance.projection != facts.projection
        or result.fingerprint != f"sha256:{sha256(projection).hexdigest()}"
    ):
        _fail("RESULT_FACTORY_REQUIRED")
    _ISSUED_RESULTS[issuance] = facts
    return result


def _result_issuance(value: object) -> _ResultIssuance | None:
    """Expose no authority; keep the private issuance read inside its own module."""
    if type(value) is not SourceNeutralEvaluationResult:
        return None
    try:
        return value.issuance
    except AttributeError:
        return None


__all__ = [
    "EvaluationContractError",
    "OpaqueEvaluationReference",
    "SourceNeutralEvaluationCase",
    "SourceNeutralEvaluationRequest",
    "SourceNeutralEvaluationResult",
    "SourceNeutralReferenceTruth",
    "SourceNeutralValidationOutcome",
    "SourceNeutralValidationSnapshot",
    "evaluate_source_neutral_contract",
    "load_source_neutral_evaluation_request",
    "replay_source_neutral_evaluation",
]
