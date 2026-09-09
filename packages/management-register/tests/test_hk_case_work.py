"""Task 6A blocked Cases durable-work contract tests."""

import copy
import json
import pickle
from collections.abc import Callable, Iterator
from dataclasses import fields, replace
from hashlib import sha256

import pytest
from asklegal_management_register_ports.hk_case_work import (
    HKCaseWorkCheckpoint,
    HKCaseWorkCheckpointFactory,
    HKCaseWorkCheckpointStatus,
    HKCaseWorkError,
    HKCaseWorkErrorCode,
    HKCaseWorkIdentity,
    HKCaseWorkRequest,
    HKCaseWorkStage,
    InMemoryHKCaseWorkCheckpointStore,
    build_hk_case_work_identity,
    canonical_hk_case_work_checkpoint,
    replay_hk_case_work_checkpoint,
)

_FP_A = "sha256:" + "a" * 64
_FP_B = "sha256:" + "b" * 64
_BLOCKERS = (
    "AUTHENTIC_INVENTORY_NOT_ADMITTED",
    "CURRENT_AUTHORITY_NOT_ESTABLISHED",
    "REGISTER_IDENTITY_ISSUANCE_UNAVAILABLE",
    "SEMANTIC_WORKFLOW_NOT_ADMITTED",
    "SEMANTIC_CAPABILITY_DISABLED",
)
_PICKLE_LOADER_NAME = "loads"
_PICKLE_LOADS = getattr(pickle, _PICKLE_LOADER_NAME)


def _request(**changes: object) -> HKCaseWorkRequest:
    values: dict[str, object] = {
        "workflow_version": "hk-cases-work/v1",
        "source_cycle_ref": "cycle:a",
        "source_cycle_fingerprint": _FP_A,
        "accounting_checkpoint_ref": "accounting:a",
        "accounting_checkpoint_fingerprint": _FP_A,
        "withholding_checkpoint_ref": "withholding:a",
        "withholding_checkpoint_fingerprint": _FP_A,
        "listing_id": "listing-a",
        "stage": HKCaseWorkStage.PROPOSITION_DECISION,
        "subject_fingerprint": _FP_A,
        "input_fingerprint": _FP_A,
    }
    values.update(changes)
    stage = values["stage"]
    assert isinstance(stage, HKCaseWorkStage)
    text_values: dict[str, str] = {}
    for name, value in values.items():
        if name != "stage":
            assert isinstance(value, str)
            text_values[name] = value
    return HKCaseWorkRequest(
        text_values["workflow_version"],
        text_values["source_cycle_ref"],
        text_values["source_cycle_fingerprint"],
        text_values["accounting_checkpoint_ref"],
        text_values["accounting_checkpoint_fingerprint"],
        text_values["withholding_checkpoint_ref"],
        text_values["withholding_checkpoint_fingerprint"],
        text_values["listing_id"],
        stage,
        text_values["subject_fingerprint"],
        text_values["input_fingerprint"],
    )


def _checkpoint() -> tuple[HKCaseWorkCheckpointFactory, HKCaseWorkCheckpoint]:
    factory = HKCaseWorkCheckpointFactory()
    identity = build_hk_case_work_identity(_request())
    return factory, factory.issue_blocked(identity, _BLOCKERS)


def _record(
    store: InMemoryHKCaseWorkCheckpointStore, checkpoint: HKCaseWorkCheckpoint
) -> HKCaseWorkCheckpoint:
    return store.record_checkpoint(checkpoint, canonical_hk_case_work_checkpoint(checkpoint))


