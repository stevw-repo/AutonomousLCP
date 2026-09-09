"""Local-only current-unadmitted Hong Kong V1 due-cycle activity proof."""

from __future__ import annotations

import ast
import copy
import gc
import json
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Thread
from typing import cast

import pytest
from asklegal_acquisition_worker import hk_v1_due_cycle as due_cycle
from asklegal_acquisition_worker.hk_v1_due_cycle import HongKongV1DueCycleActivities
from asklegal_acquisition_worker.hk_v1_due_predecessor import (
    DueCyclePredecessorState,
    DueCyclePredecessorWriteReceipt,
    LocalDueCyclePredecessorStore,
)
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import (
    ArtifactClass,
    CorruptEvidence,
    EvidenceReadReceipt,
    ExactObjectReference,
    LocalImmutableVault,
    RetentionProfile,
    VaultCollision,
    VaultName,
    VaultWriteReceipt,
    s3_version_reference,
)
from asklegal_reporting import (
    DueChangeStatus,
    DueCycleKind,
    DueImmutableReference,
    DueTerminalOutcome,
    HongKongV1DueCycleError,
    HongKongV1DueCycleInstruction,
    IssuedDueResultBinding,
    hk_v1_due_cycle_manifest_key,
    hk_v1_due_source_payload_key,
    hk_v1_due_source_result_manifest_key,
    hk_v1_due_source_terminal_key,
    load_hk_v1_coverage_matrix,
    parse_hk_v1_due_terminal,
)

_DUE_PLAN_NAME = "_plan"
_DUE_REQUIREMENT_FOR_NAME = "_requirement_for"
_DUE_UNADMITTED_PAYLOAD_NAME = "_unadmitted_payload"
_DUE_BINDING_FROM_PAYLOAD_NAME = "_binding_from_retained_payload"
_DUE_BINDING_FROM_ATTEMPT_NAME = "_binding_from_retained_attempt"
_DUE_REFERENCE_NAME = "_reference"
_DUE_ADAPTER_SOURCE_IDS_NAME = "_ADAPTER_SOURCE_IDS"
_DUE_BUNDLE_FROM_RESOURCE_SNAPSHOT_NAME = "_bundle_from_resource_snapshot"
_DUE_RETAINED_BINDING_PROOF_NAME = "_retained_binding_proof"
_DUE_CONSUME_RETAINED_BINDING_PROOF_NAME = "_consume_retained_binding_proof"
_DUE_RECONSTRUCTED_ATTEMPT_BINDINGS_NAME = "_RECONSTRUCTED_ATTEMPT_BINDINGS"
_DUE_RETAINED_BINDING_PROOFS_NAME = "_RETAINED_BINDING_PROOFS"
_DUE_RETAINED_PROOF_BINDING_IDS_NAME = "_RETAINED_PROOF_BINDING_IDS"
_DUE_RECEIPT_SNAPSHOT_NAME = "_receipt_snapshot"
_due_plan = getattr(due_cycle, _DUE_PLAN_NAME)
_due_requirement_for = getattr(due_cycle, _DUE_REQUIREMENT_FOR_NAME)
_due_unadmitted_payload = getattr(due_cycle, _DUE_UNADMITTED_PAYLOAD_NAME)
_due_binding_from_payload = getattr(due_cycle, _DUE_BINDING_FROM_PAYLOAD_NAME)
_due_binding_from_attempt = getattr(due_cycle, _DUE_BINDING_FROM_ATTEMPT_NAME)
_due_reference = getattr(due_cycle, _DUE_REFERENCE_NAME)
_due_adapter_source_ids = getattr(due_cycle, _DUE_ADAPTER_SOURCE_IDS_NAME)
_due_bundle_from_resource_snapshot = getattr(due_cycle, _DUE_BUNDLE_FROM_RESOURCE_SNAPSHOT_NAME)
_due_retained_binding_proof = getattr(due_cycle, _DUE_RETAINED_BINDING_PROOF_NAME)
_due_consume_retained_binding_proof = getattr(due_cycle, _DUE_CONSUME_RETAINED_BINDING_PROOF_NAME)
_due_reconstructed_attempt_bindings = getattr(due_cycle, _DUE_RECONSTRUCTED_ATTEMPT_BINDINGS_NAME)
_due_retained_binding_proofs = getattr(due_cycle, _DUE_RETAINED_BINDING_PROOFS_NAME)
_due_retained_proof_binding_ids = getattr(due_cycle, _DUE_RETAINED_PROOF_BINDING_IDS_NAME)
_due_receipt_snapshot = getattr(due_cycle, _DUE_RECEIPT_SNAPSHOT_NAME)


def _context() -> ActivityContext:
    """Provide the inert SDK context required by direct activity tests."""
    return ActivityContext("hk-v1-due-cycle-test", 1)


def _instruction(kind: DueCycleKind = DueCycleKind.FULL_PERIODIC) -> dict[str, str]:
    matrix = load_hk_v1_coverage_matrix()
    return {
        "cycle_id": f"hk-v1-{kind.value.lower()}-20260826",
        "cycle_kind": kind.value,
        "scheduled_at": "2026-08-26T00:00:00Z",
        "observation_cutoff": "2026-08-26T00:00:00Z",
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
    }


class _RecordingVault:
    """Tiny in-memory observation wrapper over the real local fake."""

    vault_name = VaultName.PRIMARY

    def __init__(self, root: Path) -> None:
        self._inner = LocalImmutableVault(root, VaultName.PRIMARY)
        self.objects: dict[str, bytes] = {}
        self.receipts: dict[str, VaultWriteReceipt] = {}
        self.writes: list[str] = []

    def conditional_create(
        self, logical_key: str, content: bytes, retention: RetentionProfile
    ) -> VaultWriteReceipt:
        self.writes.append(logical_key)
        receipt = self._inner.conditional_create(logical_key, content, retention)
        self.objects[logical_key] = content
        self.receipts[logical_key] = receipt
        return receipt

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        return self._inner.read_exact(reference)

    def read_for_use(
        self,
        reference: ExactObjectReference,
        *,
        required_use: str,
        artifact_class: ArtifactClass,
        accessed_at: str,
    ) -> tuple[bytes, EvidenceReadReceipt]:
        return self._inner.read_for_use(
            reference,
            required_use=required_use,
            artifact_class=artifact_class,
            accessed_at=accessed_at,
        )

    def exists_exact(self, reference: ExactObjectReference) -> bool:
        return self._inner.exists_exact(reference)

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        return self._inner.resolve_current(logical_key)

    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        return self._inner.retention(reference)


class _FaultyReceiptVault(_RecordingVault):
    """Return one faulty create receipt without weakening the real inner vault."""

    def __init__(self, root: Path, field: str, nth: int = 1) -> None:
        super().__init__(root)
        self._field = field
        self._nth = nth

    def conditional_create(
        self, logical_key: str, content: bytes, retention: RetentionProfile
    ) -> VaultWriteReceipt:
        receipt = super().conditional_create(logical_key, content, retention)
        if len(self.writes) != self._nth:
            return receipt
        reference = receipt.reference
        if self._field == "read_back_verified":
            malformed = object.__new__(VaultWriteReceipt)
            object.__setattr__(malformed, "reference", reference)
            object.__setattr__(malformed, "created", receipt.created)
            object.__setattr__(malformed, "read_back_verified", False)
            object.__setattr__(malformed, "retention", receipt.retention)
            return malformed
        if self._field == "created":
            malformed = object.__new__(VaultWriteReceipt)
            object.__setattr__(malformed, "reference", reference)
            object.__setattr__(malformed, "created", "not-a-bool")
            object.__setattr__(malformed, "read_back_verified", receipt.read_back_verified)
            object.__setattr__(malformed, "retention", receipt.retention)
            return malformed
        if self._field in {"profile_id", "retain_until", "legal_hold"}:
            mutations: dict[str, object] = {
                "profile_id": "wrong-profile",
                "retain_until": "2098-12-31T00:00:00Z",
                "legal_hold": True,
            }
            return replace(
                receipt,
                retention=replace(receipt.retention, **{self._field: mutations[self._field]}),
            )
        mutations: dict[str, object] = {
            "vault": VaultName.RECOVERY,
            "logical_key": "wrong/key.json",
            "version_id": "v" + ("0" * 64),
            "fingerprint": "sha256:" + ("0" * 64),
            "byte_length": reference.byte_length + 1,
        }
        return replace(
            receipt, reference=replace(reference, **{self._field: mutations[self._field]})
        )


class _WrongReadVault(_RecordingVault):
    def __init__(self, root: Path, nth: int = 1) -> None:
        super().__init__(root)
        self._nth = nth

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        self._inner.read_exact(reference)
        if len(self.writes) == self._nth:
            return b"{}"
        return self._inner.read_exact(reference)


class _MutationDuringReadVault(_RecordingVault):
    """Mutate every adapter-owned receipt/reference leaf after its proof point."""

    def __init__(self, root: Path, nth: int, leaf: str) -> None:
        super().__init__(root)
        self._nth = nth
        self._leaf = leaf

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        content = self._inner.read_exact(reference)
        if len(self.writes) != self._nth:
            return content
        receipt = self.receipts[self.writes[self._nth - 1]]
        original = receipt.reference
        if self._leaf in {"vault", "logical_key", "version_id", "fingerprint", "byte_length"}:
            changes: dict[str, object] = {
                "vault": VaultName.RECOVERY,
                "logical_key": "wrong/key.json",
                "version_id": "v" + ("0" * 64),
                "fingerprint": "sha256:" + ("0" * 64),
                "byte_length": original.byte_length + 1,
            }
            object.__setattr__(reference, self._leaf, changes[self._leaf])
            object.__setattr__(
                receipt, "reference", replace(original, **{self._leaf: changes[self._leaf]})
            )
        elif self._leaf == "created":
            object.__setattr__(receipt, "created", False)
        elif self._leaf == "read_back_verified":
            object.__setattr__(receipt, "read_back_verified", False)
        else:
            retention_changes: dict[str, object] = {
                "profile_id": "different-profile",
                "retain_until": "2098-12-31T00:00:00Z",
                "legal_hold": True,
            }
            retention = receipt.retention
            object.__setattr__(
                receipt,
                "retention",
                replace(retention, **{self._leaf: retention_changes[self._leaf]}),
            )
        return content


class _ChangingResource:
    """A hostile traversable-like double whose second read changes the source view."""

    def __init__(self, first: bytes, second: bytes) -> None:
        self._first = first
        self._second = second
        self.calls = 0

    def read_bytes(self) -> bytes:
        self.calls += 1
        return self._first if self.calls == 1 else self._second


