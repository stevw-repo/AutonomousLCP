"""Local-only proofs for the exact V1 credential-rotation protocol."""

# Test doubles mirror the nominal ports; their methods need no repeated docs.
# ruff: noqa: D102, D107, FBT001

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import TypedDict, cast

import pytest

from tools.hk_v1_rotate_credentials import (
    AcknowledgementLost,
    AuthenticationReceipt,
    CleanupReceipt,
    CredentialHealthChecker,
    CredentialManifest,
    CredentialManifestEntry,
    CredentialRotationBlocker,
    CredentialRotationPlan,
    CredentialRotationReport,
    CredentialRotationState,
    DependentUnitController,
    LocalRotationLayout,
    RestartReceipt,
    RollbackReceipt,
    SealedCredentialStore,
    StageReceipt,
    SwitchReceipt,
    SystemCommandRunner,
    build_credential_manifest,
    credential_manifest_bytes,
    credential_rotation_plan_bytes,
    execute_local_rotation,
    execution_authority_bytes,
    main,
    parse_credential_rotation_report_bytes,
    plan_local_rotation,
    plan_rotation,
    rotate_credentials,
)

_ROTATION_ID = "rot_" + "1" * 48
_PREDECESSOR = "binding_" + "2" * 48
_CANDIDATE = "binding_" + "3" * 48
_OTHER_BINDING = "binding_" + "4" * 48
_UNIT = "asklegal-control-plane.service"


def _plan(*, rotation_id: str = _ROTATION_ID) -> CredentialRotationPlan:
    manifest = build_credential_manifest((CredentialManifestEntry("sql-control", (_UNIT,)),))
    return plan_rotation(
        manifest,
        credential_name="sql-control",
        rotation_id=rotation_id,
        predecessor_binding_ref=_PREDECESSOR,
        candidate_binding_ref=_CANDIDATE,
    )


class FakeStore(SealedCredentialStore):
    """Exact deterministic sealed-store double; it holds references, never values."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.stage_error: BaseException | None = None
        self.stage_readback: StageReceipt | None = None
        self.stage_candidate_ref = _CANDIDATE
        self.switch_error: BaseException | None = None
        self.switch_readback: SwitchReceipt | None = None
        self.cleanup_error: BaseException | None = None
        self.cleanup_readback: CleanupReceipt | None = None
        self.plaintext_absent = True
        self.obsolete_absent = True
        self.rollback_error: BaseException | None = None
        self.rollback_readback: RollbackReceipt | None = None
        self.rollback_restored = True
        self.rollback_candidate_absent = True
        self.rollback_plaintext_absent = True

    def stage_candidate(self, plan: CredentialRotationPlan) -> StageReceipt:
        self.calls.append("stage")
        if self.stage_error is not None:
            raise self.stage_error
        return _stage(plan, candidate_ref=self.stage_candidate_ref)

    def read_staged_candidate(self, plan: CredentialRotationPlan) -> StageReceipt | None:
        del plan
        self.calls.append("read-stage")
        return self.stage_readback

    def switch_binding(self, plan: CredentialRotationPlan, stage: StageReceipt) -> SwitchReceipt:
        del stage
        self.calls.append("switch")
        if self.switch_error is not None:
            raise self.switch_error
        return _switch(plan)

    def read_switched_binding(self, plan: CredentialRotationPlan) -> SwitchReceipt | None:
        del plan
        self.calls.append("read-switch")
        return self.switch_readback

    def remove_obsolete(
        self, plan: CredentialRotationPlan, switch: SwitchReceipt
    ) -> CleanupReceipt:
        del switch
        self.calls.append("cleanup")
        if self.cleanup_error is not None:
            raise self.cleanup_error
        return _cleanup(
            plan,
            obsolete_absent=self.obsolete_absent,
            plaintext_absent=self.plaintext_absent,
        )

    def read_cleanup(self, plan: CredentialRotationPlan) -> CleanupReceipt | None:
        del plan
        self.calls.append("read-cleanup")
        return self.cleanup_readback

    def restore_predecessor(self, plan: CredentialRotationPlan) -> RollbackReceipt:
        self.calls.append("restore")
        if self.rollback_error is not None:
            raise self.rollback_error
        return _rollback(
            plan,
            restored=self.rollback_restored,
            candidate_absent=self.rollback_candidate_absent,
            plaintext_absent=self.rollback_plaintext_absent,
        )

    def read_rollback(self, plan: CredentialRotationPlan) -> RollbackReceipt | None:
        del plan
        self.calls.append("read-rollback")
        return self.rollback_readback


class FakeUnits(DependentUnitController):
    """Exact dependent-unit controller double."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.candidate_units: tuple[str, ...] = (_UNIT,)
        self.predecessor_units: tuple[str, ...] = (_UNIT,)
        self.error: BaseException | None = None
        self.candidate_readback: RestartReceipt | None = None
        self.predecessor_readback: RestartReceipt | None = None

    def restart_exact(self, plan: CredentialRotationPlan, *, binding_ref: str) -> RestartReceipt:
        self.calls.append(
            "restart-candidate" if binding_ref == plan.candidate_binding_ref else "restart-old"
        )
        if self.error is not None:
            raise self.error
        units = (
            self.candidate_units
            if binding_ref == plan.candidate_binding_ref
            else self.predecessor_units
        )
        return _restart(plan, binding_ref=binding_ref, units=units)

    def read_restart(
        self, plan: CredentialRotationPlan, *, binding_ref: str
    ) -> RestartReceipt | None:
        self.calls.append(
            "read-restart-candidate"
            if binding_ref == plan.candidate_binding_ref
            else "read-restart-old"
        )
        return (
            self.candidate_readback
            if binding_ref == plan.candidate_binding_ref
            else self.predecessor_readback
        )


