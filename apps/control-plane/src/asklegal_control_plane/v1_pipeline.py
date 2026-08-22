"""Effect-safe source observation orchestration for the V1 CONTROL_PLANE.

The control plane sequences acquisition and legal processing on the shared general
scheduler destination. It deliberately has no route to the promotion hub and no
activity that can turn an analysis decision into a serving record. Promotion begins
only from a separately frozen proposal and exact human Approval; that command-bound
path is not yet installed in the real V1 service, so production effects remain
closed.

Each stage is an activity, because scheduling another orchestration and waiting on
it is an effect. The orchestrator holds no client and no clock.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import V1SchedulerSettings

if TYPE_CHECKING:
    from collections.abc import Generator

    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

    from asklegal_control_plane.v1_infrastructure import V1ControlInfrastructure

_LOGGER = logging.getLogger("asklegal_control_plane.v1_pipeline")
_VERSION = "1.0.0"
_STAGE_TIMEOUT_SECONDS = 900
SOURCE_OBSERVATION_ACTIVITIES = ("start_acquisition", "start_analysis")


class ControlPipelineError(RuntimeError):
    """One exact control-plane orchestration failure, safe to log."""


def _run_stage(application: str, orchestration: str, payload: object) -> JsonValue:
    """Schedule one orchestration on another application's hub and await it."""
    settings = V1SchedulerSettings.for_application(application)
    client = settings.create_client(default_version=_VERSION)
    instance = client.schedule_new_orchestration(orchestration, input=payload)
    state = client.wait_for_orchestration_completion(instance, timeout=_STAGE_TIMEOUT_SECONDS)
    if state is None or state.runtime_status.name != "COMPLETED":
        detail = "no terminal state"
        if state is not None and state.failure_details is not None:
            detail = state.failure_details.message[:300]
        message = f"{application}/{orchestration} did not complete: {detail}"
        raise ControlPipelineError(message)
    if not state.serialized_output:
        message = f"{application}/{orchestration} returned no output"
        raise ControlPipelineError(message)
    return checked_json_value(json.loads(state.serialized_output))


class ControlActivities:
    """The control plane's two observation effects, bound to one infrastructure."""

    def __init__(self, infrastructure: V1ControlInfrastructure) -> None:
        """Hold the infrastructure this application is allowed to act through."""
        self._infrastructure = infrastructure

    def start_acquisition(self, _context: ActivityContext, payload: object) -> object:
        """Run one capture on the acquisition hub and return its evidence reference."""
        result = _run_stage("ACQUISITION_WORKER", "acquire_endpoint", payload)
        if isinstance(result, dict):
            _LOGGER.info(
                "CONTROL_PLANE acquired %s bytes from %s",
                result.get("byte_length"),
                result.get("source_id"),
            )
        return result

    def start_analysis(self, _context: ActivityContext, payload: object) -> object:
        """Run one analysis on the legal-processing hub and return its decision."""
        result = _run_stage("LEGAL_PROCESSING_WORKER", "analyse_stored_evidence", payload)
        if isinstance(result, dict):
            _LOGGER.info("CONTROL_PLANE analysed to %s", result.get("decision_code"))
        return result


def observe_source_endpoint(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Acquire and analyse one endpoint without requesting a serving effect."""
    evidence = yield context.call_activity(SOURCE_OBSERVATION_ACTIVITIES[0], input=payload)
    decision = yield context.call_activity(SOURCE_OBSERVATION_ACTIVITIES[1], input=evidence)
    return observation_result(evidence, decision)


def observation_result(evidence: object, decision: object) -> dict[str, object]:
    """Close observation without manufacturing a release or promotion request."""
    return {
        "evidence": evidence,
        "decision": decision,
        "promotion_state": "NOT_REQUESTED",
    }
