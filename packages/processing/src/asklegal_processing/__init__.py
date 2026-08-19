"""Candidate processing and sole gated semantic-task boundary."""

from .model import (
    AdmittedSemanticDecision,
    CandidateArtifact,
    ProcessingError,
    SemanticDecision,
    SemanticTaskRequest,
)
from .remote import (
    AZURE_OPENAI_PROVIDER,
    AzureDeployment,
    AzureSemanticTaskRunner,
    BoundedModelTransport,
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
    "AZURE_OPENAI_PROVIDER",
    "PACKAGE_ROLE",
    "AdmittedSemanticDecision",
    "AzureDeployment",
    "AzureSemanticTaskRunner",
    "BoundedModelTransport",
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