class FakeChecker(CredentialHealthChecker):
    """Exact authentication/read-back double."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.candidate_accepted = True
        self.candidate_healthy = True
        self.predecessor_accepted_before_rollback = False
        self.predecessor_accepted_after_rollback = True
        self.predecessor_healthy = True
        self.error: BaseException | None = None
        self._predecessor_checks = 0

    def check_binding(
        self, plan: CredentialRotationPlan, *, binding_ref: str
    ) -> AuthenticationReceipt:
        if self.error is not None:
            raise self.error
        if binding_ref == plan.candidate_binding_ref:
            self.calls.append("check-candidate")
            return _authentication(
                plan,
                binding_ref=binding_ref,
                accepted=self.candidate_accepted,
                healthy=self.candidate_healthy,
            )
        self._predecessor_checks += 1
        restoring = "restore" in self.calls
        suffix = "restored" if restoring else "rejected"
        self.calls.append(f"check-old-{suffix}")
        accepted = (
            self.predecessor_accepted_after_rollback
            if restoring
            else self.predecessor_accepted_before_rollback
        )
        return _authentication(
            plan,
            binding_ref=binding_ref,
            accepted=accepted,
            healthy=self.predecessor_healthy,
        )


class BoundKwargs(TypedDict):
    """Typed exact common receipt arguments."""

    rotation_id: str
    manifest_fingerprint: str
    credential_name: str
    predecessor_binding_ref: str
    candidate_binding_ref: str
    dependent_units: tuple[str, ...]


def _bound(plan: CredentialRotationPlan) -> BoundKwargs:
    return {
        "rotation_id": plan.rotation_id,
        "manifest_fingerprint": plan.manifest_fingerprint,
        "credential_name": plan.credential_name,
        "predecessor_binding_ref": plan.predecessor_binding_ref,
        "candidate_binding_ref": plan.candidate_binding_ref,
        "dependent_units": plan.dependent_units,
    }


def _stage(plan: CredentialRotationPlan, *, candidate_ref: str = _CANDIDATE) -> StageReceipt:
    values = _bound(plan)
    values["candidate_binding_ref"] = candidate_ref
    return StageReceipt(**values)


def _switch(plan: CredentialRotationPlan) -> SwitchReceipt:
    return SwitchReceipt(**_bound(plan), current_binding_ref=plan.candidate_binding_ref)


def _restart(
    plan: CredentialRotationPlan, *, binding_ref: str, units: tuple[str, ...]
) -> RestartReceipt:
    return RestartReceipt(**_bound(plan), active_binding_ref=binding_ref, restarted_units=units)


def _authentication(
    plan: CredentialRotationPlan, *, binding_ref: str, accepted: bool, healthy: bool
) -> AuthenticationReceipt:
    return AuthenticationReceipt(
        **_bound(plan),
        checked_binding_ref=binding_ref,
        credential_accepted=accepted,
        dependent_services_healthy=healthy,
    )


def _cleanup(
    plan: CredentialRotationPlan, *, obsolete_absent: bool, plaintext_absent: bool
) -> CleanupReceipt:
    return CleanupReceipt(
        **_bound(plan),
        obsolete_predecessor_absent=obsolete_absent,
        plaintext_staging_absent=plaintext_absent,
    )


def _rollback(
    plan: CredentialRotationPlan,
    *,
    restored: bool,
    candidate_absent: bool,
    plaintext_absent: bool,
) -> RollbackReceipt:
    return RollbackReceipt(
        **_bound(plan),
        predecessor_binding_restored=restored,
        candidate_material_absent=candidate_absent,
        plaintext_staging_absent=plaintext_absent,
    )


def _execute(
    *,
    store: FakeStore | None = None,
    units: FakeUnits | None = None,
    checker: FakeChecker | None = None,
    plan: CredentialRotationPlan | None = None,
    prior_report: CredentialRotationReport | None = None,
) -> tuple[CredentialRotationReport, list[str], FakeStore, FakeUnits, FakeChecker]:
    calls = (
        store.calls
        if store is not None
        else units.calls
        if units is not None
        else checker.calls
        if checker is not None
        else []
    )
    actual_store = store or FakeStore(calls)
    actual_units = units or FakeUnits(calls)
    actual_checker = checker or FakeChecker(calls)
    result = rotate_credentials(
        plan or _plan(),
        store=actual_store,
        units=actual_units,
        checker=actual_checker,
        prior_report=prior_report,
    )
    return result, calls, actual_store, actual_units, actual_checker


def test_rotation_succeeds_only_after_exact_order_rejection_and_cleanup() -> None:
    """Catches success issued before the old credential and plaintext are gone."""
    result, calls, _store, _units, _checker = _execute()

    assert calls == [
        "stage",
        "switch",
        "restart-candidate",
        "check-candidate",
        "check-old-rejected",
        "cleanup",
    ]
    assert result.state is CredentialRotationState.SUCCEEDED
    assert result.complete is True
    assert result.new_value_works is True
    assert result.old_value_rejected is True
    assert result.obsolete_binding_absent is True
    assert result.plaintext_staging_absent is True
    assert result.blocker_codes == ()


def test_failed_candidate_check_restores_and_reverifies_predecessor() -> None:
    """Catches candidate failure being reported without a proved rollback."""
    calls: list[str] = []
    checker = FakeChecker(calls)
    checker.candidate_accepted = False
    result, _ignored, _store, _units, _checker = _execute(checker=checker)

    assert calls == [
        "stage",
        "switch",
        "restart-candidate",
        "check-candidate",
        "restore",
        "restart-old",
        "check-old-restored",
    ]
    assert result.state is CredentialRotationState.ROLLED_BACK
    assert result.complete is False
    assert result.old_binding_restored is True
    assert result.candidate_material_absent is True
    assert result.plaintext_staging_absent is True
    assert CredentialRotationBlocker.CANDIDATE_REJECTED in result.blocker_codes


def test_old_value_still_accepted_is_blocked_even_after_safe_restoration() -> None:
    """Catches a failed old-value rejection being mislabeled as rotated or rolled back."""
    calls: list[str] = []
    checker = FakeChecker(calls)
    checker.predecessor_accepted_before_rollback = True
    result, _ignored, _store, _units, _checker = _execute(checker=checker)

    assert calls[-3:] == ["restore", "restart-old", "check-old-restored"]
    assert result.state is CredentialRotationState.BLOCKED
    assert result.old_binding_restored is True
    assert result.old_value_rejected is False
    assert result.blocker_codes == (CredentialRotationBlocker.PREDECESSOR_STILL_ACCEPTED,)


@pytest.mark.parametrize(
    ("plaintext_absent", "obsolete_absent", "expected"),
    [
        (False, True, CredentialRotationBlocker.PLAINTEXT_STAGING_REMAINS),
        (True, False, CredentialRotationBlocker.OBSOLETE_BINDING_REMAINS),
    ],
)
def test_cleanup_material_remaining_blocks_completion(
    plaintext_absent: bool,
    obsolete_absent: bool,
    expected: CredentialRotationBlocker,
) -> None:
    """Catches cleanup acknowledgement being mistaken for verified absence."""
    calls: list[str] = []
    store = FakeStore(calls)
    store.plaintext_absent = plaintext_absent
    store.obsolete_absent = obsolete_absent
    result, _ignored, _store, _units, _checker = _execute(store=store)

    assert result.state is CredentialRotationState.BLOCKED
    assert result.complete is False
    assert expected in result.blocker_codes


@pytest.mark.parametrize(
    ("units", "expected"),
    [
        ((), CredentialRotationBlocker.ADAPTER_FAILED),
        ((_UNIT, _UNIT), CredentialRotationBlocker.ADAPTER_FAILED),
        (
            (_UNIT, "asklegal-review-api.service"),
            CredentialRotationBlocker.RECEIPT_MISMATCH,
        ),
    ],
)
def test_missing_duplicate_or_extra_restart_receipts_fail_closed(
    units: tuple[str, ...], expected: CredentialRotationBlocker
) -> None:
    """Catches partial or over-broad service restart being accepted."""
    calls: list[str] = []
    controller = FakeUnits(calls)
    controller.candidate_units = units
    result, _ignored, _store, _units, _checker = _execute(units=controller)

    assert result.state is not CredentialRotationState.SUCCEEDED
    assert expected in result.blocker_codes


def test_binding_drift_in_stage_receipt_fails_closed() -> None:
    """Catches a receipt for another candidate being borrowed by this plan."""
    calls: list[str] = []
    store = FakeStore(calls)
    store.stage_candidate_ref = _OTHER_BINDING
    result, _ignored, _store, _units, _checker = _execute(store=store)

    assert result.state is CredentialRotationState.BLOCKED
    assert result.blocker_codes == (CredentialRotationBlocker.RECEIPT_MISMATCH,)
    assert "switch" not in calls


def test_partial_rollback_never_reports_rolled_back() -> None:
    """Catches restoration inferred from a partial rollback receipt."""
    calls: list[str] = []
    store = FakeStore(calls)
    store.rollback_candidate_absent = False
    checker = FakeChecker(calls)
    checker.candidate_accepted = False
    result, _ignored, _store, _units, _checker = _execute(store=store, checker=checker)

    assert result.state is CredentialRotationState.BLOCKED
    assert result.old_binding_restored is False
    assert CredentialRotationBlocker.ROLLBACK_NOT_PROVED in result.blocker_codes


def test_caller_cannot_construct_an_unproved_rolled_back_report() -> None:
    """Catches replay accepting a caller-forged rollback without complete proof."""
    success, _calls, _store, _units, _checker = _execute()
    with pytest.raises(ValueError, match="unproved rollback"):
        replace(
            success,
            state=CredentialRotationState.ROLLED_BACK,
            complete=False,
            blocker_codes=(CredentialRotationBlocker.CANDIDATE_REJECTED,),
            new_value_works=False,
            old_value_rejected=False,
            old_binding_restored=False,
            candidate_material_absent=False,
            obsolete_binding_absent=False,
            plaintext_staging_absent=False,
        )


def test_lost_stage_acknowledgement_reconciles_only_by_exact_readback() -> None:
    """Catches an acknowledgement exception being treated as proof of staging."""
    calls: list[str] = []
    store = FakeStore(calls)
    store.stage_error = AcknowledgementLost()
    store.stage_readback = _stage(_plan())
    result, _ignored, _store, _units, _checker = _execute(store=store)

    assert result.state is CredentialRotationState.SUCCEEDED
    assert calls[:3] == ["stage", "read-stage", "switch"]

    calls = []
    store = FakeStore(calls)
    store.stage_error = AcknowledgementLost()
    result, _ignored, _store, _units, _checker = _execute(store=store)
    assert result.state is CredentialRotationState.BLOCKED
    assert result.blocker_codes == (CredentialRotationBlocker.ACKNOWLEDGEMENT_UNRECONCILED,)
    assert calls == [
        "stage",
        "read-stage",
        "restore",
        "restart-old",
        "check-old-restored",
    ]


def test_exact_terminal_replay_is_deterministic_only_after_fresh_readback() -> None:
    """Catches a caller-supplied terminal report being treated as authority."""
    first, _calls, _store, _units, _checker = _execute()
    calls: list[str] = []
    plan = _plan()
    store = FakeStore(calls)
    store.switch_readback = _switch(plan)
    store.cleanup_readback = _cleanup(plan, obsolete_absent=True, plaintext_absent=True)
    replay_units = FakeUnits(calls)
    replay_units.candidate_readback = _restart(plan, binding_ref=_CANDIDATE, units=(_UNIT,))
    replay = rotate_credentials(
        plan,
        store=store,
        units=replay_units,
        checker=FakeChecker(calls),
        prior_report=first,
    )
    assert replay == first
    assert calls == [
        "read-switch",
        "read-restart-candidate",
        "check-candidate",
        "check-old-rejected",
        "read-cleanup",
    ]


def test_consistent_caller_forged_success_cannot_bypass_readback() -> None:
    """Catches a structurally valid public report minting success without proof."""
    plan = _plan()
    forged = CredentialRotationReport(
        **_bound(plan),
        state=CredentialRotationState.SUCCEEDED,
        complete=True,
        new_value_works=True,
        old_value_rejected=True,
        old_binding_restored=False,
        candidate_material_absent=False,
        obsolete_binding_absent=True,
        plaintext_staging_absent=True,
        blocker_codes=(),
    )
    result, calls, _store, _units, _checker = _execute(prior_report=forged)

    assert result.state is CredentialRotationState.BLOCKED
    assert result.blocker_codes == (CredentialRotationBlocker.REPLAY_DRIFT,)
    assert calls == [
        "read-switch",
        "read-restart-candidate",
        "check-candidate",
        "check-old-rejected",
        "read-cleanup",
    ]


def test_terminal_replay_drift_cannot_borrow_success() -> None:
    """Catches a terminal result being reused for another rotation identity."""
    first, _calls, _store, _units, _checker = _execute()
    drifted = _plan(rotation_id="rot_" + "9" * 48)

    class ExplodingPort:
        def __getattr__(self, _name: str) -> object:
            message = "drifted replay called an adapter"
            raise AssertionError(message)

    result = rotate_credentials(
        drifted,
        store=cast("SealedCredentialStore", ExplodingPort()),
        units=cast("DependentUnitController", ExplodingPort()),
        checker=cast("CredentialHealthChecker", ExplodingPort()),
        prior_report=first,
    )
    assert result.state is not CredentialRotationState.SUCCEEDED
    assert result.blocker_codes == (CredentialRotationBlocker.REPLAY_DRIFT,)


def test_manifest_and_plan_reject_ambiguous_or_secret_bearing_values() -> None:
    """Catches arbitrary values entering the closed plan surface."""
    entry = CredentialManifestEntry("sql-control", (_UNIT,))
    with pytest.raises(ValueError, match="duplicate credential"):
        build_credential_manifest((entry, entry))
    with pytest.raises((TypeError, ValueError)):
        CredentialManifestEntry("sql-control", cast("tuple[str, ...]", [_UNIT]))
    with pytest.raises(ValueError, match="credential name"):
        CredentialManifestEntry("sk-secretvalue", (_UNIT,))
    with pytest.raises(ValueError, match="credential name"):
        CredentialManifestEntry("a" * 57, (_UNIT,))
    with pytest.raises(ValueError, match="binding reference"):
        plan_rotation(
            build_credential_manifest((entry,)),
            credential_name="sql-control",
            rotation_id=_ROTATION_ID,
            predecessor_binding_ref="postgres://user:secret@host/database",
            candidate_binding_ref=_CANDIDATE,
        )


def test_report_serialization_contains_only_closed_non_secret_facts() -> None:
    """Catches secret or arbitrary adapter material being retained in the report."""
    result, _calls, _store, _units, _checker = _execute()
    document = json.dumps(asdict(result), sort_keys=True)

    assert set(asdict(result)) == {
        "rotation_id",
        "manifest_fingerprint",
        "credential_name",
        "predecessor_binding_ref",
        "candidate_binding_ref",
        "dependent_units",
        "state",
        "complete",
        "new_value_works",
        "old_value_rejected",
        "old_binding_restored",
        "candidate_material_absent",
        "obsolete_binding_absent",
        "plaintext_staging_absent",
        "blocker_codes",
    }
    assert "secret" not in document.lower()
    assert "postgres://" not in document
    assert "command" not in document.lower()


def test_ordinary_adapter_error_is_sanitized() -> None:
    """Catches raw adapter error text leaking through the terminal report."""
    marker = "postgres://admin:leaked-password@host/database"
    calls: list[str] = []
    store = FakeStore(calls)
    store.stage_error = RuntimeError(marker)
    result, _ignored, _store, _units, _checker = _execute(store=store)

    document = json.dumps(asdict(result), sort_keys=True)
    assert result.blocker_codes == (CredentialRotationBlocker.ADAPTER_FAILED,)
    assert marker not in document
    assert "leaked-password" not in document


class AbortRotation(BaseException):
    """Synthetic non-Exception cancellation."""


def test_base_exception_remains_visible() -> None:
    """Catches cancellation being normalized into an ordinary blocker."""
    calls: list[str] = []
    store = FakeStore(calls)
    store.stage_error = AbortRotation()
    with pytest.raises(AbortRotation):
        _execute(store=store)


def test_hostile_receipt_properties_are_never_inspected() -> None:
    """Catches duck-typed hostile receipts running properties during validation."""

    class HostileReceipt:
        @property
        def rotation_id(self) -> str:
            message = "hostile property executed"
            raise AssertionError(message)

    calls: list[str] = []
    store = FakeStore(calls)
    store.stage_candidate = cast("object", lambda _plan: HostileReceipt())  # type: ignore[method-assign]
    result, _ignored, _store, _units, _checker = _execute(store=store)

    assert result.state is CredentialRotationState.BLOCKED
    assert result.blocker_codes == (CredentialRotationBlocker.RECEIPT_MISMATCH,)


def test_hostile_exact_receipt_field_cannot_run_equality_hook() -> None:
    """Catches an exact-class receipt mutated after construction running hostile equality."""

    class HostileEquality:
        __hash__ = object.__hash__

        def __eq__(self, _other: object) -> bool:
            message = "hostile equality executed"
            raise RuntimeError(message)

    class HostileStore(FakeStore):
        def stage_candidate(self, plan: CredentialRotationPlan) -> StageReceipt:
            self.calls.append("stage")
            receipt = _stage(plan)
            object.__setattr__(receipt, "rotation_id", HostileEquality())
            return receipt

    calls: list[str] = []
    result, _ignored, _store, _units, _checker = _execute(store=HostileStore(calls))

    assert result.state is CredentialRotationState.BLOCKED
    assert CredentialRotationBlocker.RECEIPT_MISMATCH in result.blocker_codes
    assert calls == ["stage", "restore", "restart-old", "check-old-restored"]


def test_callback_cannot_mutate_accepted_plan_or_report_binding() -> None:
    """Catches frozen-dataclass bypass in an adapter rebinding accepted facts."""

    class MutatingStore(FakeStore):
        def stage_candidate(self, plan: CredentialRotationPlan) -> StageReceipt:
            self.calls.append("stage")
            object.__setattr__(plan, "rotation_id", "rot_" + "9" * 48)
            return _stage(plan)

    calls: list[str] = []
    original = _plan()
    result, _ignored, _store, _units, _checker = _execute(store=MutatingStore(calls), plan=original)

    assert original.rotation_id == _ROTATION_ID
    assert result.rotation_id == _ROTATION_ID
    assert result.state is CredentialRotationState.BLOCKED
    assert CredentialRotationBlocker.RECEIPT_MISMATCH in result.blocker_codes


@pytest.mark.parametrize("phase", ["switch", "cleanup"])
def test_lost_acknowledgement_requires_exact_phase_readback(phase: str) -> None:
    """Catches switch or cleanup acknowledgement alone being accepted as proof."""
    calls: list[str] = []
    plan = _plan()
    store = FakeStore(calls)
    if phase == "switch":
        store.switch_error = AcknowledgementLost()
    else:
        store.cleanup_error = AcknowledgementLost()
    result, _ignored, _store, _units, _checker = _execute(store=store)
    expected_state = (
        CredentialRotationState.ROLLED_BACK
        if phase == "switch"
        else CredentialRotationState.BLOCKED
    )
    assert result.state is expected_state
    assert CredentialRotationBlocker.ACKNOWLEDGEMENT_UNRECONCILED in result.blocker_codes

    calls = []
    store = FakeStore(calls)
    if phase == "switch":
        store.switch_error = AcknowledgementLost()
        store.switch_readback = _switch(plan)
    else:
        store.cleanup_error = AcknowledgementLost()
        store.cleanup_readback = _cleanup(plan, obsolete_absent=True, plaintext_absent=True)
    result, _ignored, _store, _units, _checker = _execute(store=store)
    assert result.state is CredentialRotationState.SUCCEEDED


def test_lost_rollback_acknowledgement_requires_exact_readback() -> None:
    """Catches a lost restore acknowledgement being inferred as rollback proof."""
    calls: list[str] = []
    plan = _plan()
    store = FakeStore(calls)
    store.rollback_error = AcknowledgementLost()
    checker = FakeChecker(calls)
    checker.candidate_accepted = False
    result, _ignored, _store, _units, _checker = _execute(store=store, checker=checker)
    assert result.state is CredentialRotationState.BLOCKED
    assert CredentialRotationBlocker.ACKNOWLEDGEMENT_UNRECONCILED in result.blocker_codes
    assert CredentialRotationBlocker.ROLLBACK_NOT_PROVED in result.blocker_codes

    calls = []
    store = FakeStore(calls)
    store.rollback_error = AcknowledgementLost()
    store.rollback_readback = _rollback(
        plan, restored=True, candidate_absent=True, plaintext_absent=True
    )
    checker = FakeChecker(calls)
    checker.candidate_accepted = False
    result, _ignored, _store, _units, _checker = _execute(store=store, checker=checker)
    assert result.state is CredentialRotationState.ROLLED_BACK


def test_lost_restart_acknowledgement_requires_exact_readback() -> None:
    """Catches an unobserved restart being inferred from acknowledgement loss."""
    calls: list[str] = []
    units = FakeUnits(calls)
    units.error = AcknowledgementLost()
    result, _ignored, _store, _units, _checker = _execute(units=units)
    assert result.state is CredentialRotationState.BLOCKED
    assert CredentialRotationBlocker.ACKNOWLEDGEMENT_UNRECONCILED in result.blocker_codes

    calls = []
    plan = _plan()
    units = FakeUnits(calls)
    units.error = AcknowledgementLost()
    units.candidate_readback = _restart(plan, binding_ref=_CANDIDATE, units=plan.dependent_units)
    result, _ignored, _store, _units, _checker = _execute(units=units)
    assert result.state is CredentialRotationState.SUCCEEDED


@pytest.mark.parametrize("failure", ["restart", "health"])
def test_rollback_restart_or_health_failure_never_proves_restoration(failure: str) -> None:
    """Catches store restoration alone being reported as a complete rollback."""
    calls: list[str] = []
    checker = FakeChecker(calls)
    checker.candidate_accepted = False

    if failure == "restart":

        class OldRestartFails(FakeUnits):
            def restart_exact(
                self, plan: CredentialRotationPlan, *, binding_ref: str
            ) -> RestartReceipt:
                if binding_ref == plan.predecessor_binding_ref:
                    message = "sensitive restart failure"
                    raise RuntimeError(message)
                return super().restart_exact(plan, binding_ref=binding_ref)

        units: FakeUnits = OldRestartFails(calls)
    else:

        class OldHealthFails(FakeChecker):
            def check_binding(
                self, plan: CredentialRotationPlan, *, binding_ref: str
            ) -> AuthenticationReceipt:
                if binding_ref == plan.predecessor_binding_ref and "restore" in self.calls:
                    message = "sensitive health failure"
                    raise RuntimeError(message)
                return super().check_binding(plan, binding_ref=binding_ref)

        units = FakeUnits(calls)
        checker = OldHealthFails(calls)
        checker.candidate_accepted = False

    result, _ignored, _store, _units, _checker = _execute(units=units, checker=checker)
    assert result.state is CredentialRotationState.BLOCKED
    assert CredentialRotationBlocker.ROLLBACK_NOT_PROVED in result.blocker_codes


def test_unhealthy_predecessor_uses_health_blocker_not_receipt_mismatch() -> None:
    """Catches an exact negative health fact being mislabeled as malformed evidence."""
    calls: list[str] = []
    checker = FakeChecker(calls)
    checker.predecessor_healthy = False
    result, _ignored, _store, _units, _checker = _execute(checker=checker)

    assert result.state is CredentialRotationState.BLOCKED
    assert CredentialRotationBlocker.DEPENDENT_UNITS_UNHEALTHY in result.blocker_codes
    assert CredentialRotationBlocker.RECEIPT_MISMATCH not in result.blocker_codes


@pytest.mark.parametrize(
    "field", ["rotation_id", "manifest_fingerprint", "credential_name", "dependent_units"]
)
def test_common_receipt_binding_drift_fails_closed(field: str) -> None:
    """Catches replay across any common plan-binding dimension."""

    class DriftStore(FakeStore):
        def stage_candidate(self, plan: CredentialRotationPlan) -> StageReceipt:
            self.calls.append("stage")
            values: dict[str, object] = dict(_bound(plan))
            replacements: dict[str, object] = {
                "rotation_id": "rot_" + "8" * 48,
                "manifest_fingerprint": "sha256:" + "7" * 64,
                "credential_name": "sql-review",
                "dependent_units": ("asklegal-review-api.service",),
            }
            values[field] = replacements[field]
            return StageReceipt(**cast("BoundKwargs", values))

    calls: list[str] = []
    result, _ignored, _store, _units, _checker = _execute(store=DriftStore(calls))
    assert result.state is CredentialRotationState.BLOCKED
    assert CredentialRotationBlocker.RECEIPT_MISMATCH in result.blocker_codes


def test_manifest_detaches_caller_owned_units() -> None:
    """Catches later caller mutation changing an accepted manifest or plan."""
    original = (_UNIT,)
    entry = CredentialManifestEntry("sql-control", original)
    manifest = build_credential_manifest((entry,))
    plan = plan_rotation(
        manifest,
        credential_name="sql-control",
        rotation_id=_ROTATION_ID,
        predecessor_binding_ref=_PREDECESSOR,
        candidate_binding_ref=_CANDIDATE,
    )

    assert manifest.entries == (CredentialManifestEntry("sql-control", (_UNIT,)),)
    assert plan.dependent_units == (_UNIT,)


def test_direct_manifest_detaches_entry_objects_before_acceptance() -> None:
    """Catches later mutation of an entry rebinding a directly built manifest."""
    entry = CredentialManifestEntry("sql-control", (_UNIT,))
    built = build_credential_manifest((entry,))
    direct = CredentialManifest(built.manifest_fingerprint, (entry,))

    object.__setattr__(entry, "credential_name", "sql-review")

    assert direct.entries == (CredentialManifestEntry("sql-control", (_UNIT,)),)


def test_detachment_never_executes_hostile_unit_iterators() -> None:
    """Catches tuple conversion executing caller-controlled iteration before validation."""

    class HostileUnits:
        def __iter__(self) -> object:
            message = "hostile iterator executed"
            raise AssertionError(message)

    entry = CredentialManifestEntry("sql-control", (_UNIT,))
    object.__setattr__(entry, "dependent_units", HostileUnits())
    with pytest.raises(TypeError, match="dependent units"):
        build_credential_manifest((entry,))

    plan = _plan()
    object.__setattr__(plan, "dependent_units", HostileUnits())
    calls: list[str] = []
    with pytest.raises(TypeError, match="dependent units"):
        rotate_credentials(
            plan,
            store=FakeStore(calls),
            units=FakeUnits(calls),
            checker=FakeChecker(calls),
        )


class LocalRunner(SystemCommandRunner):
    """Value-free local systemd double used by filesystem-composition tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.candidate_accepted = True

    def run(self, arguments: tuple[str, ...]) -> bool:
        self.calls.append(arguments)
        if arguments[0] == "/usr/local/libexec/asklegal-credential-health":
            binding_ref = arguments[7]
            if binding_ref == _CANDIDATE:
                return self.candidate_accepted
            current = Path(arguments[5]).joinpath("current-sql-control")
            return current.is_symlink() and current.readlink() == Path(_PREDECESSOR)
        return True