class _ReadErrorVault(_RecordingVault):
    """Raise one ordinary evidence-read failure only at the selected stage."""

    def __init__(self, root: Path, nth: int, error: Exception) -> None:
        super().__init__(root)
        self._nth = nth
        self._error = error

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        if len(self.writes) == self._nth:
            raise self._error
        return self._inner.read_exact(reference)


class _OneStageFailureVault(_RecordingVault):
    """Inject one ordinary or lost-return failure at an exact create/read stage."""

    def __init__(self, root: Path, operation: str, nth: int, *, lost_return: bool = False) -> None:
        super().__init__(root)
        self._operation = operation
        self._nth = nth
        self._lost_return = lost_return
        self._creates = 0
        self._reads = 0
        self.attempted_contents: list[bytes] = []

    def conditional_create(
        self, logical_key: str, content: bytes, retention: RetentionProfile
    ) -> VaultWriteReceipt:
        self._creates += 1
        self.attempted_contents.append(content)
        if self._operation == "create" and self._creates == self._nth:
            if self._lost_return:
                super().conditional_create(logical_key, content, retention)
            raise RuntimeError
        return super().conditional_create(logical_key, content, retention)

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        self._reads += 1
        if self._operation == "read" and self._reads == self._nth:
            raise RuntimeError
        return self._inner.read_exact(reference)


class _ProviderVersionRecoveryVault(_OneStageFailureVault):
    """A deterministic vault fake whose resolved immutable version is provider-shaped."""

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        reference = self._inner.resolve_current(logical_key)
        if reference is None:
            return None
        return ExactObjectReference(
            reference.vault,
            reference.logical_key,
            s3_version_reference("provider/version-1"),
            reference.fingerprint,
            reference.byte_length,
        )

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        self._reads += 1
        if self._operation == "read" and self._reads == self._nth:
            raise RuntimeError
        actual = self._inner.resolve_current(reference.logical_key)
        if actual is None:
            raise FileNotFoundError(reference.logical_key)
        if (
            actual.vault is not reference.vault
            or actual.logical_key != reference.logical_key
            or actual.fingerprint != reference.fingerprint
            or actual.byte_length != reference.byte_length
        ):
            raise CorruptEvidence(reference.logical_key)
        return self._inner.read_exact(actual)

    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        actual = self._inner.resolve_current(reference.logical_key)
        if actual is None:
            raise FileNotFoundError(reference.logical_key)
        return self._inner.retention(actual)


class _ProviderVersionWriteVault(_RecordingVault):
    """Present opaque provider version IDs for every create and later exact read."""

    def conditional_create(
        self, logical_key: str, content: bytes, retention: RetentionProfile
    ) -> VaultWriteReceipt:
        receipt = super().conditional_create(logical_key, content, retention)
        reference = receipt.reference
        return VaultWriteReceipt(
            ExactObjectReference(
                reference.vault,
                reference.logical_key,
                s3_version_reference(f"provider/{len(self.writes)}"),
                reference.fingerprint,
                reference.byte_length,
            ),
            receipt.created,
            receipt.read_back_verified,
            receipt.retention,
        )

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        actual = self._inner.resolve_current(reference.logical_key)
        if actual is None:
            raise FileNotFoundError(reference.logical_key)
        if (
            actual.vault is not reference.vault
            or actual.logical_key != reference.logical_key
            or actual.fingerprint != reference.fingerprint
            or actual.byte_length != reference.byte_length
        ):
            raise CorruptEvidence(reference.logical_key)
        return self._inner.read_exact(actual)

    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        actual = self._inner.resolve_current(reference.logical_key)
        if actual is None:
            raise FileNotFoundError(reference.logical_key)
        return self._inner.retention(actual)


class _StaleNoneResolveVault(_RecordingVault):
    """Simulate a normal writer winning after the failure recorder's first key lookup."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._resolve_calls = 0

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        self._resolve_calls += 1
        if self._resolve_calls == 1:
            return None
        return self._inner.resolve_current(logical_key)


class _StaleNoneThenResolveErrorVault(_StaleNoneResolveVault):
    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        if self._resolve_calls >= 1:
            self._resolve_calls += 1
            raise RuntimeError
        return super().resolve_current(logical_key)


class _StaleNoneWrongRetentionVault(_StaleNoneResolveVault):
    """Expose a concurrent winner whose exact bytes have the wrong WORM policy."""

    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        del reference
        return RetentionProfile("wrong-policy", "2031-01-01T00:00:00Z")


class _RetentionEqualityLiar(RetentionProfile):
    """A hostile foreign retention value that claims equality with every policy."""

    __hash__ = object.__hash__

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False


class _LyingRetentionVault(_RecordingVault):
    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        del reference
        return _RetentionEqualityLiar("wrong-policy", "2031-01-01T00:00:00Z")


class _StaleNoneLyingRetentionVault(_StaleNoneResolveVault):
    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        del reference
        return _RetentionEqualityLiar("wrong-policy", "2031-01-01T00:00:00Z")


class _MutatingResolvedReferenceVault(_RecordingVault):
    """Mutate only a callback-owned reference to prove activity snapshots stay closed."""

    def __init__(self, root: Path, callback: str, field: str) -> None:
        super().__init__(root)
        self._callback = callback
        self._field = field
        self.armed = False

    def retention(self, reference: ExactObjectReference) -> RetentionProfile:
        actual = self._inner.resolve_current(reference.logical_key)
        if actual is None:
            raise FileNotFoundError(reference.logical_key)
        retained = self._inner.retention(actual)
        if self.armed and self._callback == "retention":
            object.__setattr__(reference, self._field, [])
        return retained

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        content = self._inner.read_exact(reference)
        if self.armed and self._callback == "read":
            object.__setattr__(reference, self._field, [])
        return content


class _AssemblyReadFaultVault(_RecordingVault):
    """Fail or substitute only the final-manifest read after terminal preparation."""

    def __init__(self, root: Path, replacement: bytes | Exception) -> None:
        super().__init__(root)
        self._replacement = replacement

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        if reference.logical_key.endswith("/manifest.json"):
            if isinstance(self._replacement, Exception):
                raise self._replacement
            return self._replacement
        return self._inner.read_exact(reference)


class _OperationRecordingVault(_RecordingVault):
    """Record the public vault operation order without changing its semantics."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.operations: list[tuple[str, str]] = []

    def conditional_create(
        self, logical_key: str, content: bytes, retention: RetentionProfile
    ) -> VaultWriteReceipt:
        self.operations.append(("write", logical_key))
        return super().conditional_create(logical_key, content, retention)

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        self.operations.append(("read", reference.logical_key))
        return self._inner.read_exact(reference)


class _MappedReadVault(_RecordingVault):
    """Return a deliberate retained-artifact substitution by fixed logical key."""

    def __init__(self, root: Path, replacements: dict[str, bytes]) -> None:
        super().__init__(root)
        self._replacements = replacements

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        replacement = self._replacements.get(reference.logical_key)
        if replacement is not None:
            return replacement
        return self._inner.read_exact(reference)

    def replace_read_content(self, logical_key: str, content: bytes) -> None:
        self._replacements[logical_key] = content


class _BytesSubclass(bytes):
    """A contract-shaped, but not exact, vault response."""


class _EqualityLiar(str):
    __slots__ = ()
    __hash__ = str.__hash__

    def __eq__(self, _other: object) -> bool:
        return True


class _ResealedEqualityLiarVault(_RecordingVault):
    """Return a copied receipt whose key only claims to match the fixed object."""

    def conditional_create(
        self, logical_key: str, content: bytes, retention: RetentionProfile
    ) -> VaultWriteReceipt:
        receipt = super().conditional_create(logical_key, content, retention)
        if len(self.writes) != 1:
            return receipt
        reference = replace(receipt.reference)
        object.__setattr__(reference, "logical_key", _EqualityLiar(logical_key))
        return replace(receipt, reference=reference)


def test_due_cycle_plan_uses_fixed_resources_and_derives_all_periodic_roles(
    tmp_path: Path,
) -> None:
    """The worker derives the frozen full cycle without caller-supplied registers."""
    matrix = load_hk_v1_coverage_matrix()
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )

    plan = activities.plan_hk_v1_due_cycle(
        _context(),
        {
            "cycle_id": "hk-v1-full-20260826",
            "cycle_kind": DueCycleKind.FULL_PERIODIC.value,
            "scheduled_at": "2026-08-26T00:00:00Z",
            "observation_cutoff": "2026-08-26T00:00:00Z",
            "matrix_revision": matrix.revision,
            "matrix_fingerprint": matrix.fingerprint,
        },
    )

    assert plan["schema_id"] == "asklegal.hk-v1-due-cycle-plan"
    assert plan["schema_version"] == "1.0.0"
    assert plan["instruction"] == {
        "cycle_id": "hk-v1-full-20260826",
        "cycle_kind": DueCycleKind.FULL_PERIODIC.value,
        "scheduled_at": "2026-08-26T00:00:00Z",
        "observation_cutoff": "2026-08-26T00:00:00Z",
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
    }
    assert [
        {key: register[key] for key in ("register_id", "register_version", "register_fingerprint")}
        for register in plan["registers"]
    ] == [
        {
            "register_id": "hcr_000000000000000000000000000000000000000000000001",
            "register_version": "2026-09-06.1",
            "register_fingerprint": (
                "sha256:a697a7f7b9b1327169d368ebdef722ee71d6dae447057c8da2a502b5bcdbe13e"
            ),
        },
        {
            "register_id": "hsr_000000000000000000000000000000000000000000000001",
            "register_version": "2026-08-28.3",
            "register_fingerprint": (
                "sha256:be2dc02b4ef087ac2357ad96dc05be5a36127e2a7f395bffe5b7a98f6408de67"
            ),
        },
    ]
    assert all(
        frozenset(register)
        == {
            "register_id",
            "register_version",
            "register_fingerprint",
            "sources",
        }
        and register["sources"]
        and all(
            frozenset(source)
            == {
                "source_id",
                "source_version",
                "endpoint_ids",
                "operational_state",
                "blockers",
            }
            for source in register["sources"]
        )
        for register in plan["registers"]
    )
    assert all(
        frozenset(requirement)
        == {
            "material_family",
            "source_id",
            "source_version",
            "cadence",
            "outage_impact",
            "register_id",
            "register_version",
            "register_fingerprint",
            "matrix_policy_fingerprint",
            "policy_conflict",
            "result_schema",
            "technical_state",
            "rights_state",
        }
        for requirement in plan["requirements"]
    )
    assert plan["predecessor_fingerprint"] is None
    assert plan["source_ids"] == [
        "HK-CASE-HKLII-DISCOVERY",
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
    ]


