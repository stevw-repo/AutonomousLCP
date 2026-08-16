"""Closed immutable values for executable Source Rulebook Packages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class RulebookErrorCode(StrEnum):
    """Fail-closed package and execution failures."""

    AMBIGUOUS = "RULEBOOK_AMBIGUOUS"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    ENVIRONMENT_MISUSE = "ENVIRONMENT_MISUSE"
    EVALUATION_LEAKAGE = "EVALUATION_LEAKAGE"
    EXPIRED_PROFILE = "EXPIRED_PROFILE"
    FINGERPRINT_DRIFT = "FINGERPRINT_DRIFT"
    INCOMPLETE_SOURCE_INVENTORY = "INCOMPLETE_SOURCE_INVENTORY"
    INVENTORY_MISMATCH = "INVENTORY_MISMATCH"
    NON_TOTAL = "RULEBOOK_NON_TOTAL"
    OVERLAPPING_SCOPES = "OVERLAPPING_SCOPES"
    PACKAGE_NOT_ACTIVE = "PACKAGE_NOT_ACTIVE"
    PATH_INVALID = "PATH_INVALID"
    STALE_ACTIVATION = "STALE_ACTIVATION"
    UNKNOWN_CODE = "UNKNOWN_CODE"


class RulebookError(RuntimeError):
    """One exact package failure with no permissive fallback."""

    def __init__(self, code: RulebookErrorCode, detail: str = "") -> None:
        """Retain a stable code and non-authoritative diagnostic detail."""
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail


class ReadinessState(StrEnum):
    """Closed Release Scope lifecycle."""

    ACTIVE = "ACTIVE"
    ATTESTED_INACTIVE = "ATTESTED_INACTIVE"
    DECISION_READY = "DECISION_READY"
    NOT_READY = "NOT_READY"
    SUPERSEDED = "SUPERSEDED"
    SUSPENDED = "SUSPENDED"


class LegalDisposition(StrEnum):
    """Cross-cutting processing consequences; legal meaning stays in the package."""

    CANDIDATE = "CANDIDATE"
    NO_CHANGE = "NO_CHANGE"
    QUARANTINE = "QUARANTINE"
    REVIEW = "REVIEW"
    WITHHOLD = "WITHHOLD"


class PredicateOperator(StrEnum):
    """Closed deterministic predicate language understood by the engine."""

    ABSENT = "ABSENT"
    EQUALS = "EQUALS"
    PRESENT = "PRESENT"


class GenerativeTask(StrEnum):
    """Closed semantic stages allocated by accepted design decisions."""

    HK_CASE_PROPOSITION_ANALYSIS = "HK_CASE_PROPOSITION_ANALYSIS"
    HK_CASE_PROPOSITION_CHALLENGE = "HK_CASE_PROPOSITION_CHALLENGE"
    HK_LATER_TREATMENT_DISCOVERY = "HK_LATER_TREATMENT_DISCOVERY"
    HK_LATER_TREATMENT_CANDIDATE_ANALYSIS = "HK_LATER_TREATMENT_CANDIDATE_ANALYSIS"
    HK_REGULATORY_UPDATE_ANALYSIS = "HK_REGULATORY_UPDATE_ANALYSIS"
    HK_REGULATORY_UPDATE_CHALLENGE = "HK_REGULATORY_UPDATE_CHALLENGE"
    HK_REGULATORY_RECORD_ANALYSIS = "HK_REGULATORY_RECORD_ANALYSIS"
    HK_REGULATORY_RECORD_CHALLENGE = "HK_REGULATORY_RECORD_CHALLENGE"
    GAZETTE_EVENT_ANALYSIS = "GAZETTE_EVENT_ANALYSIS"
    GAZETTE_EVENT_CHALLENGE = "GAZETTE_EVENT_CHALLENGE"
    RECONSTRUCTION_PLAN_DECISION = "RECONSTRUCTION_PLAN_DECISION"
    RECONSTRUCTION_PLAN_CHALLENGE = "RECONSTRUCTION_PLAN_CHALLENGE"


SEMANTIC_TASK_PAIRS: frozenset[tuple[GenerativeTask, GenerativeTask]] = frozenset(
    {
        (GenerativeTask.HK_CASE_PROPOSITION_ANALYSIS, GenerativeTask.HK_CASE_PROPOSITION_CHALLENGE),
        (
            GenerativeTask.HK_LATER_TREATMENT_DISCOVERY,
            GenerativeTask.HK_LATER_TREATMENT_CANDIDATE_ANALYSIS,
        ),
        (
            GenerativeTask.HK_REGULATORY_UPDATE_ANALYSIS,
            GenerativeTask.HK_REGULATORY_UPDATE_CHALLENGE,
        ),
        (
            GenerativeTask.HK_REGULATORY_RECORD_ANALYSIS,
            GenerativeTask.HK_REGULATORY_RECORD_CHALLENGE,
        ),
        (GenerativeTask.GAZETTE_EVENT_ANALYSIS, GenerativeTask.GAZETTE_EVENT_CHALLENGE),
        (GenerativeTask.RECONSTRUCTION_PLAN_DECISION, GenerativeTask.RECONSTRUCTION_PLAN_CHALLENGE),
    }
)


@dataclass(frozen=True, slots=True)
class PackageFile:
    """One exact declared non-manifest package member."""

    path: str
    role: str
    byte_size: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """One complete source-universe entry."""

    source_id: str
    role: str
    endpoint_families: tuple[str, ...]
    checking_tier: str
    permitted_use: str
    completeness_rule: str
    outage_consequence: str


@dataclass(frozen=True, slots=True)
class ReleaseScope:
    """One stable, non-overlapping ownership boundary."""

    scope_id: str
    ownership_keys: tuple[str, ...]
    required_source_ids: tuple[str, ...]
    zero_record_rule: str
    withholding_rule: str
    readiness: ReadinessState
    blocker_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RulePredicate:
    """One closed exact fact predicate."""

    fact: str
    operator: PredicateOperator
    value: str | None


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    """One terminal package-authored legal rule."""

    rule_id: str
    scope_id: str
    predicates: tuple[RulePredicate, ...]
    evidence_roles: tuple[str, ...]
    disposition: LegalDisposition
    reason_code: str
    failure_code: str | None
    next_action: str


@dataclass(frozen=True, slots=True)
class SemanticTaskProfile:
    """One exact admitted stateless semantic-task execution profile."""

    profile_id: str
    task: str
    provider: str
    resource_class: str
    geography_class: str
    deployment_name: str
    model_id: str
    model_version: str
    api_contract: str
    tokenizer: str
    prompt_fingerprint: str
    input_schema: str
    output_schema: str
    evidence_budget_bytes: int
    max_output_tokens: int
    content_filter_policy: str
    retry_policy: str
    data_handling_profile: str
    evaluator_id: str
    threshold_basis_points: int
    expires_at: str
    stateful_features: bool
    allowed_environments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RulebookManifest:
    """Validated canonical package root."""

    package_id: str
    package_version: str
    package_fingerprint: str
    jurisdiction: str
    environment: str
    material_family: str
    legal_desk_owner: str
    effective_cutoff: str
    predecessor: str | None
    contract_locks: tuple[str, ...]
    code_locks: tuple[str, ...]
    source_universe_fingerprint: str
    scope_readiness: tuple[tuple[str, ReadinessState], ...]
    unresolved_policy_codes: tuple[str, ...]
    impact_declaration: str
    minimum_engine_version: str
    files: tuple[PackageFile, ...]


@dataclass(frozen=True, slots=True)
class LoadedRulebook:
    """One fully validated immutable executable package."""

    manifest: RulebookManifest
    sources: tuple[SourceDefinition, ...]
    scopes: tuple[ReleaseScope, ...]
    rules: tuple[RuleDefinition, ...]
    semantic_profiles: tuple[SemanticTaskProfile, ...]
    fixture_ids: tuple[str, ...]
    evaluation_ids: tuple[str, ...]
    attestation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActivationRecord:
    """One register lifecycle event admitting exact package bytes."""

    activation_id: str
    package_id: str
    package_fingerprint: str
    engine_build: str
    contract_set_fingerprint: str
    deterministic_suite_fingerprint: str
    semantic_profile_ids: tuple[str, ...]
    owner_attestation_id: str
    allowed_scope_ids: tuple[str, ...]
    environment: str
    activated_at: str


@dataclass(frozen=True, slots=True)
class ProcessingSubject:
    """Evidence-bound facts admitted for one rule execution."""

    subject_id: str
    scope_id: str
    observation_id: str
    source_snapshot_id: str
    evidence_refs: tuple[str, ...]
    evidence_roles: tuple[str, ...]
    prior_state: str
    facts: tuple[tuple[str, str], ...]
    input_fingerprint: str


@dataclass(frozen=True, slots=True)
class RuleTraceEntry:
    """One evaluated terminal rule and its exact result."""

    rule_id: str
    matched: bool
    predicate_results: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class RuleExecutionResult:
    """Immutable complete result of executing one active package."""

    result_id: str
    package_id: str
    package_version: str
    package_fingerprint: str
    rule_id: str
    subject_id: str
    evidence_refs: tuple[str, ...]
    prior_state: str
    trace: tuple[RuleTraceEntry, ...]
    processing_result: Literal["SUCCEEDED", "BLOCKED"]
    disposition: LegalDisposition | None
    reason_code: str
    failure_code: str | None
    coverage_effect: str
    review_effect: str
    candidate_artifact_refs: tuple[str, ...]
    next_action: str
    immutable: Literal[True] = True
