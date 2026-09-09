"""Continuous Promotion service fail-closed retained-input composition."""

from __future__ import annotations

import json
import multiprocessing
import runpy
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Protocol, cast

import pytest
from _v1_serving_profile_fixture import exact_serving_profile
from asklegal_application_runtime import ServiceExitCode
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_durable_task import OrchestrationStatus
from asklegal_promotion import PromotionError, PromotionManifest, ServingStateCandidate
from asklegal_promotion.backup import freeze_backup_request
from asklegal_promotion_worker import local_serving_state, v1_infrastructure, v1_service
from asklegal_promotion_worker.local_backup import (
    FileNativeBackupWriter,
    FileRecoveryBackupWriter,
)
from asklegal_promotion_worker.local_intents import (
    LocalRetainedEffectIntentSource,
    retain_v1_effect_intents,
)
from asklegal_promotion_worker.local_package import (
    load_v1_promotion_manifest_from_review_package,
)
from asklegal_promotion_worker.local_serving_state import (
    FileServingStateStore,
    initial_serving_state_bytes,
    open_or_initialize_serving_state,
)
from asklegal_promotion_worker.service import PromotionService
from asklegal_promotion_worker.v1_execution import (
    ApprovedPromotionActivity,
    register_approved_promotion_handlers,
)
from asklegal_promotion_worker.v1_infrastructure import V1PromotionPreflight

if TYPE_CHECKING:
    from asklegal_durable_task import ActivityContext

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_NAMESPACE = runpy.run_path(str(_ROOT / "tools/tests/task8_local_review_fixture.py"))
_WRITE_REVIEW_FIXTURE = cast(
    "Callable[..., object]", _FIXTURE_NAMESPACE["write_task8_local_review_fixture"]
)
_APPROVAL_NAMESPACE = runpy.run_path(
    str(_ROOT / "apps/promotion-worker/tests/test_v1_approval_to_promotion.py")
)
_REAL_MANIFEST = cast("Callable[..., object]", _APPROVAL_NAMESPACE["_real_manifest"])


class _FixtureResult(Protocol):
    promotion_manifest_id: str
    promotion_manifest_fingerprint: str


def test_service_is_inert_without_retained_promotion_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing local authority returns NOT_READY before credential construction."""

    def unexpected_credentials(_environment: object) -> object:
        message = "credentials reached before retained promotion authority"
        raise AssertionError(message)

    monkeypatch.setattr(v1_service, "load_v1_infrastructure", unexpected_credentials)
    environment: dict[str, str] = {}
    monkeypatch.setattr(v1_service.os, "environ", environment)
    assert v1_service.run() == int(ServiceExitCode.NOT_READY)


def test_service_is_inert_for_unknown_local_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured but unapproved trigger fails before credential construction."""
    state_root = tmp_path / "state"
    package_root = tmp_path / "package"
    native_root = tmp_path / "native"
    recovery_root = tmp_path / "recovery"
    for directory in (state_root, package_root, native_root, recovery_root):
        directory.mkdir()
    approval_ledger = tmp_path / "approval-ledger.json"
    approval_ledger.write_bytes(
        canonicalize(
            checked_json_value(
                {
                    "approval_states": {},
                    "events": [],
                    "revoked": [],
                    "schema_id": "asklegal.local-review-approval-ledger/v1",
                }
            )
        )
    )
    trigger = state_root / "approval-trigger.json"
    trigger.write_bytes(
        canonicalize(
            checked_json_value(
                {
                    "approval_id": "apr_" + "1" * 48,
                    "execution_lineage_id": "exe_" + "2" * 48,
                    "execution_time": "2026-09-08T00:00:00Z",
                    "schema_id": "asklegal.local-promotion-trigger/v1",
                }
            )
        )
    )
    files = {
        "ASKLEGAL_PROMOTION_APPROVAL_LEDGER": approval_ledger,
        "ASKLEGAL_PROMOTION_CURRENT_SERVING_STATE": state_root / "current-serving-state",
        "ASKLEGAL_PROMOTION_EFFECT_INTENT_LEDGER": state_root / "effect-intents",
        "ASKLEGAL_PROMOTION_SERVING_PROFILE": tmp_path / "serving-profile.json",
        "ASKLEGAL_PROMOTION_TOKENIZER_RESOURCE": tmp_path / "tokenizer.tiktoken",
        "ASKLEGAL_PROMOTION_TRIGGER": trigger,
    }
    files["ASKLEGAL_PROMOTION_EFFECT_INTENT_LEDGER"].mkdir()
    for path in files.values():
        if not path.exists():
            path.write_bytes(b"{}")
    environment = {
        **{key: str(path) for key, path in files.items()},
        "ASKLEGAL_PROMOTION_NATIVE_BACKUP_ROOT": str(native_root),
        "ASKLEGAL_PROMOTION_PACKAGE_ROOT": str(package_root),
        "ASKLEGAL_PROMOTION_RECOVERY_BACKUP_ROOT": str(recovery_root),
        "ASKLEGAL_PROMOTION_STATE_ROOT": str(state_root),
    }

    def unexpected_credentials(_environment: object) -> object:
        message = "credentials reached for unapproved local trigger"
        raise AssertionError(message)

    monkeypatch.setattr(v1_service, "load_v1_infrastructure", unexpected_credentials)
    monkeypatch.setattr(v1_service.os, "environ", environment)
    assert v1_service.run() == int(ServiceExitCode.NOT_READY)


