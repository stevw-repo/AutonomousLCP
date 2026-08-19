"""Real scheduler-driven acquisition work for the V1 ACQUISITION_WORKER.

Two activities. The first fetches one configured official endpoint through this
application's own egress proxy, using the bounded connector that already enforces
the endpoint contract, the byte ceiling, and hostile-content classification. The
second writes exactly those bytes into the Primary evidence vault under Object
Lock and verifies the read-back.

The orchestrator holds no fetch and no clock, because the scheduler replays it on
every work item; both effects live in activities, which are checkpointed once.

Only endpoints the register already marks enabled can be fetched. The payload
names an endpoint id, never a URL, so a scheduled message cannot direct this
worker at a host the register has not admitted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from asklegal_durable_task import TaskFailedError
from asklegal_evidence_vault import RetentionProfile
from asklegal_source_connectors import (
    HkelGazetteRegisterClient,
    HttpMethod,
    OfficialFetchRequest,
    OfficialHttpConnector,
    ProxiedOfficialHttpTransport,
    load_hk_legislation_source_register,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

    from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure

_LOGGER = logging.getLogger("asklegal_acquisition_worker.v1_pipeline")
_RETENTION_PROFILE = "poc-source-evidence"
# A fixed instant, not a clock reading. The object key is the content
# fingerprint, so re-capturing identical bytes must adopt the existing object,
# and adoption compares the whole retention profile. Any clock-derived value
# makes the same bytes collide with themselves on a later run. This is a POC
# retention horizon and nothing more.
_RETENTION_UNTIL = "2027-01-01T00:00:00Z"
_FETCH_TIMEOUT_SECONDS = 45
_GAZETTE_ARTIFACT_ENDPOINT = "sep_00000000000000000000000000000000000000000000004f"
_GAZETTE_LOCATOR_PLACEHOLDER = "gazette_artifact_locator"
_GAZETTE_MAX_PAGES = 50


class AcquisitionPipelineError(RuntimeError):
    """One exact acquisition-pipeline failure, safe to log."""


@dataclass(frozen=True, slots=True)
class FetchInstruction:
    """One endpoint the orchestration is asked to capture."""

    endpoint_id: str

    @classmethod
    def from_json(cls, value: object) -> FetchInstruction:
        """Parse one instruction from the scheduler payload."""
        if isinstance(value, str):
            return cls(value)
        if isinstance(value, dict):
            endpoint_id = value.get("endpoint_id")
            if isinstance(endpoint_id, str) and endpoint_id:
                return cls(endpoint_id)
        message = "acquisition instruction needs an endpoint_id"
        raise AcquisitionPipelineError(message)


def _proxy(infrastructure: V1AcquisitionInfrastructure) -> tuple[str, int]:
    raw = infrastructure.source_egress_proxy_credential.reveal().decode().strip()
    parsed = urlsplit(raw)
    if not parsed.hostname or not parsed.port:
        message = "source egress proxy credential is not host:port"
        raise AcquisitionPipelineError(message)
    return (parsed.hostname, parsed.port)


class AcquisitionActivities:
    """The two real effects this worker performs, bound to one infrastructure."""

    def __init__(self, infrastructure: V1AcquisitionInfrastructure) -> None:
        """Compose the bounded connector and the vault this worker writes to."""
        host, port = _proxy(infrastructure)
        self._register = load_hk_legislation_source_register()
        self._connector = OfficialHttpConnector(
            self._register,
            ProxiedOfficialHttpTransport(host, port),
        )
        self._endpoints = {item.endpoint_id: item for item in self._register.endpoints}
        self._vault = infrastructure.primary_vault
        self._transport = ProxiedOfficialHttpTransport(host, port)

    def capture_gazette_window(self, _context: ActivityContext, payload: object) -> object:
        """Enumerate the gazette register for a date window and retain its PDFs.

        Two boundaries meet here and stay separate. The register grid is a
        publisher API reached through the proxied transport, and it produces only
        locators — discovery, never evidence. Each addressed PDF is then fetched
        through the inert connector and retained the ordinary way, so the bytes
        that become evidence arrive on the evidence path.

        The window is required. An unbounded walk is not reproducible: the
        register grows at the front, so page one shifts between runs and two
        captures of the same query disagree. A closed window over past dates
        returns the same rows every time.
        """
        if not isinstance(payload, dict):
            message = "capture_gazette_window needs a date window"
            raise AcquisitionPipelineError(message)
        date_from = str(payload.get("date_from", ""))
        date_to = str(payload.get("date_to", ""))
        if not date_from or not date_to:
            message = "capture_gazette_window needs both date_from and date_to as DD/MM/YYYY"
            raise AcquisitionPipelineError(message)
        language = str(payload.get("language", "en"))

        client = HkelGazetteRegisterClient(self._transport)
        client.open_session()
        # The PDFs sit behind the same capability gate as the register page, so
        # the inert fetch has to carry the session the grid client established or
        # it is redirected to the gate and the media type never matches.
        session_connector = OfficialHttpConnector(
            self._register,
            self._transport.with_session(client.session_cookies),
        )
        listed = 0
        retained: list[dict[str, object]] = []
        skipped: list[dict[str, str]] = []
        for entry in client.iter_entries(
            date_from=date_from, date_to=date_to, max_pages=_GAZETTE_MAX_PAGES
        ):
            listed += 1
            address = entry.pdf_url(language)
            if address is None:
                # A language the publisher never issued is a fact, not a failure.
                skipped.append({"gazette_id": entry.gazette_id, "reason": "NOT_PUBLISHED"})
                continue
            locator = address.split("/hk/", 1)[1]
            try:
                retained.append(
                    self._retain_gazette_artifact(entry, locator, session_connector)
                )
            except AcquisitionPipelineError as error:
                skipped.append({"gazette_id": entry.gazette_id, "reason": str(error)[:120]})
        _LOGGER.info(
            "ACQUISITION_WORKER gazette window %s-%s: listed %s, retained %s, skipped %s",
            date_from,
            date_to,
            listed,
            len(retained),
            len(skipped),
        )
        return {
            "date_from": date_from,
            "date_to": date_to,
            "language": language,
            "listed": listed,
            "retained": len(retained),
            "skipped": len(skipped),
            "artifacts": retained,
            "skips": skipped,
        }

    def _retain_gazette_artifact(
        self,
        entry: object,
        locator: str,
        connector: OfficialHttpConnector,
    ) -> dict[str, object]:
        """Fetch one addressed gazette PDF inertly and retain it."""
        endpoint = self._endpoints.get(_GAZETTE_ARTIFACT_ENDPOINT)
        if endpoint is None or not endpoint.enabled:
            message = "the gazette artifact endpoint is absent or disabled"
            raise AcquisitionPipelineError(message)
        result = connector.fetch(
            OfficialFetchRequest(
                endpoint_id=endpoint.endpoint_id,
                endpoint_version=endpoint.version,
                method=HttpMethod.GET,
                prior_fingerprint=None,
                timeout_seconds=_FETCH_TIMEOUT_SECONDS,
                substitutions=((_GAZETTE_LOCATOR_PLACEHOLDER, locator),),
            )
        )
        if result.failure_code is not None:
            message = f"gazette artifact fetch failed: {result.failure_code}"
            raise AcquisitionPipelineError(message)
        if not result.classification.admitted:
            message = f"gazette artifact not admitted: {result.classification.reasons}"
            raise AcquisitionPipelineError(message)
        logical_key = f"poc/source/gazette/{result.fingerprint.removeprefix('sha256:')}"
        receipt = self._vault.conditional_create(
            logical_key,
            result.body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        return {
            "gazette_id": getattr(entry, "gazette_id", ""),
            "locator": locator,
            "logical_key": logical_key,
            "fingerprint": result.fingerprint,
            "byte_length": len(result.body),
            "created": receipt.created,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }

    def capture_endpoint(self, _context: ActivityContext, payload: object) -> object:
        """Capture one enabled endpoint and retain it, returning only its reference.

        Fetch and store are one activity on purpose. Splitting them would put the
        whole document body into the orchestration history, because that is where
        an activity result is persisted and replayed from. Only the reference
        travels through the scheduler.
        """
        instruction = FetchInstruction.from_json(payload)
        endpoint = self._endpoints.get(instruction.endpoint_id)
        if endpoint is None:
            message = f"unknown endpoint {instruction.endpoint_id}"
            raise AcquisitionPipelineError(message)
        if not endpoint.enabled:
            message = f"endpoint {instruction.endpoint_id} is not enabled in the register"
            raise AcquisitionPipelineError(message)
        result = self._connector.fetch(
            OfficialFetchRequest(
                endpoint_id=endpoint.endpoint_id,
                endpoint_version=endpoint.version,
                method=HttpMethod.GET,
                prior_fingerprint=None,
                timeout_seconds=_FETCH_TIMEOUT_SECONDS,
            )
        )
        if result.failure_code is not None:
            message = f"fetch failed for {endpoint.endpoint_id}: {result.failure_code}"
            raise AcquisitionPipelineError(message)
        if not result.classification.admitted:
            message = (
                f"content from {endpoint.endpoint_id} was not admitted: "
                f"{result.classification.reasons}"
            )
            raise AcquisitionPipelineError(message)
        _LOGGER.info(
            "ACQUISITION_WORKER captured %s from %s: %s bytes, %s",
            endpoint.endpoint_id,
            endpoint.source_id,
            len(result.body),
            result.code.value,
        )
        # The fingerprint is the key, so re-capturing identical bytes adopts the
        # existing object rather than writing a second conflicting version.
        logical_key = (
            f"poc/source/{endpoint.endpoint_id}/"
            f"{result.fingerprint.removeprefix('sha256:')}"
        )
        receipt = self._vault.conditional_create(
            logical_key,
            result.body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        _LOGGER.info(
            "ACQUISITION_WORKER retained %s bytes at %s (created=%s verified=%s)",
            len(result.body),
            logical_key,
            receipt.created,
            receipt.read_back_verified,
        )
        return {
            "endpoint_id": endpoint.endpoint_id,
            "source_id": endpoint.source_id,
            "logical_key": logical_key,
            "fingerprint": result.fingerprint,
            "byte_length": len(result.body),
            "media_type": result.media_type,
            "created": receipt.created,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }


def acquire_endpoint(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Orchestrate one capture, keeping the document body out of the history."""
    captured = yield context.call_activity("capture_endpoint", input=payload)
    return captured


