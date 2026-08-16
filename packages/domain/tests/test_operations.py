"""Conformance tests for immutable M2 command and effect domain objects."""

from dataclasses import FrozenInstanceError
from enum import StrEnum

import pytest
from asklegal_domain import (
    ApplicationCode,
    CommandEnvelope,
    CommandPayload,
    CommandResult,
    CommandResultCode,
    CommandSubmissionResolutionCode,
    ContractReference,
    DestinationClass,
    EffectCancelledDetail,
    EffectCapability,
    EffectFinalFailureDetail,
    EffectIntent,
    EffectReceipt,
    EffectReceiptDetail,
    EffectReceiptStatus,
    EffectSuccessDetail,
    EffectType,
    EffectUnknownDetail,
    ExpectedVersion,
    FailureCode,
    ImmutableReference,
    NoCompensation,
    ReferenceType,
    RetryClass,
    StopCondition,
)


class SyntheticCommandType(StrEnum):
    """One closed test-only command type."""

    START_SYNTHETIC_WORK = "START_SYNTHETIC_WORK"


def _fingerprint(digit: str) -> str:
    return f"sha256:{digit * 64}"


def _reference(ref_type: ReferenceType, prefix: str, digit: str) -> ImmutableReference:
    return ImmutableReference(ref_type, f"{prefix}_{digit * 48}", _fingerprint(digit))


def _contract(digit: str) -> ContractReference:
    return ContractReference("asklegal.synthetic-contract", "1.0.0", _fingerprint(digit))


def _command() -> CommandEnvelope[SyntheticCommandType]:
    return CommandEnvelope(
        command_id=f"cmd_{'1' * 48}",
        command_type=SyntheticCommandType.START_SYNTHETIC_WORK,
        contract_version="1.0.0",
        target_ref=_reference(ReferenceType.AGGREGATE, "wki", "2"),
        expected_version=ExpectedVersion.ABSENT,
        actor_ref=_reference(ReferenceType.ACTOR, "act", "3"),
        authority_ref=_reference(ReferenceType.EVIDENCE, "evi", "4"),
        causation_ref=_reference(ReferenceType.EXECUTION_EVENT, "pex", "5"),
        correlation_id=f"run_{'6' * 48}",
        execution_lineage_ref=None,
        input_refs=(_reference(ReferenceType.ARTIFACT, "art", "7"),),
        policy_profile_refs=(_reference(ReferenceType.POLICY_PROFILE, "pol", "8"),),
        configuration_ref=_reference(ReferenceType.CONFIGURATION, "cfg", "9"),
        contract_set_ref=_reference(ReferenceType.CONTRACT_SET, "cst", "a"),
        build_ref=_reference(ReferenceType.BUILD, "bld", "b"),
        submitted_at="2026-08-16T01:00:00Z",
        expires_at="2026-08-16T01:05:00Z",
        payload=CommandPayload(
            payload_contract_ref=_contract("c"),
            payload_object_ref=_reference(ReferenceType.ARTIFACT, "art", "d"),
        ),
    )


def _effect_intent() -> EffectIntent:
    return EffectIntent(
        effect_intent_id=f"efi_{'1' * 48}",
        created_at="2026-08-16T01:00:00Z",
        effect_type=EffectType.EVIDENCE_WRITE,
        owning_application=ApplicationCode.ACQUISITION_WORKER,
        aggregate_ref=_reference(ReferenceType.AGGREGATE, "wki", "2"),
        command_ref=_reference(ReferenceType.COMMAND, "cmd", "3"),
        execution_lineage_ref=_reference(ReferenceType.EXECUTION_LINEAGE, "exe", "4"),
        permitted_checkpoint="EVIDENCE_VALIDATED",
        input_refs=(_reference(ReferenceType.ARTIFACT, "art", "5"),),
        effect_command_fingerprint=_fingerprint("6"),
        required_capability=EffectCapability.WRITE_EVIDENCE,
        capability_profile_ref=_reference(ReferenceType.CAPABILITY_PROFILE, "cap", "7"),
        destination_class=DestinationClass.EVIDENCE_VAULT,
        stable_idempotency_key="synthetic-effect-1",
        retry_class=RetryClass.RECONCILE_BEFORE_RETRY,
        attempt_ceiling=3,
        deadline="2026-08-16T01:10:00Z",
        stop_conditions=(
            StopCondition.ATTEMPT_CEILING,
            StopCondition.CAPABILITY_INACTIVE,
            StopCondition.DEADLINE,
        ),
        expected_remote_precondition_ref=_contract("8"),
        success_postcondition_ref=_contract("9"),
        compensation=NoCompensation(),
    )


