"""Offline tests for the real Azure OpenAI semantic task runner.

The transport is stubbed so the suite never leaves the machine. What matters here
is strictness: a legal component that repairs a malformed model reply into a
plausible judgment is worse than one that refuses, so every deviation fails closed.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from asklegal_legal_desks import SemanticTaskProfile
from asklegal_processing.model import ProcessingError, SemanticTaskRequest
from asklegal_processing.remote import AzureDeployment, AzureSemanticTaskRunner

_EVIDENCE_REFS = ("ev_1", "ev_2")


class StubTransport:
    """Returns one queued chat-completions body."""

    def __init__(self, content: object) -> None:
        """Queue the assistant content this transport will return."""
        self._content = content
        self.calls = 0

    def post_json(self, url: str, headers: dict[str, str], body: object) -> dict[str, object]:
        """Return a chat-completions envelope wrapping the queued content."""
        del url, headers, body
        self.calls += 1
        content = self._content
        rendered = content if isinstance(content, str) else json.dumps(content)
        return {"choices": [{"message": {"content": rendered}}]}


def _deployment() -> AzureDeployment:
    return AzureDeployment("https://example.openai.azure.com", "chat-1", "2024-10-21", "k")


def _profile() -> SemanticTaskProfile:
    return SemanticTaskProfile(
        profile_id="stp_1",
        task="HK_LATER_TREATMENT",
        provider="AZURE_OPENAI",
        resource_class="HOSTED",
        geography_class="US",
        deployment_name="chat-1",
        model_id="gpt-5.4",
        model_version="1",
        api_contract="2024-10-21",
        tokenizer="o200k_base",
        prompt_fingerprint="sha256:" + "0" * 64,
        input_schema="v1",
        output_schema="v1",
        evidence_budget_bytes=24_000,
        max_output_tokens=1024,
        content_filter_policy="DEFAULT",
        retry_policy="NONE",
        data_handling_profile="NO_TRAINING",
        evaluator_id="eval_1",
        threshold_basis_points=9000,
        expires_at="2027-01-01T00:00:00Z",
        stateful_features=False,
        allowed_environments=("POC",),
    )


def _request() -> SemanticTaskRequest:
    return SemanticTaskRequest(
        request_id="req_1",
        task="HK_LATER_TREATMENT",
        phase="DECISION",
        profile_id="stp_1",
        package_fingerprint="sha256:" + "1" * 64,
        subject_id="subject_1",
        evidence_refs=_EVIDENCE_REFS,
        evidence_bytes=b"evidence",
        input_fingerprint="sha256:" + "2" * 64,
    )


def _wellformed() -> dict[str, object]:
    return {
        "decision_code": "MAINTAINED",
        "supporting_evidence_refs": ["ev_1"],
        "unresolved_facts": [],
        "challenge_code": "PASS",
    }


def test_runner_returns_one_strict_decision() -> None:
    """A well-formed reply becomes an exact decision with a stable fingerprint."""
    runner = AzureSemanticTaskRunner(_deployment(), StubTransport(_wellformed()))

    decision = runner.invoke(_profile(), _request())

    assert decision.decision_code == "MAINTAINED"
    assert decision.supporting_evidence_refs == ("ev_1",)
    assert decision.challenge_code == "PASS"
    assert decision.output_fingerprint.startswith("sha256:")
    assert decision.request_id == "req_1"


def test_runner_is_deterministic_for_the_same_reply() -> None:
    """The same decision content must fingerprint identically."""
    first = AzureSemanticTaskRunner(_deployment(), StubTransport(_wellformed()))
    second = AzureSemanticTaskRunner(_deployment(), StubTransport(_wellformed()))

    assert (
        first.invoke(_profile(), _request()).output_fingerprint
        == second.invoke(_profile(), _request()).output_fingerprint
    )


def test_runner_refuses_a_provider_it_does_not_serve() -> None:
    """Only an Azure-admitted profile may reach this deployment."""
    runner = AzureSemanticTaskRunner(_deployment(), StubTransport(_wellformed()))

    with pytest.raises(ProcessingError):
        runner.invoke(replace(_profile(), provider="LOCAL_FAKE"), _request())


def test_runner_refuses_a_deployment_the_credential_does_not_match() -> None:
    """A profile and credential that disagree would answer with the wrong model."""
    runner = AzureSemanticTaskRunner(_deployment(), StubTransport(_wellformed()))

    with pytest.raises(ProcessingError):
        runner.invoke(replace(_profile(), deployment_name="other"), _request())


def test_runner_refuses_output_that_is_not_json() -> None:
    """Prose instead of an object must fail rather than be salvaged."""
    runner = AzureSemanticTaskRunner(_deployment(), StubTransport("the answer is maintained"))

    with pytest.raises(ProcessingError):
        runner.invoke(_profile(), _request())


def test_runner_refuses_extra_fields() -> None:
    """An unexpected key means the model answered a different contract."""
    payload = {**_wellformed(), "confidence": 0.9}
    runner = AzureSemanticTaskRunner(_deployment(), StubTransport(payload))

    with pytest.raises(ProcessingError):
        runner.invoke(_profile(), _request())


def test_runner_refuses_a_missing_field() -> None:
    """A dropped key must not be defaulted into a decision."""
    payload = {k: v for k, v in _wellformed().items() if k != "challenge_code"}
    runner = AzureSemanticTaskRunner(_deployment(), StubTransport(payload))

    with pytest.raises(ProcessingError):
        runner.invoke(_profile(), _request())


def test_runner_refuses_an_unknown_challenge_code() -> None:
    """The challenge vocabulary is closed."""
    payload = {**_wellformed(), "challenge_code": "MAYBE"}
    runner = AzureSemanticTaskRunner(_deployment(), StubTransport(payload))

    with pytest.raises(ProcessingError):
        runner.invoke(_profile(), _request())


def test_runner_refuses_a_citation_that_was_never_supplied() -> None:
    """A reference the evidence never offered is a fabrication, not a judgment."""
    payload = {**_wellformed(), "supporting_evidence_refs": ["ev_invented"]}
    runner = AzureSemanticTaskRunner(_deployment(), StubTransport(payload))

    with pytest.raises(ProcessingError):
        runner.invoke(_profile(), _request())
