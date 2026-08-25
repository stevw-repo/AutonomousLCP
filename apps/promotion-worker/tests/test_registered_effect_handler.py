"""Disabled first-intent claim, fencing, outcome, and receipt proofs."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import (
    ApplicationCode,
    ContractReference,
    DestinationClass,
    EffectCapability,
    EffectFinalFailureDetail,
    EffectReceiptStatus,
    EffectSuccessDetail,
    EffectType,
    EffectUnknownDetail,
    FailureCode,
    ImmutableReference,
    NoCompensation,
    ReferenceType,
    RetryClass,
    StopCondition,
)
from asklegal_management_register import (
    ClaimedEffect,
    EffectReceiptRecord,
    RecordedEffectReceipt,
)
from asklegal_promotion import (
    PromotionActionAuthority,
    promotion_action_authority_document,
)
from asklegal_promotion_worker import (
    CurrentCapabilityEvidence,
    CurrentExecutionActionAuthority,
    RegisteredEffectHandler,
    RegisteredEffectHandlerContext,
    RegisteredEffectHandlerDependencies,
    RegisteredEffectHandlerError,
    RegisteredEffectHandlerErrorCode,
    RegisteredEffectOutcome,
)

_INTENT_ID = "efi_" + "1" * 48
_LINEAGE = ImmutableReference(
    ReferenceType.EXECUTION_LINEAGE,
    "exe_" + "2" * 48,
    "sha256:" + "2" * 64,
)
_PROFILE = ImmutableReference(
    ReferenceType.CAPABILITY_PROFILE,
    "cap_" + "3" * 48,
    "sha256:" + "3" * 64,
)
_AUTHORITY_EVIDENCE = ImmutableReference(
    ReferenceType.EVIDENCE,
    "evi_" + "4" * 48,
    "sha256:" + "4" * 64,
)
_CAPABILITY_EVIDENCE = ImmutableReference(
    ReferenceType.EVIDENCE,
    "evi_" + "5" * 48,
    "sha256:" + "5" * 64,
)
_OUTCOME_EVIDENCE = ImmutableReference(
    ReferenceType.EVIDENCE,
    "evi_" + "6" * 48,
    "sha256:" + "6" * 64,
)


class Handoff:
    """Exact in-memory handoff fake with fencing and receipt replay."""

    def __init__(self, claim: ClaimedEffect) -> None:
        """Set one unreceipted claim candidate."""
        self.claim = claim
        self.renewals = 0
        self.attempts: list[tuple[int, bytes]] = []
        self.receipt: RecordedEffectReceipt | None = None

    def claim_next(
        self,
        *,
        owning_application: str,
        effect_type: str,
        claimant_id: str,
        lease_seconds: int = 900,
    ) -> ClaimedEffect | None:
        """Return the configured exact owner/type candidate until terminal."""
        del lease_seconds
        if (
            self.receipt is not None
            or owning_application != ApplicationCode.PROMOTION_WORKER.value
            or effect_type != self.claim.effect_type
            or claimant_id != self.claim.claimant_id
        ):
            return None
        return self.claim

    def renew_claim(self, claim: ClaimedEffect, *, lease_seconds: int = 900) -> None:
        """Require the exact live fence."""
        del lease_seconds
        if claim.fencing_token != self.claim.fencing_token:
            message = "stale fence"
            raise RuntimeError(message)
        self.renewals += 1

    def append_attempt(
        self,
        claim: ClaimedEffect,
        *,
        attempt_number: int,
        event_code: str,
        event_bytes: bytes,
    ) -> None:
        """Append only the next exact attempt under the current fence."""
        if (
            claim.fencing_token != self.claim.fencing_token
            or event_code != "STARTED"
            or attempt_number != self.claim.prior_attempt_count + len(self.attempts) + 1
        ):
            message = "stale or nonsequential attempt"
            raise RuntimeError(message)
        self.attempts.append((attempt_number, event_bytes))

    def record_receipt(
        self,
        record: EffectReceiptRecord,
    ) -> RecordedEffectReceipt:
        """Select one exact receipt or return its exact replay."""
        if sha256(record.receipt_bytes).digest() != record.receipt_fingerprint:
            message = "receipt fingerprint mismatch"
            raise RuntimeError(message)
        if record.terminal_status == EffectReceiptStatus.CANCELLED_BEFORE_EFFECT.value:
            assert record.fencing_token is None
            assert record.claimant_id is None
            assert record.attempt_count == 0
        else:
            assert record.fencing_token == self.claim.fencing_token
            assert record.claimant_id == self.claim.claimant_id
        selected = RecordedEffectReceipt(
            record.effect_receipt_id,
            record.effect_intent_id,
            record.terminal_status,
            record.attempt_count,
            record.receipt_bytes,
            record.fencing_token,
            self.receipt is not None,
        )
        if self.receipt is not None:
            if replace(selected, replayed=False) != replace(self.receipt, replayed=False):
                message = "receipt conflict"
                raise RuntimeError(message)
            return replace(self.receipt, replayed=True)
        self.receipt = selected
        return selected


class Authorities:
    """Current execution-action authority fake."""

    def __init__(self, authority: CurrentExecutionActionAuthority | None) -> None:
        """Set the current authority response."""
        self.authority = authority

    def current(
        self,
        execution_lineage_id: str,
        effect_intent_id: str,
        at: str,
    ) -> CurrentExecutionActionAuthority | None:
        """Return only the configured exact lineage and intent authority."""
        del at
        if execution_lineage_id != _LINEAGE.ref_id or effect_intent_id != _INTENT_ID:
            return None
        return self.authority


class Capabilities:
    """Current capability-evidence fake."""

    def __init__(self, capability: CurrentCapabilityEvidence | None) -> None:
        """Set the current capability response."""
        self.capability = capability

    def current(self, profile_id: str, at: str) -> CurrentCapabilityEvidence | None:
        """Return only the configured exact profile response."""
        del at
        if profile_id != _PROFILE.ref_id:
            return None
        return self.capability


class EffectFake:
    """Injected deterministic effect and reconciliation fake."""

    def __init__(
        self,
        perform_outcome: RegisteredEffectOutcome,
        reconcile_outcome: RegisteredEffectOutcome | None = None,
    ) -> None:
        """Set terminal fake outcomes."""
        self.perform_outcome = perform_outcome
        self.reconcile_outcome = reconcile_outcome or perform_outcome
        self.perform_calls = 0
        self.reconcile_calls = 0

    def perform(self, intent_bytes: bytes, fencing_token: int) -> RegisteredEffectOutcome:
        """Return the configured effect outcome."""
        assert intent_bytes
        assert fencing_token == 7
        self.perform_calls += 1
        return self.perform_outcome

    def reconcile(self, intent_bytes: bytes) -> RegisteredEffectOutcome:
        """Return the configured prior-attempt reconciliation outcome."""
        assert intent_bytes
        self.reconcile_calls += 1
        return self.reconcile_outcome


def _contract(name: str, digit: str) -> ContractReference:
    return ContractReference(name, "1.0.0", "sha256:" + digit * 64)


def _action() -> PromotionActionAuthority:
    return PromotionActionAuthority(
        1,
        "EMBED_RECORDS",
        EffectType.EMBEDDING_PROVIDER_CALL,
        ApplicationCode.PROMOTION_WORKER,
        "EMBED_RECORDS",
        (
            ImmutableReference(
                ReferenceType.DESIRED_STATE_INVENTORY,
                "dsi_" + "7" * 48,
                "sha256:" + "7" * 64,
            ),
            ImmutableReference(
                ReferenceType.EMBEDDING_PROFILE,
                "emp_" + "8" * 48,
                "sha256:" + "8" * 64,
            ),
        ),
        "sha256:" + "9" * 64,
        EffectCapability.CALL_EMBEDDING_PROVIDER,
        _PROFILE,
        DestinationClass.EMBEDDING_PROVIDER,
        "promotion-embed-records-v1",
        RetryClass.RECONCILE_BEFORE_RETRY,
        3,
        "2026-08-25T00:00:00Z",
        tuple(StopCondition),
        _contract("asklegal.embedding-precondition", "a"),
        _contract("asklegal.embedding-postcondition", "b"),
        NoCompensation(),
    )


def _intent_bytes(action: PromotionActionAuthority | None = None) -> bytes:
    selected = action or _action()
    action_document = promotion_action_authority_document(selected)
    return canonicalize(
        checked_json_value(
            {
                "aggregate_ref": _reference_document(_LINEAGE),
                "attempt_ceiling": action_document["attempt_ceiling"],
                "capability_profile_ref": action_document["capability_profile_ref"],
                "command_ref": _reference_document(
                    ImmutableReference(
                        ReferenceType.COMMAND,
                        "cmd_" + "9" * 48,
                        "sha256:" + "c" * 64,
                    )
                ),
                "compensation": action_document["compensation"],
                "created_at": "2026-08-24T12:00:00Z",
                "deadline": action_document["deadline"],
                "destination_class": action_document["destination_class"],
                "effect_command_fingerprint": action_document["effect_command_fingerprint"],
                "effect_intent_id": _INTENT_ID,
                "effect_type": action_document["effect_type"],
                "execution_lineage_ref": _reference_document(_LINEAGE),
                "expected_remote_precondition_ref": action_document[
                    "expected_remote_precondition_ref"
                ],
                "immutable": True,
                "input_refs": action_document["input_refs"],
                "owning_application": action_document["owning_application"],
                "permitted_checkpoint": action_document["permitted_checkpoint"],
                "required_capability": action_document["required_capability"],
                "retry_class": action_document["retry_class"],
                "schema_id": "asklegal.effect-intent",
                "schema_version": "1.0.0",
                "stable_idempotency_key": action_document["stable_idempotency_key"],
                "stop_conditions": action_document["stop_conditions"],
                "success_postcondition_ref": action_document["success_postcondition_ref"],
            }
        )
    )


def _claim(
    *,
    action: PromotionActionAuthority | None = None,
    prior_attempt_count: int = 0,
) -> ClaimedEffect:
    intent = _intent_bytes(action)
    return ClaimedEffect(
        _INTENT_ID,
        EffectType.EMBEDDING_PROVIDER_CALL.value,
        _LINEAGE.ref_id,
        intent,
        sha256(intent).digest(),
        "act_" + "d" * 48,
        7,
        3,
        prior_attempt_count,
    )


def _authority(
    *,
    action: PromotionActionAuthority | None = None,
    active: bool = True,
) -> CurrentExecutionActionAuthority:
    return CurrentExecutionActionAuthority(
        _LINEAGE,
        action or _action(),
        active,
        _AUTHORITY_EVIDENCE,
    )


def _capability(*, active: bool = True) -> CurrentCapabilityEvidence:
    return CurrentCapabilityEvidence(
        _PROFILE,
        ApplicationCode.PROMOTION_WORKER,
        frozenset({EffectCapability.CALL_EMBEDDING_PROVIDER}),
        active,
        "2026-08-24T00:00:00Z",
        "2026-08-25T00:00:00Z",
        _CAPABILITY_EVIDENCE,
    )


def _success() -> RegisteredEffectOutcome:
    return RegisteredEffectOutcome(
        EffectReceiptStatus.SUCCEEDED,
        (_OUTCOME_EVIDENCE,),
        EffectSuccessDetail(
            "synthetic-remote",
            "v1",
            "synthetic-request",
            "sha256:" + "d" * 64,
            (_OUTCOME_EVIDENCE,),
        ),
    )


def _unknown() -> RegisteredEffectOutcome:
    return RegisteredEffectOutcome(
        EffectReceiptStatus.OUTCOME_UNKNOWN,
        (_OUTCOME_EVIDENCE,),
        EffectUnknownDetail(
            FailureCode.FAILURE_EXTERNAL_EFFECT,
            (_OUTCOME_EVIDENCE,),
        ),
    )


def _service(
    handoff: Handoff,
    effect: EffectFake,
    *,
    authority: CurrentExecutionActionAuthority | None = None,
    capability: CurrentCapabilityEvidence | None = None,
) -> RegisteredEffectHandler:
    return RegisteredEffectHandler(
        EffectType.EMBEDDING_PROVIDER_CALL.value,
        RegisteredEffectHandlerDependencies(
            handoff,
            Authorities(authority),
            Capabilities(capability),
            effect,
            SchemaRegistry.from_contracts_root(Path(__file__).parents[3] / "contracts"),
        ),
    )


def _context() -> RegisteredEffectHandlerContext:
    return RegisteredEffectHandlerContext(
        "act_" + "d" * 48,
        "2026-08-24T12:05:00Z",
        120,
    )


def test_current_first_intent_is_attempted_once_and_receipted() -> None:
    """One valid claimed intent reaches only the injected fake and exact receipt."""
    handoff = Handoff(_claim())
    effect = EffectFake(_success())
    result = _service(
        handoff,
        effect,
        authority=_authority(),
        capability=_capability(),
    ).handle_next(_context())

    assert result is not None
    assert result.terminal_status is EffectReceiptStatus.SUCCEEDED
    assert result.attempt_count == 1
    assert effect.perform_calls == 1
    assert effect.reconcile_calls == 0
    assert handoff.renewals == 1
    assert len(handoff.attempts) == 1
    attempt = parse_json_bytes(handoff.attempts[0][1], max_bytes=100_000)
    receipt = parse_json_bytes(result.receipt_bytes, max_bytes=100_000)
    assert isinstance(attempt, dict)
    assert attempt["event_code"] == "STARTED"
    assert isinstance(receipt, dict)
    assert receipt["terminal_status"] == "SUCCEEDED"


def test_inactive_capability_cancels_before_effect() -> None:
    """Current inactive evidence produces a zero-attempt terminal cancellation."""
    handoff = Handoff(_claim())
    effect = EffectFake(_success())
    result = _service(
        handoff,
        effect,
        authority=_authority(),
        capability=_capability(active=False),
    ).handle_next(_context())

    assert result is not None
    assert result.terminal_status is EffectReceiptStatus.CANCELLED_BEFORE_EFFECT
    assert result.attempt_count == 0
    assert not handoff.attempts
    assert effect.perform_calls == 0


def test_stale_or_changed_capability_cancels_before_effect() -> None:
    """Expiry or profile drift after BEGIN cannot reach the effect fake."""
    stale = replace(_capability(), valid_until=_context().at)
    changed = replace(
        _capability(),
        profile_ref=replace(_PROFILE, fingerprint="sha256:" + "0" * 64),
    )
    for capability in (stale, changed):
        handoff = Handoff(_claim())
        effect = EffectFake(_success())
        result = _service(
            handoff,
            effect,
            authority=_authority(),
            capability=capability,
        ).handle_next(_context())
        assert result is not None
        assert result.terminal_status is EffectReceiptStatus.CANCELLED_BEFORE_EFFECT
        assert not handoff.attempts
        assert effect.perform_calls == 0


def test_changed_current_action_cancels_before_effect() -> None:
    """Action drift after BEGIN cannot inherit the already-created intent."""
    changed = replace(_action(), effect_command_fingerprint="sha256:" + "0" * 64)
    handoff = Handoff(_claim())
    effect = EffectFake(_success())
    result = _service(
        handoff,
        effect,
        authority=_authority(action=changed),
        capability=_capability(),
    ).handle_next(_context())

    assert result is not None
    assert result.terminal_status is EffectReceiptStatus.CANCELLED_BEFORE_EFFECT
    assert not handoff.attempts
    assert effect.perform_calls == 0


@pytest.mark.parametrize("missing", ["authority", "capability"])
def test_missing_current_evidence_never_attempts_or_invents_a_receipt(missing: str) -> None:
    """An unreadable authority source remains unresolved rather than repaired."""
    handoff = Handoff(_claim())
    effect = EffectFake(_success())
    with pytest.raises(RegisteredEffectHandlerError) as raised:
        _service(
            handoff,
            effect,
            authority=None if missing == "authority" else _authority(),
            capability=None if missing == "capability" else _capability(),
        ).handle_next(_context())
    assert raised.value.code is RegisteredEffectHandlerErrorCode.AUTHORITY_UNAVAILABLE
    assert not handoff.attempts
    assert handoff.receipt is None
    assert effect.perform_calls == 0


def test_prior_attempt_reconciles_without_repeating_the_effect() -> None:
    """Restart after an unreceipted attempt calls reconciliation, not perform."""
    handoff = Handoff(_claim(prior_attempt_count=1))
    effect = EffectFake(_success(), _unknown())
    result = _service(
        handoff,
        effect,
        authority=_authority(),
        capability=_capability(),
    ).handle_next(_context())

    assert result is not None
    assert result.terminal_status is EffectReceiptStatus.OUTCOME_UNKNOWN
    assert result.attempt_count == 1
    assert effect.perform_calls == 0
    assert effect.reconcile_calls == 1
    assert not handoff.attempts


def test_malformed_or_fingerprint_drifted_intent_never_reaches_authority() -> None:
    """Claim read-back drift fails before current checks or fake effects."""
    valid = _claim()
    broken = replace(valid, intent_fingerprint=b"\x00" * 32)
    handoff = Handoff(broken)
    effect = EffectFake(_success())
    with pytest.raises(RegisteredEffectHandlerError) as raised:
        _service(
            handoff,
            effect,
            authority=_authority(),
            capability=_capability(),
        ).handle_next(_context())
    assert raised.value.code is RegisteredEffectHandlerErrorCode.INVALID_INTENT
    assert effect.perform_calls == 0
    assert handoff.receipt is None


def test_final_failure_receipt_remains_sanitized_and_schema_valid() -> None:
    """A fake final failure records only a closed code and evidence reference."""
    failure = RegisteredEffectOutcome(
        EffectReceiptStatus.FAILED_FINAL,
        (_OUTCOME_EVIDENCE,),
        EffectFinalFailureDetail(
            FailureCode.FAILURE_EXTERNAL_EFFECT,
            (_OUTCOME_EVIDENCE,),
        ),
    )
    handoff = Handoff(_claim())
    result = _service(
        handoff,
        EffectFake(failure),
        authority=_authority(),
        capability=_capability(),
    ).handle_next(_context())
    assert result is not None
    document = parse_json_bytes(result.receipt_bytes, max_bytes=100_000)
    assert isinstance(document, dict)
    assert document["terminal_status"] == "FAILED_FINAL"
    assert "synthetic-remote" not in result.receipt_bytes.decode()


def _reference_document(reference: ImmutableReference) -> dict[str, str]:
    return {
        "fingerprint": reference.fingerprint,
        "ref_id": reference.ref_id,
        "ref_type": reference.ref_type.value,
    }
