"""Fail-closed V1 PROMOTION_WORKER service process.

This is the continuous V1 entrypoint, not the local `--check` boundary. It loads
its own systemd credentials, composes only its own adapters, proves every declared
dependency once, and then runs its no-ingress worker loop until systemd sends
`SIGTERM`.

No credential or effect handler is reached until every retained local authority
input has been reread and bound to the exact named-human Approval.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Protocol, cast

from asklegal_application_runtime import (
    CredentialError,
    DependencyCode,
    ServiceExitCode,
    destination_for,
    exclusive_local_state_lock,
    run_v1_service,
)
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import RetryClass, StopCondition
from asklegal_durable_task import ConcurrencyOptions, OrchestrationStatus
from asklegal_promotion import ProfileError, PromotionError, ProviderTransport

from asklegal_promotion_worker.local_intents import LocalRetainedEffectIntentSource
from asklegal_promotion_worker.v1_execution import (
    ApprovedPromotionActivity,
    RetainedPromotionActivity,
    compose_approved_promotion_activity,
    register_approved_promotion_handlers,
)
from asklegal_promotion_worker.v1_infrastructure import (
    PromotionCompositionError,
    load_v1_infrastructure,
    preflight_v1_promotion,
    readiness_gate,
    validate_v1_promotion_configuration,
)

if TYPE_CHECKING:
    from asklegal_promotion_worker.v1_infrastructure import V1PromotionInfrastructure

_LOGGER = logging.getLogger("asklegal_promotion_worker.v1_service")
_APPROVAL_ID = re.compile(r"^apr_[0-9a-f]{48}$")
_EXECUTION_ID = re.compile(r"^exe_[0-9a-f]{48}$")
_NOT_READY = "PROMOTION_LOCAL_INPUTS_NOT_READY"
_RETRY_SCHEMA = "asklegal.local-promotion-dispatch-retry/v1"
_RECOVERY_SCHEMA = "asklegal.local-promotion-recovery-authority/v1"
_EXPECTED_EFFECT_INTENTS = 3
_DISPATCH_FENCE = re.compile(r"^pdf_[0-9a-f]{48}$")


@dataclass(frozen=True, slots=True)
class _RetryPolicy:
    retry_class: RetryClass
    attempt_ceiling: int
    deadline: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _RetryState:
    attempt_count: int
    dispatch_fence: str
    phase: str
    last_status: str
    policy_fingerprint: str
    scheduler_observation_fingerprint: str | None
    scheduler_created_at: str | None
    scheduler_updated_at: str | None
    scheduler_input_fingerprint: str | None
    scheduler_failure_fingerprint: str | None
    authority_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class _SchedulerObservation:
    status: OrchestrationStatus
    fingerprint: str
    created_at: str
    updated_at: str
    input_fingerprint: str
    failure_fingerprint: str | None


class _PromotionClient(Protocol):
    def get_orchestration_state(self, instance_id: str) -> object | None: ...

    def schedule_new_orchestration(
        self,
        orchestrator: str,
        *,
        input: object,  # noqa: A002 - durable-task SDK keyword.
        instance_id: str,
        version: str,
    ) -> str: ...

    def restart_orchestration(
        self,
        instance_id: str,
        *,
        restart_with_new_instance_id: bool = False,
    ) -> str: ...


def _pending_triggers(root: Path) -> tuple[dict[str, str], ...]:
    """Read every canonical retained wakeup item without claiming or mutating it."""
    if not root.exists():
        return ()
    if root.is_symlink() or not root.is_dir():
        raise PromotionCompositionError(_NOT_READY)
    pending: list[dict[str, str]] = []
    for path in sorted(root.glob("apr_*.json")):
        content = path.read_bytes()
        value = parse_json_bytes(content, max_bytes=10_000)
        if (
            not isinstance(value, dict)
            or set(value) != {"approval_id", "execution_lineage_id", "execution_time", "schema_id"}
            or value.get("schema_id") != "asklegal.local-promotion-trigger/v1"
            or canonicalize(value) != content
            or _APPROVAL_ID.fullmatch(str(value.get("approval_id"))) is None
            or path.name != f"{value.get('approval_id')}.json"
            or _EXECUTION_ID.fullmatch(str(value.get("execution_lineage_id"))) is None
            or type(value.get("execution_time")) is not str
        ):
            raise PromotionCompositionError(_NOT_READY)
        pending.append(
            {
                "approval_id": str(value["approval_id"]),
                "execution_lineage_id": str(value["execution_lineage_id"]),
                "execution_time": str(value["execution_time"]),
            }
        )
    return tuple(pending)


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise PromotionCompositionError(_NOT_READY) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PromotionCompositionError(_NOT_READY)
    return parsed.astimezone(UTC)


def _utc_now(now: Callable[[], datetime]) -> datetime:
    observed = now()
    if type(observed) is not datetime or observed.tzinfo is None or observed.utcoffset() is None:
        raise PromotionCompositionError(_NOT_READY)
    return observed.astimezone(UTC)


def _timestamp(value: object) -> str:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PromotionCompositionError(_NOT_READY)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _scheduler_observation(
    state: object,
    payload: dict[str, str],
) -> _SchedulerObservation:
    """Fingerprint the exact scheduler generation seen before a dispatch decision."""
    status = getattr(state, "runtime_status", None)
    instance_id = getattr(state, "instance_id", None)
    name = getattr(state, "name", None)
    serialized_input = getattr(state, "serialized_input", None)
    created_at = _timestamp(getattr(state, "created_at", None))
    updated_at = _timestamp(getattr(state, "last_updated_at", None))
    if (
        type(status) is not OrchestrationStatus
        or instance_id != payload["execution_lineage_id"]
        or name != "promote_approved_hk_v1"
        or type(serialized_input) is not str
        or _instant(updated_at) < _instant(created_at)
    ):
        raise PromotionCompositionError(_NOT_READY)
    try:
        input_value = parse_json_bytes(serialized_input.encode(), max_bytes=20_000)
    except (RuntimeError, ValueError) as error:
        raise PromotionCompositionError(_NOT_READY) from error
    expected_input = {
        "approval_id": payload["approval_id"],
        "execution_lineage_id": payload["execution_lineage_id"],
    }
    if input_value != expected_input:
        raise PromotionCompositionError(_NOT_READY)
    input_fingerprint = (
        "sha256:" + sha256(canonicalize(checked_json_value(input_value))).hexdigest()
    )
    failure = getattr(state, "failure_details", None)
    failure_fingerprint: str | None = None
    if failure is not None:
        message = getattr(failure, "message", None)
        error_type = getattr(failure, "error_type", None)
        stack_trace = getattr(failure, "stack_trace", None)
        if (
            type(message) is not str
            or not message
            or type(error_type) is not str
            or not error_type
            or (stack_trace is not None and type(stack_trace) is not str)
        ):
            raise PromotionCompositionError(_NOT_READY)
        failure_fingerprint = (
            "sha256:"
            + sha256(
                canonicalize(
                    checked_json_value(
                        {
                            "error_type": error_type,
                            "message": message,
                            "stack_trace": stack_trace,
                        }
                    )
                )
            ).hexdigest()
        )
    # ``last_updated_at`` is mutable polling metadata and therefore cannot
    # identify a restarted generation.  A generation changes only when one of
    # the stable scheduler facts below changes.
    material = canonicalize(
        checked_json_value(
            {
                "created_at": created_at,
                "failure_fingerprint": failure_fingerprint,
                "input_fingerprint": input_fingerprint,
                "instance_id": instance_id,
                "name": name,
                "status": status.name,
            }
        )
    )
    return _SchedulerObservation(
        status,
        "sha256:" + sha256(material).hexdigest(),
        created_at,
        updated_at,
        input_fingerprint,
        failure_fingerprint,
    )


def _policy(intent_root: Path, payload: dict[str, str]) -> _RetryPolicy:
    """Derive orchestration retry limits only from retained owner-issued intents."""
    path = intent_root / f"{payload['execution_lineage_id']}.json"
    try:
        intents = LocalRetainedEffectIntentSource(path).effect_intents(
            payload["execution_lineage_id"]
        )
    except (OSError, PromotionError, TypeError, ValueError) as error:
        raise PromotionCompositionError(_NOT_READY) from error
    if (
        len(intents) != _EXPECTED_EFFECT_INTENTS
        or any(intent.created_at != payload["execution_time"] for intent in intents)
        or any(intent.retry_class is not RetryClass.RECONCILE_BEFORE_RETRY for intent in intents)
        or any(
            StopCondition.ATTEMPT_CEILING not in intent.stop_conditions
            or StopCondition.DEADLINE not in intent.stop_conditions
            for intent in intents
        )
    ):
        raise PromotionCompositionError(_NOT_READY)
    ceiling = min(intent.attempt_ceiling for intent in intents)
    deadline = min(intents, key=lambda intent: _instant(intent.deadline)).deadline
    material = canonicalize(
        checked_json_value(
            {
                "attempt_ceiling": ceiling,
                "deadline": deadline,
                "effect_intent_ids": [intent.effect_intent_id for intent in intents],
                "execution_lineage_id": payload["execution_lineage_id"],
                "retry_class": RetryClass.RECONCILE_BEFORE_RETRY.value,
            }
        )
    )
    return _RetryPolicy(
        RetryClass.RECONCILE_BEFORE_RETRY,
        ceiling,
        deadline,
        "sha256:" + sha256(material).hexdigest(),
    )


def _state_path(root: Path, execution_lineage_id: str) -> Path:
    if root.is_symlink():
        raise PromotionCompositionError(_NOT_READY)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir():
        raise PromotionCompositionError(_NOT_READY)
    return root / f"{execution_lineage_id}.json"


def _read_retry_state(path: Path, payload: dict[str, str]) -> _RetryState | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise PromotionCompositionError(_NOT_READY)
    content = path.read_bytes()
    try:
        value = parse_json_bytes(content, max_bytes=20_000)
    except (RuntimeError, ValueError) as error:
        raise PromotionCompositionError(_NOT_READY) from error
    fields = {
        "approval_id",
        "attempt_count",
        "authority_fingerprint",
        "dispatch_fence",
        "execution_lineage_id",
        "last_status",
        "phase",
        "policy_fingerprint",
        "scheduler_created_at",
        "scheduler_failure_fingerprint",
        "scheduler_input_fingerprint",
        "scheduler_observation_fingerprint",
        "scheduler_updated_at",
        "schema_id",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or canonicalize(value) != content
        or value.get("schema_id") != _RETRY_SCHEMA
        or value.get("approval_id") != payload["approval_id"]
        or value.get("execution_lineage_id") != payload["execution_lineage_id"]
        or type(value.get("attempt_count")) is not int
        or cast("int", value["attempt_count"]) < 0
        or type(value.get("dispatch_fence")) is not str
        or (
            cast("str", value["dispatch_fence"]) != ""
            and _DISPATCH_FENCE.fullmatch(cast("str", value["dispatch_fence"])) is None
        )
        or value.get("phase") not in {"ACTIVE", "OUTCOME_UNKNOWN", "SETTLED", "STOPPED", "COMPLETE"}
        or type(value.get("last_status")) is not str
        or type(value.get("policy_fingerprint")) is not str
        or (
            value.get("authority_fingerprint") is not None
            and type(value.get("authority_fingerprint")) is not str
        )
        or any(
            value.get(field) is not None and type(value.get(field)) is not str
            for field in (
                "scheduler_created_at",
                "scheduler_failure_fingerprint",
                "scheduler_input_fingerprint",
                "scheduler_observation_fingerprint",
                "scheduler_updated_at",
            )
        )
    ):
        raise PromotionCompositionError(_NOT_READY)
    return _RetryState(
        cast("int", value["attempt_count"]),
        cast("str", value["dispatch_fence"]),
        cast("str", value["phase"]),
        cast("str", value["last_status"]),
        cast("str", value["policy_fingerprint"]),
        cast("str | None", value["scheduler_observation_fingerprint"]),
        cast("str | None", value["scheduler_created_at"]),
        cast("str | None", value["scheduler_updated_at"]),
        cast("str | None", value["scheduler_input_fingerprint"]),
        cast("str | None", value["scheduler_failure_fingerprint"]),
        cast("str | None", value["authority_fingerprint"]),
    )


def _retry_state_bytes(payload: dict[str, str], state: _RetryState) -> bytes:
    return canonicalize(
        checked_json_value(
            {
                "approval_id": payload["approval_id"],
                "attempt_count": state.attempt_count,
                "authority_fingerprint": state.authority_fingerprint,
                "dispatch_fence": state.dispatch_fence,
                "execution_lineage_id": payload["execution_lineage_id"],
                "last_status": state.last_status,
                "phase": state.phase,
                "policy_fingerprint": state.policy_fingerprint,
                "scheduler_created_at": state.scheduler_created_at,
                "scheduler_failure_fingerprint": state.scheduler_failure_fingerprint,
                "scheduler_input_fingerprint": state.scheduler_input_fingerprint,
                "scheduler_observation_fingerprint": state.scheduler_observation_fingerprint,
                "scheduler_updated_at": state.scheduler_updated_at,
                "schema_id": _RETRY_SCHEMA,
            }
        )
    )


def _write_retry_state_locked(path: Path, payload: dict[str, str], state: _RetryState) -> None:
    """Replace one retry projection while its exact adjacent lock is held."""
    content = _retry_state_bytes(payload, state)
    temporary = path.parent / f".{path.name}.{token_hex(16)}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise PromotionCompositionError(_NOT_READY)
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        temporary.replace(path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    if path.is_symlink() or path.read_bytes() != content:
        raise PromotionCompositionError(_NOT_READY)


def _retry_state(  # noqa: PLR0913
    *,
    attempt_count: int,
    dispatch_fence: str,
    phase: str,
    policy_fingerprint: str,
    observation: _SchedulerObservation | None,
    last_status: str | None = None,
    authority_fingerprint: str | None = None,
) -> _RetryState:
    return _RetryState(
        attempt_count,
        dispatch_fence,
        phase,
        ("MISSING" if observation is None else observation.status.name)
        if last_status is None
        else last_status,
        policy_fingerprint,
        None if observation is None else observation.fingerprint,
        None if observation is None else observation.created_at,
        None if observation is None else observation.updated_at,
        None if observation is None else observation.input_fingerprint,
        None if observation is None else observation.failure_fingerprint,
        authority_fingerprint,
    )


def _recovery_authority(
    root: Path,
    payload: dict[str, str],
    policy: _RetryPolicy,
    authorized_attempt: int,
    now: datetime,
) -> str | None:
    path = root / f"{payload['execution_lineage_id']}.attempt-{authorized_attempt:06d}.json"
    consumed_path = root / (
        f"{payload['execution_lineage_id']}.attempt-{authorized_attempt:06d}.consumed.json"
    )
    if consumed_path.exists():
        if consumed_path.is_symlink() or not consumed_path.is_file():
            raise PromotionCompositionError(_NOT_READY)
        return None
    if not path.exists():
        return None
    if root.is_symlink() or path.is_symlink() or not path.is_file():
        raise PromotionCompositionError(_NOT_READY)
    content = path.read_bytes()
    try:
        value = parse_json_bytes(content, max_bytes=20_000)
    except (RuntimeError, ValueError) as error:
        raise PromotionCompositionError(_NOT_READY) from error
    if not isinstance(value, dict) or canonicalize(value) != content:
        raise PromotionCompositionError(_NOT_READY)
    supplied = value.get("fingerprint")
    unsigned = dict(value)
    unsigned.pop("fingerprint", None)
    if (
        set(value)
        != {
            "approval_id",
            "authorized_attempt",
            "authorized_at",
            "execution_lineage_id",
            "expires_at",
            "fingerprint",
            "policy_fingerprint",
            "schema_id",
            "terminal_status",
        }
        or value.get("schema_id") != _RECOVERY_SCHEMA
        or value.get("approval_id") != payload["approval_id"]
        or value.get("authorized_attempt") != authorized_attempt
        or value.get("execution_lineage_id") != payload["execution_lineage_id"]
        or value.get("policy_fingerprint") != policy.fingerprint
        or value.get("terminal_status") != OrchestrationStatus.TERMINATED.name
        or type(value.get("authorized_at")) is not str
        or type(value.get("expires_at")) is not str
        or type(supplied) is not str
        or supplied != "sha256:" + sha256(canonicalize(checked_json_value(unsigned))).hexdigest()
        or not (_instant(cast("str", value["authorized_at"])) <= now)
        or not (now < _instant(cast("str", value["expires_at"])))
    ):
        raise PromotionCompositionError(_NOT_READY)
    return supplied


def _consume_recovery_authority(
    root: Path,
    payload: dict[str, str],
    authorized_attempt: int,
    authority_fingerprint: str,
    dispatch_fence: str,
) -> None:
    """Append one immutable receipt before a TERMINATED generation is restarted."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / (
        f"{payload['execution_lineage_id']}.attempt-{authorized_attempt:06d}.consumed.json"
    )
    content = canonicalize(
        checked_json_value(
            {
                "approval_id": payload["approval_id"],
                "authority_fingerprint": authority_fingerprint,
                "authorized_attempt": authorized_attempt,
                "dispatch_fence": dispatch_fence,
                "execution_lineage_id": payload["execution_lineage_id"],
                "schema_id": "asklegal.local-promotion-recovery-authority-consumption/v1",
            }
        )
    )
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise PromotionCompositionError(_NOT_READY)
        return
    temporary = path.parent / f".{path.name}.{token_hex(16)}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise PromotionCompositionError(_NOT_READY)
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                raise PromotionCompositionError(_NOT_READY) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    if path.read_bytes() != content:
        raise PromotionCompositionError(_NOT_READY)


