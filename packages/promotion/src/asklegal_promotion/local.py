"""Deterministic local-only M6 embedding, target, backup, routing, and coverage fakes."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asklegal_corpus import CoverageStatusManifest

from .model import (
    BackupVerification,
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingReceipt,
    EmbeddingRequest,
    OutcomeUnknown,
    PromotionError,
    PromotionErrorCode,
    TargetDefinition,
    TargetRecord,
)


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


@dataclass(frozen=True, slots=True)
class LocalFailurePlan:
    """Exact synthetic fault selection for one conformance case."""

    partial_batch: bool = False
    lost_ack_once: bool = False
    vector_mismatch: bool = False
    unknown_remote_record: bool = False
    backup_failure: bool = False
    recovery_failure: bool = False
    routing_cas_loss: bool = False
    swap_preflight_failure: bool = False
    warmup_failure: bool = False
    post_cutover_failure: bool = False
    rollback_failure: bool = False
    retrieval_failure: bool = False


class LocalEmbeddingAdapter:
    """No-network exact fake with deterministic finite float32 vectors."""

    def __init__(self, plan: LocalFailurePlan | None = None) -> None:
        """Create the adapter with an optional exact synthetic failure plan."""
        self._plan = plan or LocalFailurePlan()
        self.calls: list[str] = []

    def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> EmbeddedVector:
        """Return a deterministic vector only for the reserved local provider."""
        if profile.provider != "LOCAL_FAKE":
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "provider disabled")
        digest = sha256((request.cache_key + request.text).encode()).digest()
        dimensions = profile.dimensions + (1 if self._plan.vector_mismatch else 0)
        values = tuple(
            ((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(dimensions)
        )
        if any(not math.isfinite(value) for value in values):
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID)
        raw = b"".join(struct.pack("!f", value) for value in values)
        receipt = EmbeddingReceipt(
            _stable_id("emc", request.request_id, _fingerprint(raw)),
            request.request_id,
            f"local-{request.request_id}",
            len(values),
            _fingerprint(raw),
            request.token_count,
            0,
            "SUCCEEDED",
        )
        self.calls.append(request.request_id)
        return EmbeddedVector(values, receipt)


class LocalServingTargetStore:
    """Replacement-only target fake with exact inventory enumeration."""

    def __init__(self, plan: LocalFailurePlan | None = None) -> None:
        """Create an empty replacement-target store."""
        self._plan = plan or LocalFailurePlan()
        self._targets: dict[str, tuple[TargetDefinition, dict[str, TargetRecord]]] = {}
        self._lost_ack_fired = False

    def create(self, definition: TargetDefinition) -> None:
        """Create or exactly replay one replacement target."""
        existing = self._targets.get(definition.name)
        if existing is not None and existing[0] != definition:
            raise PromotionError(PromotionErrorCode.TARGET_COLLISION)
        self._targets.setdefault(definition.name, (definition, {}))

    def describe(self, name: str) -> TargetDefinition:
        """Return the exact immutable target definition."""
        return self._targets[name][0]

    def upsert_batch(self, name: str, records: tuple[TargetRecord, ...]) -> None:
        """Write an exact bounded batch, optionally injecting one declared fault."""
        target = self._targets[name][1]
        selected = records[:-1] if self._plan.partial_batch and len(records) > 1 else records
        for record in selected:
            target[record.record_id] = record
        if self._plan.lost_ack_once and not self._lost_ack_fired:
            self._lost_ack_fired = True
            raise OutcomeUnknown(name)

    def enumerate(self, name: str) -> tuple[TargetRecord, ...]:
        """Return the complete actual target inventory in identity order."""
        target = self._targets[name][1]
        if self._plan.unknown_remote_record and "rec_unknown" not in target:
            target["rec_unknown"] = TargetRecord(
                "rec_unknown",
                "sha256:" + "f" * 64,
                (0.0,),
                "unknown",
                "unknown",
                "unknown",
                "unknown",
                "unknown",
                "unknown",
            )
        return tuple(target[key] for key in sorted(target))

    def delete_exact(self, name: str, exact_name: str) -> str:
        """Delete only one exact named target; broad selectors have no representation."""
        if name != exact_name or name not in self._targets:
            raise PromotionError(PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN)
        del self._targets[name]
        return _stable_id("efr", "retire", name)

    def contains(self, name: str) -> bool:
        """Report exact target existence for tests and rollback checks."""
        return name in self._targets

    def verify_queries(self, name: str, expected_record_ids: tuple[str, ...]) -> None:
        """Prove every exact synthetic ID is retrievable without a mutable alias."""
        if self._plan.retrieval_failure:
            raise PromotionError(PromotionErrorCode.RETRIEVAL_GATE_FAILED)
        actual = self._targets[name][1]
        if any(record_id not in actual for record_id in expected_record_ids):
            raise PromotionError(PromotionErrorCode.RETRIEVAL_GATE_FAILED)


class LocalBackupStore:
    """Exact verified backup fake with no external mutation."""

    def __init__(self, plan: LocalFailurePlan | None = None) -> None:
        """Create an empty synthetic backup store."""
        self._plan = plan or LocalFailurePlan()
        self.receipts: list[BackupVerification] = []

    def create_and_verify(self, target_name: str, inventory_fingerprint: str) -> BackupVerification:
        """Create one exact synthetic backup receipt or fail closed."""
        if self._plan.backup_failure:
            raise PromotionError(PromotionErrorCode.BACKUP_FAILED)
        if self._plan.recovery_failure:
            raise PromotionError(PromotionErrorCode.BACKUP_FAILED, "recovery verification")
        receipt = BackupVerification(
            _stable_id("efr", "native-backup", target_name, inventory_fingerprint),
            _stable_id("efr", "recovery-copy", target_name, inventory_fingerprint),
            native_verified=True,
            recovery_verified=True,
        )
        self.receipts.append(receipt)
        return receipt


class LocalRoutingStore:
    """Complete-generation compare-and-set and exact reverse-swap fake."""

    def __init__(self, active_state_id: str, plan: LocalFailurePlan | None = None) -> None:
        """Create routing pinned to one exact predecessor state."""
        self.active_state_id = active_state_id
        self._plan = plan or LocalFailurePlan()

    def activate(self, expected_base: str, candidate: str) -> str:
        """Run preflight, warm-up, and one atomic generation swap."""
        if self._plan.swap_preflight_failure:
            raise PromotionError(PromotionErrorCode.SWAP_PREFLIGHT_FAILED)
        if self._plan.warmup_failure:
            raise PromotionError(PromotionErrorCode.WARMUP_FAILED)
        if self._plan.routing_cas_loss or self.active_state_id != expected_base:
            raise PromotionError(PromotionErrorCode.ROUTING_COMPARE_AND_SET_LOST)
        self.active_state_id = candidate
        return _stable_id("efr", "routing", expected_base, candidate)

    def verify_post_cutover(self, candidate: str) -> None:
        """Verify the pinned candidate generation after swap."""
        if self._plan.post_cutover_failure or self.active_state_id != candidate:
            raise PromotionError(PromotionErrorCode.POST_CUTOVER_FAILED)

    def rollback(self, candidate: str, predecessor: str) -> str:
        """Reverse only the exact manifest-declared swap."""
        if self._plan.rollback_failure or self.active_state_id != candidate:
            raise PromotionError(PromotionErrorCode.POST_CUTOVER_FAILED, "rollback failed")
        self.active_state_id = predecessor
        return _stable_id("efr", "rollback", candidate, predecessor)


class LocalCoverageStore:
    """Fingerprint-verifying store plus per-generation verified cache."""

    def __init__(self, manifest: CoverageStatusManifest | None) -> None:
        """Create a protected-store fake around one immutable manifest."""
        self._manifest = manifest
        self._available = True
        self._cache: dict[str, CoverageStatusManifest] = {}

    def set_available(self, *, available: bool) -> None:
        """Inject a protected-store availability state."""
        self._available = available

    def load_for_activation(
        self, generation_id: str, expected_fingerprint: str
    ) -> CoverageStatusManifest:
        """Require valid stored bytes; cache cannot admit a new generation."""
        if not self._available or self._manifest is None:
            raise PromotionError(PromotionErrorCode.COVERAGE_UNAVAILABLE)
        if self._manifest.fingerprint != expected_fingerprint:
            raise PromotionError(PromotionErrorCode.COVERAGE_FINGERPRINT_MISMATCH)
        self._cache[generation_id] = self._manifest
        return self._manifest

    def load_for_request(
        self, generation_id: str, expected_fingerprint: str
    ) -> CoverageStatusManifest:
        """Use only stored or same-generation previously verified bytes."""
        if self._available and self._manifest is not None:
            if self._manifest.fingerprint != expected_fingerprint:
                raise PromotionError(PromotionErrorCode.COVERAGE_FINGERPRINT_MISMATCH)
            self._cache[generation_id] = self._manifest
            return self._manifest
        cached = self._cache.get(generation_id)
        if cached is None or cached.fingerprint != expected_fingerprint:
            raise PromotionError(PromotionErrorCode.COVERAGE_UNAVAILABLE)
        return cached
