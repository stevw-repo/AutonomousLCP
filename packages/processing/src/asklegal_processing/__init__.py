"""Candidate processing and sole gated semantic-task boundary."""

from .model import (
    AdmittedSemanticDecision,
    CandidateArtifact,
    ProcessingError,
    SemanticDecision,
    SemanticTaskRequest,
)
from .render import render_candidate
from .semantic import (
    DeterministicSemanticTaskRunner,
    DisabledSemanticTaskRunner,
    SemanticTaskGate,
    SemanticTaskRunner,
)

PACKAGE_ROLE: str = "processing"

__all__ = [
    "PACKAGE_ROLE",
    "AdmittedSemanticDecision",
    "CandidateArtifact",
    "DeterministicSemanticTaskRunner",
    "DisabledSemanticTaskRunner",
    "ProcessingError",
    "SemanticDecision",
    "SemanticTaskGate",
    "SemanticTaskRequest",
    "SemanticTaskRunner",
    "render_candidate",
]