def _receipt(
    detail: EffectReceiptDetail,
    status: EffectReceiptStatus,
    attempts: int,
) -> EffectReceipt:
    return EffectReceipt(
        effect_receipt_id=f"efr_{'1' * 48}",
        effect_intent_ref=_reference(ReferenceType.EFFECT_INTENT, "efi", "2"),
        command_ref=_reference(ReferenceType.COMMAND, "cmd", "3"),
        execution_lineage_ref=_reference(ReferenceType.EXECUTION_LINEAGE, "exe", "4"),
        terminal_status=status,
        attempt_count=attempts,
        observed_at="2026-08-16T01:02:00Z",
        evidence_refs=(_reference(ReferenceType.EVIDENCE, "evi", "5"),),
        detail=detail,
    )


def test_command_is_closed_immutable_and_authority_bound() -> None:
    command = _command()

    assert command.command_type is SyntheticCommandType.START_SYNTHETIC_WORK
    assert command.expected_version is ExpectedVersion.ABSENT
    assert command.execution_lineage_ref is None
    with pytest.raises(FrozenInstanceError):
        command.__setattr__("command_id", f"cmd_{'f' * 48}")


@pytest.mark.parametrize("invalid_version", [True, False, -1, 1.5])
def test_command_rejects_non_exact_or_negative_expected_versions(
    invalid_version: object,
) -> None:
    command = _command()
    object.__setattr__(command, "expected_version", invalid_version)

    with pytest.raises((TypeError, ValueError), match="expected_version"):
        command.__post_init__()


def test_command_rejects_unsorted_or_duplicate_input_references() -> None:
    command = _command()
    high = _reference(ReferenceType.ARTIFACT, "art", "f")
    low = _reference(ReferenceType.ARTIFACT, "art", "1")

    object.__setattr__(command, "input_refs", (high, low))
    with pytest.raises(ValueError, match="sorted"):
        command.__post_init__()

    object.__setattr__(command, "input_refs", (low, low))
    with pytest.raises(ValueError, match="duplicate"):
        command.__post_init__()


def test_command_requires_a_future_expiry_and_exact_authority_reference() -> None:
    command = _command()
    object.__setattr__(command, "expires_at", command.submitted_at)
    with pytest.raises(ValueError, match="later"):
        command.__post_init__()

    object.__setattr__(
        command,
        "authority_ref",
        _reference(ReferenceType.ACTOR, "act", "4"),
    )
    with pytest.raises(ValueError, match="authority_ref"):
        command.__post_init__()


def test_reference_identity_prefix_must_match_its_declared_type() -> None:
    with pytest.raises(ValueError, match="prefix"):
        ImmutableReference(
            ReferenceType.ACTOR,
            f"src_{'1' * 48}",
            _fingerprint("1"),
        )


def test_command_result_separates_durable_outcome_from_replay_resolution() -> None:
    applied = CommandResult(
        command_result_id=f"cmr_{'1' * 48}",
        command_ref=_reference(ReferenceType.COMMAND, "cmd", "2"),
        recorded_at="2026-08-16T01:01:00Z",
        result_code=CommandResultCode.APPLIED,
        authoritative_version=1,
        event_refs=(_reference(ReferenceType.EXECUTION_EVENT, "pex", "3"),),
        effect_intent_refs=(_reference(ReferenceType.EFFECT_INTENT, "efi", "4"),),
        evidence_refs=(),
    )

    assert applied.result_code is CommandResultCode.APPLIED
    assert CommandSubmissionResolutionCode.EXACT_REPLAY.value not in {
        code.value for code in CommandResultCode
    }
    assert CommandSubmissionResolutionCode.INDETERMINATE.value not in {
        code.value for code in CommandResultCode
    }