def test_stable_idle_configuration_does_not_require_future_serving_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh worker can become healthy before its first approved proposal exists."""
    state_root = tmp_path / "promotion"
    state_root.mkdir()
    for name in (
        "package",
        "native",
        "recovery",
    ):
        (tmp_path / name).mkdir()
    approval_ledger = tmp_path / "review" / "approval-register.json"
    approval_ledger.parent.mkdir()
    profile_path = tmp_path / "serving-profile.json"
    tokenizer_path = tmp_path / "tokenizer.tiktoken"
    profile_path.write_bytes(b"profile")
    tokenizer_path.write_bytes(b"tokenizer")
    environment = {
        "ASKLEGAL_PROMOTION_APPROVAL_LEDGER": str(approval_ledger),
        "ASKLEGAL_PROMOTION_CURRENT_SERVING_STATE": str(state_root / "current-serving-state"),
        "ASKLEGAL_PROMOTION_EFFECT_INTENT_LEDGER": str(tmp_path / "effect-intents"),
        "ASKLEGAL_PROMOTION_NATIVE_BACKUP_ROOT": str(tmp_path / "native"),
        "ASKLEGAL_PROMOTION_PACKAGE_ROOT": str(tmp_path / "package"),
        "ASKLEGAL_PROMOTION_RECOVERY_BACKUP_ROOT": str(tmp_path / "recovery"),
        "ASKLEGAL_PROMOTION_SERVING_PROFILE": str(profile_path),
        "ASKLEGAL_PROMOTION_STATE_ROOT": str(state_root),
        "ASKLEGAL_PROMOTION_TOKENIZER_RESOURCE": str(tokenizer_path),
    }

    def fake_profile(_reader: object) -> object:
        return SimpleNamespace(embedding=SimpleNamespace(tokenizer="test"))

    def fake_counter(*_args: object) -> object:
        return object()

    monkeypatch.setattr(v1_infrastructure, "load_serving_capability_profile", fake_profile)
    monkeypatch.setattr(v1_infrastructure, "ExactTokenizerResourceCounter", fake_counter)

    trigger_root = v1_infrastructure.validate_v1_promotion_configuration(environment)

    assert trigger_root == approval_ledger.parent / "promotion-triggers"
    assert not (state_root / "current-serving-state").exists()
    assert (tmp_path / "effect-intents").is_dir()


def _reference(kind: ReferenceType, digit: str) -> ImmutableReference:
    prefix = "cap" if kind is ReferenceType.CAPABILITY_PROFILE else "art"
    return ImmutableReference(kind, f"{prefix}_{digit * 48}", f"sha256:{digit * 64}")


def test_file_serving_state_cas_readback_and_restart(tmp_path: Path) -> None:
    """Activation and exact rollback replay survive store reconstruction."""
    root = tmp_path
    base = "srv_" + "1" * 48
    candidate_id = "srv_" + "2" * 48
    state_path = root / "current-serving-state"
    state_path.write_bytes(initial_serving_state_bytes(base))
    candidate = ServingStateCandidate(
        candidate_id,
        "sha256:" + "2" * 64,
        base,
        "asklegal-dev-hk-20260908-" + "2" * 16,
        "sha256:" + "3" * 64,
        "sha256:" + "4" * 64,
        "emp_" + "5" * 48,
        "sha256:" + "5" * 64,
        "apr_" + "6" * 48,
        "exe_" + "7" * 48,
    )
    activation = FileServingStateStore(state_path).activate(base, candidate)
    restarted = FileServingStateStore(state_path)
    restarted.verify(candidate_id)
    replay = restarted.activate(base, candidate)
    assert replay.replayed is True
    rollback = restarted.rollback(candidate, activation.receipt_id)
    assert rollback.state_id == base
    assert (
        FileServingStateStore(state_path).rollback(candidate, activation.receipt_id).replayed
        is True
    )


def test_first_approved_manifest_initializes_serving_state_once(tmp_path: Path) -> None:
    """An idle installation needs no invented state, while deletion fails closed."""
    state_path = tmp_path / "current-serving-state"
    base = "srv_" + "1" * 48

    first = open_or_initialize_serving_state(state_path, base)
    assert first.active_state_id == base
    assert open_or_initialize_serving_state(state_path, base).active_state_id == base
    marker = state_path.with_suffix(".initialized")
    assert marker.is_file()

    candidate = ServingStateCandidate(
        "srv_" + "2" * 48,
        "sha256:" + "2" * 64,
        base,
        "asklegal-dev-candidate",
        "sha256:" + "3" * 64,
        "sha256:" + "4" * 64,
        "emp_" + "5" * 48,
        "sha256:" + "5" * 64,
        "apr_" + "6" * 48,
        "exe_" + "7" * 48,
    )
    first.activate(base, candidate)
    assert (
        open_or_initialize_serving_state(state_path, candidate.state_id).active_state_id
        == candidate.state_id
    )

    state_path.unlink()
    with pytest.raises(PromotionError):
        open_or_initialize_serving_state(state_path, base)


def test_file_serving_state_supports_a_second_distinct_promotion(tmp_path: Path) -> None:
    """The retained current-state projection advances across successive releases."""
    state_path = tmp_path / "current-serving-state"
    base = "srv_" + "1" * 48
    first = ServingStateCandidate(
        "srv_" + "2" * 48,
        "sha256:" + "2" * 64,
        base,
        "asklegal-dev-first",
        "sha256:" + "3" * 64,
        "sha256:" + "4" * 64,
        "emp_" + "5" * 48,
        "sha256:" + "5" * 64,
        "apr_" + "6" * 48,
        "exe_" + "7" * 48,
    )
    second = ServingStateCandidate(
        "srv_" + "8" * 48,
        "sha256:" + "8" * 64,
        first.state_id,
        "asklegal-dev-second",
        "sha256:" + "9" * 64,
        "sha256:" + "a" * 64,
        "emp_" + "b" * 48,
        "sha256:" + "b" * 64,
        "apr_" + "c" * 48,
        "exe_" + "d" * 48,
    )

    store = open_or_initialize_serving_state(state_path, base)
    store.activate(base, first)
    second_receipt = store.activate(first.state_id, second)

    restarted = open_or_initialize_serving_state(state_path, second.state_id)
    assert restarted.active_state_id == second.state_id
    assert restarted.activate(first.state_id, second).replayed is True
    rollback = restarted.rollback(second, second_receipt.receipt_id)
    assert rollback.state_id == first.state_id
    assert restarted.restore(second, rollback.receipt_id).state_id == second.state_id
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(state_path.with_suffix(".initialized").stat().st_mode) == 0o600


def test_file_serving_state_does_not_follow_or_remove_temporary_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pre-planted temporary path cannot redirect or be consumed by a state write."""
    state_path = tmp_path / "current-serving-state"
    base = "srv_" + "1" * 48
    store = open_or_initialize_serving_state(state_path, base)
    candidate = ServingStateCandidate(
        "srv_" + "2" * 48,
        "sha256:" + "2" * 64,
        base,
        "asklegal-dev-candidate",
        "sha256:" + "3" * 64,
        "sha256:" + "4" * 64,
        "emp_" + "5" * 48,
        "sha256:" + "5" * 64,
        "apr_" + "6" * 48,
        "exe_" + "7" * 48,
    )
    external = tmp_path / "external"
    external.write_bytes(b"unchanged")
    temporary = tmp_path / ".current-serving-state.fixed.tmp"
    temporary.symlink_to(external)

    def fixed_token(_size: int) -> str:
        return "fixed"

    monkeypatch.setattr(local_serving_state, "token_hex", fixed_token)

    with pytest.raises(PromotionError):
        store.activate(base, candidate)

    assert external.read_bytes() == b"unchanged"
    assert temporary.is_symlink()
    assert store.active_state_id == base