def test_unadmitted_source_persists_explicit_incomplete_terminal_without_transport(
    tmp_path: Path,
) -> None:
    """A current role stores an exact not-proved terminal instead of attempting I/O."""
    matrix = load_hk_v1_coverage_matrix()
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    instruction = {
        "cycle_id": "hk-v1-daily-20260826",
        "cycle_kind": DueCycleKind.DAILY_CURRENT_LAW.value,
        "scheduled_at": "2026-08-26T00:00:00Z",
        "observation_cutoff": "2026-08-26T00:00:00Z",
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
    }
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)

    result = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )

    assert result["source_id"] == "HK-LEG-GLD-EGAZETTE"
    assert result["payload_created"] is True
    assert result["attempt_created"] is True
    assert result["terminal_created"] is True


def test_full_unadmitted_cycle_persists_all_seven_roles_and_adopts_exact_replay(
    tmp_path: Path,
) -> None:
    """Every required role stays visible; retrying creates no divergent terminal."""
    matrix = load_hk_v1_coverage_matrix()
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    instruction = {
        "cycle_id": "hk-v1-full-replay-20260826",
        "cycle_kind": DueCycleKind.FULL_PERIODIC.value,
        "scheduled_at": "2026-08-26T00:00:00Z",
        "observation_cutoff": "2026-08-26T00:00:00Z",
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
    }
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    source_ids = plan["source_ids"]
    results = [
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": source_id,
            },
        )
        for source_id in source_ids
    ]
    replay = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )

    assert len(results) == 7
    assert {item["source_id"] for item in results} == set(source_ids)
    assert replay["payload_created"] is False
    assert replay["attempt_created"] is False
    assert replay["terminal_created"] is False


@pytest.mark.parametrize(
    "injected",
    [
        {"due_source_ids": []},
        {"prior_fingerprints": {}},
        {"registers": []},
        {"register_paths": []},
        {"requirements": []},
    ],
)
def test_public_plan_rejects_every_caller_owned_policy_override(
    tmp_path: Path, injected: dict[str, object]
) -> None:
    """The durable planning boundary is exactly the six reporting fields."""
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_INSTRUCTION_INVALID"):
        activities.plan_hk_v1_due_cycle(_context(), _instruction() | injected)


def test_public_plan_rejects_a_live_instruction_object(tmp_path: Path) -> None:
    """A durable activity receives canonical JSON data, not a caller-minted object."""
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    instruction = _instruction()
    typed = HongKongV1DueCycleInstruction.from_json(instruction)
    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_INSTRUCTION_INVALID"):
        activities.plan_hk_v1_due_cycle(_context(), typed)


@pytest.mark.parametrize(
    "field",
    ["vault", "logical_key", "version_id", "fingerprint", "byte_length", "read_back_verified"],
)
def test_capture_rejects_every_inexact_payload_receipt_field(tmp_path: Path, field: str) -> None:
    """No receipt claim can substitute for the expected fixed payload object."""
    vault = _FaultyReceiptVault(tmp_path / field, field)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.FULL_PERIODIC)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_PAYLOAD_READBACK_INVALID"):
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": "HK-LEG-GLD-EGAZETTE",
            },
        )


def test_capture_rejects_an_exact_receipt_with_wrong_read_back_bytes(tmp_path: Path) -> None:
    """A vault must provide the same bytes it acknowledged, before issuance."""
    vault = _WrongReadVault(tmp_path / "wrong-read")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.FULL_PERIODIC)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_PAYLOAD_READBACK_INVALID"):
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": "HK-LEG-GLD-EGAZETTE",
            },
        )


@pytest.mark.parametrize("nth", [1, 2, 3])
@pytest.mark.parametrize(
    "leaf",
    [
        "created",
        "read_back_verified",
        "profile_id",
        "retain_until",
        "legal_hold",
        "vault",
        "logical_key",
        "version_id",
        "fingerprint",
        "byte_length",
    ],
)
def test_capture_uses_private_receipt_snapshots_after_every_vault_read(
    tmp_path: Path, nth: int, leaf: str
) -> None:
    """Post-read mutation of any adapter receipt leaf cannot alter the terminal projection."""
    vault = _MutationDuringReadVault(tmp_path / f"{nth}-{leaf}", nth, leaf)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    result = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )
    terminal_reference = result["terminal_reference"]
    assert isinstance(terminal_reference, dict)
    assert terminal_reference["logical_key"] == hk_v1_due_source_terminal_key(
        instruction["cycle_id"], "HK-LEG-GLD-EGAZETTE"
    )
    assert terminal_reference["vault"] == VaultName.PRIMARY.value
    assert result["payload_created"] is True
    assert result["attempt_created"] is True
    assert result["terminal_created"] is True


@pytest.mark.parametrize(
    ("nth", "code"),
    [
        (1, "DUE_PAYLOAD_READBACK_INVALID"),
        (2, "DUE_ATTEMPT_READBACK_INVALID"),
        (3, "DUE_TERMINAL_READBACK_INVALID"),
    ],
)
@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("missing"),
        CorruptEvidence("corrupt"),
        RuntimeError("raw-adapter-detail"),
        TypeError("bad adapter"),
        ValueError("bad adapter"),
    ],
)
def test_capture_normalizes_every_ordinary_stage_read_error(
    tmp_path: Path, nth: int, code: str, error: Exception
) -> None:
    """Read transport/evidence ordinary failures never escape the closed stage code."""
    vault = _ReadErrorVault(tmp_path / f"{nth}-{type(error).__name__}", nth, error)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    with pytest.raises(HongKongV1DueCycleError, match=code):
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": "HK-LEG-GLD-EGAZETTE",
            },
        )


def test_receipt_snapshot_rejects_a_resealed_equality_lying_reference(tmp_path: Path) -> None:
    """Exact primitive reconstruction rejects a value that compares equal to the key."""
    vault = _ResealedEqualityLiarVault(tmp_path / "liar")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_PAYLOAD_READBACK_INVALID"):
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": "HK-LEG-GLD-EGAZETTE",
            },
        )


@pytest.mark.parametrize(
    ("filename", "loader_name"),
    [
        ("hk_legislation_source_register.json", "load_hk_legislation_source_register"),
        ("hk_cases_source_register.json", "load_hk_cases_source_register"),
    ],
)
def test_register_bundle_uses_one_resource_snapshot_for_family_validation_and_projection(
    filename: str, loader_name: str
) -> None:
    """A changing traversable cannot validate one register view then project another."""
    resource_root = due_cycle.resources.files("asklegal_source_connectors")
    content = resource_root.joinpath(filename).read_bytes()
    resource = _ChangingResource(content, b"{}")
    loader = getattr(due_cycle, loader_name)
    bundle = _due_bundle_from_resource_snapshot(resource, filename, loader)
    assert resource.calls == 1
    assert bundle.register_fingerprint in content.decode("utf-8")


@pytest.mark.parametrize(
    ("nth", "code"),
    [
        (2, "DUE_ATTEMPT_READBACK_INVALID"),
        (3, "DUE_TERMINAL_READBACK_INVALID"),
    ],
)
def test_capture_rejects_every_inexact_later_receipt(tmp_path: Path, nth: int, code: str) -> None:
    """The attempt and terminal have the same exact receipt boundary as payload."""
    vault = _FaultyReceiptVault(tmp_path / code, "logical_key", nth=nth)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    with pytest.raises(HongKongV1DueCycleError, match=code):
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": "HK-LEG-GLD-EGAZETTE",
            },
        )


@pytest.mark.parametrize(
    ("nth", "code"),
    [
        (2, "DUE_ATTEMPT_READBACK_INVALID"),
        (3, "DUE_TERMINAL_READBACK_INVALID"),
    ],
)
def test_capture_rejects_wrong_attempt_or_terminal_read_back(
    tmp_path: Path, nth: int, code: str
) -> None:
    """Every retained stage is reconstructed from its own exact read-back bytes."""
    vault = _WrongReadVault(tmp_path / code, nth=nth)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    with pytest.raises(HongKongV1DueCycleError, match=code):
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": "HK-LEG-GLD-EGAZETTE",
            },
        )


def test_replay_survives_a_fresh_activity_and_cleared_weak_binding_registry(tmp_path: Path) -> None:
    """A restart replays retained bytes and does not depend on the prior weak registry."""
    root = tmp_path / "primary"
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    first = HongKongV1DueCycleActivities(
        LocalImmutableVault(root, VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    plan = first.plan_hk_v1_due_cycle(_context(), instruction)
    initial = first.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )
    del first
    gc.collect()
    replay = HongKongV1DueCycleActivities(
        LocalImmutableVault(root, VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    repeated = replay.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )
    assert initial["terminal_reference"] == repeated["terminal_reference"]
    assert repeated["payload_created"] is False
    assert repeated["attempt_created"] is False
    assert repeated["terminal_created"] is False


def test_divergent_payload_at_fixed_key_never_adopts_a_collision(tmp_path: Path) -> None:
    """A different fixed-key object stops before a forged binding can be registered."""
    vault = _RecordingVault(tmp_path / "primary")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    vault.conditional_create(
        hk_v1_due_source_payload_key(instruction["cycle_id"], "HK-LEG-GLD-EGAZETTE"),
        b"{}",
        RetentionProfile("test", "2099-12-31T00:00:00Z"),
    )
    with pytest.raises(VaultCollision):
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": "HK-LEG-GLD-EGAZETTE",
            },
        )


@pytest.mark.parametrize("stage", ["attempt", "terminal"])
def test_divergent_later_fixed_key_never_adopts_a_collision(tmp_path: Path, stage: str) -> None:
    """Attempt and terminal collisions are as closed as a divergent payload collision."""
    vault = _RecordingVault(tmp_path / stage)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = _due_plan(HongKongV1DueCycleInstruction.from_json(instruction))
    requirement = _due_requirement_for(plan, "HK-LEG-GLD-EGAZETTE")
    retention = RetentionProfile("test", "2099-12-31T00:00:00Z")
    payload_key = hk_v1_due_source_payload_key(instruction["cycle_id"], requirement.source_id)
    payload = _due_unadmitted_payload(plan, requirement)
    payload_receipt = vault.conditional_create(payload_key, payload, retention)
    attempt_key = hk_v1_due_source_result_manifest_key(
        instruction["cycle_id"], requirement.source_id
    )
    binding = _due_binding_from_payload(
        payload,
        plan,
        requirement,
        _due_reference(payload_receipt.reference),
    )
    attempt, _ = due_cycle.build_hk_v1_due_result_manifest(binding)
    if stage == "attempt":
        vault.conditional_create(attempt_key, b"{}", retention)
    else:
        vault.conditional_create(attempt_key, attempt, retention)
        vault.conditional_create(
            hk_v1_due_source_terminal_key(instruction["cycle_id"], requirement.source_id),
            b"{}",
            retention,
        )
    plan_body = activities.plan_hk_v1_due_cycle(_context(), instruction)
    with pytest.raises(VaultCollision):
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan_body["plan_fingerprint"],
                "source_id": requirement.source_id,
            },
        )


