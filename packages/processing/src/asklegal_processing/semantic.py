"""Sole gated stateless generative-task runner boundary."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, Never, Protocol

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

if TYPE_CHECKING:
    from asklegal_legal_desks import SemanticTaskProfile

from asklegal_legal_desks import SEMANTIC_TASK_PAIRS, GenerativeTask

from .model import (
    AdmittedSemanticDecision,
    ProcessingError,
    SemanticDecision,
    SemanticTaskRequest,
)


class SemanticTaskRunner(Protocol):
    """Provider-neutral stateless execution boundary."""

    def invoke(
        self,
        profile: SemanticTaskProfile,
        request: SemanticTaskRequest,
    ) -> SemanticDecision:
        """Return one strict bounded decision without tools or stored state."""
        ...


def _fail(code: str) -> Never:
    raise ProcessingError(code)


def _challenge_code(value: str) -> Literal["NOT_APPLICABLE", "PASS", "FAIL"]:
    if value == "NOT_APPLICABLE":
        return "NOT_APPLICABLE"
    if value == "PASS":
        return "PASS"
    if value == "FAIL":
        return "FAIL"
    _fail("UNKNOWN_CHALLENGE_CODE")


class DisabledSemanticTaskRunner:
    """Fail-closed default when no exact workflow is admitted."""

    def invoke(
        self,
        profile: SemanticTaskProfile,
        request: SemanticTaskRequest,
    ) -> SemanticDecision:
        """Reject every attempted provider effect."""
        del profile, request
        _fail("SEMANTIC_CAPABILITY_DISABLED")


class DeterministicSemanticTaskRunner:
    """Local-only exact fake keyed by task, phase, and input fingerprint."""

    def __init__(
        self,
        outputs: Mapping[tuple[str, str, str], tuple[str, tuple[str, ...], tuple[str, ...], str]],
    ) -> None:
        """Freeze exact outputs; there is no network, model, tool, or hidden state."""
        self._outputs = dict(outputs)
        self.invocations: list[str] = []

    def invoke(
        self,
        profile: SemanticTaskProfile,
        request: SemanticTaskRequest,
    ) -> SemanticDecision:
        """Return only a predeclared deterministic fixture result."""
        if (
            profile.provider != "LOCAL_FAKE"
            or "LOCAL_SYNTHETIC" not in profile.allowed_environments
        ):
            _fail("LOCAL_FAKE_ENVIRONMENT_MISUSE")
        key = (request.task, request.phase, request.input_fingerprint)
        try:
            decision_code, refs, unresolved, challenge = self._outputs[key]
        except KeyError as error:
            message = "NO_EXACT_SYNTHETIC_OUTPUT"
            raise ProcessingError(message) from error
        value = {
            "challenge_code": challenge,
            "decision_code": decision_code,
            "phase": request.phase,
            "request_id": request.request_id,
            "supporting_evidence_refs": list(refs),
            "task": request.task,
            "unresolved_facts": list(unresolved),
        }
        output_fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"
        self.invocations.append(request.request_id)
        return SemanticDecision(
            request.request_id,
            request.task,
            request.phase,
            decision_code,
            refs,
            unresolved,
            _challenge_code(challenge),
            output_fingerprint,
        )


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        message = "PROFILE_EXPIRY_INVALID"
        raise ProcessingError(message) from error
    if parsed.tzinfo is None:
        _fail("PROFILE_EXPIRY_INVALID")
    return parsed.astimezone(UTC)


class SemanticTaskGate:
    """Validate, invoke, challenge, and reconcile one exact semantic workflow."""

    def __init__(self, runner: SemanticTaskRunner) -> None:
        """Bind the sole runner implementation."""
        self._runner = runner

    def decide(
        self,
        profiles: tuple[SemanticTaskProfile, SemanticTaskProfile],
        requests: tuple[SemanticTaskRequest, SemanticTaskRequest],
        *,
        environment: str,
        now: str,
    ) -> AdmittedSemanticDecision:
        """Admit a bounded result only after independent challenge and deterministic checks."""
        primary_profile, challenge_profile = profiles
        primary_request, challenge_request = requests
        if (
            primary_profile.profile_id != primary_request.profile_id
            or primary_profile.task != primary_request.task
            or challenge_profile.profile_id != challenge_request.profile_id
            or challenge_profile.task != challenge_request.task
        ):
            _fail("PROFILE_REQUEST_MISMATCH")
        if (
            environment not in primary_profile.allowed_environments
            or environment not in challenge_profile.allowed_environments
        ):
            _fail("PROFILE_ENVIRONMENT_MISMATCH")
        if _parse_utc(primary_profile.expires_at) <= _parse_utc(now) or _parse_utc(
            challenge_profile.expires_at
        ) <= _parse_utc(now):
            _fail("PROFILE_EXPIRED")
        if primary_profile.stateful_features or challenge_profile.stateful_features:
            _fail("STATEFUL_PROVIDER_FEATURE_FORBIDDEN")
        if (
            len(primary_request.evidence_bytes) > primary_profile.evidence_budget_bytes
            or len(challenge_request.evidence_bytes) > challenge_profile.evidence_budget_bytes
        ):
            _fail("EVIDENCE_BUDGET_EXCEEDED")
        try:
            task_pair = (
                GenerativeTask(primary_request.task),
                GenerativeTask(challenge_request.task),
            )
        except ValueError:
            _fail("UNKNOWN_GENERATIVE_TASK")
        if (
            primary_request.request_id == challenge_request.request_id
            or primary_profile.profile_id == challenge_profile.profile_id
            or primary_profile.prompt_fingerprint == challenge_profile.prompt_fingerprint
            or challenge_request.phase != "CHALLENGE"
            or primary_request.phase != "DECISION"
            or task_pair not in SEMANTIC_TASK_PAIRS
            or challenge_request.package_fingerprint != primary_request.package_fingerprint
            or challenge_request.subject_id != primary_request.subject_id
            or challenge_request.evidence_refs != primary_request.evidence_refs
            or challenge_request.evidence_bytes != primary_request.evidence_bytes
            or challenge_request.input_fingerprint != primary_request.input_fingerprint
        ):
            _fail("CHALLENGE_BINDING_MISMATCH")
        primary = self._runner.invoke(primary_profile, primary_request)
        challenge = self._runner.invoke(challenge_profile, challenge_request)
        allowed_refs = set(primary_request.evidence_refs)
        if (
            primary.request_id != primary_request.request_id
            or primary.task != primary_request.task
            or primary.phase != "DECISION"
            or not set(primary.supporting_evidence_refs).issubset(allowed_refs)
            or primary.unresolved_facts
            or challenge.request_id != challenge_request.request_id
            or challenge.task != challenge_request.task
            or challenge.phase != "CHALLENGE"
            or not set(challenge.supporting_evidence_refs).issubset(allowed_refs)
            or challenge.challenge_code != "PASS"
            or challenge.decision_code != primary.decision_code
        ):
            _fail("SEMANTIC_DECISION_REJECTED")
        return AdmittedSemanticDecision(
            primary_profile.profile_id,
            challenge_profile.profile_id,
            primary,
            challenge,
            (("semantic.decision_code", primary.decision_code),),
        )