def test_distinct_file_backup_writers_replay_exact_readback(tmp_path: Path) -> None:
    """Native and recovery paths retain independently verifiable artifacts."""
    root = tmp_path
    native_root = root / "native"
    recovery_root = root / "recovery"
    native_root.mkdir()
    recovery_root.mkdir()
    request = freeze_backup_request(
        target_name="asklegal-dev-candidate",
        target_definition_ref=_reference(ReferenceType.PINECONE_INDEX_GENERATION, "1"),
        desired_inventory_fingerprint="sha256:" + "2" * 64,
        backup_profile_ref=_reference(ReferenceType.CAPABILITY_PROFILE, "3"),
        source_export_ref=_reference(ReferenceType.ARTIFACT, "4"),
    )
    native = FileNativeBackupWriter(native_root, "native-local-v1")
    recovery = FileRecoveryBackupWriter(recovery_root, "recovery-local-v1")
    first_native = native.write_native(request)
    first_recovery = recovery.write_recovery(request)
    assert native.write_native(request) == first_native
    assert recovery.write_recovery(request) == first_recovery
    native_readback = native.read_native(request)
    recovery_readback = recovery.read_recovery(request)
    assert native_readback is not None
    assert recovery_readback is not None
    assert native_readback.role != recovery_readback.role
    assert native_readback.backend_id != recovery_readback.backend_id
    assert len(tuple(native_root.glob("*.json"))) == 1
    assert len(tuple(recovery_root.glob("*.json"))) == 1