@pytest.mark.parametrize(
    ("field_name", "different"),
    [
        ("workflow_version", "hk-cases-work/v2"),
        ("source_cycle_ref", "cycle:b"),
        ("source_cycle_fingerprint", _FP_B),
        ("accounting_checkpoint_ref", "accounting:b"),
        ("accounting_checkpoint_fingerprint", _FP_B),
        ("withholding_checkpoint_ref", "withholding:b"),
        ("withholding_checkpoint_fingerprint", _FP_B),
        ("listing_id", "listing-b"),
        ("stage", HKCaseWorkStage.TREATMENT_DECISION),
        ("subject_fingerprint", _FP_B),
        ("input_fingerprint", _FP_B),
    ],
)
def test_identity_binds_every_opaque_fact(field_name: str, different: object) -> None:
    """Changing any authority-bearing primitive changes the work ID."""
    baseline = build_hk_case_work_identity(_request()).work_item_id
    assert build_hk_case_work_identity(_request(**{field_name: different})).work_item_id != baseline


def test_request_schema_coverage_and_exact_types_are_closed() -> None:
    """A new field or a caller-controlled subtype cannot escape the identity projection."""
    assert tuple(field.name for field in fields(HKCaseWorkRequest)) == (
        "workflow_version",
        "source_cycle_ref",
        "source_cycle_fingerprint",
        "accounting_checkpoint_ref",
        "accounting_checkpoint_fingerprint",
        "withholding_checkpoint_ref",
        "withholding_checkpoint_fingerprint",
        "listing_id",
        "stage",
        "subject_fingerprint",
        "input_fingerprint",
    )

    class RequestSubclass(HKCaseWorkRequest):
        pass

    original = _request()
    subclass = RequestSubclass(
        original.workflow_version,
        original.source_cycle_ref,
        original.source_cycle_fingerprint,
        original.accounting_checkpoint_ref,
        original.accounting_checkpoint_fingerprint,
        original.withholding_checkpoint_ref,
        original.withholding_checkpoint_fingerprint,
        original.listing_id,
        original.stage,
        original.subject_fingerprint,
        original.input_fingerprint,
    )
    with pytest.raises(HKCaseWorkError) as caught:
        build_hk_case_work_identity(subclass)
    assert caught.value.code is HKCaseWorkErrorCode.REQUEST_INVALID
    hostile_text = type("Text", (str,), {})("listing-a")
    with pytest.raises(HKCaseWorkError):
        build_hk_case_work_identity(_request(listing_id=hostile_text))


@pytest.mark.parametrize(
    ("field_name", "unsafe"),
    [
        ("source_cycle_ref", "https://example.invalid/cycle"),
        ("accounting_checkpoint_ref", "accounting reference with text"),
        ("withholding_checkpoint_ref", "withholding\ncheckpoint"),
        ("listing_id", "full judgment text must remain evidence only"),
    ],
)
def test_opaque_refs_reject_urls_whitespace_and_source_text(field_name: str, unsafe: str) -> None:
    """Scheduler-safe opaque references cannot carry URLs or legal text."""
    with pytest.raises(HKCaseWorkError) as caught:
        build_hk_case_work_identity(_request(**{field_name: unsafe}))
    assert caught.value.code is HKCaseWorkErrorCode.REQUEST_INVALID


def test_hostile_equality_and_container_hooks_are_never_invoked() -> None:
    """Exact-type gates reject callback-bearing primitives before comparison or iteration."""

    class HookInvoked(BaseException):
        pass

    class HostileText:
        def __eq__(self, other: object) -> bool:
            del other
            raise HookInvoked

        def __repr__(self) -> str:
            raise HookInvoked

        def __str__(self) -> str:
            raise HookInvoked

        def __hash__(self) -> int:
            raise HookInvoked

    request = _request()
    object.__setattr__(request, "listing_id", HostileText())
    with pytest.raises(HKCaseWorkError) as caught:
        build_hk_case_work_identity(request)
    assert caught.value.code is HKCaseWorkErrorCode.REQUEST_INVALID

    class HostileCodes(tuple[str, ...]):
        __slots__ = ()

        def __iter__(self) -> Iterator[str]:
            raise HookInvoked

    factory, checkpoint = _checkpoint()
    with pytest.raises(HKCaseWorkError) as container:
        factory.issue_blocked(checkpoint.identity, HostileCodes(_BLOCKERS))
    assert container.value.code is HKCaseWorkErrorCode.CHECKPOINT_INVALID


