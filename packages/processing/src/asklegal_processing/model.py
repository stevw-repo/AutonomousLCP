"""Immutable M5 processing and bounded semantic-task values."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal


class ProcessingError(RuntimeError):
    """A fail-closed processing or semantic admission failure."""


@dataclass(frozen=True, slots=True)
class SemanticTaskRequest:
    """One evidence-bound bounded task request with no tools or credentials."""

    request_id: str
    task: str
    phase: Literal["DECISION", "CHALLENGE"]
    profile_id: str
    package_fingerprint: str
    subject_id: str
    evidence_refs: tuple[str, ...]
    evidence_bytes: bytes
    input_fingerprint: str


@dataclass(frozen=True, slots=True)
class SemanticDecision:
    """Strict provider output for only the fields named by the task contract."""

    request_id: str
    task: str
    phase: Literal["DECISION", "CHALLENGE"]
    decision_code: str
    supporting_evidence_refs: tuple[str, ...]
    unresolved_facts: tuple[str, ...]
    challenge_code: Literal["NOT_APPLICABLE", "PASS", "FAIL"]
    output_fingerprint: str
    provider: str = "UNREPORTED"
    provider_request_id: str = "unreported"
    effect_receipt_id: str = "unreported"


def semantic_effect_receipt_id(
    request_id: str, provider_request_id: str, output_fingerprint: str
) -> str:
    """Derive one safe owner receipt from an actual provider response identity."""
    material = f"{request_id}\x1f{provider_request_id}\x1f{output_fingerprint}".encode()
    return "mec_" + sha256(material).hexdigest()[:48]


@dataclass(frozen=True, slots=True)
class AdmittedSemanticDecision:
    """Primary bounded judgment that survived independent challenge and validators."""

    primary_profile_id: str
    challenge_profile_id: str
    primary: SemanticDecision
    challenge: SemanticDecision
    admitted_fields: tuple[tuple[str, str], ...]
    immutable: Literal[True] = True


@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    """Deterministically rendered candidate; never a Search Record or Approval."""

    artifact_id: str
    rule_result_id: str
    subject_id: str
    disposition: str
    evidence_refs: tuple[str, ...]
    semantic_decision_ref: str | None
    canonical_bytes: bytes
    fingerprint: str