def _local_layout(tmp_path: Path) -> tuple[LocalRotationLayout, Path]:
    sealed = tmp_path / "sealed"
    state = tmp_path / "state"
    predecessor = sealed / _PREDECESSOR
    candidate = sealed / _CANDIDATE
    for directory in (sealed, state, predecessor, candidate):
        directory.mkdir()
    predecessor.joinpath("credential.cred").write_bytes(b"opaque-sealed-predecessor")
    candidate.joinpath("credential.cred").write_bytes(b"opaque-sealed-candidate")
    sealed.joinpath("current-sql-control").symlink_to(_PREDECESSOR)
    manifest = build_credential_manifest((CredentialManifestEntry("sql-control", (_UNIT,)),))
    manifest_path = tmp_path / "credential-manifest.json"
    manifest_path.write_bytes(credential_manifest_bytes(manifest))
    return LocalRotationLayout(sealed, predecessor, candidate, state), manifest_path


def _local_plan(layout: LocalRotationLayout, manifest: Path) -> CredentialRotationPlan:
    return plan_local_rotation(
        manifest,
        layout,
        credential_name="sql-control",
        rotation_id=_ROTATION_ID,
    )


def test_cli_defaults_to_value_free_plan_without_mutation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default CLI emits only exact references and never touches rotation state."""
    layout, manifest = _local_layout(tmp_path)
    arguments = [
        "--manifest",
        str(manifest),
        "--credential-name",
        "sql-control",
        "--rotation-id",
        _ROTATION_ID,
        "--sealed-root",
        str(layout.sealed_root),
        "--predecessor-binding-dir",
        str(layout.predecessor_binding_dir),
        "--candidate-binding-dir",
        str(layout.candidate_binding_dir),
        "--state-root",
        str(layout.state_root),
    ]

    assert main(arguments) == 0
    output = capsys.readouterr().out
    assert json.loads(output) == json.loads(
        credential_rotation_plan_bytes(_local_plan(layout, manifest))
    )
    assert not any(layout.state_root.iterdir())
    assert "opaque-sealed" not in output


def test_execution_authority_drift_is_inert_before_adapters(tmp_path: Path) -> None:
    """Wrong plan authority cannot switch a binding, restart a unit, or write state."""
    layout, manifest = _local_layout(tmp_path)
    plan = _local_plan(layout, manifest)
    other = replace(plan, rotation_id="rot_" + "9" * 48)
    authority = tmp_path / "authority.json"
    authority.write_bytes(execution_authority_bytes(other, layout, authority_id="auth_" + "8" * 48))
    runner = LocalRunner()

    with pytest.raises(ValueError, match="rotation authority"):
        execute_local_rotation(plan, layout, authority, runner=runner)

    assert runner.calls == []
    assert layout.sealed_root.joinpath("current-sql-control").readlink() == Path(_PREDECESSOR)
    assert not any(layout.state_root.iterdir())


def test_local_adapters_execute_and_replay_after_restart_without_secret_output(
    tmp_path: Path,
) -> None:
    """Filesystem switch, systemd restart, rejection, cleanup, and replay compose."""
    layout, manifest = _local_layout(tmp_path)
    plan = _local_plan(layout, manifest)
    authority = tmp_path / "authority.json"
    authority.write_bytes(execution_authority_bytes(plan, layout, authority_id="auth_" + "8" * 48))
    runner = LocalRunner()

    first = execute_local_rotation(plan, layout, authority, runner=runner)
    assert first.state is CredentialRotationState.SUCCEEDED
    assert layout.sealed_root.joinpath("current-sql-control").readlink() == Path(_CANDIDATE)
    assert not layout.predecessor_binding_dir.exists()
    assert runner.calls[0] == ("/usr/bin/systemctl", "restart", _UNIT)

    restarted_runner = LocalRunner()
    replay = execute_local_rotation(plan, layout, authority, runner=restarted_runner)
    assert replay == first
    assert all(call[1] in {"authenticate", "is-active"} for call in restarted_runner.calls)
    retained = b"".join(path.read_bytes() for path in layout.state_root.rglob("*.json"))
    assert b"opaque-sealed" not in retained
    assert b"credential.cred" not in retained


def test_terminal_rotation_report_has_an_independent_canonical_parser(tmp_path: Path) -> None:
    """Gate F can revalidate a retained successful rotation without adapter state."""
    layout, manifest = _local_layout(tmp_path)
    plan = _local_plan(layout, manifest)
    authority = tmp_path / "authority.json"
    authority.write_bytes(execution_authority_bytes(plan, layout, authority_id="auth_" + "8" * 48))

    expected = execute_local_rotation(plan, layout, authority, runner=LocalRunner())
    report_path = layout.state_root / plan.rotation_id / "report.json"
    assert parse_credential_rotation_report_bytes(report_path.read_bytes()) == expected

    document = json.loads(report_path.read_bytes())
    document["old_value_rejected"] = False
    hostile = json.dumps(
        document, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()
    with pytest.raises(ValueError, match="credential rotation report"):
        parse_credential_rotation_report_bytes(hostile)


def test_local_candidate_failure_restores_predecessor_and_removes_candidate(
    tmp_path: Path,
) -> None:
    """Negative candidate evidence drives exact rollback and restored health proof."""
    layout, manifest = _local_layout(tmp_path)
    plan = _local_plan(layout, manifest)
    authority = tmp_path / "authority.json"
    authority.write_bytes(execution_authority_bytes(plan, layout, authority_id="auth_" + "8" * 48))
    runner = LocalRunner()
    runner.candidate_accepted = False
    result = execute_local_rotation(plan, layout, authority, runner=runner)
    assert result.state is CredentialRotationState.ROLLED_BACK
    assert layout.sealed_root.joinpath("current-sql-control").readlink() == Path(_PREDECESSOR)
    assert not layout.candidate_binding_dir.exists()
    assert result.plaintext_staging_absent is True
    assert execute_local_rotation(plan, layout, authority, runner=runner) == result


def test_plaintext_staging_presence_blocks_and_is_never_persisted(tmp_path: Path) -> None:
    """Plaintext staging is neither read nor copied and prevents completion."""
    layout, manifest = _local_layout(tmp_path)
    plan = _local_plan(layout, manifest)
    authority = tmp_path / "authority.json"
    authority.write_bytes(execution_authority_bytes(plan, layout, authority_id="auth_" + "8" * 48))
    staging = layout.sealed_root / "plaintext-staging" / plan.credential_name
    staging.parent.mkdir()
    staging.write_bytes(b"forbidden-plaintext-marker")

    result = execute_local_rotation(plan, layout, authority, runner=LocalRunner())
    assert result.complete is False
    assert result.plaintext_staging_absent is False
    assert staging.read_bytes() == b"forbidden-plaintext-marker"
    retained = b"".join(path.read_bytes() for path in layout.state_root.rglob("*.json"))
    assert b"forbidden-plaintext-marker" not in retained
