"""Cross-stage orchestration for the V1 CONTROL_PLANE.

The control plane is the only application whose job is to sequence other stages,
so it is the only one that holds clients to hubs other than its own. It reaches
them because `dts-general` is already one of its declared destinations and hosts
the acquisition, control, and legal-processing hubs; nothing here widens the
network or amends the one-hub-per-application binding.

The promotion hub is on `dts-promotion`, which the control plane cannot reach, so
this chain stops after analysis and records what promotion should do. Handing that
to the promotion worker belongs in the register, whose `effect_intent` tables exist
for exactly that, and is not done here.

Each stage is an activity, because scheduling another orchestration and waiting on
it is an effect. The orchestrator holds no client and no clock.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from asklegal_durable_task import V1SchedulerSettings

if TYPE_CHECKING:
    from collections.abc import Generator

    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

_LOGGER = logging.getLogger("asklegal_control_plane.v1_pipeline")
_VERSION = "1.0.0"
_STAGE_TIMEOUT_SECONDS = 900


class ControlPipelineError(RuntimeError):
    """One exact control-plane orchestration failure, safe to log."""


def _run_stage(application: str, orchestration: str, payload: object) -> object:
    """Schedule one orchestration on another application's hub and await it."""
    settings = V1SchedulerSettings.for_application(application)
    client = settings.create_client(default_version=_VERSION)
    instance = client.schedule_new_orchestration(orchestration, input=payload)
    state = client.wait_for_orchestration_completion(
        instance, timeout=_STAGE_TIMEOUT_SECONDS
    )
    if state is None or state.runtime_status.name != "COMPLETED":
        detail = "no terminal state"
        if state is not None and state.failure_details is not None:
            detail = state.failure_details.message[:300]
        message = f"{application}/{orchestration} did not complete: {detail}"
        raise ControlPipelineError(message)
    if not state.serialized_output:
        message = f"{application}/{orchestration} returned no output"
        raise ControlPipelineError(message)
    return json.loads(state.serialized_output)


def start_acquisition(_context: ActivityContext, payload: object) -> object:
    """Run one capture on the acquisition hub and return its evidence reference."""
    result = _run_stage("ACQUISITION_WORKER", "acquire_endpoint", payload)
    if isinstance(result, dict):
        _LOGGER.info(
            "CONTROL_PLANE acquired %s bytes from %s",
            result.get("byte_length"),
            result.get("source_id"),
        )
    return result


def start_analysis(_context: ActivityContext, payload: object) -> object:
    """Run one analysis on the legal-processing hub and return its decision."""
    result = _run_stage("LEGAL_PROCESSING_WORKER", "analyse_stored_evidence", payload)
    if isinstance(result, dict):
        _LOGGER.info("CONTROL_PLANE analysed to %s", result.get("decision_code"))
    return result


def run_source_pipeline(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Chain acquisition and analysis for one endpoint, in order, once."""
    evidence = yield context.call_activity("start_acquisition", input=payload)
    decision = yield context.call_activity("start_analysis", input=evidence)
    return {
        "evidence": evidence,
        "decision": decision,
        # Promotion is deliberately absent: its hub is unreachable from here, and
        # inventing a path to it would cost the isolation that put it there.
        "promotion": "NOT_SCHEDULED_FROM_CONTROL_PLANE",
    }