class _RegistrationWorker:
    def __init__(self) -> None:
        self.activities: list[str] = []
        self.orchestrators: list[str] = []

    def add_activity(self, fn: Callable[..., object]) -> str:
        name = getattr(fn, "__name__", "")
        self.activities.append(name)
        return name

    def add_orchestrator(self, fn: Callable[..., object]) -> str:
        name = getattr(fn, "__name__", "")
        self.orchestrators.append(name)
        return name


def test_only_stable_approval_triggered_promotion_handlers_are_registered() -> None:
    """Continuous worker exposes one named Approval-bound execution boundary."""
    worker = _RegistrationWorker()
    activity = ApprovedPromotionActivity(
        PromotionService.__new__(PromotionService),
        V1PromotionPreflight.__new__(V1PromotionPreflight),
    )
    register_approved_promotion_handlers(worker, activity)
    assert worker.activities == ["promote_approved_hk_v1"]
    assert worker.orchestrators == ["promote_approved_hk_v1"]


@dataclass(frozen=True, slots=True)
class _WakeupState:
    runtime_status: OrchestrationStatus
    instance_id: str
    name: str
    created_at: datetime
    last_updated_at: datetime
    serialized_input: str
    failure_details: object | None


def _wakeup_state(
    status: OrchestrationStatus,
    approval_id: str,
    execution_id: str,
    generation: int = 1,
) -> _WakeupState:
    created = datetime(2026, 8, 16, 1, tzinfo=UTC) + timedelta(minutes=generation)
    failure = (
        SimpleNamespace(message="retained failure", error_type="RuntimeError", stack_trace=None)
        if status is OrchestrationStatus.FAILED
        else None
    )
    return _WakeupState(
        status,
        execution_id,
        "promote_approved_hk_v1",
        created,
        created,
        canonicalize(
            checked_json_value({"approval_id": approval_id, "execution_lineage_id": execution_id})
        ).decode(),
        failure,
    )


class _WakeupClient:
    def __init__(self) -> None:
        self.states: dict[str, object] = {}
        self.calls: list[tuple[str, object, str, str]] = []
        self.restart_calls: list[tuple[str, bool]] = []

    def get_orchestration_state(self, instance_id: str) -> object | None:
        return self.states.get(instance_id)

    def schedule_new_orchestration(
        self,
        orchestrator: str,
        *,
        input: object,  # noqa: A002 - mirrors durable-task SDK.
        instance_id: str,
        version: str,
    ) -> str:
        self.calls.append((orchestrator, input, instance_id, version))
        approval_id = cast("dict[str, str]", input)["approval_id"]
        self.states[instance_id] = _wakeup_state(
            OrchestrationStatus.PENDING, approval_id, instance_id
        )
        return instance_id

    def restart_orchestration(
        self,
        instance_id: str,
        *,
        restart_with_new_instance_id: bool = False,
    ) -> str:
        self.restart_calls.append((instance_id, restart_with_new_instance_id))
        current = cast("_WakeupState", self.states[instance_id])
        self.states[instance_id] = replace(
            current,
            runtime_status=OrchestrationStatus.PENDING,
            created_at=current.created_at + timedelta(minutes=1),
            last_updated_at=current.last_updated_at + timedelta(minutes=1),
            failure_details=None,
        )
        return instance_id


class _CrossProcessClient:
    """Minimal fixed-generation client used to exercise the filesystem fence."""

    def __init__(self, state: _WakeupState, counter: _SharedCounter) -> None:
        self.state = state
        self.counter = counter

    def get_orchestration_state(self, instance_id: str) -> object:
        del instance_id
        return self.state

    def schedule_new_orchestration(self, *_args: object, **_kwargs: object) -> str:
        message = "unexpected initial schedule"
        raise AssertionError(message)

    def restart_orchestration(
        self, instance_id: str, *, restart_with_new_instance_id: bool = False
    ) -> str:
        del restart_with_new_instance_id
        with self.counter.get_lock():
            self.counter.value += 1
        time.sleep(0.1)
        return instance_id


class _SharedLock(Protocol):
    def __enter__(self) -> object: ...

    def __exit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> object: ...


class _SharedCounter(Protocol):
    value: int

    def get_lock(self) -> _SharedLock: ...


class _StartEvent(Protocol):
    def wait(self) -> bool: ...


def _cross_process_dispatch(  # noqa: PLR0913,PLR0917
    trigger_root: str,
    intent_root: str,
    approval_id: str,
    execution_id: str,
    counter: _SharedCounter,
    start: _StartEvent,
) -> None:
    client = _CrossProcessClient(
        _wakeup_state(OrchestrationStatus.FAILED, approval_id, execution_id), counter
    )
    start.wait()
    v1_service.dispatch_pending_promotions(
        client,
        Path(trigger_root),
        effect_intent_root=Path(intent_root),
        now=_retry_now,
    )


_RETRY_TIME = "2026-08-16T01:00:00Z"