def test_factory_issuance_is_identity_bound_and_not_transferable() -> None:
    """Copies can replay durable facts but cannot become factory-issued objects."""
    factory, checkpoint = _checkpoint()
    assert factory.assert_issued(checkpoint) is checkpoint
    for detached in (
        copy.copy(checkpoint),
        copy.deepcopy(checkpoint),
        replace(checkpoint),
        _PICKLE_LOADS(pickle.dumps(checkpoint)),
    ):
        assert canonical_hk_case_work_checkpoint(detached) == canonical_hk_case_work_checkpoint(
            checkpoint
        )
        with pytest.raises(HKCaseWorkError) as caught:
            factory.assert_issued(detached)
        assert caught.value.code is HKCaseWorkErrorCode.REPLAY_MISMATCH


@pytest.mark.parametrize("operation", [copy.copy, copy.deepcopy, pickle.dumps])
def test_factory_itself_cannot_be_copied_or_serialized(
    operation: Callable[[object], object],
) -> None:
    """Factory provenance cannot be reconstructed from caller-controlled bytes."""
    with pytest.raises(HKCaseWorkError) as caught:
        operation(HKCaseWorkCheckpointFactory())
    assert caught.value.code is HKCaseWorkErrorCode.REPLAY_MISMATCH


def test_checkpoint_replay_copy_replace_and_canonical_bytes_are_exact() -> None:
    """Every durable reconstruction has one canonical negative projection."""
    _, checkpoint = _checkpoint()
    canonical = canonical_hk_case_work_checkpoint(checkpoint)
    assert replay_hk_case_work_checkpoint(checkpoint) is checkpoint
    assert canonical_hk_case_work_checkpoint(copy.copy(checkpoint)) == canonical
    assert canonical_hk_case_work_checkpoint(copy.deepcopy(checkpoint)) == canonical
    assert canonical_hk_case_work_checkpoint(replace(checkpoint)) == canonical
    assert canonical_hk_case_work_checkpoint(_PICKLE_LOADS(pickle.dumps(checkpoint))) == canonical
    assert b"WITHHELD_NOT_PROCESSED" not in canonical
    assert b"BLOCKED_SEMANTIC_CAPABILITY_DISABLED" in canonical


@pytest.mark.parametrize(
    "invalid_blockers",
    [
        (),
        ("SEMANTIC_CAPABILITY_DISABLED",),
        (*_BLOCKERS, "UNKNOWN_BLOCKER"),
        tuple(reversed(_BLOCKERS)),
        (*_BLOCKERS, "SEMANTIC_CAPABILITY_DISABLED"),
    ],
)
def test_factory_requires_exact_complete_ordered_blocker_inventory(
    invalid_blockers: tuple[str, ...],
) -> None:
    """No empty, subset, superset, reordered, or duplicate blockers can be issued."""
    factory = HKCaseWorkCheckpointFactory()
    identity = build_hk_case_work_identity(_request())
    with pytest.raises(HKCaseWorkError) as caught:
        factory.issue_blocked(identity, invalid_blockers)
    assert caught.value.code is HKCaseWorkErrorCode.CHECKPOINT_INVALID


def test_replay_rejects_coherently_resealed_incomplete_blockers() -> None:
    """A matching digest cannot turn an incomplete blocker set into a valid checkpoint."""
    _, checkpoint = _checkpoint()
    document = json.loads(canonical_hk_case_work_checkpoint(checkpoint))
    document["blocker_codes"] = ["SEMANTIC_CAPABILITY_DISABLED"]
    document.pop("checkpoint_fingerprint")
    encoded = json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    object.__setattr__(checkpoint, "blocker_codes", ("SEMANTIC_CAPABILITY_DISABLED",))
    object.__setattr__(
        checkpoint, "checkpoint_fingerprint", f"sha256:{sha256(encoded).hexdigest()}"
    )
    with pytest.raises(HKCaseWorkError) as caught:
        replay_hk_case_work_checkpoint(checkpoint)
    assert caught.value.code is HKCaseWorkErrorCode.CHECKPOINT_INVALID


