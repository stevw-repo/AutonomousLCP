"""M2 conformance tests for the typed deterministic Management Register fake."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from enum import StrEnum
from hashlib import sha256

import pytest
from asklegal_domain import (
    ApplicationCode,
    CommandEnvelope,
    CommandPayload,
    CommandResultCode,
    CommandSubmissionResolutionCode,
    ContractReference,
    DestinationClass,
    EffectCancelledDetail,
    EffectCapability,
    EffectIntent,
    EffectReceipt,
    EffectReceiptStatus,
    EffectSuccessDetail,
    EffectType,
    ExpectedVersion,
    ImmutableReference,
    NoCompensation,
    ReferenceType,
    RetryClass,
    StopCondition,
)
from asklegal_management_register_ports import (
    CommandGuardDecision,
    CommandIdentityConflict,
    CommandTransaction,
    EffectAttemptEvent,
    EffectClaimConflict,
    InMemoryManagementRegister,
    ManagementRegisterStore,
    PolicyDecisionState,
    PolicyState,
    RecoveryDigestMismatch,
    StaleFencingToken,
)
from hypothesis import given
from hypothesis import strategies as st

_T0 = "2026-08-16T01:00:00Z"
_T1 = "2026-08-16T01:01:00Z"
_T2 = "2026-08-16T01:02:00Z"
_T3 = "2026-08-16T01:03:00Z"
_T4 = "2026-08-16T01:04:00Z"


class SyntheticCommand(StrEnum):
    """Closed test command catalogue."""

    APPLY = "APPLY"


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _reference(ref_type: ReferenceType, prefix: str, digit: str) -> ImmutableReference:
    return ImmutableReference(ref_type, f"{prefix}_{digit * 48}", _fingerprint(digit.encode()))


def _contract(digit: str) -> ContractReference:
    return ContractReference("asklegal.synthetic", "1.0.0", _fingerprint(digit.encode()))


def _transaction(
    digit: str,
    *,
    target_digit: str = "a",
    expected_version: int | ExpectedVersion = ExpectedVersion.ABSENT,
    result_code: CommandResultCode = CommandResultCode.APPLIED,
    winner_key: str | None = None,
    expires_at: str = "2026-08-16T01:10:00Z",
    with_effect: bool = False,
) -> CommandTransaction:
    raw = f'{{"command":"{digit}"}}'.encode()
    command_fingerprint = _fingerprint(raw)
    command_id = f"cmd_{digit * 48}"
    target = _reference(ReferenceType.AGGREGATE, "agg", target_digit)
    envelope = CommandEnvelope[StrEnum](
        command_id=command_id,
        command_type=SyntheticCommand.APPLY,
        contract_version="1.0.0",
        target_ref=target,
        expected_version=expected_version,
        actor_ref=_reference(ReferenceType.ACTOR, "act", "1"),
        authority_ref=_reference(ReferenceType.EVIDENCE, "evi", "2"),
        causation_ref=_reference(ReferenceType.EXECUTION_EVENT, "evt", "3"),
        correlation_id=f"run_{'4' * 48}",
        execution_lineage_ref=_reference(ReferenceType.EXECUTION_LINEAGE, "exe", "5"),
        input_refs=(_reference(ReferenceType.ARTIFACT, "art", "6"),),
        policy_profile_refs=(_reference(ReferenceType.POLICY_PROFILE, "pol", "7"),),
        configuration_ref=_reference(ReferenceType.CONFIGURATION, "cfg", "8"),
        contract_set_ref=_reference(ReferenceType.CONTRACT_SET, "cst", "9"),
        build_ref=_reference(ReferenceType.BUILD, "bld", "b"),
        submitted_at=_T0,
        expires_at=expires_at,
        payload=CommandPayload(_contract("c"), _reference(ReferenceType.ARTIFACT, "art", "d")),
    )
    effects = (_intent(command_id, command_fingerprint, target),) if with_effect else ()
    return CommandTransaction(
        envelope,
        raw,
        command_fingerprint,
        CommandGuardDecision(
            result_code,
            "SYNTHETIC_APPLIED" if result_code is CommandResultCode.APPLIED else None,
            winner_key,
        ),
        effects,
        (),
    )


def _intent(
    command_id: str,
    command_fingerprint: str,
    aggregate: ImmutableReference,
) -> EffectIntent:
    return EffectIntent(
        effect_intent_id=f"efi_{'e' * 48}",
        created_at=_T0,
        effect_type=EffectType.EVIDENCE_WRITE,
        owning_application=ApplicationCode.ACQUISITION_WORKER,
        aggregate_ref=aggregate,
        command_ref=ImmutableReference(ReferenceType.COMMAND, command_id, command_fingerprint),
        execution_lineage_ref=_reference(ReferenceType.EXECUTION_LINEAGE, "exe", "5"),
        permitted_checkpoint="EVIDENCE_VALIDATED",
        input_refs=(_reference(ReferenceType.ARTIFACT, "art", "6"),),
        effect_command_fingerprint=_fingerprint(b"effect"),
        required_capability=EffectCapability.WRITE_EVIDENCE,
        capability_profile_ref=_reference(ReferenceType.CAPABILITY_PROFILE, "cap", "7"),
        destination_class=DestinationClass.EVIDENCE_VAULT,
        stable_idempotency_key="synthetic-effect",
        retry_class=RetryClass.RECONCILE_BEFORE_RETRY,
        attempt_ceiling=2,
        deadline="2026-08-16T01:10:00Z",
        stop_conditions=(
            StopCondition.ATTEMPT_CEILING,
            StopCondition.CAPABILITY_INACTIVE,
            StopCondition.DEADLINE,
        ),
        expected_remote_precondition_ref=_contract("e"),
        success_postcondition_ref=_contract("f"),
        compensation=NoCompensation(),
    )


def _receipt(transaction: CommandTransaction, *, cancelled: bool = False) -> EffectReceipt:
    intent = transaction.effect_intents[0]
    evidence = (_reference(ReferenceType.EVIDENCE, "evi", "f"),)
    status = (
        EffectReceiptStatus.CANCELLED_BEFORE_EFFECT if cancelled else EffectReceiptStatus.SUCCEEDED
    )
    detail = (
        EffectCancelledDetail(evidence)
        if cancelled
        else EffectSuccessDetail("remote", "v1", "request", _fingerprint(b"response"), evidence)
    )
    return EffectReceipt(
        effect_receipt_id=f"efr_{'f' * 48}",
        effect_intent_ref=ImmutableReference(
            ReferenceType.EFFECT_INTENT,
            intent.effect_intent_id,
            intent.effect_command_fingerprint,
        ),
        command_ref=intent.command_ref,
        execution_lineage_ref=intent.execution_lineage_ref,
        terminal_status=status,
        attempt_count=0 if cancelled else 1,
        observed_at=_T2,
        evidence_refs=evidence,
        detail=detail,
    )


def test_fake_implements_typed_port_and_exact_replay() -> None:
    store: ManagementRegisterStore = InMemoryManagementRegister()
    transaction = _transaction("1")

    original = store.submit_command(transaction, now=_T1)
    replay = store.submit_command(transaction, now=_T1)
    resolved = store.resolve_command(
        transaction.envelope.command_id,
        transaction.command_fingerprint,
    )

    assert original.resolution is CommandSubmissionResolutionCode.RESULT_RECORDED
    assert replay.resolution is CommandSubmissionResolutionCode.EXACT_REPLAY
    assert replay.result is original.result
    assert replay.result_bytes == resolved.result_bytes == original.result_bytes


def test_reused_command_identity_with_different_bytes_never_executes() -> None:
    store = InMemoryManagementRegister()
    original = _transaction("1")
    store.submit_command(original, now=_T1)
    conflicting = replace(
        _transaction("2", target_digit="b"),
        envelope=replace(_transaction("2").envelope, command_id=original.envelope.command_id),
    )

    with pytest.raises(CommandIdentityConflict):
        store.submit_command(conflicting, now=_T1)
    assert len(store.events) == 1


@pytest.mark.parametrize(
    "code",
    [
        CommandResultCode.REJECTED_INVALID_INPUT,
        CommandResultCode.REJECTED_INVALID_STATE,
        CommandResultCode.REJECTED_UNAUTHORIZED,
        CommandResultCode.REJECTED_CAPABILITY,
    ],
)
def test_owner_guard_rejections_are_durable_and_append_no_facts(code: CommandResultCode) -> None:
    store = InMemoryManagementRegister()
    result = store.submit_command(_transaction("1", result_code=code), now=_T1).result

    assert result.result_code is code
    assert result.event_refs == result.effect_intent_refs == ()
    assert store.events == ()


def test_expiry_and_optimistic_version_are_register_enforced() -> None:
    store = InMemoryManagementRegister()
    expired = store.submit_command(
        _transaction("1", expires_at="2026-08-16T01:00:30Z"),
        now=_T1,
    )
    first = store.submit_command(_transaction("2", target_digit="b"), now=_T1)
    stale = store.submit_command(_transaction("3", target_digit="b"), now=_T1)

    assert expired.result.result_code is CommandResultCode.REJECTED_EXPIRED
    assert first.result.result_code is CommandResultCode.APPLIED
    assert stale.result.result_code is CommandResultCode.REJECTED_STALE_VERSION


def test_concurrent_single_winner_and_overlap_guard() -> None:
    store = InMemoryManagementRegister()

    def submit(transaction: CommandTransaction) -> CommandResultCode:
        return store.submit_command(transaction, now=_T1).result.result_code

    transactions = (
        _transaction("1", target_digit="a", winner_key="serving:development"),
        _transaction("2", target_digit="b", winner_key="serving:development"),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, transactions))

    assert results.count(CommandResultCode.APPLIED) == 1
    assert results.count(CommandResultCode.REJECTED_CONFLICT) == 1
    assert len(store.events) == 1


def test_concurrent_absent_version_has_one_applied_command() -> None:
    store = InMemoryManagementRegister()
    transactions = (_transaction("1"), _transaction("2"))

    def submit(transaction: CommandTransaction) -> CommandResultCode:
        return store.submit_command(transaction, now=_T1).result.result_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, transactions))

    assert results.count(CommandResultCode.APPLIED) == 1
    assert results.count(CommandResultCode.REJECTED_STALE_VERSION) == 1
    assert len(store.events) == 1


@given(st.lists(st.sampled_from(tuple("123456789abcdef")), min_size=1, max_size=10, unique=True))
def test_monotonic_versions_and_replay_hold_for_every_generated_sequence(
    digits: list[str],
) -> None:
    store = InMemoryManagementRegister()
    transactions = [
        _transaction(
            digit,
            expected_version=ExpectedVersion.ABSENT if index == 0 else index,
        )
        for index, digit in enumerate(digits)
    ]
    originals = [store.submit_command(transaction, now=_T1) for transaction in transactions]
    replays = [store.submit_command(transaction, now=_T2) for transaction in transactions]

    assert [submission.result.authoritative_version for submission in originals] == list(
        range(1, len(digits) + 1)
    )
    assert all(
        submission.resolution is CommandSubmissionResolutionCode.EXACT_REPLAY
        for submission in replays
    )
    assert len(store.events) == len(digits)


def test_precommit_failure_leaves_no_partial_event_or_result() -> None:
    store = InMemoryManagementRegister()
    first = _transaction("1", with_effect=True)
    store.submit_command(first, now=_T1)
    second = _transaction("2", target_digit="b", with_effect=True)

    with pytest.raises(ValueError, match="duplicate effect intent"):
        store.submit_command(second, now=_T1)

    assert len(store.events) == 1
    with pytest.raises(LookupError):
        store.resolve_command(second.envelope.command_id, second.command_fingerprint)


def test_effect_claim_expiry_fences_old_worker_and_receipt_replays() -> None:
    store = InMemoryManagementRegister()
    transaction = _transaction("1", with_effect=True)
    store.submit_command(transaction, now=_T1)
    intent_id = transaction.effect_intents[0].effect_intent_id
    old = store.claim_effect(
        intent_id,
        owning_application=ApplicationCode.ACQUISITION_WORKER,
        claimant_id="worker-old",
        now=_T1,
        lease_seconds=30,
    )
    current = store.claim_effect(
        intent_id,
        owning_application=ApplicationCode.ACQUISITION_WORKER,
        claimant_id="worker-new",
        now=_T2,
        lease_seconds=120,
    )
    event = EffectAttemptEvent(intent_id, 1, current.fencing_token, "STARTED", (), _T2)

    with pytest.raises(StaleFencingToken):
        store.append_effect_attempt(replace(event, fencing_token=old.fencing_token), now=_T2)
    store.append_effect_attempt(event, now=_T2)
    receipt = _receipt(transaction)
    selected = store.record_effect_receipt(
        receipt,
        fencing_token=current.fencing_token,
        now=_T2,
    )

    assert current.generation == old.generation + 1
    assert current.fencing_token == old.fencing_token + 1
    assert (
        store.record_effect_receipt(
            receipt,
            fencing_token=current.fencing_token,
            now=_T2,
        )
        is selected
    )


def test_claim_renewal_and_owner_boundary_fail_closed() -> None:
    store = InMemoryManagementRegister()
    transaction = _transaction("1", with_effect=True)
    store.submit_command(transaction, now=_T1)
    intent_id = transaction.effect_intents[0].effect_intent_id

    with pytest.raises(EffectClaimConflict, match="owner"):
        store.claim_effect(
            intent_id,
            owning_application=ApplicationCode.PROMOTION_WORKER,
            claimant_id="wrong-owner",
            now=_T1,
            lease_seconds=30,
        )
    claim = store.claim_effect(
        intent_id,
        owning_application=ApplicationCode.ACQUISITION_WORKER,
        claimant_id="worker",
        now=_T1,
        lease_seconds=120,
    )
    renewed = store.renew_effect_claim(
        intent_id,
        claimant_id="worker",
        fencing_token=claim.fencing_token,
        now=_T2,
        lease_seconds=120,
    )
    assert renewed.fencing_token == claim.fencing_token
    assert renewed.expires_at > claim.expires_at


def test_cancellation_is_allowed_only_before_effect_attempt() -> None:
    before_store = InMemoryManagementRegister()
    before = _transaction("1", with_effect=True)
    before_store.submit_command(before, now=_T1)
    receipt = _receipt(before, cancelled=True)
    assert before_store.record_effect_receipt(receipt, fencing_token=None, now=_T1) is receipt

    after_store = InMemoryManagementRegister()
    after = _transaction("2", with_effect=True)
    after_store.submit_command(after, now=_T1)
    intent_id = after.effect_intents[0].effect_intent_id
    claim = after_store.claim_effect(
        intent_id,
        owning_application=ApplicationCode.ACQUISITION_WORKER,
        claimant_id="worker",
        now=_T1,
        lease_seconds=120,
    )
    after_store.append_effect_attempt(
        EffectAttemptEvent(intent_id, 1, claim.fencing_token, "STARTED", (), _T1),
        now=_T1,
    )
    with pytest.raises(EffectClaimConflict, match="started"):
        after_store.record_effect_receipt(
            _receipt(after, cancelled=True),
            fencing_token=None,
            now=_T1,
        )


def test_projection_rebuild_and_digest_verified_recovery_replay() -> None:
    original = InMemoryManagementRegister()
    transaction = _transaction("1")
    first = original.submit_command(transaction, now=_T1)
    expected_projection = original.rebuild_projections()
    package = original.export_recovery(("000001", "000002"))
    restored = InMemoryManagementRegister()
    restored.restore_recovery(package)

    assert restored.rebuild_projections() == expected_projection
    assert (
        restored.resolve_command(
            transaction.envelope.command_id,
            transaction.command_fingerprint,
        ).result_bytes
        == first.result_bytes
    )

    with pytest.raises(RecoveryDigestMismatch):
        restored.restore_recovery(replace(package, external_digest=_fingerprint(b"wrong")))


def test_policy_state_is_never_implicitly_defaulted() -> None:
    store = InMemoryManagementRegister()
    policy_ref = _reference(ReferenceType.POLICY_PROFILE, "pol", "1")
    undecided = PolicyState(policy_ref, PolicyDecisionState.UNDECIDED, None)
    configured = PolicyState(
        policy_ref,
        PolicyDecisionState.CONFIGURED,
        _reference(ReferenceType.CONFIGURATION, "cfg", "2"),
    )

    store.set_policy_state(undecided)
    store.set_policy_state(configured)
    assert store.export_recovery(("000001",)).snapshot.policies == (undecided, configured)
