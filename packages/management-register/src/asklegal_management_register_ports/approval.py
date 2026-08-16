"""M6 human governance, review, and single-use Approval register boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from threading import RLock
from typing import Protocol


class ApprovalErrorCode(StrEnum):
    """Closed M6 governance and consumption failures."""

    APPROVAL_CONSUMED = "APPROVAL_CONSUMED"
    APPROVAL_INVALIDATED = "APPROVAL_INVALIDATED"
    APPROVAL_NOT_FOUND = "APPROVAL_NOT_FOUND"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_REVOKED = "APPROVAL_REVOKED"
    AUTHORITY_REMOVED = "AUTHORITY_REMOVED"
    MANIFEST_DRIFT = "MANIFEST_DRIFT"
    MANIFEST_INVALID = "MANIFEST_INVALID"
    REASON_REQUIRED = "REASON_REQUIRED"
    UNAUTHORIZED_PRINCIPAL = "UNAUTHORIZED_PRINCIPAL"


class ApprovalError(RuntimeError):
    """One exact Approval or governance failure."""

    def __init__(self, code: ApprovalErrorCode, detail: str = "") -> None:
        """Create one closed governance failure."""
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail


class ApprovalState(StrEnum):
    """Closed Approval lifecycle projection."""

    APPROVED = "APPROVAL_APPROVED"
    CONSUMED = "APPROVAL_CONSUMED"
    INVALIDATED = "APPROVAL_INVALIDATED"
    REJECTED = "APPROVAL_REJECTED"
    REVOKED = "APPROVAL_REVOKED"


@dataclass(frozen=True, slots=True)
class ReviewerPrincipal:
    """Verified named principal at the application boundary."""

    subject: str
    delegated_human: bool
    roles: frozenset[str]


@dataclass(frozen=True, slots=True)
class ManifestSnapshot:
    """Exact immutable Promotion Manifest validity projection."""

    manifest_id: str
    fingerprint: str
    expected_base_serving_state_id: str
    valid_from: str
    valid_until: str
    validity_predicates: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ReviewComment:
    """Human comment bound to one exact proposal section and fingerprint."""

    comment_id: str
    manifest_id: str
    manifest_fingerprint: str
    section: str
    author_subject: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Immutable all-or-nothing human decision."""

    approval_id: str
    manifest_id: str
    manifest_fingerprint: str
    decision: str
    reviewer_subject: str
    reason: str
    decision_time: str
    expected_base_serving_state_id: str
    authority_evidence_ref: str


@dataclass(frozen=True, slots=True)
class ApprovalLifecycleEvent:
    """Append-only Approval state change."""

    event_id: str
    approval_id: str
    from_state: ApprovalState
    to_state: ApprovalState
    event_type: str
    responsible_subject: str
    event_time: str
    reason: str
    execution_lineage_id: str


@dataclass(frozen=True, slots=True)
class ApprovalProjection:
    """Current state derived from immutable decision and events."""

    decision: ApprovalDecision
    state: ApprovalState
    execution_lineage_id: str


@dataclass(frozen=True, slots=True)
class ApprovalConsumption:
    """Current facts checked while consuming one exact Approval."""

    current_base_serving_state_id: str
    current_predicates: tuple[tuple[str, str], ...]
    at: str


@dataclass(frozen=True, slots=True)
class ApprovalTransition:
    """Exact append-only Approval state-transition facts."""

    state: ApprovalState
    event_type: str
    subject: str
    at: str
    reason: str
    lineage: str = ""


class ApprovalRegisterStore(Protocol):
    """Authoritative M6 Review and Approval boundary."""

    def decide(
        self,
        principal: ReviewerPrincipal,
        manifest: ManifestSnapshot,
        *,
        decision: str,
        reason: str,
        decision_time: str,
    ) -> ApprovalProjection:
        """Record one exact human decision."""
        ...

    def consume(
        self,
        approval_id: str,
        execution_lineage_id: str,
        manifest: ManifestSnapshot,
        context: ApprovalConsumption,
    ) -> ApprovalProjection:
        """Atomically consume one valid Approval into one lineage."""
        ...


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