@pytest.mark.parametrize(
    "field_name",
    [
        "source_cycle_fingerprint",
        "accounting_checkpoint_fingerprint",
        "withholding_checkpoint_fingerprint",
        "subject_fingerprint",
        "input_fingerprint",
    ],
)
def test_uppercase_fingerprint_spelling_cannot_split_work_identity(field_name: str) -> None:
    """One digest has only the lowercase canonical spelling and one work ID."""
    lowercase = build_hk_case_work_identity(_request()).work_item_id
    assert lowercase == build_hk_case_work_identity(_request()).work_item_id
    with pytest.raises(HKCaseWorkError) as caught:
        build_hk_case_work_identity(_request(**{field_name: "sha256:" + "A" * 64}))
    assert caught.value.code is HKCaseWorkErrorCode.REQUEST_INVALID


def test_store_adopts_once_and_recreated_service_replays_detached_state() -> None:
    """Retained port state survives service-object recreation without live Task objects."""
    _, checkpoint = _checkpoint()
    store = InMemoryHKCaseWorkCheckpointStore()
    adopted = _record(store, checkpoint)
    assert canonical_hk_case_work_checkpoint(_record(store, copy.deepcopy(checkpoint))) == (
        canonical_hk_case_work_checkpoint(adopted)
    )
    restarted_service_store = store
    replayed = restarted_service_store.get_checkpoint(checkpoint.identity.work_item_id)
    assert canonical_hk_case_work_checkpoint(replayed) == canonical_hk_case_work_checkpoint(adopted)
    assert replayed is not adopted


def test_same_work_id_with_divergent_checkpoint_is_conflict() -> None:
    """A valid divergent stored value never overwrites or aliases the requested storage key."""
    _, checkpoint = _checkpoint()
    store = InMemoryHKCaseWorkCheckpointStore()
    _record(store, checkpoint)
    divergent_factory = HKCaseWorkCheckpointFactory()
    divergent = divergent_factory.issue_blocked(
        build_hk_case_work_identity(_request(listing_id="listing-b")), _BLOCKERS
    )
    values = object.__getattribute__(store, "_values")
    values[checkpoint.identity.work_item_id] = divergent
    with pytest.raises(HKCaseWorkError) as caught:
        _record(store, checkpoint)
    assert caught.value.code is HKCaseWorkErrorCode.IDENTITY_CONFLICT


def test_missing_and_mutated_checkpoint_fail_closed() -> None:
    """Missing or changed state cannot become a completed or supported-zero result."""
    store = InMemoryHKCaseWorkCheckpointStore()
    with pytest.raises(HKCaseWorkError) as missing:
        store.get_checkpoint("hk-case-work:missing")
    assert missing.value.code is HKCaseWorkErrorCode.CHECKPOINT_MISSING
    _, checkpoint = _checkpoint()
    object.__setattr__(checkpoint, "checkpoint_fingerprint", _FP_A)
    with pytest.raises(HKCaseWorkError) as invalid:
        replay_hk_case_work_checkpoint(checkpoint)
    assert invalid.value.code is HKCaseWorkErrorCode.CHECKPOINT_INVALID


def test_checkpoint_subclasses_and_hostile_containers_reject() -> None:
    """Caller subtype hooks and tuple subclasses never enter canonicalization."""
    _, checkpoint = _checkpoint()

    class CheckpointSubclass(HKCaseWorkCheckpoint):
        pass

    with pytest.raises(HKCaseWorkError):
        CheckpointSubclass(
            checkpoint.identity,
            checkpoint.status,
            checkpoint.blocker_codes,
            None,
            None,
            checkpoint.checkpoint_fingerprint,
        )
    factory = HKCaseWorkCheckpointFactory()
    hostile_codes = type("Codes", (tuple,), {})(_BLOCKERS)
    with pytest.raises(HKCaseWorkError) as caught:
        factory.issue_blocked(checkpoint.identity, hostile_codes)
    assert caught.value.code is HKCaseWorkErrorCode.CHECKPOINT_INVALID