def test_retained_payload_attempt_and_terminal_reject_unknown_missing_and_forged_fields(
    tmp_path: Path,
) -> None:
    """Every local parser/reconstructor refuses canonical but non-authoritative bytes."""
    vault = _RecordingVault(tmp_path / "primary")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = _due_plan(HongKongV1DueCycleInstruction.from_json(instruction))
    requirement = _due_requirement_for(plan, "HK-LEG-GLD-EGAZETTE")
    result = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan.plan_fingerprint,
            "source_id": requirement.source_id,
        },
    )
    payload_key = hk_v1_due_source_payload_key(instruction["cycle_id"], requirement.source_id)
    payload_reference = _due_reference(vault.receipts[payload_key].reference)
    payload = vault.objects[payload_key]
    for forged in (
        canonicalize(checked_json_value(json.loads(payload) | {"cached_success": True})),
        canonicalize(
            checked_json_value(
                {key: value for key, value in json.loads(payload).items() if key != "source_id"}
            )
        ),
        canonicalize(checked_json_value(json.loads(payload) | {"outcome": "COMPLETE"})),
    ):
        with pytest.raises(HongKongV1DueCycleError, match="DUE_PAYLOAD_READBACK_INVALID"):
            _due_binding_from_payload(forged, plan, requirement, payload_reference)

    binding = _due_binding_from_payload(payload, plan, requirement, payload_reference)
    attempt_key = hk_v1_due_source_result_manifest_key(
        instruction["cycle_id"], requirement.source_id
    )
    attempt = vault.objects[attempt_key]
    for forged in (
        canonicalize(checked_json_value(json.loads(attempt) | {"cached_success": True})),
        canonicalize(
            checked_json_value(
                {
                    key: value
                    for key, value in json.loads(attempt).items()
                    if key != "payload_reference"
                }
            )
        ),
    ):
        with pytest.raises(HongKongV1DueCycleError, match="DUE_ATTEMPT_READBACK_INVALID"):
            _due_binding_from_attempt(forged, binding)

    terminal_key = hk_v1_due_source_terminal_key(instruction["cycle_id"], requirement.source_id)
    terminal = vault.objects[terminal_key]
    for forged in (
        canonicalize(checked_json_value(json.loads(terminal) | {"cached_success": True})),
        canonicalize(
            checked_json_value(
                {
                    key: value
                    for key, value in json.loads(terminal).items()
                    if key != "result_fingerprint"
                }
            )
        ),
    ):
        with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_INVALID"):
            parse_hk_v1_due_terminal(forged)
    terminal_reference = result["terminal_reference"]
    assert isinstance(terminal_reference, dict)
    assert terminal_reference["logical_key"] == terminal_key


def test_full_periodic_cycle_keeps_all_adapter_identities_and_unproved_payloads(
    tmp_path: Path,
) -> None:
    """All seven scheduled adapters persist only their own current incomplete result."""
    vault = _RecordingVault(tmp_path / "primary")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction()
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    for source_id in plan["source_ids"]:
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": source_id,
            },
        )
    assert set(plan["source_ids"]) == _due_adapter_source_ids - {
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
        "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
    }
    for source_id in plan["source_ids"]:
        payload_key = hk_v1_due_source_payload_key(instruction["cycle_id"], source_id)
        terminal_key = hk_v1_due_source_terminal_key(instruction["cycle_id"], source_id)
        payload = json.loads(vault.objects[payload_key])
        terminal = parse_hk_v1_due_terminal(vault.objects[terminal_key])
        assert payload["source_id"] == source_id
        assert payload["outcome"] == DueTerminalOutcome.INCOMPLETE_OBSERVATION.value
        assert payload["change_status"] == DueChangeStatus.NOT_PROVED.value
        assert payload["expected_count"] == payload["retained_count"] == 0
        assert "SOURCE_TECHNICAL_ADMISSION_MISSING" in payload["failure_codes"]
        assert "SOURCE_RIGHTS_ADMISSION_MISSING" in payload["failure_codes"]
        assert terminal.requirement.source_id == source_id
        assert terminal.outcome is DueTerminalOutcome.INCOMPLETE_OBSERVATION
        assert terminal.change_status is DueChangeStatus.NOT_PROVED
        assert terminal.attempt_manifest is not None
        assert terminal.attempt_manifest.logical_key == hk_v1_due_source_result_manifest_key(
            instruction["cycle_id"], source_id
        )
    assert {
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
        "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
    }.issubset(_due_adapter_source_ids)
    assert not any(source_id.startswith("HK-REG-HKEX-") for source_id in plan["source_ids"])


@pytest.mark.parametrize(
    "source_id",
    ["HK-LEG-NPC-NATIONAL-LAWS-DATABASE", "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS"],
)
def test_full_periodic_capture_cannot_invoke_dormant_npc_adapter(
    tmp_path: Path, source_id: str
) -> None:
    """Dormant adapter vocabulary cannot escape the Matrix-derived V1 plan."""
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    instruction = _instruction(DueCycleKind.FULL_PERIODIC)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)

    with pytest.raises(HongKongV1DueCycleError, match="DUE_SOURCE_NOT_DUE"):
        activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": source_id,
            },
        )


def test_capture_rejects_pseudo_source_and_cross_family_substitution(tmp_path: Path) -> None:
    """No family aggregate or foreign source can stand in for a closed adapter."""
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    for source_id, code in (
        ("HK-REG-HKEX", "DUE_SOURCE_ADAPTER_INVALID"),
        ("HK-LEG-HKEL-EDITORIAL-RECORDS", "DUE_SOURCE_NOT_DUE"),
        ("HK-CASE-JUDICIARY-LRS-INVENTORY-ALL", "DUE_SOURCE_ADAPTER_INVALID"),
    ):
        with pytest.raises(HongKongV1DueCycleError, match=code):
            activities.capture_hk_v1_due_source(
                _context(),
                {
                    "instruction": instruction,
                    "expected_plan_fingerprint": plan["plan_fingerprint"],
                    "source_id": source_id,
                },
            )


def test_capture_input_is_exact_and_never_accepts_typed_or_unknown_fields(tmp_path: Path) -> None:
    """Capture accepts only the closed JSON input, including its nested instruction."""
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    for value in (
        {"instruction": instruction, "expected_plan_fingerprint": plan["plan_fingerprint"]},
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
            "prior": {},
        },
        {
            "instruction": HongKongV1DueCycleInstruction.from_json(instruction),
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
        [instruction],
    ):
        with pytest.raises(HongKongV1DueCycleError, match="DUE_CAPTURE_INPUT_INVALID"):
            activities.capture_hk_v1_due_source(_context(), value)


def _registrar_ast_facts(
    path: Path, root: Path
) -> tuple[
    list[tuple[Path, int]],
    list[tuple[Path, str, str | None]],
    list[Path],
    list[Path],
    list[Path],
    list[Path],
    list[Path],
]:
    """Return every production-level spelling that could reach the registrar."""
    relative = path.relative_to(root)
    nodes = tuple(ast.walk(ast.parse(path.read_text(encoding="utf-8"))))
    calls = [
        (relative, node.lineno)
        for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_register_validated_acquisition_due_result_binding"
    ]
    imports = [
        (relative, alias.name, alias.asname)
        for node in nodes
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == "_register_validated_acquisition_due_result_binding"
    ]
    attributes = [
        relative
        for node in nodes
        if isinstance(node, ast.Attribute)
        and node.attr == "_register_validated_acquisition_due_result_binding"
    ]
    dynamic = [
        relative
        for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"getattr", "setattr"}
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "_register_validated_acquisition_due_result_binding"
    ]
    test_hooks = [
        relative
        for node in nodes
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == "issue_test_only_due_result_binding"
    ]
    aliases = [
        relative
        for node in nodes
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and isinstance(node.value, ast.Name)
        and node.value.id == "_register_validated_acquisition_due_result_binding"
    ]
    reexports = [
        relative
        for node in nodes
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
        and any(
            isinstance(value, ast.Constant)
            and value.value == "_register_validated_acquisition_due_result_binding"
            for value in ast.walk(node.value)
        )
    ]
    return calls, imports, attributes, dynamic, test_hooks, aliases, reexports


def test_registrar_has_one_static_acquisition_call_site_and_no_test_hook_import() -> None:
    """The one production issuer call stays repository-wide AST-reviewable."""
    module = Path(due_cycle.__file__).resolve()
    root = next(parent for parent in module.parents if (parent / "AGENTS.md").is_file())
    production_paths = tuple(
        path
        for directory in (root / "apps", root / "packages", root / "tools")
        for path in directory.rglob("*.py")
        if "tests" not in path.parts
    )
    facts = [_registrar_ast_facts(path, root) for path in production_paths]
    registrar_calls = [item for calls, *_ in facts for item in calls]
    private_imports = [item for _, imports, *_ in facts for item in imports]
    private_attribute_accesses = [item for _, _, attributes, *_ in facts for item in attributes]
    dynamic_private_accesses = [item for _, _, _, dynamic, *_ in facts for item in dynamic]
    test_hook_imports = [item for *_, test_hooks, _, _ in facts for item in test_hooks]
    registrar_aliases = [item for *_, aliases, _ in facts for item in aliases]
    registrar_reexports = [item for *_, reexports in facts for item in reexports]
    registrar_call_owners = [
        (path.relative_to(root), function.name)
        for path in production_paths
        for function in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_register_validated_acquisition_due_result_binding"
            for node in ast.walk(function)
        )
    ]
    issuance_proxies = [
        (path.relative_to(root), function.name)
        for path in production_paths
        for function in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
        and function.name == "_register_rebuilt_binding"
    ]
    acquisition_module = Path(
        "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py"
    )
    assert len(registrar_calls) == 1
    assert registrar_calls[0][0] == acquisition_module
    assert registrar_call_owners == [(acquisition_module, "_consume_retained_binding_proof")]
    assert private_imports == [
        (acquisition_module, "_register_validated_acquisition_due_result_binding", None)
    ]
    assert private_attribute_accesses == []
    assert dynamic_private_accesses == []
    assert test_hook_imports == []
    assert registrar_aliases == []
    assert registrar_reexports == []
    assert issuance_proxies == []


def _terminal_entry(result: dict[str, object]) -> dict[str, object]:
    reference = result["terminal_reference"]
    assert isinstance(reference, dict)
    source_id = result["source_id"]
    assert isinstance(source_id, str)
    return {"source_id": source_id, "reference": reference}


