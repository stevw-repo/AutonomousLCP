"""Framework-free stable domain boundary."""

from .lifecycles import (
    COVERAGE_GAP_MACHINE,
    PIPELINE_RUN_MACHINE,
    QUARANTINE_MACHINE,
    SOURCE_CONTRACT_REVIEW_MACHINE,
    WORK_ITEM_MACHINE,
    CoverageGapState,
    DomainInvariantError,
    LifecycleEvent,
    LifecycleSnapshot,
    PipelineRunState,
    QuarantineState,
    SourceContractReviewState,
    StateMachine,
    TransitionResult,
    TransitionResultCode,
    WorkItemState,
)

PACKAGE_ROLE: str = "domain"

__all__ = [
    "COVERAGE_GAP_MACHINE",
    "PACKAGE_ROLE",
    "PIPELINE_RUN_MACHINE",
    "QUARANTINE_MACHINE",
    "SOURCE_CONTRACT_REVIEW_MACHINE",
    "WORK_ITEM_MACHINE",
    "CoverageGapState",
    "DomainInvariantError",
    "LifecycleEvent",
    "LifecycleSnapshot",
    "PipelineRunState",
    "QuarantineState",
    "SourceContractReviewState",
    "StateMachine",
    "TransitionResult",
    "TransitionResultCode",
    "WorkItemState",
]
