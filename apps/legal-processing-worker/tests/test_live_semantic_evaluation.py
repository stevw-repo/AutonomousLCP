"""Focused live semantic owner-receipt tests."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from typing import cast

import pytest
from _v1_semantic_profile_fixture import exact_semantic_profile_bytes
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_processing import (
    LiveSemanticEvaluationCase,
    LiveSemanticEvaluationError,
    SemanticDecision,
    SemanticProfileSet,
    SemanticTaskGate,
    SemanticTaskRequest,
    load_semantic_profile_set,
    parse_live_semantic_evaluation,
    run_live_semantic_evaluation,
    semantic_effect_receipt_id,
)

_INPUT = "sha256:" + "1" * 64
_PACKAGE = "sha256:" + "2" * 64
_PROPOSAL = "sha256:" + "3" * 64
_SERVING = "sha256:" + "4" * 64
_EVIDENCE = "primary/ref@sha256:" + "5" * 64
_SUITE = "sha256:" + "6" * 64
_SUITE_CASE = "sha256:" + "7" * 64


class _Reader:
    def __init__(self, raw: bytes) -> None:
        self.reference = ImmutableReference(
            ReferenceType.WORKFLOW_PROFILE,
            "wap_" + "1" * 48,
            "sha256:" + sha256(raw).hexdigest(),
        )
        self.raw = raw

    def read_exact(self, reference: ImmutableReference) -> bytes:
        assert reference == self.reference
        return self.raw


def _profiles() -> SemanticProfileSet:
    document = cast("dict[str, object]", json.loads(exact_semantic_profile_bytes()))
    profiles = cast("list[object]", document["profiles"])
    challenge = next(
        cast("dict[str, object]", item)
        for item in profiles
        if cast("dict[str, object]", item)["task"] == "GAZETTE_EVENT_CHALLENGE"
    )
    challenge["prompt_fingerprint"] = "sha256:" + "f" * 64
    document.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(document))).hexdigest()
    )
    raw = canonicalize(checked_json_value(document))
    return load_semantic_profile_set(_Reader(raw))


class _Runner:
    def invoke(self, profile: object, request: SemanticTaskRequest) -> SemanticDecision:
        del profile
        challenge = "PASS" if request.phase == "CHALLENGE" else "NOT_APPLICABLE"
        value = {
            "challenge_code": challenge,
            "decision_code": "AMENDMENT",
            "phase": request.phase,
            "request_id": request.request_id,
            "supporting_evidence_refs": [_EVIDENCE],
            "task": request.task,
            "unresolved_facts": [],
        }
        output_fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(value))).hexdigest()
        provider_request_id = "azure-" + request.request_id
        return SemanticDecision(
            request.request_id,
            request.task,
            request.phase,
            "AMENDMENT",
            (_EVIDENCE,),
            (),
            cast("object", challenge),  # pyright: ignore[reportArgumentType]
            output_fingerprint,
            "AZURE_OPENAI",
            provider_request_id,
            semantic_effect_receipt_id(request.request_id, provider_request_id, output_fingerprint),
        )


def _case() -> tuple[SemanticProfileSet, LiveSemanticEvaluationCase]:
    profile_set = _profiles()
    primary = next(item for item in profile_set.profiles if item.task == "GAZETTE_EVENT_ANALYSIS")
    challenge = next(
        item for item in profile_set.profiles if item.task == "GAZETTE_EVENT_CHALLENGE"
    )
    request = SemanticTaskRequest(
        "semantic-eval-primary",
        primary.task,
        "DECISION",
        primary.profile_id,
        _PACKAGE,
        "gazette-event-eval",
        (_EVIDENCE,),
        b"retained evaluator evidence",
        _INPUT,
    )
    challenge_request = replace(
        request,
        request_id="semantic-eval-challenge",
        task=challenge.task,
        phase="CHALLENGE",
        profile_id=challenge.profile_id,
    )
    return profile_set, LiveSemanticEvaluationCase(
        "gazette-amendment-en", (request, challenge_request), "AMENDMENT", _SUITE_CASE
    )


def test_actual_semantic_gate_outputs_issue_two_distinct_passed_receipts() -> None:
    """Two configured gate executions retain distinct passed owner receipts."""
    profile_set, case = _case()
    first = run_live_semantic_evaluation(
        run_id="semantic-run-1",
        observation_cutoff="2026-09-08T12:00:00+08:00",
        proposal_fingerprint=_PROPOSAL,
        serving_profile_fingerprint=_SERVING,
        suite_fingerprint=_SUITE,
        profile_set=profile_set,
        cases=(case,),
        gate=SemanticTaskGate(_Runner()),
        environment="LOCAL_SYNTHETIC",
        now="2026-09-08T00:00:00Z",
    )
    second = run_live_semantic_evaluation(
        run_id="semantic-run-2",
        observation_cutoff="2026-09-08T12:00:00+08:00",
        proposal_fingerprint=_PROPOSAL,
        serving_profile_fingerprint=_SERVING,
        suite_fingerprint=_SUITE,
        profile_set=profile_set,
        cases=(case,),
        gate=SemanticTaskGate(_Runner()),
        environment="LOCAL_SYNTHETIC",
        now="2026-09-08T00:00:00Z",
    )
    assert parse_live_semantic_evaluation(first).result == "PASSED"
    assert parse_live_semantic_evaluation(second).run_id == "semantic-run-2"
    assert first != second


def test_semantic_receipt_cannot_turn_failed_decision_into_passed() -> None:
    """Receipt parsing rejects a challenge result altered after execution."""
    profile_set, case = _case()
    raw = run_live_semantic_evaluation(
        run_id="semantic-run-1",
        observation_cutoff="2026-09-08T12:00:00+08:00",
        proposal_fingerprint=_PROPOSAL,
        serving_profile_fingerprint=_SERVING,
        suite_fingerprint=_SUITE,
        profile_set=profile_set,
        cases=(case,),
        gate=SemanticTaskGate(_Runner()),
        environment="LOCAL_SYNTHETIC",
        now="2026-09-08T00:00:00Z",
    )
    document = cast("dict[str, object]", json.loads(raw))
    first = cast("dict[str, object]", cast("list[object]", document["cases"])[0])
    cast("dict[str, object]", first["challenge"])["challenge_code"] = "FAIL"
    forged = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(LiveSemanticEvaluationError):
        parse_live_semantic_evaluation(forged)