def test_failure_record_is_closed_and_assembly_reports_it_without_raw_diagnostics(
    tmp_path: Path,
) -> None:
    """A catch-path failure becomes an exact FAILED terminal, not an exception transcript."""
    vault = _RecordingVault(tmp_path / "failure")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    failed = activities.record_hk_v1_due_source_failure(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
            "failure_code": "DUE_SOURCE_ACTIVITY_FAILED",
        },
    )
    failed_source_id = failed["source_id"]
    assert isinstance(failed_source_id, str)
    payload = vault.objects[hk_v1_due_source_payload_key(instruction["cycle_id"], failed_source_id)]
    assert b"DUE_SOURCE_ACTIVITY_FAILED" in payload
    assert b"traceback" not in payload.lower()
    terminal = parse_hk_v1_due_terminal(
        vault.objects[hk_v1_due_source_terminal_key(instruction["cycle_id"], failed_source_id)]
    )
    assert terminal.outcome is DueTerminalOutcome.FAILED
    assert terminal.expected_count == terminal.failed_count == 1
    assembled = activities.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": [_terminal_entry(failed)],
        },
    )
    assert assembled["failed_source_ids"] == ["HK-LEG-GLD-EGAZETTE"]
    missing_source_ids = assembled["missing_source_ids"]
    assert isinstance(missing_source_ids, list)
    assert "HK-LEG-GLD-EGAZETTE" not in missing_source_ids


@pytest.mark.parametrize(
    ("operation", "nth", "lost_return"),
    [
        ("read", 1, False),
        ("create", 2, False),
        ("read", 2, False),
        ("create", 3, False),
        ("read", 3, False),
        ("create", 1, True),
        ("create", 2, True),
        ("create", 3, True),
    ],
)
def test_failure_record_recovers_coherent_partial_normal_chain_without_failed_overwrite(
    tmp_path: Path, operation: str, nth: int, lost_return: object
) -> None:
    """Normal payload/attempt/terminal partial writes are resumed, never replaced by FAILED."""
    assert type(lost_return) is bool
    vault = _OneStageFailureVault(
        tmp_path / f"{operation}-{nth}-{lost_return}", operation, nth, lost_return=lost_return
    )
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    request = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": "HK-LEG-GLD-EGAZETTE",
    }
    with pytest.raises(HongKongV1DueCycleError):
        activities.capture_hk_v1_due_source(_context(), request)
    vault.attempted_contents.clear()
    recovered = activities.record_hk_v1_due_source_failure(
        _context(), request | {"failure_code": "DUE_SOURCE_ACTIVITY_FAILED"}
    )
    source_id = "HK-LEG-GLD-EGAZETTE"
    payload = vault.objects[hk_v1_due_source_payload_key(instruction["cycle_id"], source_id)]
    terminal = parse_hk_v1_due_terminal(
        vault.objects[hk_v1_due_source_terminal_key(instruction["cycle_id"], source_id)]
    )
    assert b'"outcome":"FAILED"' not in payload
    assert all(b'"outcome":"FAILED"' not in content for content in vault.attempted_contents)
    assert terminal.outcome is DueTerminalOutcome.INCOMPLETE_OBSERVATION
    assert recovered["source_id"] == source_id


def test_failure_recovery_accepts_a_provider_version_resolved_reference(tmp_path: Path) -> None:
    """Recovery resolves a key through the vault instead of assuming local `v<sha>` IDs."""
    vault = _ProviderVersionRecoveryVault(tmp_path / "s3-shaped", "create", 2)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    request = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": "HK-LEG-GLD-EGAZETTE",
    }
    with pytest.raises(HongKongV1DueCycleError):
        activities.capture_hk_v1_due_source(_context(), request)
    recovered = activities.record_hk_v1_due_source_failure(
        _context(), request | {"failure_code": "DUE_SOURCE_ACTIVITY_FAILED"}
    )
    assert recovered["terminal_created"] is True


def test_due_cycle_creation_accepts_adapter_owned_provider_versions(tmp_path: Path) -> None:
    """Payload, attempt, terminal and final manifest never assume local version syntax."""
    vault = _ProviderVersionWriteVault(tmp_path / "provider-create")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    source_id = "HK-LEG-GLD-EGAZETTE"
    captured = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": source_id,
        },
    )
    assembled = activities.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": [
                {"source_id": source_id, "reference": captured["terminal_reference"]}
            ],
        },
    )
    assert assembled["manifest_reference"] != {}
    assert len(vault.writes) == 4


