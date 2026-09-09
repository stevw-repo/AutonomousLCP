"""Provider-neutral M6 promotion effect ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from asklegal_corpus import CoverageStatusManifest
    from asklegal_domain import ImmutableReference

from .model import (
    BackupVerification,
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingRequest,
    ServingStateCandidate,
    ServingStateReceipt,
    TargetDefinition,
    TargetRecord,
)


class EmbeddingPort(Protocol):
    """Sole embedding-provider boundary."""

    def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> EmbeddedVector:
        """Return one exact vector and safe receipt."""
        ...


class EmbeddingTokenCounter(Protocol):
    """Exact provider-profile tokenizer boundary used before embedding effects."""

    @property
    def tokenizer_id(self) -> str:
        """Return the exact tokenizer identity implemented by this counter."""
        ...

    def count(self, text: str) -> int:
        """Return the exact token count for one exact text value."""
        ...


class ServingTargetPort(Protocol):
    """Replacement-target-only serving adapter."""

    def create(self, definition: TargetDefinition) -> None:
        """Create or replay one exact replacement target."""
        ...

    def describe(self, name: str) -> TargetDefinition:
        """Describe the complete immutable target configuration."""
        ...

    def upsert_batch(self, name: str, records: tuple[TargetRecord, ...]) -> None:
        """Upsert one exact bounded batch."""
        ...

    def enumerate(self, name: str) -> tuple[TargetRecord, ...]:
        """Enumerate the complete actual inventory."""
        ...

    def delete_exact(self, name: str, exact_name: str) -> str:
        """Delete only the exact declared target."""
        ...

    def contains(self, name: str) -> bool:
        """Report whether an exact target exists."""
        ...

    def verify_queries(self, name: str, expected_record_ids: tuple[str, ...]) -> None:
        """Run the deterministic synthetic retrieval gate."""
        ...


class BackupPort(Protocol):
    """Exact target backup and verification boundary."""

    def create_and_verify(
        self,
        target_name: str,
        inventory_fingerprint: str,
        backup_profile_ref: ImmutableReference | None,
    ) -> BackupVerification:
        """Create and independently verify one exact backup."""
        ...


class CoveragePort(Protocol):
    """Protected immutable coverage retrieval and verified-cache boundary."""

    def load_for_activation(
        self, generation_id: str, expected_fingerprint: str
    ) -> CoverageStatusManifest:
        """Require protected bytes and verify them before activation."""
        ...

    def load_for_request(
        self, generation_id: str, expected_fingerprint: str
    ) -> CoverageStatusManifest:
        """Retrieve protected bytes or only a same-generation verified cache."""
        ...


class RoutingPort(Protocol):
    """Complete-generation activation and reverse-swap boundary."""

    active_state_id: str

    def activate(self, expected_base: str, candidate: str) -> str:
        """Compare-and-set one complete candidate generation."""
        ...

    def verify_post_cutover(self, candidate: str) -> None:
        """Verify the exact pinned production generation."""
        ...

    def rollback(self, candidate: str, predecessor: str) -> str:
        """Reverse-swap to the exact retained predecessor."""
        ...


class ServingStatePort(Protocol):
    """Management Register V1 activation boundary, with no application routing."""

    @property
    def active_state_id(self) -> str:
        """Return the currently retained active Serving State identity."""
        ...

    def activate(self, expected_base: str, candidate: ServingStateCandidate) -> ServingStateReceipt:
        """Atomically record one exact verified candidate state."""
        ...

    def verify(self, candidate_state_id: str) -> None:
        """Re-read the exact state recorded by a successful activation."""
        ...

    def rollback(
        self, candidate: ServingStateCandidate, activation_receipt_id: str
    ) -> ServingStateReceipt:
        """Append the only permitted reversal of one exact active activation fact."""
        ...
