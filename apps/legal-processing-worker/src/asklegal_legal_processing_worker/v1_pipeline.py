"""Real scheduler-driven analysis for the V1 LEGAL_PROCESSING_WORKER.

Two activities. The first reads one exact evidence version from the Primary vault,
verifying its length and fingerprint on the way out. The second asks the admitted
generative deployment for one bounded decision about those bytes, through this
application's own egress proxy.

The orchestrator holds no model call and no clock, because the scheduler replays it
on every work item; both effects live in activities, which are checkpointed once.

The strictness lives in the runner, not here. A reply with an extra field, a
missing field, an unknown challenge code, or a citation the evidence never supplied
fails closed rather than becoming a plausible-looking legal judgment.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from asklegal_evidence_vault import ExactObjectReference, VaultName
from asklegal_legal_desks import SemanticTaskProfile
from asklegal_processing import (
    AzureDeployment,
    AzureSemanticTaskRunner,
    BoundedModelTransport,
    SemanticTaskRequest,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

    from asklegal_legal_processing_worker.v1_infrastructure import (
        V1LegalProcessingInfrastructure,
    )

_LOGGER = logging.getLogger("asklegal_legal_processing_worker.v1_pipeline")
_MAX_EVIDENCE_BYTES = 24_000
_TASK = "HK_LATER_TREATMENT"
_MAX_OUTPUT_TOKENS = 1024


class ProcessingPipelineError(RuntimeError):
    """One exact processing-pipeline failure, safe to log."""


def _proxy(infrastructure: V1LegalProcessingInfrastructure) -> tuple[str, int]:
    raw = infrastructure.model_egress_proxy_credential.reveal().decode().strip()
    parsed = urlsplit(raw)
    if not parsed.hostname or not parsed.port:
        message = "model egress proxy credential is not host:port"
        raise ProcessingPipelineError(message)
    return (parsed.hostname, parsed.port)


def _profile(deployment: str, api_contract: str) -> SemanticTaskProfile:
    """Build the profile this worker analyses under.

    Provider and deployment are fixed here rather than taken from the payload, so a
    scheduled message cannot talk the worker into a different model.
    """
    return SemanticTaskProfile(
        profile_id="stp_v1_poc",
        task=_TASK,
        provider="AZURE_OPENAI",
        resource_class="HOSTED",
        geography_class="US",
        deployment_name=deployment,
        model_id="gpt-5.4",
        model_version="1",
        api_contract=api_contract,
        tokenizer="o200k_base",
        prompt_fingerprint="sha256:" + "0" * 64,
        input_schema="v1",
        output_schema="v1",
        evidence_budget_bytes=_MAX_EVIDENCE_BYTES,
        max_output_tokens=_MAX_OUTPUT_TOKENS,
        content_filter_policy="DEFAULT",
        retry_policy="NONE",
        data_handling_profile="NO_TRAINING",
        evaluator_id="eval_v1_poc",
        threshold_basis_points=9000,
        expires_at="2027-01-01T00:00:00Z",
        stateful_features=False,
        allowed_environments=("POC",),
    )


class ProcessingActivities:
    """The two real effects this worker performs, bound to one infrastructure."""

    def __init__(self, infrastructure: V1LegalProcessingInfrastructure) -> None:
        """Compose the vault reader and the admitted generative runner."""
        host, port = _proxy(infrastructure)
        self._vault = infrastructure.primary_vault
        self._deployment = AzureDeployment.from_credential_json(
            infrastructure.model_provider_credential.reveal()
        )
        self._runner = AzureSemanticTaskRunner(
            self._deployment,
            BoundedModelTransport(host, port),
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
        self._profile = _profile(self._deployment.deployment, self._deployment.api_version)

    @property
    def deployment(self) -> str:
        """Return the deployment this worker analyses with."""
        return self._deployment.deployment

    def read_evidence(self, _context: ActivityContext, payload: object) -> object:
        """Read exactly one retained evidence version from the Primary vault."""
        if not isinstance(payload, dict):
            message = "read_evidence needs the stored-evidence result"
            raise ProcessingPipelineError(message)
        reference = ExactObjectReference(
            VaultName.PRIMARY,
            str(payload["logical_key"]),
            str(payload["version_id"]),
            str(payload["fingerprint"]),
            int(payload["byte_length"]),
        )
        body = self._vault.read_exact(reference)
        _LOGGER.info(
            "LEGAL_PROCESSING_WORKER read %s bytes from %s",
            len(body),
            reference.logical_key,
        )
        return {
            "logical_key": reference.logical_key,
            "fingerprint": reference.fingerprint,
            "evidence_ref": f"ev_{reference.fingerprint.removeprefix('sha256:')[:16]}",
            "subject_id": str(payload.get("endpoint_id", reference.logical_key)),
            # The budget is enforced here as well as in the runner, so an
            # oversized capture is truncated once, visibly, rather than silently.
            "text": body[:_MAX_EVIDENCE_BYTES].decode("utf-8", "replace"),
            "truncated": len(body) > _MAX_EVIDENCE_BYTES,
        }

    def analyse_evidence(self, _context: ActivityContext, payload: object) -> object:
        """Ask the admitted deployment for one bounded decision about the evidence."""
        if not isinstance(payload, dict):
            message = "analyse_evidence needs the read-evidence result"
            raise ProcessingPipelineError(message)
        evidence_ref = str(payload["evidence_ref"])
        request = SemanticTaskRequest(
            request_id=f"req_{evidence_ref}",
            task=_TASK,
            phase="DECISION",
            profile_id=self._profile.profile_id,
            package_fingerprint="sha256:" + "0" * 64,
            subject_id=str(payload["subject_id"]),
            evidence_refs=(evidence_ref,),
            evidence_bytes=str(payload["text"]).encode(),
            input_fingerprint=str(payload["fingerprint"]),
        )
        decision = self._runner.invoke(self._profile, request)
        _LOGGER.info(
            "LEGAL_PROCESSING_WORKER decided %s for %s (challenge=%s)",
            decision.decision_code,
            request.subject_id,
            decision.challenge_code,
        )
        return {
            "subject_id": request.subject_id,
            "decision_code": decision.decision_code,
            "supporting_evidence_refs": list(decision.supporting_evidence_refs),
            "unresolved_facts": list(decision.unresolved_facts),
            "challenge_code": decision.challenge_code,
            "output_fingerprint": decision.output_fingerprint,
            "truncated_evidence": bool(payload.get("truncated", False)),
        }


def analyse_stored_evidence(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Orchestrate one analysis: read the retained evidence, then decide on it."""
    evidence = yield context.call_activity("read_evidence", input=payload)
    decision = yield context.call_activity("analyse_evidence", input=evidence)
    return decision


def build_activities(
    infrastructure: V1LegalProcessingInfrastructure,
    _environment: Mapping[str, str],
) -> ProcessingActivities:
    """Compose this worker's activities from its own infrastructure."""
    return ProcessingActivities(infrastructure)