def test_receipt_snapshot_keeps_created_before_concurrent_receipt_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mutation after receipt validation cannot change the returned created flag."""
    vault = _RecordingVault(tmp_path / "receipt-race")
    content = b"exact"
    key = "fixed/receipt.json"
    receipt = vault.conditional_create(
        key, content, RetentionProfile("hk-v1-due-cycle", "2099-12-31T00:00:00Z")
    )
    original_sha256 = due_cycle.sha256

    def gated_sha256(value: bytes) -> object:
        object.__setattr__(receipt, "created", [])
        return original_sha256(value)

    monkeypatch.setattr(due_cycle, "sha256", gated_sha256)
    snapshot = _due_receipt_snapshot(receipt, key, content, "DUE_PAYLOAD_READBACK_INVALID")
    assert snapshot.created is True


def test_failure_recovery_resumes_normal_chain_after_stale_none_lookup_collision(
    tmp_path: Path,
) -> None:
    """A concurrent normal winner after a stale lookup is resumed rather than left missing."""
    vault = _StaleNoneResolveVault(tmp_path / "stale-none")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    request = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": "HK-LEG-GLD-EGAZETTE",
    }
    initial = activities.capture_hk_v1_due_source(_context(), request)
    recovered = activities.record_hk_v1_due_source_failure(
        _context(), request | {"failure_code": "DUE_SOURCE_ACTIVITY_FAILED"}
    )
    assert recovered["terminal_reference"] == initial["terminal_reference"]
    assert recovered["payload_created"] is False
    assert recovered["attempt_created"] is False
    assert recovered["terminal_created"] is False


def test_failure_recovery_normalizes_raw_retry_resolve_error_after_stale_none(
    tmp_path: Path,
) -> None:
    """Raw retry lookup failure normalizes to the closed payload error."""
    vault = _StaleNoneThenResolveErrorVault(tmp_path / "stale-error")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    request = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": "HK-LEG-GLD-EGAZETTE",
    }
    activities.capture_hk_v1_due_source(_context(), request)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_PAYLOAD_READBACK_INVALID"):
        activities.record_hk_v1_due_source_failure(
            _context(), request | {"failure_code": "DUE_SOURCE_ACTIVITY_FAILED"}
        )


def test_failure_recovery_rejects_wrong_retention_on_concurrent_normal_winner(
    tmp_path: Path,
) -> None:
    """A stale lookup never adopts matching bytes retained under a different policy."""
    vault = _StaleNoneWrongRetentionVault(tmp_path / "stale-wrong-retention")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    request = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": "HK-LEG-GLD-EGAZETTE",
    }
    activities.capture_hk_v1_due_source(_context(), request)

    with pytest.raises(HongKongV1DueCycleError, match="DUE_PAYLOAD_READBACK_INVALID"):
        activities.record_hk_v1_due_source_failure(
            _context(), request | {"failure_code": "DUE_SOURCE_ACTIVITY_FAILED"}
        )


@pytest.mark.parametrize("vault_kind", ["initial", "stale"])
def test_failure_recovery_rejects_foreign_equality_liar_retention(
    tmp_path: Path, vault_kind: str
) -> None:
    """Only an exact rebuilt retention profile may authorize resolved-chain adoption."""
    vault: _RecordingVault
    if vault_kind == "stale":
        vault = _StaleNoneLyingRetentionVault(tmp_path / "stale-liar-retention")
    else:
        vault = _LyingRetentionVault(tmp_path / "liar-retention")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    request = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": "HK-LEG-GLD-EGAZETTE",
    }
    activities.capture_hk_v1_due_source(_context(), request)

    with pytest.raises(HongKongV1DueCycleError, match="DUE_PAYLOAD_READBACK_INVALID"):
        activities.record_hk_v1_due_source_failure(
            _context(), request | {"failure_code": "DUE_SOURCE_ACTIVITY_FAILED"}
        )


@pytest.mark.parametrize(
    ("callback", "field"), [("retention", "logical_key"), ("read", "fingerprint")]
)
def test_failure_recovery_normalizes_mutated_callback_reference_without_writes(
    tmp_path: Path, callback: str, field: str
) -> None:
    """A vault callback cannot mutate the retained resolver snapshot or trigger failure writes."""
    vault = _MutatingResolvedReferenceVault(tmp_path / f"mutated-{callback}", callback, field)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    request = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": "HK-LEG-GLD-EGAZETTE",
    }
    activities.capture_hk_v1_due_source(_context(), request)
    writes_before = tuple(vault.writes)
    vault.armed = True

    if callback == "retention":
        with pytest.raises(HongKongV1DueCycleError, match="DUE_PAYLOAD_READBACK_INVALID"):
            activities.record_hk_v1_due_source_failure(
                _context(), request | {"failure_code": "DUE_SOURCE_ACTIVITY_FAILED"}
            )
    else:
        recovered = activities.record_hk_v1_due_source_failure(
            _context(), request | {"failure_code": "DUE_SOURCE_ACTIVITY_FAILED"}
        )
        assert recovered["payload_created"] is False
        assert all(b'"outcome":"FAILED"' not in content for content in vault.objects.values())
    if callback == "retention":
        assert tuple(vault.writes) == writes_before


@pytest.mark.parametrize(
    ("operation", "nth", "lost_return"),
    [
        ("create", 1, False),
        ("read", 1, False),
        ("create", 2, False),
        ("read", 2, False),
        ("create", 3, False),
        ("read", 3, False),
        ("create", 1, True),
        ("create", 2, True),
        ("create", 3, True),
    ],
)
def test_failure_chain_recovers_every_failed_payload_attempt_terminal_boundary(
    tmp_path: Path, operation: str, nth: int, lost_return: object
) -> None:
    """FAILED payload/attempt/terminal writes survive exact retry after every local boundary."""
    assert type(lost_return) is bool
    vault = _OneStageFailureVault(
        tmp_path / f"failed-{operation}-{nth}-{lost_return}",
        operation,
        nth,
        lost_return=lost_return,
    )
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    request = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": "HK-LEG-GLD-EGAZETTE",
        "failure_code": "DUE_SOURCE_ACTIVITY_FAILED",
    }
    with pytest.raises(HongKongV1DueCycleError):
        activities.record_hk_v1_due_source_failure(_context(), request)
    recovered = activities.record_hk_v1_due_source_failure(_context(), request)
    replay = activities.record_hk_v1_due_source_failure(_context(), request)
    assert recovered["source_id"] == replay["source_id"] == "HK-LEG-GLD-EGAZETTE"
    assert replay["payload_created"] is False
    assert replay["attempt_created"] is False
    assert replay["terminal_created"] is False


def _reconstructed_due_binding(tmp_path: Path) -> IssuedDueResultBinding:
    """Produce one acquisition-local reconstructed binding without consuming its proof."""
    vault = _RecordingVault(tmp_path / "proof")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan_body = activities.plan_hk_v1_due_cycle(_context(), instruction)
    plan = _due_plan(HongKongV1DueCycleInstruction.from_json(instruction))
    source_id = "HK-LEG-GLD-EGAZETTE"
    requirement = _due_requirement_for(plan, source_id)
    payload = _due_unadmitted_payload(plan, requirement)
    payload_key = hk_v1_due_source_payload_key(instruction["cycle_id"], source_id)
    receipt = vault.conditional_create(
        payload_key, payload, RetentionProfile("test", "2099-12-31T00:00:00Z")
    )
    binding = _due_binding_from_payload(
        payload, plan, requirement, _due_reference(receipt.reference)
    )
    attempt, _ = due_cycle.build_hk_v1_due_result_manifest(binding)
    assert plan_body["plan_fingerprint"] == plan.plan_fingerprint
    return _due_binding_from_attempt(attempt, binding)


def test_retained_proof_moves_authority_and_failed_consume_is_permanent(tmp_path: Path) -> None:
    """Mint and consume are both destructive: mutation failure cannot be restored and retried."""
    binding = _reconstructed_due_binding(tmp_path)
    assert id(binding) in _due_reconstructed_attempt_bindings
    proof = _due_retained_binding_proof(binding)
    assert id(binding) not in _due_reconstructed_attempt_bindings
    assert id(binding) in _due_retained_binding_proofs
    original = binding.plan_fingerprint
    object.__setattr__(binding, "plan_fingerprint", "sha256:" + ("0" * 64))
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RETAINED_BINDING_PROOF_INVALID"):
        _due_consume_retained_binding_proof(binding, proof)
    object.__setattr__(binding, "plan_fingerprint", original)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RETAINED_BINDING_PROOF_INVALID"):
        _due_consume_retained_binding_proof(binding, proof)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RETAINED_BINDING_PROOF_INVALID"):
        _due_retained_binding_proof(binding)


def test_retained_proof_successful_consume_is_permanent_and_gc_cleans_abandoned_proof(
    tmp_path: Path,
) -> None:
    """Neither a successful consume nor an abandoned proof leaves renewable authority."""
    binding = _reconstructed_due_binding(tmp_path / "success")
    proof = _due_retained_binding_proof(binding)
    assert _due_consume_retained_binding_proof(binding, proof) is binding
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RETAINED_BINDING_PROOF_INVALID"):
        _due_consume_retained_binding_proof(binding, proof)
    abandoned = _reconstructed_due_binding(tmp_path / "gc")
    abandoned_id = id(abandoned)
    abandoned_proof = _due_retained_binding_proof(abandoned)
    assert abandoned_id in _due_retained_binding_proofs
    del abandoned_proof
    del abandoned
    gc.collect()
    assert abandoned_id not in _due_retained_binding_proofs
    assert all(
        binding_id != abandoned_id for binding_id in _due_retained_proof_binding_ids.values()
    )
    reconstructed = _reconstructed_due_binding(tmp_path / "reconstructed-gc")
    reconstructed_id = id(reconstructed)
    assert reconstructed_id in _due_reconstructed_attempt_bindings
    del reconstructed
    gc.collect()
    assert reconstructed_id not in _due_reconstructed_attempt_bindings


def test_retained_proof_mutated_unhashable_binding_id_burns_authority(tmp_path: Path) -> None:
    """Proof lookup uses its immutable runtime identity, not a mutable field."""
    binding = _reconstructed_due_binding(tmp_path)
    proof = _due_retained_binding_proof(binding)
    original = proof.binding_id
    object.__setattr__(proof, "binding_id", [])
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RETAINED_BINDING_PROOF_INVALID"):
        _due_consume_retained_binding_proof(binding, proof)
    object.__setattr__(proof, "binding_id", original)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RETAINED_BINDING_PROOF_INVALID"):
        _due_consume_retained_binding_proof(binding, proof)


def test_retained_proof_rejects_second_mint_copy_and_concurrent_mint(tmp_path: Path) -> None:
    """Exactly one concurrent caller can move reconstruction authority into one proof."""
    binding = _reconstructed_due_binding(tmp_path)
    barrier = Barrier(2)
    results: list[object] = []

    def mint() -> None:
        barrier.wait()
        try:
            results.append(_due_retained_binding_proof(binding))
        except HongKongV1DueCycleError as error:
            results.append(error)

    first = Thread(target=mint)
    second = Thread(target=mint)
    first.start()
    second.start()
    first.join()
    second.join()
    proofs = [result for result in results if type(result).__name__ == "_RetainedBindingProof"]
    errors = [result for result in results if isinstance(result, HongKongV1DueCycleError)]
    assert len(proofs) == len(errors) == 1
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RETAINED_BINDING_PROOF_INVALID"):
        _due_consume_retained_binding_proof(binding, copy.copy(proofs[0]))
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RETAINED_BINDING_PROOF_INVALID"):
        _due_consume_retained_binding_proof(replace(binding), proofs[0])
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RETAINED_BINDING_PROOF_INVALID"):
        _due_consume_retained_binding_proof(binding, proofs[0])


def test_retained_proof_concurrent_consume_has_one_winner(tmp_path: Path) -> None:
    """The proof registry pop makes concurrent consume attempts one-winner only."""
    binding = _reconstructed_due_binding(tmp_path)
    proof = _due_retained_binding_proof(binding)
    barrier = Barrier(2)
    results: list[object] = []

    def consume() -> None:
        barrier.wait()
        try:
            results.append(_due_consume_retained_binding_proof(binding, proof))
        except HongKongV1DueCycleError as error:
            results.append(error)

    first = Thread(target=consume)
    second = Thread(target=consume)
    first.start()
    second.start()
    first.join()
    second.join()
    assert sum(result is binding for result in results) == 1
    assert sum(isinstance(result, HongKongV1DueCycleError) for result in results) == 1


def test_assembly_writes_manifest_last_and_adopts_identical_replay(tmp_path: Path) -> None:
    """All terminals precede the one fixed cycle manifest and identical replay adopts it."""
    vault = _RecordingVault(tmp_path / "assembly")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.FULL_PERIODIC)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    terminals = [
        _terminal_entry(
            activities.capture_hk_v1_due_source(
                _context(),
                {
                    "instruction": instruction,
                    "expected_plan_fingerprint": plan["plan_fingerprint"],
                    "source_id": source_id,
                },
            )
        )
        for source_id in plan["source_ids"]
    ]
    assembled = activities.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": list(reversed(terminals)),
        },
    )
    manifest_key = hk_v1_due_cycle_manifest_key(instruction["cycle_id"])
    assert vault.writes[-1] == manifest_key
    assert assembled["manifest_created"] is True
    assert assembled["predecessor_state_created"] is True
    assert type(assembled["predecessor_state_fingerprint"]) is str
    assert assembled["missing_source_ids"] == []
    assert assembled["duplicate_source_ids"] == []
    assert assembled["complete_source_ids"] == []
    assert assembled["failed_source_ids"] == sorted(plan["source_ids"])
    assert assembled["accounting_complete"] is True
    assert assembled["release_blocking"] is True
    repeated = activities.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": terminals,
        },
    )
    assert repeated["manifest_created"] is False
    assert repeated["manifest_reference"] == assembled["manifest_reference"]
    assert repeated["predecessor_state_created"] is False
    assert repeated["predecessor_state_fingerprint"] == assembled["predecessor_state_fingerprint"]


def test_assembly_keeps_failed_and_missing_distinct_and_rejects_unknown_terminal(
    tmp_path: Path,
) -> None:
    """The final report does not turn an absent failure record into a synthetic terminal."""
    vault = _RecordingVault(tmp_path / "missing")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    failed = activities.record_hk_v1_due_source_failure(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
            "failure_code": "DUE_SOURCE_ACTIVITY_FAILED",
        },
    )
    report = activities.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": [_terminal_entry(failed)],
        },
    )
    assert report["failed_source_ids"] == ["HK-LEG-GLD-EGAZETTE"]
    assert report["missing_source_ids"] == sorted(
        source_id for source_id in plan["source_ids"] if source_id != "HK-LEG-GLD-EGAZETTE"
    )
    forged = _terminal_entry(failed)
    forged["source_id"] = "HK-REG-HKEX"
    with pytest.raises(HongKongV1DueCycleError):
        activities.assemble_hk_v1_due_cycle(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "terminal_references": [forged],
            },
        )


def test_assembly_restart_replays_retained_terminal_attempt_and_payload(tmp_path: Path) -> None:
    """A fresh worker rebuilds the final report without a surviving weak registry."""
    root = tmp_path / "assembly-restart"
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    first = HongKongV1DueCycleActivities(
        LocalImmutableVault(root, VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    plan = first.plan_hk_v1_due_cycle(_context(), instruction)
    captured = first.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )
    initial = first.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": [_terminal_entry(captured)],
        },
    )
    del first
    gc.collect()
    replay = HongKongV1DueCycleActivities(
        LocalImmutableVault(root, VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    repeated = replay.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": [_terminal_entry(captured)],
        },
    )
    assert repeated["manifest_created"] is False
    assert repeated["manifest_reference"] == initial["manifest_reference"]


def test_assembly_reports_duplicate_terminal_reference_visibly(tmp_path: Path) -> None:
    """Duplicate supplied terminals remain visible rather than being silently deduplicated."""
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "duplicates", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    captured = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )
    report = activities.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": [_terminal_entry(captured), _terminal_entry(captured)],
        },
    )
    assert report["duplicate_source_ids"] == ["HK-LEG-GLD-EGAZETTE"]
    assert report["accounting_complete"] is False


def test_divergent_fixed_cycle_manifest_is_a_visible_collision_and_never_overwrites(
    tmp_path: Path,
) -> None:
    """A changed terminal set cannot silently adopt or replace a frozen cycle manifest."""
    vault = _RecordingVault(tmp_path / "manifest-collision")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    captured = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )
    entry = _terminal_entry(captured)
    initial = activities.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": [entry],
        },
    )
    manifest_key = hk_v1_due_cycle_manifest_key(instruction["cycle_id"])
    original = vault.objects[manifest_key]
    with pytest.raises(VaultCollision):
        activities.assemble_hk_v1_due_cycle(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "terminal_references": [entry, entry],
            },
        )
    assert vault.objects[manifest_key] == original
    assert vault.writes[-1] == manifest_key
    assert initial["manifest_created"] is True


@pytest.mark.parametrize(
    "field",
    [
        "created",
        "read_back_verified",
        "profile_id",
        "retain_until",
        "legal_hold",
        "vault",
        "logical_key",
        "version_id",
        "fingerprint",
        "byte_length",
    ],
)
def test_assembly_rejects_every_inexact_final_manifest_receipt_leaf(
    tmp_path: Path, field: str
) -> None:
    """The final receipt is rebuilt just as strictly as every source artifact receipt."""
    vault = _FaultyReceiptVault(tmp_path / field, field, nth=4)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    captured = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )
    with pytest.raises(HongKongV1DueCycleError, match="DUE_MANIFEST_READBACK_INVALID"):
        activities.assemble_hk_v1_due_cycle(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "terminal_references": [_terminal_entry(captured)],
            },
        )


@pytest.mark.parametrize(
    "replacement",
    [
        b"not-json",
        _BytesSubclass(b"not-exact-bytes"),
        FileNotFoundError("missing"),
        CorruptEvidence("corrupt"),
        RuntimeError("raw adapter diagnostic"),
    ],
)
def test_assembly_normalizes_raw_corrupt_and_error_final_manifest_reads(
    tmp_path: Path, replacement: bytes | Exception
) -> None:
    """No raw evidence/vault error can escape through the final-manifest boundary."""
    vault = _AssemblyReadFaultVault(tmp_path / str(type(replacement)), replacement)
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    captured = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )
    with pytest.raises(HongKongV1DueCycleError, match="DUE_MANIFEST_READBACK_INVALID"):
        activities.assemble_hk_v1_due_cycle(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "terminal_references": [_terminal_entry(captured)],
            },
        )


def test_assembly_normalizes_a_final_manifest_parser_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parser failure after an exact read-back remains a closed manifest failure."""
    vault = _RecordingVault(tmp_path / "parser")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    captured = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )

    def fail_parser(*_args: object) -> object:
        raise ValueError

    monkeypatch.setattr(due_cycle, "parse_hk_v1_due_cycle_report", fail_parser)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_MANIFEST_READBACK_INVALID"):
        activities.assemble_hk_v1_due_cycle(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "terminal_references": [_terminal_entry(captured)],
            },
        )