def test_checkpoint_subclass_property_trap_rejects_before_access() -> None:
    """Exact outer type rejection occurs before a hostile inherited field property can run."""

    class PropertyInvoked(BaseException):
        pass

    def trap_identity(value: object) -> HKCaseWorkIdentity:
        del value
        raise PropertyInvoked

    checkpoint_type = type(
        "PropertyCheckpoint",
        (HKCaseWorkCheckpoint,),
        {"__slots__": (), "identity": property(trap_identity)},
    )
    hostile = object.__new__(checkpoint_type)
    assert isinstance(hostile, HKCaseWorkCheckpoint)
    with pytest.raises(HKCaseWorkError) as caught:
        replay_hk_case_work_checkpoint(hostile)
    assert caught.value.code is HKCaseWorkErrorCode.CHECKPOINT_INVALID


def test_no_positive_checkpoint_surface_exists() -> None:
    """Task 6A has no completed, release, READY, or result-bearing terminal."""
    assert tuple(HKCaseWorkCheckpointStatus) == (
        HKCaseWorkCheckpointStatus.BLOCKED_SEMANTIC_CAPABILITY_DISABLED,
    )
    _, checkpoint = _checkpoint()
    assert checkpoint.result_ref is None
    assert checkpoint.result_fingerprint is None
    assert not any(
        word in checkpoint.status.value
        for word in ("COMPLETED", "READY", "RELEASED", "AUTHENTIC", "CANDIDATE")
    )


def test_caller_supplied_positive_result_is_explicitly_unsupported() -> None:
    """A supplied result reference is refusal, never malformed data repaired to blocked work."""
    _, checkpoint = _checkpoint()
    positive = object.__new__(HKCaseWorkCheckpoint)
    for name, value in (
        ("identity", checkpoint.identity),
        ("status", checkpoint.status),
        ("blocker_codes", checkpoint.blocker_codes),
        ("result_ref", "candidate:forbidden"),
        ("result_fingerprint", _FP_A),
        ("checkpoint_fingerprint", checkpoint.checkpoint_fingerprint),
    ):
        object.__setattr__(positive, name, value)
    with pytest.raises(HKCaseWorkError) as caught:
        positive.__post_init__()
    assert caught.value.code is HKCaseWorkErrorCode.POSITIVE_RESULT_UNSUPPORTED


def test_identity_and_checkpoint_direct_reseal_cannot_gain_factory_issuance() -> None:
    """Byte-identical direct objects remain detached facts, never issuance proof."""
    factory, checkpoint = _checkpoint()
    direct_identity = HKCaseWorkIdentity(
        checkpoint.identity.work_item_id,
        checkpoint.identity.workflow_version,
        checkpoint.identity.source_cycle_ref,
        checkpoint.identity.source_cycle_fingerprint,
        checkpoint.identity.accounting_checkpoint_ref,
        checkpoint.identity.accounting_checkpoint_fingerprint,
        checkpoint.identity.withholding_checkpoint_ref,
        checkpoint.identity.withholding_checkpoint_fingerprint,
        checkpoint.identity.listing_id,
        checkpoint.identity.stage,
        checkpoint.identity.subject_fingerprint,
        checkpoint.identity.input_fingerprint,
    )
    direct = HKCaseWorkCheckpoint(
        direct_identity,
        checkpoint.status,
        checkpoint.blocker_codes,
        None,
        None,
        checkpoint.checkpoint_fingerprint,
    )
    assert canonical_hk_case_work_checkpoint(direct) == canonical_hk_case_work_checkpoint(
        checkpoint
    )
    with pytest.raises(HKCaseWorkError) as caught:
        factory.assert_issued(direct)
    assert caught.value.code is HKCaseWorkErrorCode.REPLAY_MISMATCH
