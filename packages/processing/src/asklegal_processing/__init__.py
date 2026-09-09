"""Candidate processing and sole gated semantic-task boundary."""

from .live_evaluation import (
    LiveSemanticEvaluationCase,
    LiveSemanticEvaluationError,
    LiveSemanticEvaluationReceipt,
    parse_live_semantic_evaluation,
    run_live_semantic_evaluation,
    semantic_evaluation_request_id,
)
from .model import (
    AdmittedSemanticDecision,
    CandidateArtifact,
    ProcessingError,
    SemanticDecision,
    SemanticTaskRequest,
    semantic_effect_receipt_id,
)
from .profiles import (
    ProfileError,
    ProfileReader,
    ProviderRetryProfile,
    SemanticBudgetProfile,
    SemanticProfileSet,
    TokenizerSpecification,
    load_semantic_profile_set,
    validate_semantic_profile_set_authority,
)
from .remote import (
    AZURE_OPENAI_PROVIDER,
    AzureDeployment,
    AzureSemanticTaskRunner,
    BoundedModelTransport,
    ModelCall,
    semantic_prompt_fingerprint,
    semantic_provider_input_text,
    validate_semantic_task_contract,
)
from .render import render_candidate
from .semantic import (
    DeterministicSemanticTaskRunner,
    DisabledSemanticTaskRunner,
    SemanticTaskGate,
    SemanticTaskRunner,
)
from .tokenization import (
    ExactTokenCounter,
    ExactTokenizerResourceCounter,
    ProviderBudgetDecision,
    ProviderBudgetRequest,
    TokenCounter,
    preflight_provider_budget,
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
    "ExactTokenCounter",
    "ExactTokenizerResourceCounter",
    "LiveSemanticEvaluationCase",
    "LiveSemanticEvaluationError",
    "LiveSemanticEvaluationReceipt",
    "ModelCall",
    "ProcessingError",
    "ProfileError",
    "ProfileReader",
    "ProviderBudgetDecision",
    "ProviderBudgetRequest",
    "ProviderRetryProfile",
    "SemanticBudgetProfile",
    "SemanticDecision",
    "SemanticProfileSet",
    "SemanticTaskGate",
    "SemanticTaskRequest",
    "SemanticTaskRunner",
    "TokenCounter",
    "TokenizerSpecification",
    "load_semantic_profile_set",
    "parse_live_semantic_evaluation",
    "preflight_provider_budget",
    "render_candidate",
    "run_live_semantic_evaluation",
    "semantic_effect_receipt_id",
    "semantic_evaluation_request_id",
    "semantic_prompt_fingerprint",
    "semantic_provider_input_text",
    "validate_semantic_profile_set_authority",
    "validate_semantic_task_contract",
]
