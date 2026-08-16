"""Typed framework-free port for Management Register persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .model import (
    CommandSubmission,
    CommandTransaction,
    EffectAttemptEvent,
    EffectClaim,
    PolicyState,
    ProjectionRow,
    RecoveryPackage,
)

if TYPE_CHECKING:
    from asklegal_domain import ApplicationCode, EffectReceipt


class ManagementRegisterStore(Protocol):
    """Authoritative M2 operations required by application command handlers."""

    def submit_command(self, transaction: CommandTransaction, *, now: str) -> CommandSubmission:
        """Commit one result and its applied facts, or return an exact replay."""
        ...

    def resolve_command(self, command_id: str, command_fingerprint: str) -> CommandSubmission:
        """Resolve a prior submission without rerunning its command decision."""
        ...

    def claim_effect(
        self,
        effect_intent_id: str,
        *,
        owning_application: ApplicationCode,
        claimant_id: str,
        now: str,
        lease_seconds: int,
    ) -> EffectClaim:
        """Claim an uncompleted intent for its exclusive owning application."""
        ...

    def renew_effect_claim(
        self,
        effect_intent_id: str,
        *,
        claimant_id: str,
        fencing_token: int,
        now: str,
        lease_seconds: int,
    ) -> EffectClaim:
        """Renew only the current live claim without changing its fence."""
        ...

    def append_effect_attempt(self, event: EffectAttemptEvent, *, now: str) -> None:
        """Append a sanitized attempt fact under the current live fence."""
        ...

    def record_effect_receipt(
        self,
        receipt: EffectReceipt,
        *,
        fencing_token: int | None,
        now: str,
    ) -> EffectReceipt:
        """Select exactly one terminal receipt, returning an exact replay."""
        ...

    def set_policy_state(self, state: PolicyState) -> None:
        """Record one explicit configured-or-undecided policy definition."""
        ...

    def rebuild_projections(self) -> tuple[ProjectionRow, ...]:
        """Discard and deterministically rebuild disposable projections."""
        ...

    def export_recovery(self, migration_set: tuple[str, ...]) -> RecoveryPackage:
        """Export all authoritative and recovery-relevant state with a digest."""
        ...

    def restore_recovery(self, package: RecoveryPackage) -> None:
        """Verify a recovery digest, replace state, and rebuild projections."""
        ...


__all__ = ["ManagementRegisterStore"]
