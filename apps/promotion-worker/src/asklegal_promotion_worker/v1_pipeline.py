"""Real scheduler-driven promotion work for the V1 PROMOTION_WORKER.

This is the piece that turns the worker from a process that proves its
dependencies into one that does work. The orchestration and its activities run on
the application's own Durable Task hub, and the activities call the real providers
through the application's own egress proxy.

The split between orchestrator and activity is not cosmetic. The orchestrator is
replayed on every work item, so it holds no provider call and no clock; every
effect lives in an activity, which the scheduler records once and replays from its
own checkpoint rather than re-running.

Writes stay behind explicit authorization. The worker only builds a writing store
when `PROMOTION_WRITE_AUTHORIZED` is exactly `true`, so a deployment that has not
been granted that authority can still run the orchestration and will fail closed at
the upsert rather than quietly reaching a real index.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from asklegal_management_register import EffectHandoffStore
from asklegal_promotion import (
    AzureOpenAIConfig,
    AzureOpenAIEmbeddingAdapter,
    EmbeddingProfile,
    EmbeddingRequest,
    PineconeConfig,
    PineconeServingTargetStore,
    PromotionError,
    ProviderTransport,
    TargetRecord,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

    from asklegal_promotion_worker.v1_infrastructure import V1PromotionInfrastructure

_LOGGER = logging.getLogger("asklegal_promotion_worker.v1_pipeline")
_WRITE_AUTHORIZED_VARIABLE = "PROMOTION_WRITE_AUTHORIZED"
_EMBEDDING_DIMENSIONS = 1536
_EMBEDDING_MODEL = "text-embedding-3-small"
_MAX_BATCH = 100
_PROMOTION_EFFECT = "SERVING_TARGET_UPSERT"
_CLAIM_LEASE_SECONDS = 900


class PromotionPipelineError(RuntimeError):
    """One exact promotion-pipeline failure, safe to log."""


@dataclass(frozen=True, slots=True)
class PromotionRecordInput:
    """One record the orchestration is asked to embed and serve."""

    record_id: str
    text: str

    @classmethod
    def from_json(cls, value: object) -> PromotionRecordInput:
        """Parse one record from the scheduler payload."""
        if not isinstance(value, dict):
            message = "promotion record must be an object"
            raise PromotionPipelineError(message)
        record_id = value.get("record_id")
        text = value.get("text")
        if not isinstance(record_id, str) or not record_id:
            message = "promotion record needs a record_id"
            raise PromotionPipelineError(message)
        if not isinstance(text, str) or not text:
            message = f"promotion record {record_id} needs text"
            raise PromotionPipelineError(message)
        return cls(record_id, text)


def write_authorized(environment: Mapping[str, str]) -> bool:
    """Report whether this deployment may write to the real serving target."""
    return environment.get(_WRITE_AUTHORIZED_VARIABLE, "").strip().lower() == "true"


def _proxy(infrastructure: V1PromotionInfrastructure) -> tuple[str, int]:
    raw = infrastructure.promotion_egress_proxy_credential.reveal().decode().strip()
    parsed = urlsplit(raw)
    if not parsed.hostname or not parsed.port:
        message = "promotion egress proxy credential is not host:port"
        raise PromotionPipelineError(message)
    return (parsed.hostname, parsed.port)


def _embedding_profile(deployment: str) -> EmbeddingProfile:
    """Build the profile this worker embeds under.

    The values that decide retrieval behaviour — provider, deployment, width,
    metric — are fixed here rather than taken from the payload, so a scheduled
    message cannot talk the worker into a different model or geometry.
    """
    return EmbeddingProfile(
        profile_id="prof_v1_poc",
        profile_fingerprint="sha256:" + "0" * 64,
        provider="AZURE_OPENAI",
        resource_class="HOSTED",
        geography_class="US",
        deployment_name=deployment,
        model_id=_EMBEDDING_MODEL,
        model_version="1",
        api_contract="2024-10-21",
        tokenizer="cl100k_base",
        dimensions=_EMBEDDING_DIMENSIONS,
        encoding="float32",
        normalization="NONE",
        metric="cosine",
        max_input_tokens=8191,
        cost_limit_microunits=10_000_000,
        expires_at="2027-01-01T00:00:00Z",
        allowed_environments=("POC",),
    )


class PromotionActivities:
    """The two real effects this worker performs, bound to one infrastructure."""

    def __init__(
        self,
        infrastructure: V1PromotionInfrastructure,
        environment: Mapping[str, str],
    ) -> None:
        """Compose the real provider adapters from this worker's own credentials."""
        host, port = _proxy(infrastructure)
        transport = ProviderTransport(host, port)
        self._azure = AzureOpenAIConfig.from_credential_json(
            infrastructure.embedding_provider_credential.reveal()
        )
        self._embedding = AzureOpenAIEmbeddingAdapter(self._azure, transport)
        self._pinecone = PineconeConfig.from_credential_json(
            infrastructure.pinecone_credential.reveal()
        )
        self._authorized = write_authorized(environment)
        self._store = PineconeServingTargetStore(
            self._pinecone,
            transport,
            write_authorized=self._authorized,
        )
        self._profile = _embedding_profile(self._azure.deployment)

    @property
    def index(self) -> str:
        """Return the serving target this worker writes to."""
        return self._pinecone.index

    @property
    def authorized(self) -> bool:
        """Report whether this worker may write."""
        return self._authorized

    def embed_records(self, _context: ActivityContext, payload: object) -> object:
        """Embed every supplied record and return vectors with their receipts."""
        records = [PromotionRecordInput.from_json(item) for item in _sequence(payload)]
        if len(records) > _MAX_BATCH:
            message = f"batch of {len(records)} exceeds the {_MAX_BATCH} record limit"
            raise PromotionPipelineError(message)
        embedded: list[dict[str, object]] = []
        for position, record in enumerate(records):
            request = EmbeddingRequest(
                request_id=f"req_{record.record_id}",
                record_id=record.record_id,
                serving_payload_fingerprint="sha256:" + "0" * 64,
                text=record.text,
                text_fingerprint="sha256:" + "0" * 64,
                token_count=len(record.text.split()),
                profile_id=self._profile.profile_id,
                batch_id="batch_v1_poc",
                batch_position=position,
                cache_key=f"ck_{record.record_id}",
            )
            vector = self._embedding.embed(self._profile, request)
            embedded.append(
                {
                    "record_id": record.record_id,
                    "text": record.text,
                    "vector": list(vector.values),
                    "vector_fingerprint": vector.receipt.vector_fingerprint,
                    "input_tokens": vector.receipt.input_tokens,
                    "latency_milliseconds": vector.receipt.latency_milliseconds,
                }
            )
        _LOGGER.info("PROMOTION_WORKER embedded %s record(s)", len(embedded))
        return embedded

    def upsert_records(self, _context: ActivityContext, payload: object) -> object:
        """Write the embedded records to the serving target and verify retrieval."""
        embedded = list(_sequence(payload))
        records = tuple(
            TargetRecord(
                str(item["record_id"]),
                str(item["vector_fingerprint"]),
                tuple(float(value) for value in _sequence(item["vector"])),
                str(item["text"]),
            )
            for item in embedded
            if isinstance(item, dict)
        )
        if not records:
            return {"written": 0, "verified": False, "index": self.index}
        self._store.upsert_batch(self.index, records)
        identifiers = tuple(record.record_id for record in records)
        self._store.verify_queries(self.index, identifiers)
        _LOGGER.info(
            "PROMOTION_WORKER wrote and verified %s record(s) in %s",
            len(records),
            self.index,
        )
        return {"written": len(records), "verified": True, "index": self.index}