def _retry_now() -> datetime:
    return datetime(2026, 8, 16, 2, tzinfo=UTC)


def _write_retry_trigger(root: Path, approval_id: str, execution_id: str) -> None:
    (root / f"{approval_id}.json").write_bytes(
        canonicalize(
            checked_json_value(
                {
                    "approval_id": approval_id,
                    "execution_lineage_id": execution_id,
                    "execution_time": _RETRY_TIME,
                    "schema_id": "asklegal.local-promotion-trigger/v1",
                }
            )
        )
    )


def _write_retry_intents(root: Path, approval_id: str, execution_id: str) -> Path:
    intent_root = root.parent / "effect-intents"
    intent_root.mkdir(exist_ok=True)
    profile = exact_serving_profile()
    retain_v1_effect_intents(
        intent_root,
        approval_id=approval_id,
        execution_lineage_id=execution_id,
        execution_time=_RETRY_TIME,
        manifest=cast("PromotionManifest", _REAL_MANIFEST(profile)),
        profile=profile,
    )
    return intent_root


def _write_recovery_authority(
    recovery_root: Path,
    intent_root: Path,
    approval_id: str,
    execution_id: str,
) -> None:
    payload = {
        "approval_id": approval_id,
        "execution_lineage_id": execution_id,
        "execution_time": _RETRY_TIME,
    }
    policy = v1_service._policy(intent_root, payload)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    authority: dict[str, object] = {
        "approval_id": approval_id,
        "authorized_attempt": 2,
        "authorized_at": "2026-08-16T01:30:00Z",
        "execution_lineage_id": execution_id,
        "expires_at": "2026-08-16T03:00:00Z",
        "policy_fingerprint": policy.fingerprint,
        "schema_id": "asklegal.local-promotion-recovery-authority/v1",
        "terminal_status": "TERMINATED",
    }
    authority["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(authority))).hexdigest()
    )
    (recovery_root / f"{execution_id}.attempt-000002.json").write_bytes(
        canonicalize(checked_json_value(authority))
    )


def test_retained_review_trigger_schedules_once_across_promotion_restart(tmp_path: Path) -> None:
    """The shared retained trigger is a replay-safe cross-process wakeup queue."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "1" * 48
    execution_id = "exe_" + "2" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    client = _WakeupClient()
    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=_retry_now
    )
    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=_retry_now
    )
    assert client.calls == [
        (
            "promote_approved_hk_v1",
            {"approval_id": approval_id, "execution_lineage_id": execution_id},
            execution_id,
            "1.0.0",
        )
    ]


def test_failed_promotion_restarts_under_the_same_approval_lineage(
    tmp_path: Path,
) -> None:
    """A durable transport failure retries without replacing Approval lineage identity."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "3" * 48
    execution_id = "exe_" + "4" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    client = _WakeupClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.FAILED, approval_id, execution_id
    )

    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=_retry_now
    )
    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=_retry_now
    )
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.FAILED, approval_id, execution_id, 3
    )
    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=_retry_now
    )

    assert client.restart_calls == [(execution_id, False)]
    stopped = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert stopped["attempt_count"] == 2
    assert stopped["phase"] == "STOPPED"


def test_failed_promotion_past_intent_deadline_never_restarts(tmp_path: Path) -> None:
    """Wall-clock expiry is a retained stop, not another scheduler attempt."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "9" * 48
    execution_id = "exe_" + "a" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    client = _WakeupClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.FAILED, approval_id, execution_id
    )

    v1_service.dispatch_pending_promotions(
        client,
        root,
        effect_intent_root=intent_root,
        now=lambda: datetime(2026, 8, 18, tzinfo=UTC),
    )

    assert client.restart_calls == []
    stopped = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert stopped["attempt_count"] == 1
    assert stopped["phase"] == "STOPPED"


def test_failed_promotion_rejects_non_reconciling_intent_retry_class(tmp_path: Path) -> None:
    """The dispatcher cannot silently strengthen a caller-authored retry policy."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "d" * 48
    execution_id = "exe_" + "e" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    ledger_path = intent_root / f"{execution_id}.json"
    ledger = cast("dict[str, object]", json.loads(ledger_path.read_bytes()))
    intents = cast("list[dict[str, object]]", ledger["effect_intents"])
    for intent in intents:
        intent["retry_class"] = "SAFE_SAME_INTENT"
    ledger_path.write_bytes(canonicalize(checked_json_value(ledger)))
    client = _WakeupClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.FAILED, approval_id, execution_id
    )

    with pytest.raises(v1_service.PromotionCompositionError):
        v1_service.dispatch_pending_promotions(
            client, root, effect_intent_root=intent_root, now=_retry_now
        )

    assert client.restart_calls == []