def _dispatch_fence(
    payload: dict[str, str],
    policy: _RetryPolicy,
    attempt_count: int,
    observation: _SchedulerObservation | None,
) -> str:
    material = canonicalize(
        checked_json_value(
            {
                "approval_id": payload["approval_id"],
                "attempt_count": attempt_count,
                "execution_lineage_id": payload["execution_lineage_id"],
                "policy_fingerprint": policy.fingerprint,
                "scheduler_observation_fingerprint": (
                    None if observation is None else observation.fingerprint
                ),
            }
        )
    )
    return "pdf_" + sha256(material).hexdigest()[:48]


def _resolve_policy(
    intent_root: Path,
    payload: dict[str, str],
    prepare_policy: Callable[[dict[str, str]], object] | None,
) -> _RetryPolicy:
    try:
        return _policy(intent_root, payload)
    except PromotionCompositionError:
        if prepare_policy is None:
            raise
    prepare_policy(payload)
    return _policy(intent_root, payload)


def _phase_for(observation: _SchedulerObservation) -> str:
    if observation.status is OrchestrationStatus.COMPLETED:
        return "COMPLETE"
    if observation.status in {OrchestrationStatus.FAILED, OrchestrationStatus.TERMINATED}:
        return "SETTLED"
    return "ACTIVE"