def _alter_reference_leaf(reference: object, leaf: str) -> object:
    """Return a syntactically shaped but semantically wrong immutable-reference leaf."""
    assert isinstance(reference, ExactObjectReference)
    mutations: dict[str, object] = {
        "vault": VaultName.RECOVERY,
        "logical_key": "wrong/retained-object.json",
        "version_id": "v" + ("0" * 64),
        "fingerprint": "sha256:" + ("0" * 64),
        "byte_length": reference.byte_length + 1,
    }
    return replace(reference, **{leaf: mutations[leaf]})


def _reference_body_for_content(logical_key: str, content: bytes) -> dict[str, JsonValue]:
    fingerprint = f"sha256:{due_cycle.sha256(content).hexdigest()}"
    return {
        "vault": VaultName.PRIMARY.value,
        "logical_key": logical_key,
        "version_id": f"v{fingerprint.removeprefix('sha256:')}",
        "fingerprint": fingerprint,
        "byte_length": len(content),
    }


@pytest.mark.parametrize(
    "leaf", ["vault", "logical_key", "version_id", "fingerprint", "byte_length"]
)
def test_assembly_rejects_every_nested_attempt_reference_leaf(tmp_path: Path, leaf: str) -> None:
    """Terminal -> attempt reconstruction distrusts every nested immutable-reference fact."""
    vault = _MappedReadVault(tmp_path / f"attempt-{leaf}", {})
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    captured = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": "HK-LEG-GLD-EGAZETTE",
        },
    )
    source_id = "HK-LEG-GLD-EGAZETTE"
    terminal_key = hk_v1_due_source_terminal_key(instruction["cycle_id"], source_id)
    parsed_terminal = parse_hk_v1_due_terminal(vault.objects[terminal_key])
    assert parsed_terminal.attempt_manifest is not None
    altered_attempt = _alter_reference_leaf(
        ExactObjectReference(
            VaultName(parsed_terminal.attempt_manifest.vault),
            parsed_terminal.attempt_manifest.logical_key,
            parsed_terminal.attempt_manifest.version_id,
            parsed_terminal.attempt_manifest.fingerprint,
            parsed_terminal.attempt_manifest.byte_length,
        ),
        leaf,
    )
    assert isinstance(altered_attempt, ExactObjectReference)
    altered_terminal = replace(parsed_terminal, attempt_manifest=_due_reference(altered_attempt))
    altered_terminal_bytes, _ = due_cycle.build_hk_v1_due_terminal(altered_terminal)
    vault.replace_read_content(terminal_key, altered_terminal_bytes)
    entry = {
        "source_id": source_id,
        "reference": _reference_body_for_content(terminal_key, altered_terminal_bytes),
    }
    with pytest.raises(HongKongV1DueCycleError, match="DUE_ATTEMPT_READBACK_INVALID"):
        activities.assemble_hk_v1_due_cycle(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "terminal_references": [entry],
            },
        )
    assert captured["source_id"] == source_id


@pytest.mark.parametrize(
    "leaf", ["vault", "logical_key", "version_id", "fingerprint", "byte_length"]
)
def test_assembly_rejects_every_nested_payload_reference_leaf(tmp_path: Path, leaf: str) -> None:
    """Attempt -> payload reconstruction distrusts every nested immutable-reference fact."""
    vault = _MappedReadVault(tmp_path / f"payload-{leaf}", {})
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    source_id = "HK-LEG-GLD-EGAZETTE"
    captured = activities.capture_hk_v1_due_source(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "source_id": source_id,
        },
    )
    attempt_key = hk_v1_due_source_result_manifest_key(instruction["cycle_id"], source_id)
    attempt_document = checked_json_value(json.loads(vault.objects[attempt_key]))
    assert isinstance(attempt_document, dict)
    payload_reference = attempt_document["payload_reference"]
    assert isinstance(payload_reference, dict)
    payload_vault = payload_reference["vault"]
    payload_key = payload_reference["logical_key"]
    payload_version = payload_reference["version_id"]
    payload_fingerprint = payload_reference["fingerprint"]
    payload_length = payload_reference["byte_length"]
    assert type(payload_vault) is str
    assert type(payload_key) is str
    assert type(payload_version) is str
    assert type(payload_fingerprint) is str
    assert type(payload_length) is int
    original_payload = ExactObjectReference(
        VaultName(payload_vault),
        payload_key,
        payload_version,
        payload_fingerprint,
        payload_length,
    )
    altered_payload = _alter_reference_leaf(original_payload, leaf)
    assert isinstance(altered_payload, ExactObjectReference)
    attempt_document["payload_reference"] = _reference_body_for_content(
        altered_payload.logical_key,
        vault.objects[hk_v1_due_source_payload_key(instruction["cycle_id"], source_id)],
    ) | {
        "vault": altered_payload.vault.value,
        "version_id": altered_payload.version_id,
        "fingerprint": altered_payload.fingerprint,
        "byte_length": altered_payload.byte_length,
    }
    altered_attempt_bytes = canonicalize(checked_json_value(attempt_document))
    terminal_key = hk_v1_due_source_terminal_key(instruction["cycle_id"], source_id)
    parsed_terminal = parse_hk_v1_due_terminal(vault.objects[terminal_key])
    altered_attempt_fingerprint = f"sha256:{due_cycle.sha256(altered_attempt_bytes).hexdigest()}"
    altered_attempt_reference = ExactObjectReference(
        VaultName.PRIMARY,
        attempt_key,
        f"v{altered_attempt_fingerprint.removeprefix('sha256:')}",
        altered_attempt_fingerprint,
        len(altered_attempt_bytes),
    )
    altered_terminal = replace(
        parsed_terminal,
        attempt_manifest=_due_reference(altered_attempt_reference),
    )
    altered_terminal_bytes, _ = due_cycle.build_hk_v1_due_terminal(altered_terminal)
    vault.replace_read_content(attempt_key, altered_attempt_bytes)
    vault.replace_read_content(terminal_key, altered_terminal_bytes)
    entry = {
        "source_id": source_id,
        "reference": _reference_body_for_content(terminal_key, altered_terminal_bytes),
    }
    with pytest.raises(HongKongV1DueCycleError, match="DUE_PAYLOAD_READBACK_INVALID"):
        activities.assemble_hk_v1_due_cycle(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "terminal_references": [entry],
            },
        )
    assert captured["source_id"] == source_id


def test_assembly_replays_terminal_attempt_payload_in_exact_order_before_final_write(
    tmp_path: Path,
) -> None:
    """Every source artifact is read terminal -> attempt -> payload before manifest creation."""
    vault = _OperationRecordingVault(tmp_path / "order")
    activities = HongKongV1DueCycleActivities(
        vault, LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    entries = [
        _terminal_entry(
            activities.capture_hk_v1_due_source(
                _context(),
                {
                    "instruction": instruction,
                    "expected_plan_fingerprint": plan["plan_fingerprint"],
                    "source_id": source_id,
                },
            )
        )
        for source_id in plan["source_ids"]
    ]
    vault.operations.clear()
    activities.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": list(reversed(entries)),
        },
    )
    expected_reads = [
        ("read", key)
        for entry in reversed(entries)
        for key in (
            hk_v1_due_source_terminal_key(instruction["cycle_id"], str(entry["source_id"])),
            hk_v1_due_source_result_manifest_key(instruction["cycle_id"], str(entry["source_id"])),
            hk_v1_due_source_payload_key(instruction["cycle_id"], str(entry["source_id"])),
        )
    ]
    manifest_key = hk_v1_due_cycle_manifest_key(instruction["cycle_id"])
    assert vault.operations[:-2] == expected_reads
    assert vault.operations[-2:] == [("write", manifest_key), ("read", manifest_key)]
    assert all(operation != ("write", manifest_key) for operation in vault.operations[:-2])


def test_failure_and_assembly_inputs_are_closed_against_raw_and_hostile_shapes(
    tmp_path: Path,
) -> None:
    """Failure and assembly activity boundaries reject malformed data without raw exceptions."""
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "input-hostile", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "predecessor"),
    )
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
    failure: dict[str, object] = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": "HK-LEG-GLD-EGAZETTE",
        "failure_code": "DUE_SOURCE_ACTIVITY_FAILED",
    }
    assembly: dict[str, object] = {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "terminal_references": [],
    }
    hostile_failure: tuple[object, ...] = (
        {},
        failure | {"raw_diagnostic": "traceback"},
        failure | {"failure_code": "DUE_SOURCE_ACTIVITY_FAILED: raw"},
        failure | {"source_id": _EqualityLiar("HK-LEG-GLD-EGAZETTE")},
        [failure],
    )
    invalid_terminal_references: object = object()
    missing_reference_entry: dict[str, object] = {"source_id": "HK-LEG-GLD-EGAZETTE"}
    missing_reference_list: list[object] = [missing_reference_entry]
    hostile_assembly: tuple[object, ...] = (
        object(),
        assembly | {"raw_diagnostic": "traceback"},
        assembly | {"terminal_references": invalid_terminal_references},
        assembly | {"expected_plan_fingerprint": _EqualityLiar(str(plan["plan_fingerprint"]))},
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": missing_reference_list,
        },
        [assembly],
    )
    for value in hostile_failure:
        with pytest.raises(HongKongV1DueCycleError, match="DUE_FAILURE_INPUT_INVALID"):
            activities.record_hk_v1_due_source_failure(_context(), value)
    for value in hostile_assembly:
        with pytest.raises(HongKongV1DueCycleError, match="DUE_ASSEMBLY_INPUT_INVALID"):
            activities.assemble_hk_v1_due_cycle(_context(), value)


