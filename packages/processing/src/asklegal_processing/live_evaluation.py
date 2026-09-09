"""Owner-issued semantic evaluation receipts from actual admitted runner outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Never, cast

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .model import (
    AdmittedSemanticDecision,
    SemanticDecision,
    SemanticTaskRequest,
    semantic_effect_receipt_id,
)
from .profiles import SemanticProfileSet, validate_semantic_profile_set_authority
from .semantic import SemanticTaskGate

_SCHEMA = "asklegal.hk-v1-live-semantic-evaluation/v1"
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CUTOFF = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00\Z")
_MAX_BYTES = 8_000_000
_PROFILE_PAIR_SIZE = 2
_ERROR = "LIVE_SEMANTIC_EVALUATION_INVALID"
_EFFECT_RECEIPT = re.compile(r"mec_[0-9a-f]{48}\Z")


class LiveSemanticEvaluationError(ValueError):
    """One invalid live semantic receipt or execution input."""


def _fail() -> Never:
    raise LiveSemanticEvaluationError(_ERROR)


@dataclass(frozen=True, slots=True)
class LiveSemanticEvaluationCase:
    """One executable golden case and its adjudicated decision code."""

    case_id: str
    requests: tuple[SemanticTaskRequest, SemanticTaskRequest]
    expected_decision_code: str
    suite_case_fingerprint: str


@dataclass(frozen=True, slots=True)
class LiveSemanticEvaluationReceipt:
    """Parsed passed receipt bound to one exact V1 lineage."""

    run_id: str
    observation_cutoff: str
    proposal_fingerprint: str
    semantic_profile_fingerprint: str
    serving_profile_fingerprint: str
    suite_fingerprint: str
    case_count: int
    fingerprint: str
    result: str = "PASSED"


def _decision_document(value: SemanticDecision) -> dict[str, JsonValue]:
    return {
        "challenge_code": value.challenge_code,
        "decision_code": value.decision_code,
        "effect_receipt_id": value.effect_receipt_id,
        "output_fingerprint": value.output_fingerprint,
        "phase": value.phase,
        "provider": value.provider,
        "provider_request_id": value.provider_request_id,
        "request_id": value.request_id,
        "supporting_evidence_refs": list(value.supporting_evidence_refs),
        "task": value.task,
        "unresolved_facts": list(value.unresolved_facts),
    }


def _case_document(
    case: LiveSemanticEvaluationCase, admitted: AdmittedSemanticDecision
) -> dict[str, JsonValue]:
    primary_request, _challenge_request = case.requests
    return {
        "case_id": case.case_id,
        "challenge": _decision_document(admitted.challenge),
        "challenge_profile_id": admitted.challenge_profile_id,
        "evidence_refs": list(primary_request.evidence_refs),
        "expected_decision_code": case.expected_decision_code,
        "input_fingerprint": primary_request.input_fingerprint,
        "package_fingerprint": primary_request.package_fingerprint,
        "primary": _decision_document(admitted.primary),
        "primary_profile_id": admitted.primary_profile_id,
        "suite_case_fingerprint": case.suite_case_fingerprint,
    }


def semantic_evaluation_request_id(run_id: str, case_id: str, phase: str) -> str:
    """Derive one run-bound owner request identity for an evaluation call."""
    return "ser_" + sha256(f"{run_id}\x1f{case_id}\x1f{phase}".encode()).hexdigest()[:48]


def run_live_semantic_evaluation(  # noqa: PLR0913 - exact evaluation lineage.
    *,
    run_id: str,
    observation_cutoff: str,
    proposal_fingerprint: str,
    serving_profile_fingerprint: str,
    suite_fingerprint: str,
    profile_set: SemanticProfileSet,
    cases: tuple[LiveSemanticEvaluationCase, ...],
    gate: SemanticTaskGate,
    environment: str,
    now: str,
) -> bytes:
    """Execute every case through the actual configured semantic gate and retain outputs."""
    try:
        validate_semantic_profile_set_authority(profile_set)
    except Exception as error:
        raise LiveSemanticEvaluationError(_ERROR) from error
    profiles = {profile.profile_id: profile for profile in profile_set.profiles}
    if (
        type(run_id) is not str
        or not run_id
        or _CUTOFF.fullmatch(observation_cutoff) is None
        or _FINGERPRINT.fullmatch(proposal_fingerprint) is None
        or _FINGERPRINT.fullmatch(serving_profile_fingerprint) is None
        or _FINGERPRINT.fullmatch(suite_fingerprint) is None
        or not cases
        or len({case.case_id for case in cases}) != len(cases)
    ):
        _fail()
    case_documents: list[dict[str, JsonValue]] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        if (
            type(case.case_id) is not str
            or not case.case_id
            or len(case.requests) != _PROFILE_PAIR_SIZE
            or _FINGERPRINT.fullmatch(case.suite_case_fingerprint) is None
        ):
            _fail()
        primary_request, challenge_request = case.requests
        primary_request = replace(
            primary_request,
            request_id=semantic_evaluation_request_id(run_id, case.case_id, "DECISION"),
        )
        challenge_request = replace(
            challenge_request,
            request_id=semantic_evaluation_request_id(run_id, case.case_id, "CHALLENGE"),
        )
        run_requests = (primary_request, challenge_request)
        try:
            profile_pair = (
                profiles[primary_request.profile_id],
                profiles[challenge_request.profile_id],
            )
            admitted = gate.decide(
                profile_pair,
                run_requests,
                environment=environment,
                now=now,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise LiveSemanticEvaluationError(_ERROR) from error
        if admitted.primary.decision_code != case.expected_decision_code:
            _fail()
        case_documents.append(_case_document(replace(case, requests=run_requests), admitted))
    document: dict[str, object] = {
        "cases": case_documents,
        "observation_cutoff": observation_cutoff,
        "proposal_fingerprint": proposal_fingerprint,
        "result": "PASSED",
        "run_id": run_id,
        "schema_id": _SCHEMA,
        "semantic_profile_fingerprint": profile_set.fingerprint,
        "serving_profile_fingerprint": serving_profile_fingerprint,
        "suite_fingerprint": suite_fingerprint,
    }
    unsigned = canonicalize(checked_json_value(document))
    document["fingerprint"] = "sha256:" + sha256(unsigned).hexdigest()
    raw = canonicalize(checked_json_value(document))
    parse_live_semantic_evaluation(raw)
    return raw


def _decision(
    value: object,
    *,
    challenge: bool,
    evidence_refs: set[str],
    expected_request_id: str,
) -> dict[str, object]:
    if type(value) is not dict:
        _fail()
    document = cast("dict[str, object]", value)
    if set(document) != {
        "challenge_code",
        "decision_code",
        "effect_receipt_id",
        "output_fingerprint",
        "phase",
        "provider",
        "provider_request_id",
        "request_id",
        "supporting_evidence_refs",
        "task",
        "unresolved_facts",
    }:
        _fail()
    result = cast("dict[str, object]", value)
    refs = result.get("supporting_evidence_refs")
    unresolved = result.get("unresolved_facts")
    if (
        result.get("request_id") != expected_request_id
        or type(result.get("task")) is not str
        or type(result.get("decision_code")) is not str
        or type(refs) is not list
        or any(type(item) is not str for item in cast("list[object]", refs))
        or not set(cast("list[str]", refs)).issubset(evidence_refs)
        or type(unresolved) is not list
        or unresolved
        or result.get("phase") != ("CHALLENGE" if challenge else "DECISION")
        or result.get("challenge_code") != ("PASS" if challenge else "NOT_APPLICABLE")
        or result.get("provider") != "AZURE_OPENAI"
        or type(result.get("provider_request_id")) is not str
        or not result.get("provider_request_id")
        or result.get("provider_request_id") == "unreported"
        or type(result.get("effect_receipt_id")) is not str
        or _EFFECT_RECEIPT.fullmatch(cast("str", result["effect_receipt_id"])) is None
    ):
        _fail()
    projection = {
        key: item
        for key, item in result.items()
        if key
        not in {
            "effect_receipt_id",
            "output_fingerprint",
            "provider",
            "provider_request_id",
        }
    }
    if (
        result.get("output_fingerprint")
        != "sha256:" + sha256(canonicalize(checked_json_value(projection))).hexdigest()
    ):
        _fail()
    if result.get("effect_receipt_id") != semantic_effect_receipt_id(
        expected_request_id,
        cast("str", result["provider_request_id"]),
        cast("str", result["output_fingerprint"]),
    ):
        _fail()
    return result


def parse_live_semantic_evaluation(  # noqa: C901 - closed receipt grammar.
    raw: bytes,
) -> LiveSemanticEvaluationReceipt:
    """Strictly rederive one passed live semantic evaluation receipt."""
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX_BYTES)
    except ValueError:
        _fail()
    if type(value) is not dict:
        _fail()
    document = cast("dict[str, object]", value)
    if set(document) != {
        "cases",
        "fingerprint",
        "observation_cutoff",
        "proposal_fingerprint",
        "result",
        "run_id",
        "schema_id",
        "semantic_profile_fingerprint",
        "serving_profile_fingerprint",
        "suite_fingerprint",
    }:
        _fail()
    unsigned = {key: item for key, item in document.items() if key != "fingerprint"}
    fingerprints = (
        document.get("proposal_fingerprint"),
        document.get("semantic_profile_fingerprint"),
        document.get("serving_profile_fingerprint"),
        document.get("suite_fingerprint"),
    )
    cases = document.get("cases")
    if (
        canonicalize(value) != raw
        or document.get("schema_id") != _SCHEMA
        or document.get("result") != "PASSED"
        or type(document.get("run_id")) is not str
        or not document["run_id"]
        or type(document.get("observation_cutoff")) is not str
        or _CUTOFF.fullmatch(cast("str", document["observation_cutoff"])) is None
        or any(
            type(item) is not str or _FINGERPRINT.fullmatch(item) is None for item in fingerprints
        )
        or document.get("fingerprint")
        != "sha256:" + sha256(canonicalize(checked_json_value(unsigned))).hexdigest()
        or type(cases) is not list
        or not cases
    ):
        _fail()
    case_ids: list[str] = []
    for raw_case in cast("list[object]", cases):
        if type(raw_case) is not dict:
            _fail()
        case = cast("dict[str, object]", raw_case)
        if set(case) != {
            "case_id",
            "challenge",
            "challenge_profile_id",
            "evidence_refs",
            "expected_decision_code",
            "input_fingerprint",
            "package_fingerprint",
            "primary",
            "primary_profile_id",
            "suite_case_fingerprint",
        }:
            _fail()
        refs = case.get("evidence_refs")
        if (
            type(case.get("case_id")) is not str
            or type(case.get("primary_profile_id")) is not str
            or type(case.get("challenge_profile_id")) is not str
            or case.get("primary_profile_id") == case.get("challenge_profile_id")
            or type(refs) is not list
            or any(type(item) is not str for item in cast("list[object]", refs))
            or type(case.get("expected_decision_code")) is not str
            or type(case.get("input_fingerprint")) is not str
            or _FINGERPRINT.fullmatch(cast("str", case["input_fingerprint"])) is None
            or type(case.get("package_fingerprint")) is not str
            or _FINGERPRINT.fullmatch(cast("str", case["package_fingerprint"])) is None
            or type(case.get("suite_case_fingerprint")) is not str
            or _FINGERPRINT.fullmatch(cast("str", case["suite_case_fingerprint"])) is None
        ):
            _fail()
        evidence_refs = set(cast("list[str]", refs))
        primary = _decision(
            case.get("primary"),
            challenge=False,
            evidence_refs=evidence_refs,
            expected_request_id=semantic_evaluation_request_id(
                cast("str", document["run_id"]), cast("str", case["case_id"]), "DECISION"
            ),
        )
        challenge = _decision(
            case.get("challenge"),
            challenge=True,
            evidence_refs=evidence_refs,
            expected_request_id=semantic_evaluation_request_id(
                cast("str", document["run_id"]), cast("str", case["case_id"]), "CHALLENGE"
            ),
        )
        if (
            primary.get("decision_code") != case.get("expected_decision_code")
            or challenge.get("decision_code") != case.get("expected_decision_code")
            or primary.get("task") == challenge.get("task")
            or primary.get("request_id") == challenge.get("request_id")
        ):
            _fail()
        case_ids.append(cast("str", case["case_id"]))
    if case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
        _fail()
    return LiveSemanticEvaluationReceipt(
        cast("str", document["run_id"]),
        cast("str", document["observation_cutoff"]),
        cast("str", document["proposal_fingerprint"]),
        cast("str", document["semantic_profile_fingerprint"]),
        cast("str", document["serving_profile_fingerprint"]),
        cast("str", document["suite_fingerprint"]),
        len(case_ids),
        cast("str", document["fingerprint"]),
    )