def _reconcile_dispatch(
    client: _PromotionClient,
    retry_path: Path,
    recovery_authority_root: Path,
    payload: dict[str, str],
    dispatch_fence: str,
) -> None:
    """Resolve a reserved schedule/restart only from a changed exact generation."""
    raw = client.get_orchestration_state(payload["execution_lineage_id"])
    observation = None if raw is None else _scheduler_observation(raw, payload)
    with exclusive_local_state_lock(retry_path):
        retained = _read_retry_state(retry_path, payload)
        if (
            retained is None
            or retained.dispatch_fence != dispatch_fence
            or retained.phase != "OUTCOME_UNKNOWN"
        ):
            return
        if (
            observation is None
            or observation.fingerprint == retained.scheduler_observation_fingerprint
        ):
            return
        if retained.authority_fingerprint is not None:
            _consume_recovery_authority(
                recovery_authority_root,
                payload,
                retained.attempt_count,
                retained.authority_fingerprint,
                retained.dispatch_fence,
            )
        _write_retry_state_locked(
            retry_path,
            payload,
            _retry_state(
                attempt_count=retained.attempt_count,
                dispatch_fence=retained.dispatch_fence,
                phase=_phase_for(observation),
                policy_fingerprint=retained.policy_fingerprint,
                observation=observation,
                authority_fingerprint=retained.authority_fingerprint,
            ),
        )