def test_rejected_command_result_cannot_claim_events_or_effects() -> None:
    with pytest.raises(ValueError, match="cannot declare"):
        CommandResult(
            command_result_id=f"cmr_{'1' * 48}",
            command_ref=_reference(ReferenceType.COMMAND, "cmd", "2"),
            recorded_at="2026-08-16T01:01:00Z",
            result_code=CommandResultCode.REJECTED_INVALID_STATE,
            authoritative_version=4,
            event_refs=(_reference(ReferenceType.EXECUTION_EVENT, "pex", "3"),),
            effect_intent_refs=(),
            evidence_refs=(),
        )


def test_effect_intent_declares_authority_without_performing_an_effect() -> None:
    intent = _effect_intent()

    assert intent.effect_type is EffectType.EVIDENCE_WRITE
    assert intent.required_capability is EffectCapability.WRITE_EVIDENCE
    assert type(intent.compensation) is NoCompensation


@pytest.mark.parametrize("invalid_ceiling", [True, False, 0, -1, 1.5])
def test_effect_intent_rejects_invalid_attempt_ceiling(invalid_ceiling: object) -> None:
    intent = _effect_intent()
    object.__setattr__(intent, "attempt_ceiling", invalid_ceiling)

    with pytest.raises((TypeError, ValueError), match="attempt_ceiling"):
        intent.__post_init__()


def test_effect_intent_rejects_unsorted_stop_conditions() -> None:
    intent = _effect_intent()
    object.__setattr__(
        intent,
        "stop_conditions",
        (StopCondition.DEADLINE, StopCondition.ATTEMPT_CEILING),
    )

    with pytest.raises(ValueError, match="sorted"):
        intent.__post_init__()


def test_effect_type_cannot_borrow_another_owners_capability() -> None:
    intent = _effect_intent()
    object.__setattr__(intent, "effect_type", EffectType.GENERATIVE_LLM_CALL)

    with pytest.raises(ValueError, match="owning_application"):
        intent.__post_init__()


def test_each_terminal_receipt_detail_has_one_exact_matching_status() -> None:
    evidence = (_reference(ReferenceType.EVIDENCE, "evi", "6"),)
    success = _receipt(
        EffectSuccessDetail("remote-1", "v1", "request-1", _fingerprint("7"), evidence),
        EffectReceiptStatus.SUCCEEDED,
        1,
    )
    failure = _receipt(
        EffectFinalFailureDetail(FailureCode.FAILURE_EXTERNAL_EFFECT, evidence),
        EffectReceiptStatus.FAILED_FINAL,
        3,
    )
    cancelled = _receipt(
        EffectCancelledDetail(evidence),
        EffectReceiptStatus.CANCELLED_BEFORE_EFFECT,
        0,
    )
    unknown = _receipt(
        EffectUnknownDetail(FailureCode.FAILURE_EXTERNAL_EFFECT, evidence),
        EffectReceiptStatus.OUTCOME_UNKNOWN,
        1,
    )

    assert {
        success.terminal_status,
        failure.terminal_status,
        cancelled.terminal_status,
        unknown.terminal_status,
    } == set(EffectReceiptStatus)


def test_receipt_rejects_status_detail_mismatch() -> None:
    evidence = (_reference(ReferenceType.EVIDENCE, "evi", "6"),)

    with pytest.raises(ValueError, match="must match"):
        _receipt(
            EffectFinalFailureDetail(FailureCode.FAILURE_EXTERNAL_EFFECT, evidence),
            EffectReceiptStatus.SUCCEEDED,
            1,
        )


def test_cancelled_receipt_proves_no_attempt_started() -> None:
    evidence = (_reference(ReferenceType.EVIDENCE, "evi", "6"),)

    with pytest.raises(ValueError, match="zero attempts"):
        _receipt(
            EffectCancelledDetail(evidence),
            EffectReceiptStatus.CANCELLED_BEFORE_EFFECT,
            1,
        )
