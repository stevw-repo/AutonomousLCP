"""Cross-stage orchestration for the V1 CONTROL_PLANE.

The control plane is the only application whose job is to sequence other stages,
so it is the only one that holds clients to hubs other than its own. It reaches
them because `dts-general` is already one of its declared destinations and hosts
the acquisition, control, and legal-processing hubs; nothing here widens the
network or amends the one-hub-per-application binding.

All three stages run from here, including promotion. That required a deliberate
amendment: the original rule bound every application to exactly one scheduler, and
the register enforced the same thing from the other side by rejecting any command
whose `owning_application` was not the caller. Under that rule a sequencing
component could not exist at all.

The amendment is narrow. The control plane alone declares a second scheduler
destination and reaches the promotion hub; the four workers still bind to one hub
each and still cannot reach one another. The isolation that matters — a worker
cannot start another worker's work — is intact.

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

    from asklegal_control_plane.v1_infrastructure import V1ControlInfrastructure

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


class ControlActivities:
    """The control plane's three sequencing effects, bound to one infrastructure."""

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

    def start_promotion(self, _context: ActivityContext, payload: object) -> object:
        """Serve one decision on the promotion hub and return the write result."""
        if not isinstance(payload, dict):
            message = "start_promotion needs the evidence and decision"
            raise ControlPipelineError(message)
        evidence = payload.get("evidence")
        decision = payload.get("decision")
        if not isinstance(evidence, dict) or not isinstance(decision, dict):
            message = "start_promotion needs both evidence and decision"
            raise ControlPipelineError(message)
        fingerprint = str(decision.get("output_fingerprint", "")).removeprefix("sha256:")
        records = [
            {
                "record_id": f"chain_{fingerprint[:16]}",
                "text": (
                    f"Source {evidence.get('source_id')} "
                    f"endpoint {evidence.get('endpoint_id')}. "
                    f"Decision {decision.get('decision_code')}. "
                    + " ".join(decision.get("unresolved_facts") or [])[:1200]
                ),
            }
        ]
        result = _run_stage("PROMOTION_WORKER", "promote_records", records)
        _LOGGER.info("CONTROL_PLANE promoted: %s", result)
        return result


def run_source_pipeline(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Chain all three stages for one endpoint, in order, once."""
    evidence = yield context.call_activity("start_acquisition", input=payload)
    decision = yield context.call_activity("start_analysis", input=evidence)
    promotion = yield context.call_activity(
        "start_promotion", input={"evidence": evidence, "decision": decision}
    )
    return {"evidence": evidence, "decision": decision, "promotion": promotion}