def dispatch_pending_promotions(  # noqa: C901,PLR0912,PLR0913,PLR0915
    client: _PromotionClient,
    root: Path,
    *,
    effect_intent_root: Path | None = None,
    retry_state_root: Path | None = None,
    recovery_authority_root: Path | None = None,
    prepare_policy: Callable[[dict[str, str]], object] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    """Schedule or reconcile stable Promotion instances from retained wakeups."""
    intents_root = (
        root.parent / "effect-intents" if effect_intent_root is None else effect_intent_root
    )
    retry_root = (
        root.parent / "promotion-dispatch" if retry_state_root is None else retry_state_root
    )
    recovery_root = (
        root.parent / "promotion-recovery-authorities"
        if recovery_authority_root is None
        else recovery_authority_root
    )
    for payload in _pending_triggers(root):
        instance_id = payload["execution_lineage_id"]
        policy = _resolve_policy(intents_root, payload, prepare_policy)
        observed_now = _utc_now(now)
        retry_path = _state_path(retry_root, instance_id)
        dispatch: tuple[str, str, str | None] | None = None
        with exclusive_local_state_lock(retry_path):
            raw_state = client.get_orchestration_state(instance_id)
            observation = None if raw_state is None else _scheduler_observation(raw_state, payload)
            retained = _read_retry_state(retry_path, payload)
            if retained is not None and retained.policy_fingerprint != policy.fingerprint:
                raise PromotionCompositionError(_NOT_READY)
            if retained is not None and retained.phase in {"STOPPED", "COMPLETE"}:
                continue
            if retained is not None and retained.phase == "OUTCOME_UNKNOWN":
                changed_generation = (
                    observation is not None
                    and observation.fingerprint != retained.scheduler_observation_fingerprint
                )
                if changed_generation and retained.authority_fingerprint is not None:
                    _consume_recovery_authority(
                        recovery_root,
                        payload,
                        retained.attempt_count,
                        retained.authority_fingerprint,
                        retained.dispatch_fence,
                    )
                if observed_now >= _instant(policy.deadline):
                    stopped = (
                        replace(retained, phase="STOPPED")
                        if not changed_generation
                        else _retry_state(
                            attempt_count=retained.attempt_count,
                            dispatch_fence=retained.dispatch_fence,
                            phase="STOPPED",
                            policy_fingerprint=retained.policy_fingerprint,
                            observation=observation,
                            authority_fingerprint=retained.authority_fingerprint,
                        )
                    )
                    _write_retry_state_locked(retry_path, payload, stopped)
                    continue
                if not changed_generation:
                    continue
            if retained is not None and observation is None:
                if retained.phase == "ACTIVE":
                    missing = replace(
                        retained,
                        phase="OUTCOME_UNKNOWN",
                        last_status="MISSING",
                    )
                    if observed_now >= _instant(policy.deadline):
                        missing = replace(missing, phase="STOPPED")
                    _write_retry_state_locked(retry_path, payload, missing)
                continue
            if retained is not None and observation is not None:
                next_phase = _phase_for(observation)
                if retained.phase == "SETTLED" and next_phase == "SETTLED":
                    if retained.scheduler_observation_fingerprint != observation.fingerprint:
                        raise PromotionCompositionError(_NOT_READY)
                elif retained.phase != next_phase or (
                    retained.scheduler_observation_fingerprint != observation.fingerprint
                ):
                    retained = _retry_state(
                        attempt_count=retained.attempt_count,
                        dispatch_fence=retained.dispatch_fence,
                        phase=next_phase,
                        policy_fingerprint=policy.fingerprint,
                        observation=observation,
                        authority_fingerprint=retained.authority_fingerprint,
                    )
                    _write_retry_state_locked(retry_path, payload, retained)
                if next_phase in {"ACTIVE", "COMPLETE"}:
                    continue
            if retained is None:
                if observation is not None:
                    retained = _retry_state(
                        attempt_count=1,
                        dispatch_fence="",
                        phase=_phase_for(observation),
                        policy_fingerprint=policy.fingerprint,
                        observation=observation,
                    )
                    _write_retry_state_locked(retry_path, payload, retained)
                    if retained.phase in {"ACTIVE", "COMPLETE"}:
                        continue
                else:
                    retained = _retry_state(
                        attempt_count=0,
                        dispatch_fence="",
                        phase="SETTLED",
                        policy_fingerprint=policy.fingerprint,
                        observation=None,
                    )
            if retained.phase != "SETTLED":
                continue
            if observed_now >= _instant(policy.deadline) or (
                retained.attempt_count >= policy.attempt_ceiling
            ):
                _write_retry_state_locked(
                    retry_path,
                    payload,
                    replace(retained, phase="STOPPED"),
                )
                continue
            next_attempt = retained.attempt_count + 1
            authority_fingerprint = None
            if observation is not None and observation.status is OrchestrationStatus.TERMINATED:
                authority_fingerprint = _recovery_authority(
                    recovery_root,
                    payload,
                    policy,
                    next_attempt,
                    observed_now,
                )
                if authority_fingerprint is None:
                    continue
            fence = _dispatch_fence(payload, policy, next_attempt, observation)
            pending_retry = _retry_state(
                attempt_count=next_attempt,
                dispatch_fence=fence,
                phase="OUTCOME_UNKNOWN",
                policy_fingerprint=policy.fingerprint,
                observation=observation,
                authority_fingerprint=authority_fingerprint,
            )
            _write_retry_state_locked(retry_path, payload, pending_retry)
            dispatch = (
                "SCHEDULE" if observation is None else "RESTART",
                fence,
                None if observation is None else observation.fingerprint,
            )
        dispatch_kind, fence, expected_observation = dispatch
        reconcile_only = False
        dispatch_failed = False
        result_id: str | None = None
        # Revalidate the reservation, scheduler generation, wall-clock deadline,
        # and any TERMINATED recovery authority at the actual dispatch boundary.
        # Holding the same process-shared lock through the scheduler call prevents
        # another local dispatcher from spending the reserved attempt concurrently.
        with exclusive_local_state_lock(retry_path):
            reserved = _read_retry_state(retry_path, payload)
            if (
                reserved is None
                or reserved.dispatch_fence != fence
                or reserved.phase != "OUTCOME_UNKNOWN"
            ):
                continue
            before_dispatch = client.get_orchestration_state(instance_id)
            before_observation = (
                None
                if before_dispatch is None
                else _scheduler_observation(before_dispatch, payload)
            )
            if (dispatch_kind == "SCHEDULE" and before_observation is not None) or (
                dispatch_kind == "RESTART"
                and (
                    before_observation is None
                    or before_observation.fingerprint != expected_observation
                )
            ):
                reconcile_only = True
            else:
                dispatch_now = _utc_now(now)
                if dispatch_now >= _instant(policy.deadline):
                    _write_retry_state_locked(
                        retry_path,
                        payload,
                        replace(reserved, phase="STOPPED"),
                    )
                    continue
                if reserved.authority_fingerprint is not None:
                    refreshed_authority = _recovery_authority(
                        recovery_root,
                        payload,
                        policy,
                        reserved.attempt_count,
                        dispatch_now,
                    )
                    if refreshed_authority != reserved.authority_fingerprint:
                        _write_retry_state_locked(
                            retry_path,
                            payload,
                            replace(reserved, phase="STOPPED"),
                        )
                        continue
                try:
                    if dispatch_kind == "SCHEDULE":
                        orchestration_payload = {
                            "approval_id": payload["approval_id"],
                            "execution_lineage_id": payload["execution_lineage_id"],
                        }
                        result_id = client.schedule_new_orchestration(
                            "promote_approved_hk_v1",
                            input=orchestration_payload,
                            instance_id=instance_id,
                            version="1.0.0",
                        )
                    else:
                        result_id = client.restart_orchestration(
                            instance_id,
                            restart_with_new_instance_id=False,
                        )
                except Exception:  # noqa: BLE001 - reconcile ambiguous scheduler outcome.
                    dispatch_failed = True
        if reconcile_only or dispatch_failed:
            _reconcile_dispatch(client, retry_path, recovery_root, payload, fence)
            continue
        if result_id != instance_id:
            raise PromotionCompositionError(_NOT_READY)
        _reconcile_dispatch(client, retry_path, recovery_root, payload, fence)


def _build_serve(  # noqa: PLR0913 - all retained recovery roots are load-bearing.
    infrastructure: V1PromotionInfrastructure,
    activity: ApprovedPromotionActivity | RetainedPromotionActivity,
    trigger_root: Path | None = None,
    *,
    effect_intent_root: Path | None = None,
    retry_state_root: Path | None = None,
    recovery_authority_root: Path | None = None,
) -> Callable[[asyncio.Event], Awaitable[None]]:
    """Bind the sole approval-triggered promotion worker protocol."""

    def prepare_policy(payload: dict[str, str]) -> object:
        exact_payload = {
            "approval_id": payload["approval_id"],
            "execution_lineage_id": payload["execution_lineage_id"],
        }
        if type(activity) is RetainedPromotionActivity:
            return activity.resolve(exact_payload)
        return activity

    async def _serve(shutdown: asyncio.Event) -> None:
        """Serve the exact task hub until cooperative shutdown."""
        worker = infrastructure.scheduler.create_worker(
            concurrency_options=ConcurrencyOptions(
                maximum_concurrent_activity_work_items=1,
                maximum_concurrent_orchestration_work_items=1,
                maximum_thread_pool_workers=1,
            )
        )
        register_approved_promotion_handlers(worker, activity)
        client = infrastructure.scheduler.create_client(default_version="1.0.0")
        worker.start()
        _LOGGER.info("PROMOTION_WORKER serving hub=%s", infrastructure.scheduler.task_hub)
        try:
            while not shutdown.is_set():
                if trigger_root is not None:
                    await asyncio.to_thread(
                        dispatch_pending_promotions,
                        client,
                        trigger_root,
                        effect_intent_root=effect_intent_root,
                        retry_state_root=retry_state_root,
                        recovery_authority_root=recovery_authority_root,
                        prepare_policy=prepare_policy,
                    )
                try:
                    await asyncio.wait_for(shutdown.wait(), timeout=1.0)
                except TimeoutError:
                    continue
        finally:
            await asyncio.to_thread(worker.stop)
            _LOGGER.info("PROMOTION_WORKER stopped")

    return _serve


async def _run(environment: Mapping[str, str]) -> ServiceExitCode:
    try:
        trigger_root = validate_v1_promotion_configuration(environment)
    except PromotionCompositionError:
        _LOGGER.critical("promotion inputs unavailable: PROMOTION_LOCAL_INPUTS_NOT_READY")
        return ServiceExitCode.NOT_READY
    try:
        infrastructure = load_v1_infrastructure(environment)
    except CredentialError as error:
        _LOGGER.critical("credentials unavailable: %s", error.code.value)
        return ServiceExitCode.NOT_READY
    proxy_host, proxy_port = destination_for(
        "PROMOTION_WORKER",
        DependencyCode.PROMOTION_EGRESS,
    )
    try:

        def resolve(payload: object) -> ApprovedPromotionActivity:
            if not isinstance(payload, dict):
                raise PromotionCompositionError(_NOT_READY)
            typed_payload = cast("dict[str, object]", payload)
            if set(typed_payload) != {
                "approval_id",
                "execution_lineage_id",
            }:
                raise PromotionCompositionError(_NOT_READY)
            approval_id = typed_payload.get("approval_id")
            if type(approval_id) is not str or _APPROVAL_ID.fullmatch(approval_id) is None:
                raise PromotionCompositionError(_NOT_READY)
            preflight = preflight_v1_promotion(
                environment,
                trigger_path=trigger_root / f"{approval_id}.json",
            )
            return compose_approved_promotion_activity(
                preflight,
                infrastructure,
                preflight.token_counter,
                ProviderTransport(
                    proxy_host,
                    proxy_port,
                    preflight.serving_profile.provider_timeout_seconds,
                ),
                ProviderTransport(
                    proxy_host,
                    proxy_port,
                    preflight.serving_profile.target_timeout_seconds,
                ),
            )

        activity = RetainedPromotionActivity(resolve)
    except OSError, ProfileError, PromotionError, RuntimeError, TypeError, ValueError:
        _LOGGER.critical("promotion composition unavailable: PROMOTION_EXECUTION_NOT_READY")
        return ServiceExitCode.NOT_READY
    return await run_v1_service(
        readiness_gate(infrastructure),
        _build_serve(
            infrastructure,
            activity,
            trigger_root,
            effect_intent_root=Path(environment["ASKLEGAL_PROMOTION_EFFECT_INTENT_LEDGER"]),
            retry_state_root=Path(environment["ASKLEGAL_PROMOTION_STATE_ROOT"])
            / "dispatch-retries",
            recovery_authority_root=Path(environment["ASKLEGAL_PROMOTION_STATE_ROOT"])
            / "recovery-authorities",
        ),
        report_line=_LOGGER.info,
    )


def run() -> int:
    """Run the exact V1 service and return one closed process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return int(asyncio.run(_run(os.environ)))


if __name__ == "__main__":
    sys.exit(run())