def test_terminated_promotion_requires_exact_retained_recovery_authority(tmp_path: Path) -> None:
    """Administrative termination cannot be revived by ordinary retry policy alone."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "7" * 48
    execution_id = "exe_" + "8" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    recovery_root = tmp_path / "promotion-recovery-authorities"
    recovery_root.mkdir()
    client = _WakeupClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.TERMINATED, approval_id, execution_id
    )

    v1_service.dispatch_pending_promotions(
        client,
        root,
        effect_intent_root=intent_root,
        recovery_authority_root=recovery_root,
        now=_retry_now,
    )
    assert client.restart_calls == []

    _write_recovery_authority(recovery_root, intent_root, approval_id, execution_id)

    v1_service.dispatch_pending_promotions(
        client,
        root,
        effect_intent_root=intent_root,
        recovery_authority_root=recovery_root,
        now=_retry_now,
    )
    assert client.restart_calls == [(execution_id, False)]
    assert (recovery_root / f"{execution_id}.attempt-000002.consumed.json").is_file()

    # Losing the mutable retry projection cannot make consumed authority reusable.
    (tmp_path / "promotion-dispatch" / f"{execution_id}.json").unlink()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.TERMINATED, approval_id, execution_id
    )
    v1_service.dispatch_pending_promotions(
        client,
        root,
        effect_intent_root=intent_root,
        recovery_authority_root=recovery_root,
        now=_retry_now,
    )
    assert client.restart_calls == [(execution_id, False)]


def test_unchanged_terminal_promotion_state_is_not_restarted_in_a_busy_loop(
    tmp_path: Path,
) -> None:
    """A stale terminal read cannot spend the same retained retry repeatedly."""

    class StickyTerminalClient(_WakeupClient):
        def restart_orchestration(
            self,
            instance_id: str,
            *,
            restart_with_new_instance_id: bool = False,
        ) -> str:
            self.restart_calls.append((instance_id, restart_with_new_instance_id))
            return instance_id

    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "5" * 48
    execution_id = "exe_" + "6" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    client = StickyTerminalClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.FAILED, approval_id, execution_id
    )

    for _ in range(7):
        v1_service.dispatch_pending_promotions(
            client, root, effect_intent_root=intent_root, now=_retry_now
        )

    assert client.restart_calls == [(execution_id, False)]
    assert client.calls == []
    retained = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert retained["attempt_count"] == 2
    assert retained["phase"] == "OUTCOME_UNKNOWN"
    assert (
        cast("_WakeupState", client.states[execution_id]).runtime_status
        is OrchestrationStatus.FAILED
    )

    v1_service.dispatch_pending_promotions(
        client,
        root,
        effect_intent_root=intent_root,
        now=lambda: datetime(2026, 8, 18, tzinfo=UTC),
    )
    expired = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert expired["phase"] == "STOPPED"
    assert client.restart_calls == [(execution_id, False)]


def test_terminated_no_op_restart_does_not_consume_recovery_authority(
    tmp_path: Path,
) -> None:
    """A reserved authority is consumed only after a changed scheduler generation."""

    class NoEffectRestartClient(_WakeupClient):
        def restart_orchestration(
            self,
            instance_id: str,
            *,
            restart_with_new_instance_id: bool = False,
        ) -> str:
            self.restart_calls.append((instance_id, restart_with_new_instance_id))
            message = "scheduler did not mutate before acknowledgement loss"
            raise OSError(message)

    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "7" * 48
    execution_id = "exe_" + "8" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    recovery_root = tmp_path / "promotion-recovery-authorities"
    recovery_root.mkdir()
    client = NoEffectRestartClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.TERMINATED, approval_id, execution_id
    )
    _write_recovery_authority(recovery_root, intent_root, approval_id, execution_id)

    v1_service.dispatch_pending_promotions(
        client,
        root,
        effect_intent_root=intent_root,
        recovery_authority_root=recovery_root,
        now=_retry_now,
    )

    assert client.restart_calls == [(execution_id, False)]
    assert not (recovery_root / f"{execution_id}.attempt-000002.consumed.json").exists()


def test_terminated_lost_ack_consumes_authority_after_generation_readback(
    tmp_path: Path,
) -> None:
    """A changed scheduler generation reconciles a lost acknowledgement exactly once."""

    class LostAckRestartClient(_WakeupClient):
        def restart_orchestration(
            self,
            instance_id: str,
            *,
            restart_with_new_instance_id: bool = False,
        ) -> str:
            self.restart_calls.append((instance_id, restart_with_new_instance_id))
            current = cast("_WakeupState", self.states[instance_id])
            self.states[instance_id] = replace(
                current,
                runtime_status=OrchestrationStatus.PENDING,
                created_at=current.created_at + timedelta(minutes=1),
                last_updated_at=current.last_updated_at + timedelta(minutes=1),
                failure_details=None,
            )
            message = "restart acknowledgement lost after scheduler mutation"
            raise OSError(message)

    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "9" * 48
    execution_id = "exe_" + "a" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    recovery_root = tmp_path / "promotion-recovery-authorities"
    recovery_root.mkdir()
    _write_recovery_authority(recovery_root, intent_root, approval_id, execution_id)
    client = LostAckRestartClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.TERMINATED, approval_id, execution_id
    )

    v1_service.dispatch_pending_promotions(
        client,
        root,
        effect_intent_root=intent_root,
        recovery_authority_root=recovery_root,
        now=_retry_now,
    )

    retained = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert client.restart_calls == [(execution_id, False)]
    assert retained["phase"] == "ACTIVE"
    assert (recovery_root / f"{execution_id}.attempt-000002.consumed.json").is_file()


def test_last_updated_change_does_not_masquerade_as_a_new_scheduler_generation(
    tmp_path: Path,
) -> None:
    """Mutable polling metadata cannot prove the reserved restart happened."""

    class StickyTerminalClient(_WakeupClient):
        def restart_orchestration(
            self,
            instance_id: str,
            *,
            restart_with_new_instance_id: bool = False,
        ) -> str:
            self.restart_calls.append((instance_id, restart_with_new_instance_id))
            return instance_id

    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "5" * 48
    execution_id = "exe_" + "6" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    client = StickyTerminalClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.FAILED, approval_id, execution_id
    )
    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=_retry_now
    )
    prior = cast("_WakeupState", client.states[execution_id])
    client.states[execution_id] = replace(
        prior,
        last_updated_at=prior.last_updated_at + timedelta(seconds=1),
    )

    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=_retry_now
    )

    retained = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert retained["phase"] == "OUTCOME_UNKNOWN"
    assert client.restart_calls == [(execution_id, False)]


def test_cross_process_dispatchers_reserve_exactly_one_retry(tmp_path: Path) -> None:
    """The retained attempt fence covers read, decision, and reservation across processes."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "b" * 48
    execution_id = "exe_" + "c" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    context = multiprocessing.get_context("fork")
    counter = context.Value("i", 0)
    start = context.Barrier(2)
    processes = [
        context.Process(
            target=_cross_process_dispatch,
            args=(str(root), str(intent_root), approval_id, execution_id, counter, start),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0
    assert counter.value == 1


def test_scheduler_loss_never_reschedules_a_stopped_attempt(tmp_path: Path) -> None:
    """A memory-only scheduler restart cannot erase a retained stop decision."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "9" * 48
    execution_id = "exe_" + "a" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    client = _WakeupClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.FAILED, approval_id, execution_id
    )

    def expired() -> datetime:
        return datetime(2026, 8, 18, tzinfo=UTC)

    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=expired
    )
    client.states.clear()
    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=expired
    )
    assert client.calls == []
    assert client.restart_calls == []


def test_initial_schedule_stops_when_current_deadline_is_closed(tmp_path: Path) -> None:
    """A retained old trigger cannot begin its first effect lineage after expiry."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "3" * 48
    execution_id = "exe_" + "4" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    client = _WakeupClient()
    v1_service.dispatch_pending_promotions(
        client,
        root,
        effect_intent_root=intent_root,
        now=lambda: datetime(2026, 8, 18, tzinfo=UTC),
    )
    retained = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert client.calls == []
    assert retained["attempt_count"] == 0
    assert retained["phase"] == "STOPPED"


@pytest.mark.parametrize("mode", ["INITIAL", "RETRY"])
def test_dispatch_rechecks_deadline_after_scheduler_read_before_action(
    tmp_path: Path, mode: str
) -> None:
    """A scheduler read crossing the deadline cannot start or restart work."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "3" * 48
    execution_id = "exe_" + "4" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    clock = [datetime(2026, 8, 16, 2, tzinfo=UTC)]

    class DeadlineCrossingClient(_WakeupClient):
        def __init__(self) -> None:
            super().__init__()
            self.read_count = 0

        def get_orchestration_state(self, instance_id: str) -> object | None:
            self.read_count += 1
            state = super().get_orchestration_state(instance_id)
            if self.read_count == 2:
                clock[0] = datetime(2026, 8, 18, tzinfo=UTC)
            return state

    client = DeadlineCrossingClient()
    if mode == "RETRY":
        client.states[execution_id] = _wakeup_state(
            OrchestrationStatus.FAILED, approval_id, execution_id
        )

    v1_service.dispatch_pending_promotions(
        client,
        root,
        effect_intent_root=intent_root,
        now=lambda: clock[0],
    )

    assert client.calls == []
    assert client.restart_calls == []
    retained = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert retained["phase"] == "STOPPED"


def test_terminated_authority_expiry_is_rechecked_at_restart_boundary(tmp_path: Path) -> None:
    """Authority expiring during scheduler read-back cannot authorize restart."""
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "7" * 48
    execution_id = "exe_" + "8" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    recovery_root = tmp_path / "promotion-recovery-authorities"
    recovery_root.mkdir()
    _write_recovery_authority(recovery_root, intent_root, approval_id, execution_id)
    clock = [datetime(2026, 8, 16, 2, tzinfo=UTC)]

    class AuthorityExpiryClient(_WakeupClient):
        def __init__(self) -> None:
            super().__init__()
            self.read_count = 0

        def get_orchestration_state(self, instance_id: str) -> object | None:
            self.read_count += 1
            state = super().get_orchestration_state(instance_id)
            if self.read_count == 2:
                clock[0] = datetime(2026, 8, 16, 3, tzinfo=UTC)
            return state

    client = AuthorityExpiryClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.TERMINATED, approval_id, execution_id
    )

    with pytest.raises(
        v1_service.PromotionCompositionError,
        match="PROMOTION_LOCAL_INPUTS_NOT_READY",
    ):
        v1_service.dispatch_pending_promotions(
            client,
            root,
            effect_intent_root=intent_root,
            recovery_authority_root=recovery_root,
            now=lambda: clock[0],
        )

    assert client.restart_calls == []
    assert not (recovery_root / f"{execution_id}.attempt-000002.consumed.json").exists()
    retained = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert retained["phase"] == "OUTCOME_UNKNOWN"


def test_lost_restart_ack_reconciles_changed_terminal_generation_once(tmp_path: Path) -> None:
    """A changed terminal timestamp proves the retried generation settled without replay."""

    class LostAckClient(_WakeupClient):
        def restart_orchestration(
            self,
            instance_id: str,
            *,
            restart_with_new_instance_id: bool = False,
        ) -> str:
            self.restart_calls.append((instance_id, restart_with_new_instance_id))
            current = cast("_WakeupState", self.states[instance_id])
            self.states[instance_id] = replace(
                current,
                created_at=current.created_at + timedelta(minutes=1),
                last_updated_at=current.last_updated_at + timedelta(minutes=1),
            )
            message = "acknowledgement lost"
            raise OSError(message)

    root = tmp_path / "promotion-triggers"
    root.mkdir()
    approval_id = "apr_" + "5" * 48
    execution_id = "exe_" + "6" * 48
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    client = LostAckClient()
    client.states[execution_id] = _wakeup_state(
        OrchestrationStatus.FAILED, approval_id, execution_id
    )
    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=_retry_now
    )
    v1_service.dispatch_pending_promotions(
        client, root, effect_intent_root=intent_root, now=_retry_now
    )
    retained = cast(
        "dict[str, object]",
        json.loads((tmp_path / "promotion-dispatch" / f"{execution_id}.json").read_bytes()),
    )
    assert client.restart_calls == [(execution_id, False)]
    assert retained["attempt_count"] == 2
    assert retained["phase"] == "STOPPED"


def test_activity_rechecks_current_deadline_before_service_effects(tmp_path: Path) -> None:
    """The activity does not trust the old trigger timestamp at the effect boundary."""
    approval_id = "apr_" + "7" * 48
    execution_id = "exe_" + "8" * 48
    root = tmp_path / "promotion-triggers"
    root.mkdir()
    _write_retry_trigger(root, approval_id, execution_id)
    intent_root = _write_retry_intents(root, approval_id, execution_id)
    manifest = cast("PromotionManifest", _REAL_MANIFEST(exact_serving_profile()))

    class NeverService:
        def execute_hk_v1(self, *_args: object, **_kwargs: object) -> object:
            message = "service effects reached after deadline"
            raise AssertionError(message)

    preflight = cast(
        "V1PromotionPreflight",
        SimpleNamespace(
            approval_id=approval_id,
            execution_lineage_id=execution_id,
            manifest=manifest,
            intents=LocalRetainedEffectIntentSource(intent_root / f"{execution_id}.json"),
        ),
    )
    activity = ApprovedPromotionActivity(
        cast("PromotionService", NeverService()),
        preflight,
        now=lambda: datetime(2026, 8, 18, tzinfo=UTC),
    )
    with pytest.raises(RuntimeError, match="PROMOTION_EXECUTION_WINDOW_CLOSED"):
        activity.promote_approved_hk_v1(
            cast("ActivityContext", None),
            {"approval_id": approval_id, "execution_lineage_id": execution_id},
        )


def test_executable_review_package_recovers_exact_typed_manifest(tmp_path: Path) -> None:
    """Loader re-freezes full records from reviewed members, never a lossy sidecar."""
    profile = exact_serving_profile()
    expected = cast("PromotionManifest", _REAL_MANIFEST(profile))
    fixture = cast(
        "_FixtureResult",
        _WRITE_REVIEW_FIXTURE(
            tmp_path,
            _ROOT,
            live_profile=(
                expected,
                profile.fingerprint,
                profile.namespace,
                profile.backup_profile_ref.fingerprint,
            ),
        ),
    )
    recovered = load_v1_promotion_manifest_from_review_package(
        tmp_path,
        profile,
        expected_manifest_id=fixture.promotion_manifest_id,
        expected_manifest_fingerprint=fixture.promotion_manifest_fingerprint,
    )
    assert recovered.fingerprint == fixture.promotion_manifest_fingerprint
    assert recovered.desired_state.records == expected.desired_state.records
