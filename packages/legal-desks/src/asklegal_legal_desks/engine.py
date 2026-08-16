"""Deterministic lifecycle and rule execution for validated packages."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from threading import RLock

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .model import (
    ActivationRecord,
    LoadedRulebook,
    PredicateOperator,
    ProcessingSubject,
    ReadinessState,
    RulebookError,
    RulebookErrorCode,
    RuleDefinition,
    RuleExecutionResult,
    RuleTraceEntry,
)


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "\x1f".join(parts).encode()
    return f"{prefix}_{sha256(raw).hexdigest()[:48]}"


@dataclass(frozen=True, slots=True)
class ActiveRulebook:
    """One exact activation bound to its validated package."""

    package: LoadedRulebook
    activation: ActivationRecord


class RulebookLifecycle:
    """Thread-safe local register fake for activation, suspension, and supersession."""

    def __init__(self) -> None:
        """Create an empty exact-activation projection."""
        self._lock = RLock()
        self._active: dict[tuple[str, str, str], ActiveRulebook] = {}
        self._state: dict[tuple[str, str], ReadinessState] = {}

    def activate(
        self,
        package: LoadedRulebook,
        activation: ActivationRecord,
        *,
        current_contract_set_fingerprint: str,
        current_engine_build: str,
    ) -> ActiveRulebook:
        """Admit only an exact attested package and exact allowed scopes."""
        manifest = package.manifest
        if (
            activation.package_id != manifest.package_id
            or activation.package_fingerprint != manifest.package_fingerprint
            or activation.environment != manifest.environment
            or activation.engine_build != current_engine_build
            or activation.contract_set_fingerprint != current_contract_set_fingerprint
            or activation.owner_attestation_id not in package.attestation_ids
            or set(activation.semantic_profile_ids)
            != {profile.profile_id for profile in package.semantic_profiles}
        ):
            raise RulebookError(RulebookErrorCode.STALE_ACTIVATION)
        scopes = {scope.scope_id: scope for scope in package.scopes}
        if not activation.allowed_scope_ids or not set(activation.allowed_scope_ids).issubset(
            scopes
        ):
            raise RulebookError(RulebookErrorCode.STALE_ACTIVATION, "scope set")
        for scope_id in activation.allowed_scope_ids:
            if scopes[scope_id].readiness is not ReadinessState.ATTESTED_INACTIVE:
                raise RulebookError(RulebookErrorCode.PACKAGE_NOT_ACTIVE, scope_id)
        key = (manifest.environment, manifest.jurisdiction, manifest.material_family)
        active = ActiveRulebook(package, activation)
        with self._lock:
            existing = self._active.get(key)
            if existing is not None and existing != active:
                raise RulebookError(RulebookErrorCode.STALE_ACTIVATION, "another version active")
            self._active[key] = active
            for scope_id in activation.allowed_scope_ids:
                self._state[(manifest.package_fingerprint, scope_id)] = ReadinessState.ACTIVE
        return active

    def suspend(self, package_fingerprint: str, scope_id: str) -> None:
        """Suspend new work for one exact affected scope."""
        key = (package_fingerprint, scope_id)
        with self._lock:
            if self._state.get(key) is not ReadinessState.ACTIVE:
                raise RulebookError(RulebookErrorCode.PACKAGE_NOT_ACTIVE, scope_id)
            self._state[key] = ReadinessState.SUSPENDED

    def require_active(self, package_fingerprint: str, scope_id: str) -> None:
        """Fail unless one exact scope is currently active."""
        with self._lock:
            if self._state.get((package_fingerprint, scope_id)) is not ReadinessState.ACTIVE:
                raise RulebookError(RulebookErrorCode.PACKAGE_NOT_ACTIVE, scope_id)


class RuleEngine:
    """Execute closed exact package rules without jurisdiction fallbacks."""

    def __init__(self, lifecycle: RulebookLifecycle) -> None:
        """Bind execution to one authoritative lifecycle projection."""
        self._lifecycle = lifecycle

    @staticmethod
    def _predicate(
        facts: dict[str, str],
        fact: str,
        operator: PredicateOperator,
        value: str | None,
    ) -> bool:
        if operator is PredicateOperator.ABSENT:
            return fact not in facts
        if operator is PredicateOperator.PRESENT:
            return fact in facts
        return facts.get(fact) == value

    def execute(self, package: LoadedRulebook, subject: ProcessingSubject) -> RuleExecutionResult:
        """Emit one terminal decision or an explicit totality/ambiguity block."""
        self._lifecycle.require_active(package.manifest.package_fingerprint, subject.scope_id)
        if (
            len(subject.evidence_refs) != len(set(subject.evidence_refs))
            or not subject.evidence_refs
        ):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "evidence refs")
        facts = dict(subject.facts)
        if len(facts) != len(subject.facts):
            raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, "duplicate facts")
        traces: list[RuleTraceEntry] = []
        matches: list[RuleDefinition] = []
        for rule in package.rules:
            if rule.scope_id != subject.scope_id:
                continue
            predicate_results = tuple(
                self._predicate(facts, item.fact, item.operator, item.value)
                for item in rule.predicates
            )
            evidence_ok = set(rule.evidence_roles).issubset(subject.evidence_roles)
            matched = all(predicate_results) and evidence_ok
            traces.append(RuleTraceEntry(rule.rule_id, matched, predicate_results))
            if matched:
                matches.append(rule)
        if len(matches) != 1:
            code = RulebookErrorCode.NON_TOTAL if not matches else RulebookErrorCode.AMBIGUOUS
            return RuleExecutionResult(
                _stable_id("rul", package.manifest.package_fingerprint, subject.input_fingerprint),
                package.manifest.package_id,
                package.manifest.package_version,
                package.manifest.package_fingerprint,
                "",
                subject.subject_id,
                subject.evidence_refs,
                subject.prior_state,
                tuple(traces),
                "BLOCKED",
                None,
                code.value,
                code.value,
                "BLOCK_SCOPE",
                "OPEN_LEGAL_DESK_REVIEW",
                (),
                "STOP",
            )
        rule = matches[0]
        result_id = _stable_id(
            "rul",
            package.manifest.package_fingerprint,
            subject.input_fingerprint,
            rule.rule_id,
        )
        artifact_refs = (
            (_stable_id("car", result_id, rule.disposition.value),)
            if rule.disposition.value == "CANDIDATE"
            else ()
        )
        return RuleExecutionResult(
            result_id,
            package.manifest.package_id,
            package.manifest.package_version,
            package.manifest.package_fingerprint,
            rule.rule_id,
            subject.subject_id,
            subject.evidence_refs,
            subject.prior_state,
            tuple(traces),
            "SUCCEEDED",
            rule.disposition,
            rule.reason_code,
            rule.failure_code,
            "ACCOUNTED",
            "OPEN_REVIEW" if rule.disposition.value in {"QUARANTINE", "REVIEW"} else "NONE",
            artifact_refs,
            rule.next_action,
        )

    @staticmethod
    def canonical_result(result: RuleExecutionResult) -> bytes:
        """Render byte-identical authority-neutral result bytes."""
        value = {
            "candidate_artifact_refs": list(result.candidate_artifact_refs),
            "coverage_effect": result.coverage_effect,
            "disposition": result.disposition.value if result.disposition else None,
            "evidence_refs": list(result.evidence_refs),
            "failure_code": result.failure_code,
            "immutable": result.immutable,
            "next_action": result.next_action,
            "package_fingerprint": result.package_fingerprint,
            "package_id": result.package_id,
            "package_version": result.package_version,
            "prior_state": result.prior_state,
            "processing_result": result.processing_result,
            "reason_code": result.reason_code,
            "result_id": result.result_id,
            "review_effect": result.review_effect,
            "rule_id": result.rule_id,
            "subject_id": result.subject_id,
            "trace": [
                {
                    "matched": entry.matched,
                    "predicate_results": list(entry.predicate_results),
                    "rule_id": entry.rule_id,
                }
                for entry in result.trace
            ],
        }
        return canonicalize(checked_json_value(value))
