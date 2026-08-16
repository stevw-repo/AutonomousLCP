"""Deterministic candidate rendering from an exact Legal Desk result."""

from hashlib import sha256
from typing import TYPE_CHECKING

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

if TYPE_CHECKING:
    from asklegal_legal_desks import RuleExecutionResult

from .model import AdmittedSemanticDecision, CandidateArtifact, ProcessingError


def render_candidate(
    result: RuleExecutionResult,
    semantic: AdmittedSemanticDecision | None = None,
) -> CandidateArtifact | None:
    """Render exact candidate bytes; uncertainty and non-candidates produce no text."""
    if result.processing_result != "SUCCEEDED" or result.disposition is None:
        return None
    if result.disposition.value != "CANDIDATE":
        return None
    if result.failure_code is not None:
        message = "FAILED_RESULT_CANNOT_RENDER"
        raise ProcessingError(message)
    semantic_ref = semantic.primary.output_fingerprint if semantic else None
    value = {
        "artifact_kind": "LEGAL_PROCESSING_CANDIDATE",
        "disposition": result.disposition.value,
        "evidence_refs": list(result.evidence_refs),
        "rule_result_id": result.result_id,
        "semantic_decision_ref": semantic_ref,
        "subject_id": result.subject_id,
    }
    raw = canonicalize(checked_json_value(value))
    fingerprint = f"sha256:{sha256(raw).hexdigest()}"
    return CandidateArtifact(
        result.candidate_artifact_refs[0],
        result.result_id,
        result.subject_id,
        result.disposition.value,
        result.evidence_refs,
        semantic_ref,
        raw,
        fingerprint,
    )
