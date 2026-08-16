"""Executable jurisdiction/material policy without provider calls."""

from .engine import ActiveRulebook, RulebookLifecycle, RuleEngine
from .loader import ENGINE_VERSION, load_rulebook_package
from .model import (
    SEMANTIC_TASK_PAIRS,
    ActivationRecord,
    GenerativeTask,
    LegalDisposition,
    LoadedRulebook,
    PackageFile,
    PredicateOperator,
    ProcessingSubject,
    ReadinessState,
    ReleaseScope,
    RulebookError,
    RulebookErrorCode,
    RulebookManifest,
    RuleDefinition,
    RuleExecutionResult,
    RulePredicate,
    RuleTraceEntry,
    SemanticTaskProfile,
    SourceDefinition,
)

PACKAGE_ROLE: str = "legal-desks"

__all__ = [
    "ENGINE_VERSION",
    "PACKAGE_ROLE",
    "SEMANTIC_TASK_PAIRS",
    "ActivationRecord",
    "ActiveRulebook",
    "GenerativeTask",
    "LegalDisposition",
    "LoadedRulebook",
    "PackageFile",
    "PredicateOperator",
    "ProcessingSubject",
    "ReadinessState",
    "ReleaseScope",
    "RuleDefinition",
    "RuleEngine",
    "RuleExecutionResult",
    "RulePredicate",
    "RuleTraceEntry",
    "RulebookError",
    "RulebookErrorCode",
    "RulebookLifecycle",
    "RulebookManifest",
    "SemanticTaskProfile",
    "SourceDefinition",
    "load_rulebook_package",
]
