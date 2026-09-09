"""Framework-free immutable vault protocol shared by local and V1 adapters."""

from typing import Protocol

from .model import (
    ArtifactClass,
    EvidenceReadReceipt,
    ExactObjectReference,
    RetentionProfile,
    VaultName,
    VaultWriteReceipt,
)


class ImmutableVault(Protocol):
    """Minimum exact-version boundary required by package and recovery services."""

    vault_name: VaultName

    def conditional_create(
        self,
        logical_key: str,
        content: bytes,
        retention: RetentionProfile,
    ) -> VaultWriteReceipt:
        """Create or verify one immutable exact version."""
        ...

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        """Read and verify exactly one immutable version."""
        ...

    def read_for_use(
        self,
        reference: ExactObjectReference,
        *,
        required_use: str,
        artifact_class: ArtifactClass,
        accessed_at: str,
    ) -> tuple[bytes, EvidenceReadReceipt]:
        """Read one exact version and return its access receipt."""
        ...

    def exists_exact(self, reference: ExactObjectReference) -> bool:
        """Return whether one exact version exists and verifies."""
        ...

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        """Resolve one retained key to its exact current immutable reference, or none."""
        ...

    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        """Return the exact retained policy for one verified immutable reference."""
        ...