class InMemoryApprovalRegister:
    """Thread-safe exact behavioral reference for M6 human governance."""

    def __init__(self, assignments: dict[str, frozenset[str]]) -> None:
        """Create a register with explicit current named-user assignments."""
        self._lock = RLock()
        self._assignments = dict(assignments)
        self._approvals: dict[str, ApprovalProjection] = {}
        self._manifest_approval: dict[str, str] = {}
        self._comments: list[ReviewComment] = []
        self._events: list[ApprovalLifecycleEvent] = []

    def set_roles(self, subject: str, roles: frozenset[str]) -> None:
        """Replace current governance assignments for one named subject."""
        with self._lock:
            self._assignments[subject] = roles

    def _authorize(self, principal: ReviewerPrincipal) -> None:
        if (
            not principal.delegated_human
            or "PipelineAdministrator" not in principal.roles
            or "PipelineAdministrator" not in self._assignments.get(principal.subject, frozenset())
        ):
            raise ApprovalError(ApprovalErrorCode.UNAUTHORIZED_PRINCIPAL)

    @staticmethod
    def _reason(reason: str) -> None:
        if type(reason) is not str or not reason.strip():
            raise ApprovalError(ApprovalErrorCode.REASON_REQUIRED)

    def comment(
        self,
        principal: ReviewerPrincipal,
        manifest: ManifestSnapshot,
        *,
        section: str,
        reason: str,
        recorded_at: str,
    ) -> ReviewComment:
        """Append a fingerprint-bound human comment."""
        self._authorize(principal)
        self._reason(reason)
        comment = ReviewComment(
            _stable_id(
                "art",
                manifest.manifest_id,
                manifest.fingerprint,
                section,
                principal.subject,
                reason,
                recorded_at,
            ),
            manifest.manifest_id,
            manifest.fingerprint,
            section,
            principal.subject,
            reason,
            recorded_at,
        )
        with self._lock:
            self._comments.append(comment)
        return comment

    def decide(
        self,
        principal: ReviewerPrincipal,
        manifest: ManifestSnapshot,
        *,
        decision: str,
        reason: str,
        decision_time: str,
    ) -> ApprovalProjection:
        """Record one immutable approved or rejected decision."""
        self._authorize(principal)
        self._reason(reason)
        if decision not in {"APPROVED", "REJECTED"}:
            raise ApprovalError(ApprovalErrorCode.MANIFEST_INVALID, "decision")
        approval_id = _stable_id("apr", manifest.manifest_id, manifest.fingerprint, decision)
        record = ApprovalDecision(
            approval_id,
            manifest.manifest_id,
            manifest.fingerprint,
            decision,
            principal.subject,
            reason,
            decision_time,
            manifest.expected_base_serving_state_id,
            _stable_id("art", principal.subject, decision_time, "authority"),
        )
        state = ApprovalState.APPROVED if decision == "APPROVED" else ApprovalState.REJECTED
        projection = ApprovalProjection(record, state, "")
        with self._lock:
            existing_id = self._manifest_approval.get(manifest.manifest_id)
            if existing_id is not None:
                existing = self._approvals[existing_id]
                if existing == projection:
                    return existing
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
            self._approvals[approval_id] = projection
            self._manifest_approval[manifest.manifest_id] = approval_id
        return projection

    def revoke(
        self,
        principal: ReviewerPrincipal,
        approval_id: str,
        *,
        reason: str,
        at: str,
    ) -> ApprovalProjection:
        """Revoke one exact unconsumed Approval."""
        self._authorize(principal)
        self._reason(reason)
        with self._lock:
            current = self._get(approval_id)
            if current.state is not ApprovalState.APPROVED:
                raise ApprovalError(_error_for_state(current.state))
            return self._transition(
                current,
                ApprovalTransition(ApprovalState.REVOKED, "REVOKE", principal.subject, at, reason),
            )

    def invalidate(self, approval_id: str, *, reason: str, at: str) -> ApprovalProjection:
        """Record objective pre-execution invalidation."""
        self._reason(reason)
        with self._lock:
            current = self._get(approval_id)
            if current.state is not ApprovalState.APPROVED:
                raise ApprovalError(_error_for_state(current.state))
            return self._transition(
                current,
                ApprovalTransition(
                    ApprovalState.INVALIDATED,
                    "INVALIDATE",
                    "SYSTEM_VALIDATOR",
                    at,
                    reason,
                ),
            )

    def consume(
        self,
        approval_id: str,
        execution_lineage_id: str,
        manifest: ManifestSnapshot,
        context: ApprovalConsumption,
    ) -> ApprovalProjection:
        """Atomically consume only one exact still-valid Approval."""
        with self._lock:
            current = self._get(approval_id)
            if (
                current.state is ApprovalState.CONSUMED
                and current.execution_lineage_id == execution_lineage_id
                and current.decision.manifest_id == manifest.manifest_id
                and current.decision.manifest_fingerprint == manifest.fingerprint
            ):
                return current
            if current.state is not ApprovalState.APPROVED:
                raise ApprovalError(_error_for_state(current.state))
            if "PipelineAdministrator" not in self._assignments.get(
                current.decision.reviewer_subject, frozenset()
            ):
                raise ApprovalError(ApprovalErrorCode.AUTHORITY_REMOVED)
            if (
                current.decision.manifest_id != manifest.manifest_id
                or current.decision.manifest_fingerprint != manifest.fingerprint
            ):
                raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
            if (
                context.at < manifest.valid_from
                or context.at > manifest.valid_until
                or context.current_base_serving_state_id != manifest.expected_base_serving_state_id
                or context.current_predicates != manifest.validity_predicates
            ):
                self._transition(
                    current,
                    ApprovalTransition(
                        ApprovalState.INVALIDATED,
                        "INVALIDATE",
                        "SYSTEM_VALIDATOR",
                        context.at,
                        "manifest validity predicate failed",
                    ),
                )
                raise ApprovalError(ApprovalErrorCode.MANIFEST_INVALID)
            return self._transition(
                current,
                ApprovalTransition(
                    ApprovalState.CONSUMED,
                    "CONSUME_FOR_ONE_EXECUTION_LINEAGE",
                    "PROMOTION_WORKER",
                    context.at,
                    "exact approval consumed",
                    execution_lineage_id,
                ),
            )

    def get(self, approval_id: str) -> ApprovalProjection:
        """Read one exact Approval projection."""
        with self._lock:
            return self._get(approval_id)

    def _get(self, approval_id: str) -> ApprovalProjection:
        try:
            return self._approvals[approval_id]
        except KeyError as error:
            raise ApprovalError(ApprovalErrorCode.APPROVAL_NOT_FOUND) from error

    def _transition(
        self,
        current: ApprovalProjection,
        transition: ApprovalTransition,
    ) -> ApprovalProjection:
        event = ApprovalLifecycleEvent(
            _stable_id(
                "ape",
                current.decision.approval_id,
                transition.state.value,
                transition.at,
                transition.lineage,
            ),
            current.decision.approval_id,
            current.state,
            transition.state,
            transition.event_type,
            transition.subject,
            transition.at,
            transition.reason,
            transition.lineage,
        )
        projection = ApprovalProjection(current.decision, transition.state, transition.lineage)
        self._events.append(event)
        self._approvals[current.decision.approval_id] = projection
        return projection

    @property
    def events(self) -> tuple[ApprovalLifecycleEvent, ...]:
        """Return append-only audit events."""
        with self._lock:
            return tuple(self._events)

    @property
    def comments(self) -> tuple[ReviewComment, ...]:
        """Return append-only review comments."""
        with self._lock:
            return tuple(self._comments)


def _error_for_state(state: ApprovalState) -> ApprovalErrorCode:
    return {
        ApprovalState.CONSUMED: ApprovalErrorCode.APPROVAL_CONSUMED,
        ApprovalState.INVALIDATED: ApprovalErrorCode.APPROVAL_INVALIDATED,
        ApprovalState.REJECTED: ApprovalErrorCode.APPROVAL_REJECTED,
        ApprovalState.REVOKED: ApprovalErrorCode.APPROVAL_REVOKED,
        ApprovalState.APPROVED: ApprovalErrorCode.MANIFEST_INVALID,
    }[state]