def test_retained_issuance_gateway_has_only_reviewed_internal_call_sites() -> None:  # noqa: C901
    """No production module may import, alias, or dynamically reach the private issuer chain."""
    module = Path(due_cycle.__file__).resolve()
    root = next(parent for parent in module.parents if (parent / "AGENTS.md").is_file())
    acquisition_module = module.relative_to(root)
    gateway_names = {
        "_binding_from_retained_attempt",
        "_retained_binding_proof",
        "_consume_retained_binding_proof",
        "_persist_due_failure_chain",
    }
    paths = tuple(
        path
        for directory in (root / "apps", root / "packages", root / "tools")
        for path in directory.rglob("*.py")
        if "tests" not in path.parts
    )
    imports: list[tuple[Path, str]] = []
    attributes: list[tuple[Path, str]] = []
    dynamic: list[tuple[Path, str]] = []
    aliases: list[tuple[Path, str]] = []
    reexports: list[tuple[Path, str]] = []
    calls: dict[str, list[tuple[Path, str]]] = {name: [] for name in gateway_names}
    for path in paths:
        relative = path.relative_to(root)
        nodes = tuple(ast.walk(ast.parse(path.read_text(encoding="utf-8"))))
        for node in nodes:
            if isinstance(node, ast.ImportFrom):
                imports.extend(
                    (relative, alias.name) for alias in node.names if alias.name in gateway_names
                )
            if isinstance(node, ast.Attribute) and node.attr in gateway_names:
                attributes.append((relative, node.attr))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "setattr", "globals", "vars"}
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in gateway_names
            ):
                dynamic.append((relative, str(node.args[1].value)))
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id in {"globals", "vars", "locals"}
                and isinstance(node.slice, ast.Constant)
                and node.slice.value in gateway_names
            ):
                dynamic.append((relative, str(node.slice.value)))
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "__dict__"
                and isinstance(node.slice, ast.Constant)
                and node.slice.value in gateway_names
            ):
                dynamic.append((relative, str(node.slice.value)))
            if (
                isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
                and isinstance(node.value, ast.Name)
                and node.value.id in gateway_names
            ):
                aliases.append((relative, node.value.id))
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            ):
                reexports.extend(
                    (relative, value.value)
                    for value in ast.walk(node.value)
                    if isinstance(value, ast.Constant)
                    and type(value.value) is str
                    and value.value in gateway_names
                )
        for function in (
            item for item in nodes if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in gateway_names
                ):
                    calls[node.func.id].append((relative, function.name))
    assert imports == []
    assert attributes == []
    assert dynamic == []
    assert aliases == []
    assert reexports == []
    assert calls["_binding_from_retained_attempt"] == [
        (acquisition_module, "_persist_due_failure_chain"),
        (acquisition_module, "_replay_terminal_artifact"),
        (acquisition_module, "_capture_hk_v1_due_source"),
    ]
    assert calls["_retained_binding_proof"] == [
        (acquisition_module, "_persist_due_failure_chain"),
        (acquisition_module, "_replay_terminal_artifact"),
        (acquisition_module, "_capture_hk_v1_due_source"),
    ]
    assert calls["_consume_retained_binding_proof"] == [
        (acquisition_module, "_persist_due_failure_chain"),
        (acquisition_module, "_replay_terminal_artifact"),
        (acquisition_module, "_capture_hk_v1_due_source"),
    ]
    assert calls["_persist_due_failure_chain"] == [
        (acquisition_module, "_record_hk_v1_due_source_failure"),
    ]


def test_plan_uses_retained_predecessor_and_rejects_same_cycle_instruction_drift(
    tmp_path: Path,
) -> None:
    """Activity planning trusts only the stored consumed predecessor relation."""
    matrix = load_hk_v1_coverage_matrix()
    store = LocalDueCyclePredecessorStore(tmp_path / "predecessor")
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY), store
    )
    first_instruction = {
        "cycle_id": "hk-v1-daily-predecessor-20260826",
        "cycle_kind": DueCycleKind.DAILY_CURRENT_LAW.value,
        "scheduled_at": "2026-08-26T00:00:00Z",
        "observation_cutoff": "2026-08-26T00:00:00Z",
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
    }
    first_plan = activities.plan_hk_v1_due_cycle(_context(), first_instruction)
    first_state = DueCyclePredecessorState(
        HongKongV1DueCycleInstruction.from_json(first_instruction),
        str(first_plan["plan_fingerprint"]),
        None,
        DueImmutableReference(
            VaultName.PRIMARY.value,
            hk_v1_due_cycle_manifest_key(first_instruction["cycle_id"]),
            "v" + "a" * 64,
            "sha256:" + "a" * 64,
            1,
        ),
        "sha256:" + "a" * 64,
    )
    store.compare_and_set(None, first_state)

    successor_instruction = first_instruction | {
        "cycle_id": "hk-v1-daily-predecessor-20260827",
        "scheduled_at": "2026-08-27T00:00:00Z",
        "observation_cutoff": "2026-08-27T00:00:00Z",
    }
    successor_plan = activities.plan_hk_v1_due_cycle(_context(), successor_instruction)

    assert successor_plan["predecessor_fingerprint"] == first_state.state_fingerprint
    with pytest.raises(HongKongV1DueCycleError):
        activities.plan_hk_v1_due_cycle(
            _context(), first_instruction | {"observation_cutoff": "2026-08-27T00:00:00Z"}
        )


class _InjectedPredecessorStore:
    """A deliberately hostile store boundary for activity-only validation tests."""

    def __init__(
        self,
        loaded: object = None,
        receipt: object = None,
        load_error: Exception | None = None,
        cas_error: Exception | None = None,
    ) -> None:
        self.loaded = loaded
        self.receipt = receipt
        self.load_error = load_error
        self.cas_error = cas_error

    def load(self, kind: DueCycleKind) -> DueCyclePredecessorState | None:
        del kind
        if self.load_error is not None:
            raise self.load_error
        return cast("DueCyclePredecessorState | None", self.loaded)

    def compare_and_set(
        self, expected_fingerprint: str | None, new_state: DueCyclePredecessorState
    ) -> DueCyclePredecessorWriteReceipt:
        del expected_fingerprint
        if self.cas_error is not None:
            raise self.cas_error
        return cast(
            "DueCyclePredecessorWriteReceipt",
            DueCyclePredecessorWriteReceipt(new_state, created=True)
            if self.receipt is None
            else self.receipt,
        )


def test_activity_rejects_foreign_or_hostile_predecessor_store_state(tmp_path: Path) -> None:
    """A store result must be rebuilt and bound to the requested cycle kind."""
    matrix = load_hk_v1_coverage_matrix()
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    wrong_kind_instruction = HongKongV1DueCycleInstruction(
        "hk-v1-full-foreign-20260826",
        DueCycleKind.FULL_PERIODIC,
        "2026-08-26T00:00:00Z",
        "2026-08-26T00:00:00Z",
        matrix.revision,
        matrix.fingerprint,
    )
    wrong_kind = DueCyclePredecessorState(
        wrong_kind_instruction,
        "sha256:" + "a" * 64,
        None,
        DueImmutableReference(
            VaultName.PRIMARY.value,
            hk_v1_due_cycle_manifest_key(wrong_kind_instruction.cycle_id),
            "v" + "a" * 64,
            "sha256:" + "a" * 64,
            1,
        ),
        "sha256:" + "a" * 64,
    )
    forged_state = object.__new__(DueCyclePredecessorState)
    object.__setattr__(forged_state, "instruction", wrong_kind.instruction)
    object.__setattr__(forged_state, "plan_fingerprint", _EqualityLiar("sha256:" + "a" * 64))
    object.__setattr__(forged_state, "predecessor_fingerprint", None)
    object.__setattr__(forged_state, "manifest_reference", wrong_kind.manifest_reference)
    object.__setattr__(forged_state, "report_fingerprint", wrong_kind.report_fingerprint)
    object.__setattr__(forged_state, "state_fingerprint", wrong_kind.state_fingerprint)

    for store in (
        _InjectedPredecessorStore(wrong_kind),
        _InjectedPredecessorStore(forged_state),
        _InjectedPredecessorStore(load_error=RuntimeError("raw load error")),
    ):
        activities = HongKongV1DueCycleActivities(
            LocalImmutableVault(tmp_path / f"primary-{id(store)}", VaultName.PRIMARY), store
        )
        with pytest.raises(HongKongV1DueCycleError, match="DUE_PREDECESSOR_STATE_INVALID"):
            activities.plan_hk_v1_due_cycle(_context(), instruction)


def test_assembly_rejects_foreign_or_raw_predecessor_cas_receipt(tmp_path: Path) -> None:
    """Manifest publication cannot acknowledge an opaque or crashing CAS result."""
    instruction = _instruction(DueCycleKind.DAILY_CURRENT_LAW)
    for receipt, cas_error in ((object(), None), (None, RuntimeError("raw cas error"))):
        store = _InjectedPredecessorStore(receipt=receipt, cas_error=cas_error)
        activities = HongKongV1DueCycleActivities(
            LocalImmutableVault(tmp_path / f"primary-{id(store)}", VaultName.PRIMARY), store
        )
        plan = activities.plan_hk_v1_due_cycle(_context(), instruction)
        captured = activities.capture_hk_v1_due_source(
            _context(),
            {
                "instruction": instruction,
                "expected_plan_fingerprint": plan["plan_fingerprint"],
                "source_id": "HK-LEG-GLD-EGAZETTE",
            },
        )
        with pytest.raises(HongKongV1DueCycleError, match="DUE_PREDECESSOR_STATE_INVALID"):
            activities.assemble_hk_v1_due_cycle(
                _context(),
                {
                    "instruction": instruction,
                    "expected_plan_fingerprint": plan["plan_fingerprint"],
                    "terminal_references": [_terminal_entry(captured)],
                },
            )


def test_activity_constructor_rejects_an_unusable_predecessor_store(tmp_path: Path) -> None:
    """Only an object exposing both retained-state operations can enter the activity boundary."""
    with pytest.raises(ValueError, match="DUE_CYCLE_PREDECESSOR_STORE_REQUIRED"):
        HongKongV1DueCycleActivities(
            LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY), object()
        )