def _sequence(value: object) -> list[object]:
    if isinstance(value, str):
        decoded = json.loads(value)
        return list(decoded) if isinstance(decoded, list) else [decoded]
    if isinstance(value, list):
        return list(value)
    message = "expected a sequence payload"
    raise PromotionPipelineError(message)


def promote_records(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Orchestrate one promotion: embed, then serve, then report.

    Deliberately free of provider calls and clocks. The scheduler replays this
    function on every work item, so anything with an effect belongs in an activity.
    """
    embedded = yield context.call_activity("embed_records", input=payload)
    written = yield context.call_activity("upsert_records", input=embedded)
    return written


class PromotionHandoff:
    """Claim promotion intents the control plane recorded, and serve them.

    The control plane cannot schedule on this worker's hub, so it records what
    should be served and this claims it. The claim carries a fencing token and a
    lease: two workers cannot hold one intent, and a worker that dies without a
    receipt loses the claim when the lease expires rather than stranding the work.
    """

    def __init__(
        self,
        infrastructure: V1PromotionInfrastructure,
        activities: PromotionActivities,
    ) -> None:
        """Bind the handoff to this worker's register connection and activities."""
        self._store = EffectHandoffStore(infrastructure.sql)
        self._activities = activities
        self._claimant = "promotion-worker"

    def poll_once(self) -> dict[str, object] | None:
        """Claim at most one intent, serve it, and record its terminal receipt."""
        claimed = self._store.claim_next(
            owning_application="PROMOTION_WORKER",
            effect_type=_PROMOTION_EFFECT,
            claimant_id=self._claimant,
            lease_seconds=_CLAIM_LEASE_SECONDS,
        )
        if claimed is None:
            return None
        _LOGGER.info("PROMOTION_WORKER claimed intent %s", claimed.effect_intent_id)
        status = "SUCCEEDED"
        try:
            intent = json.loads(claimed.intent_bytes)
            records = intent.get("records") if isinstance(intent, dict) else None
            embedded = self._activities.embed_records(None, records or [])
            result = self._activities.upsert_records(None, embedded)
        except (PromotionPipelineError, PromotionError, ValueError, KeyError) as error:
            # The outcome is recorded either way. An intent that failed must not
            # look unclaimed, or the next poll would repeat a real provider write.
            status = "FAILED_FINAL"
            result = {"error": str(error)[:300]}
            _LOGGER.warning(
                "PROMOTION_WORKER intent %s failed: %s", claimed.effect_intent_id, error
            )
        receipt_bytes = json.dumps(result, sort_keys=True, default=str).encode()
        self._store.record_receipt(
            effect_receipt_id=f"erc_{sha256(receipt_bytes).hexdigest()[:40]}",
            effect_intent_id=claimed.effect_intent_id,
            terminal_status=status,
            attempt_count=1,
            receipt_bytes=receipt_bytes,
            receipt_fingerprint=sha256(receipt_bytes).digest(),
            fencing_token=claimed.fencing_token,
        )
        _LOGGER.info(
            "PROMOTION_WORKER recorded %s for intent %s", status, claimed.effect_intent_id
        )
        return {"effect_intent_id": claimed.effect_intent_id, "status": status}