def acquire_endpoints(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Capture many endpoints in sequence, surviving individual failures.

    Sequential rather than fanned out on purpose. Several of these endpoints carry
    ceilings in the hundreds of megabytes, and the connector holds a response in
    memory while it classifies it; running them in parallel would multiply peak
    memory by the width of the fan-out for no useful gain.

    One endpoint failing must not lose the rest of the run, so each capture is
    caught and recorded. The failures are part of the result, not an exception:
    a source that refuses admission is a finding worth reporting, not an error.
    """
    endpoint_ids = payload if isinstance(payload, list) else []
    captured: list[object] = []
    failed: list[object] = []
    for endpoint_id in endpoint_ids:
        try:
            result = yield context.call_activity(
                "capture_endpoint", input={"endpoint_id": endpoint_id}
            )
        except TaskFailedError as error:
            failed.append({"endpoint_id": endpoint_id, "reason": str(error)[:300]})
            continue
        captured.append(result)
    return {
        "requested": len(endpoint_ids),
        "captured": len(captured),
        "failed": len(failed),
        "bytes_retained": sum(
            int(item["byte_length"]) for item in captured if isinstance(item, dict)
        ),
        "results": captured,
        "failures": failed,
    }


def build_activities(
    infrastructure: V1AcquisitionInfrastructure,
    _environment: Mapping[str, str],
) -> AcquisitionActivities:
    """Compose this worker's activities from its own infrastructure."""
    return AcquisitionActivities(infrastructure)


def acquire_gazette_window(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Capture one date-bounded slice of the gazette register."""
    captured = yield context.call_activity("capture_gazette_window", input=payload)
    return captured
