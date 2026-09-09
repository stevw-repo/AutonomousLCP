"""Real Azure OpenAI and Pinecone promotion adapters reached through egress proxies.

These are the provider boundaries the local fakes in `local.py` stand in for. They
speak the two REST contracts directly with the standard library, because the images
build offline from a pinned wheelhouse that contains neither provider SDK.

Every mutating call is fail-closed. An adapter refuses to write unless it was
constructed with explicit authorization, and refuses to delete an index unless it
was separately authorized to destroy one, so a configuration slip cannot reach a
real target.
"""

from __future__ import annotations

import json
import math
import ssl
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from http.client import HTTPSConnection
from typing import TYPE_CHECKING, Protocol
from urllib.parse import quote, urlsplit

from asklegal_contracts import ContractViolation, parse_json_bytes

from .builder import (
    SERVING_METADATA_KEYS,
    serving_metadata,
    serving_metadata_fingerprint,
)
from .live_retrieval import (
    LiveRetrievalQueryResult,
    LiveRetrievedRecord,
    live_query_result_fingerprint,
    query_readback_receipt_id,
)
from .model import (
    EmbeddedVector,
    EmbeddingReceipt,
    OutcomeUnknown,
    PromotionError,
    PromotionErrorCode,
    TargetDefinition,
    TargetRecord,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

    from .model import EmbeddingProfile, EmbeddingRequest

AZURE_OPENAI_PROVIDER = "AZURE_OPENAI"
"""The only provider value this embedding adapter will serve."""

PINECONE_API_VERSION = "2025-04"
"""The Pinecone REST contract version these calls are written against."""

_DEFAULT_TIMEOUT_SECONDS = 60
_UPSERT_BATCH_LIMIT = 100
_LIST_PAGE_LIMIT = 100
_FETCH_BATCH_LIMIT = 100
_QUERY_TOP_K_LIMIT = 100
_MAX_ERROR_BODY_BYTES = 600
_MAX_PROVIDER_BODY_BYTES = 10_000_000
_MAX_CREDENTIAL_BYTES = 65_536
_HTTP_BAD_REQUEST = 400


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _vector_fingerprint(values: tuple[float, ...]) -> str:
    return _fingerprint(b"".join(struct.pack("!f", value) for value in values))


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256('|'.join(values).encode()).hexdigest()[:24]}"


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """One decoded provider reply and the accounting the caller needs."""

    status: int
    payload: JsonValue
    request_id: str
    latency_milliseconds: int


@dataclass(frozen=True, slots=True)
class PineconeProviderCallReceipt:
    """Sanitized identity and bounded usage facts for one Pinecone HTTP call."""

    operation: str
    method: str
    request_fingerprint: str
    provider_request_id: str
    latency_milliseconds: int
    request_units: int = 1
    provider_reported_cost_microunits: int | None = None
    cost_basis: str = "PROVIDER_BILLING_OUT_OF_BAND_CALL_CEILING"


class ProviderCall(Protocol):
    """The transport surface an adapter needs, so a test can supply its own."""

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: JsonValue | None = None,
    ) -> ProviderResponse:
        """Send one request and return its decoded reply."""
        ...


class ProviderTransport:
    """Bounded JSON transport that reaches every provider through one egress proxy.

    The connection is opened to the proxy and tunnelled with CONNECT, so TLS is
    still terminated at the provider and the proxy sees only the host name. The
    proxy is a constructor argument rather than an environment lookup, so a worker
    cannot silently fall back to direct egress when the variable is unset.
    """

    def __init__(
        self,
        proxy_host: str,
        proxy_port: int,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Create a transport pinned to one proxy with default trust."""
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._timeout = timeout_seconds
        self._context = ssl.create_default_context()

    @property
    def timeout_seconds(self) -> int:
        """Expose the exact profile-bound timeout for composition admission."""
        return self._timeout

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: JsonValue | None = None,
    ) -> ProviderResponse:
        """Send one bounded request through the proxy and decode its JSON reply."""
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname is None:
            message = f"provider URL must be https: {url}"
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        sent = dict(headers)
        encoded = None
        if body is not None:
            encoded = json.dumps(body).encode()
            sent["Content-Type"] = "application/json"
        connection = HTTPSConnection(
            self._proxy_host,
            port=self._proxy_port,
            timeout=self._timeout,
            context=self._context,
        )
        started = time.monotonic()
        try:
            connection.set_tunnel(parsed.hostname, parsed.port or 443)
            connection.request(method, target, body=encoded, headers=sent)
            response = connection.getresponse()
            raw = response.read(_MAX_PROVIDER_BODY_BYTES + 1)
            if len(raw) > _MAX_PROVIDER_BODY_BYTES:
                raise PromotionError(
                    PromotionErrorCode.PROFILE_INVALID,
                    "provider response exceeds the byte limit",
                )
            status = response.status
            request_id = _request_id(response.getheader)
            if status >= _HTTP_BAD_REQUEST:
                detail = raw[:_MAX_ERROR_BODY_BYTES].decode("utf-8", "replace")
                message = f"HTTP {status} from {method} {url}: {detail}"
                raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
        except (OSError, TimeoutError) as error:
            message = f"transport failure for {method} {url}: {error}"
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message) from error
        finally:
            connection.close()
        elapsed = int((time.monotonic() - started) * 1000)
        payload = _parse_json(raw, "provider reply is not bounded JSON") if raw else {}
        return ProviderResponse(status, payload, request_id, elapsed)


def _request_id(getheader: Callable[[str], str | None]) -> str:
    for name in ("apim-request-id", "x-request-id", "x-ms-request-id", "x-pinecone-request-id"):
        value = getheader(name)
        if value:
            return str(value)
    return "unreported"


def _parse_json(raw: bytes, detail: str, *, max_bytes: int = _MAX_PROVIDER_BODY_BYTES) -> JsonValue:
    try:
        return parse_json_bytes(raw, max_bytes=max_bytes)
    except ContractViolation as error:
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, detail) from error


def _object(payload: JsonValue, detail: str) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, detail)
    return payload


def _text(document: dict[str, JsonValue], field: str) -> str:
    value = document.get(field)
    if type(value) is not str or not value:
        message = f"{field} must be one exact non-empty string"
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
    return value


def _integer(document: dict[str, JsonValue], field: str, *, minimum: int = 0) -> int:
    value = document.get(field)
    if type(value) is not int or value < minimum:
        message = f"{field} must be one integer at least {minimum}"
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
    return value


def _number(value: JsonValue) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "vector value is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "non-finite vector value")
    return result


@dataclass(frozen=True, slots=True)
class AzureOpenAIConfig:
    """Exact coordinates of one Azure OpenAI deployment."""

    endpoint: str
    deployment: str
    api_version: str
    api_key: str

    @classmethod
    def from_credential_json(cls, raw: bytes) -> AzureOpenAIConfig:
        """Parse the four-field credential this repository stages for Azure."""
        parsed = _object(
            _parse_json(raw, "azure credential must be JSON", max_bytes=_MAX_CREDENTIAL_BYTES),
            "azure credential must be a JSON object",
        )
        if set(parsed) != {"endpoint", "deployment", "api_version", "api_key"}:
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "azure credential fields")
        return cls(
            _text(parsed, "endpoint").rstrip("/"),
            _text(parsed, "deployment"),
            _text(parsed, "api_version"),
            _text(parsed, "api_key"),
        )

    def deployment_url(self, path: str) -> str:
        """Build the exact deployment URL for one operation."""
        return (
            f"{self.endpoint}/openai/deployments/{self.deployment}/{path}"
            f"?api-version={self.api_version}"
        )

    def headers(self) -> dict[str, str]:
        """Return the authentication headers for this deployment."""
        return {"api-key": self.api_key}


class AzureOpenAIEmbeddingAdapter:
    """Real `EmbeddingPort` backed by one Azure OpenAI embedding deployment."""

    def __init__(
        self,
        config: AzureOpenAIConfig,
        transport: ProviderCall,
        *,
        serving_profile_fingerprint: str | None = None,
    ) -> None:
        """Bind the adapter to one deployment and one proxied transport."""
        self._config = config
        self._transport = transport
        self.serving_profile_fingerprint = serving_profile_fingerprint
        self.calls: list[str] = []

    @property
    def deployment_name(self) -> str:
        """Return the exact credential-bound deployment."""
        return self._config.deployment

    @property
    def api_contract(self) -> str:
        """Return the exact credential-bound API contract."""
        return self._config.api_version

    @property
    def timeout_seconds(self) -> int | None:
        """Return the exact transport timeout, if the transport declares one."""
        return getattr(self._transport, "timeout_seconds", None)

    def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> EmbeddedVector:
        """Return one real vector and its safe receipt, or fail visibly."""
        if profile.provider != AZURE_OPENAI_PROVIDER:
            message = f"profile provider {profile.provider} is not {AZURE_OPENAI_PROVIDER}"
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
        if profile.deployment_name != self._config.deployment:
            message = (
                f"profile deployment {profile.deployment_name} does not match "
                f"credential deployment {self._config.deployment}"
            )
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
        response = self._transport.send(
            "POST",
            self._config.deployment_url("embeddings"),
            self._config.headers(),
            {"input": request.text},
        )
        values = self._extract_vector(response.payload)
        if len(values) != profile.dimensions:
            message = (
                f"provider returned {len(values)} dimensions, profile declares {profile.dimensions}"
            )
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID, message)
        if any(not math.isfinite(value) for value in values):
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "non-finite value")
        fingerprint = _vector_fingerprint(values)
        receipt = EmbeddingReceipt(
            _stable_id("emc", request.request_id, fingerprint),
            request.request_id,
            response.request_id,
            len(values),
            fingerprint,
            self._input_tokens(response.payload, request.token_count),
            response.latency_milliseconds,
            "SUCCEEDED",
        )
        self.calls.append(request.request_id)
        return EmbeddedVector(values, receipt)

    @staticmethod
    def _extract_vector(payload: JsonValue) -> tuple[float, ...]:
        body = _object(payload, "embedding reply must be a JSON object")
        data = body.get("data")
        if not isinstance(data, list) or not data:
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "no embedding data")
        first = _object(data[0], "embedding entry must be an object")
        vector = first.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "empty embedding")
        return tuple(_number(value) for value in vector)

    @staticmethod
    def _input_tokens(payload: JsonValue, declared: int) -> int:
        body = payload if isinstance(payload, dict) else {}
        usage = body.get("usage")
        if not isinstance(usage, dict):
            message = "provider token accounting is missing or malformed"
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
        if set(usage) != {"prompt_tokens", "total_tokens"} or any(
            type(usage[name]) is not int or usage[name] != declared
            for name in ("prompt_tokens", "total_tokens")
        ):
            message = "provider token accounting differs from exact request count"
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
        return declared


class AzureOpenAIGenerativeAdapter:
    """Real generative boundary for the legal-processing worker.

    Kept beside the embedding adapter because both speak the same deployment
    contract, differing only in path and body.
    """

    def __init__(self, config: AzureOpenAIConfig, transport: ProviderCall) -> None:
        """Bind the adapter to one chat deployment and one proxied transport."""
        self._config = config
        self._transport = transport
        self.calls: list[str] = []

    def complete(self, prompt: str, max_output_tokens: int = 512) -> tuple[str, ProviderResponse]:
        """Return one completion and the raw provider response for accounting."""
        response = self._transport.send(
            "POST",
            self._config.deployment_url("chat/completions"),
            self._config.headers(),
            {
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": max_output_tokens,
            },
        )
        body = _object(response.payload, "completion reply must be a JSON object")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "no completion choices")
        first = _object(choices[0], "completion choice must be an object")
        message = _object(first.get("message"), "completion message must be an object")
        content = message.get("content")
        self.calls.append(response.request_id)
        if type(content) is not str:
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "completion content")
        return (content, response)


@dataclass(frozen=True, slots=True)
class PineconeConfig:
    """Exact coordinates of one Pinecone project and index."""

    api_key: str
    control_plane_host: str
    index: str
    project_id: str

    @classmethod
    def from_credential_json(cls, raw: bytes) -> PineconeConfig:
        """Parse the credential this repository stages for Pinecone."""
        parsed = _object(
            _parse_json(raw, "pinecone credential must be JSON", max_bytes=_MAX_CREDENTIAL_BYTES),
            "pinecone credential must be a JSON object",
        )
        fields = set(parsed)
        current = frozenset({"api_key", "control_plane_host", "index", "project_id"})
        legacy = frozenset({"api_key", "control_plane_host", "index", "project"})
        if frozenset(fields) not in {current, legacy}:
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "pinecone credential fields")
        project_field = "project_id" if "project_id" in parsed else "project"
        return cls(
            _text(parsed, "api_key"),
            _text(parsed, "control_plane_host").rstrip("/"),
            _text(parsed, "index"),
            _text(parsed, project_field),
        )

    def headers(self) -> dict[str, str]:
        """Return the authentication headers for this project."""
        return {
            "Api-Key": self.api_key,
            "X-Pinecone-API-Version": PINECONE_API_VERSION,
            "Accept": "application/json",
        }


class PineconeOperationGate(Protocol):
    """Effect-time authority checked immediately before every target mutation."""

    def require_write(self, operation: str) -> None:
        """Raise unless the exact retained write authority is currently active."""
        ...

    def require_delete(self, operation: str) -> None:
        """Raise unless a separate exact destructive authority is active."""
        ...


def target_state_fingerprint(name: str, dimensions: int, metric: str, namespace: str) -> str:
    """Derive the exact fingerprint of one target's immutable configuration.

    Pinecone stores no such field, so the value is computed from the configuration
    that actually decides retrieval behaviour and compared on every describe.
    """
    canonical = json.dumps(
        {"name": name, "dimensions": dimensions, "metric": metric, "namespace": namespace},
        sort_keys=True,
        separators=(",", ":"),
    )
    return _fingerprint(canonical.encode())


class PineconeServingTargetStore:
    """Real `ServingTargetPort` backed by one Pinecone project.

    Every mutation asks an injected effect-time gate. A constructor Boolean
    cannot enable writes or deletion.
    """

    def __init__(  # noqa: PLR0913 - exact profile, gate, accounting, and transport bindings.
        self,
        config: PineconeConfig,
        transport: ProviderCall,
        *,
        operation_gate: PineconeOperationGate | None = None,
        provider_call_sink: Callable[[PineconeProviderCallReceipt], None] | None = None,
        namespace: str = "",
        page_size: int = _LIST_PAGE_LIMIT,
        expected_data_plane_host: str | None = None,
    ) -> None:
        """Bind one project and transport to an optional effect-time gate."""
        self._config = config
        self._transport = transport
        self._operation_gate = operation_gate
        self._provider_call_sink = provider_call_sink
        self._namespace = namespace
        if expected_data_plane_host is not None and (
            type(expected_data_plane_host) is not str
            or not expected_data_plane_host.startswith("https://")
            or expected_data_plane_host.endswith("/")
        ):
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "data-plane host")
        self._expected_data_plane_host = expected_data_plane_host
        if type(page_size) is not int or not 1 <= page_size <= _LIST_PAGE_LIMIT:
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "readback page size")
        self._page_size = page_size
        self._hosts: dict[str, str] = {}
        self._provider_calls: list[PineconeProviderCallReceipt] = []

    @property
    def target_name(self) -> str:
        """Return the sole admitted replacement target."""
        return self._config.index

    @property
    def project_id(self) -> str:
        """Return the exact Pinecone project identity."""
        return self._config.project_id

    @property
    def namespace(self) -> str:
        """Return the namespace applied to every vector operation."""
        return self._namespace

    @property
    def page_size(self) -> int:
        """Return the profile-bound list/fetch page size."""
        return self._page_size

    @property
    def timeout_seconds(self) -> int | None:
        """Return the exact transport timeout, if the transport declares one."""
        return getattr(self._transport, "timeout_seconds", None)

    @property
    def provider_call_receipts(self) -> tuple[PineconeProviderCallReceipt, ...]:
        """Return the exact sanitized call accounting retained for this adapter instance."""
        return tuple(self._provider_calls)

    def _send(
        self,
        operation: str,
        method: str,
        url: str,
        body: JsonValue | None = None,
    ) -> ProviderResponse:
        request_fingerprint = _fingerprint(
            json.dumps(
                {"body": body, "method": method, "operation": operation, "url": url},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )
        response = self._transport.send(method, url, self._config.headers(), body)
        receipt = PineconeProviderCallReceipt(
            operation,
            method,
            request_fingerprint,
            response.request_id,
            response.latency_milliseconds,
        )
        self._provider_calls.append(receipt)
        if self._provider_call_sink is not None:
            self._provider_call_sink(receipt)
        return response

    def _require_target(self, name: str) -> None:
        if name != self._config.index:
            message = f"index {name} is not the single admitted replacement target"
            raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID, message)

    def _require_write(self, operation: str) -> None:
        if self._operation_gate is None:
            message = f"{operation} requires explicit write authorization"
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
        self._operation_gate.require_write(operation)

    def _indexes(self) -> tuple[dict[str, JsonValue], ...]:
        response = self._send(
            "INDEX_DESCRIBE_OR_LIST",
            "GET",
            f"{self._config.control_plane_host}/indexes",
        )
        body = _object(response.payload, "index list must be a JSON object")
        listed = body.get("indexes")
        entries = listed if isinstance(listed, list) else []
        return tuple(entry for entry in entries if isinstance(entry, dict))

    def _index_entry(self, name: str) -> dict[str, JsonValue] | None:
        for entry in self._indexes():
            if entry.get("name") == name:
                return entry
        return None

    def _data_plane(self, name: str) -> str:
        self._require_target(name)
        cached = self._hosts.get(name)
        if cached:
            return cached
        entry = self._index_entry(name)
        if entry is None:
            message = f"index {name} does not exist"
            raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID, message)
        host = entry.get("host")
        if type(host) is not str or not host:
            message = f"index {name} reports no data-plane host"
            raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID, message)
        resolved = f"https://{host}"
        if (
            self._expected_data_plane_host is not None
            and resolved != self._expected_data_plane_host
        ):
            message = f"index {name} reports a different data-plane host"
            raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID, message)
        self._hosts[name] = resolved
        return resolved

    def data_plane_host(self, name: str) -> str:
        """Resolve and return the exact host bound to this index."""
        return self._data_plane(name)

    def create(self, definition: TargetDefinition) -> None:
        """Create the target, or replay exactly if it already matches."""
        self._require_target(definition.name)
        entry = self._index_entry(definition.name)
        if entry is not None:
            existing = self._definition_from_entry(entry, definition.namespace)
            if existing != definition:
                message = f"index {definition.name} exists with a different configuration"
                raise PromotionError(PromotionErrorCode.TARGET_COLLISION, message)
            return
        self._require_write(f"creating index {definition.name}")
        self._send(
            "INDEX_CREATE",
            "POST",
            f"{self._config.control_plane_host}/indexes",
            {
                "name": definition.name,
                "dimension": definition.dimensions,
                "metric": definition.metric,
                "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}},
            },
        )

    def describe(self, name: str) -> TargetDefinition:
        """Return the exact immutable configuration of one existing target."""
        self._require_target(name)
        entry = self._index_entry(name)
        if entry is None:
            message = f"index {name} does not exist"
            raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID, message)
        return self._definition_from_entry(entry, self._namespace)

    @staticmethod
    def _definition_from_entry(entry: dict[str, JsonValue], namespace: str) -> TargetDefinition:
        name = _text(entry, "name")
        dimensions = _integer(entry, "dimension", minimum=1)
        metric = _text(entry, "metric")
        return TargetDefinition(
            name,
            target_state_fingerprint(name, dimensions, metric, namespace),
            dimensions,
            metric,
            namespace,
        )

    def upsert_batch(self, name: str, records: tuple[TargetRecord, ...]) -> None:
        """Write one bounded batch of records into the target."""
        self._require_target(name)
        if not records:
            return
        self._require_write(f"upserting into {name}")
        if len(records) > _UPSERT_BATCH_LIMIT:
            message = f"batch of {len(records)} exceeds the {_UPSERT_BATCH_LIMIT} record limit"
            raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, message)
        namespace = self._namespace_of(records)
        vectors: list[JsonValue] = []
        for record in records:
            values: list[JsonValue] = []
            values.extend(record.vector)
            metadata: dict[str, JsonValue] = {}
            metadata.update(self._checked_metadata(record))
            vector: dict[str, JsonValue] = {
                "id": record.record_id,
                "values": values,
                "metadata": metadata,
            }
            vectors.append(vector)
        url = f"{self._data_plane(name)}/vectors/upsert"
        try:
            response = self._send(
                "VECTOR_UPSERT",
                "POST",
                url,
                {"namespace": namespace, "vectors": vectors},
            )
        except PromotionError as error:
            message = f"upsert acknowledgement unavailable: {error.code.value}"
            raise OutcomeUnknown(message) from error
        acknowledgement = response.payload
        if not isinstance(acknowledgement, dict):
            message = "upsert acknowledgement is not an object"
            raise OutcomeUnknown(message)
        acknowledged = acknowledgement.get("upsertedCount")
        if type(acknowledged) is not int or acknowledged != len(records):
            message = "upsert acknowledgement count mismatch"
            raise OutcomeUnknown(message)

    @staticmethod
    def _checked_metadata(record: TargetRecord) -> dict[str, str]:
        """Build the six-field payload and refuse one that is not what was approved.

        `content_fingerprint` is deliberately not among the six: the payload is a
        closed object, so identity-adjacent values have no place inside it. It is
        derived from the stored payload again on read.
        """
        payload = serving_metadata(record)
        actual = serving_metadata_fingerprint(payload)
        if record.content_fingerprint != actual:
            claimed = record.content_fingerprint or "nothing"
            message = (
                f"record {record.record_id} claims {claimed} "
                f"but its payload fingerprints as {actual}"
            )
            raise PromotionError(PromotionErrorCode.SERVING_PAYLOAD_INVALID, message)
        return payload

    def _namespace_of(self, records: tuple[TargetRecord, ...]) -> str:
        del records
        return self._namespace

    def enumerate(self, name: str) -> tuple[TargetRecord, ...]:
        """Return the complete actual inventory in identity order."""
        self._require_target(name)
        host = self._data_plane(name)
        identifiers = self._list_identifiers(host)
        records: list[TargetRecord] = []
        for start in range(0, len(identifiers), self._page_size):
            records.extend(self._fetch(host, identifiers[start : start + self._page_size]))
        return tuple(sorted(records, key=lambda record: record.record_id))

    def query(
        self, name: str, vector: tuple[float, ...], top_k: int
    ) -> tuple[LiveRetrievedRecord, ...]:
        """Run one read-only ranked query for the live retrieval evaluator."""
        records, _response = self._query_response(name, vector, top_k)
        return records

    def query_with_receipt(
        self, name: str, vector: tuple[float, ...], top_k: int, request_id: str
    ) -> LiveRetrievalQueryResult:
        """Run one ranked query and preserve its provider/readback identity."""
        if type(request_id) is not str or not request_id:
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "query request id invalid")
        records, response = self._query_response(name, vector, top_k)
        result_fingerprint = live_query_result_fingerprint(records)
        return LiveRetrievalQueryResult(
            records,
            request_id,
            response.request_id,
            query_readback_receipt_id(request_id, response.request_id, result_fingerprint),
            result_fingerprint,
        )

    def _query_response(
        self, name: str, vector: tuple[float, ...], top_k: int
    ) -> tuple[tuple[LiveRetrievedRecord, ...], ProviderResponse]:
        """Return the parsed ranked records together with transport accounting."""
        self._require_target(name)
        if (
            type(top_k) is not int
            or not 1 <= top_k <= _QUERY_TOP_K_LIMIT
            or not vector
            or any(not math.isfinite(value) for value in vector)
        ):
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "query input invalid")
        response = self._send(
            "VECTOR_QUERY",
            "POST",
            f"{self._data_plane(name)}/query",
            {
                "includeMetadata": True,
                "namespace": self._namespace,
                "topK": top_k,
                "vector": list(vector),
            },
        )
        body = _object(response.payload, "query response must be an object")
        raw_matches = body.get("matches")
        if not isinstance(raw_matches, list):
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "query matches missing")
        matches: list[LiveRetrievedRecord] = []
        for raw_match in raw_matches:
            match = _object(raw_match, "query match must be an object")
            metadata = _object(match.get("metadata"), "query metadata must be an object")
            if set(metadata) != set(SERVING_METADATA_KEYS):
                raise PromotionError(PromotionErrorCode.SERVING_PAYLOAD_INVALID, "query metadata")
            matches.append(
                LiveRetrievedRecord(
                    _text(match, "id"),
                    _number(match.get("score")),
                    _text(metadata, "text"),
                    _text(metadata, "country"),
                    _text(metadata, "jurisdiction"),
                    _text(metadata, "type"),
                    _text(metadata, "source"),
                    _text(metadata, "authority_note"),
                )
            )
        return tuple(matches), response

    def _list_identifiers(self, host: str) -> list[str]:
        identifiers: list[str] = []
        token = ""
        namespace = quote(self._namespace, safe="")
        while True:
            url = f"{host}/vectors/list?namespace={namespace}&limit={self._page_size}"
            if token:
                url = f"{url}&paginationToken={quote(token, safe='')}"
            response = self._send("VECTOR_LIST", "GET", url)
            body = _object(response.payload, "vector list must be a JSON object")
            listed = body.get("vectors")
            if isinstance(listed, list):
                for item in listed:
                    entry = _object(item, "vector-list entry must be an object")
                    identifiers.append(_text(entry, "id"))
            pagination = body.get("pagination")
            token = ""
            if isinstance(pagination, dict):
                candidate = pagination.get("next")
                if candidate is not None:
                    if type(candidate) is not str:
                        raise PromotionError(
                            PromotionErrorCode.PROFILE_INVALID,
                            "pagination token must be text",
                        )
                    token = candidate
            if not token:
                return identifiers

    def _fetch(self, host: str, identifiers: list[str]) -> list[TargetRecord]:
        if not identifiers:
            return []
        namespace = quote(self._namespace, safe="")
        identifiers_query = "&".join(
            f"ids={quote(identifier, safe='')}" for identifier in identifiers
        )
        response = self._send(
            "VECTOR_FETCH",
            "GET",
            f"{host}/vectors/fetch?namespace={namespace}&{identifiers_query}",
        )
        body = _object(response.payload, "vector fetch must be a JSON object")
        vectors = body.get("vectors")
        if not isinstance(vectors, dict):
            return []
        records: list[TargetRecord] = []
        for identifier, raw in vectors.items():
            if not isinstance(raw, dict):
                raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "vector is not an object")
            records.append(self._record_from_vector(identifier, raw))
        return records

    @staticmethod
    def _record_from_vector(identifier: str, raw: dict[str, JsonValue]) -> TargetRecord:
        metadata = raw.get("metadata")
        fields = metadata if isinstance(metadata, dict) else {}
        payload: dict[str, str] = {}
        for key in SERVING_METADATA_KEYS:
            value = fields.get(key)
            payload[key] = value if type(value) is str else ""
        values = raw.get("values")
        if not isinstance(values, list):
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "vector values missing")
        return TargetRecord(
            identifier,
            serving_metadata_fingerprint(payload) if all(payload.values()) else "",
            tuple(_number(value) for value in values),
            payload["text"],
            payload["country"],
            payload["jurisdiction"],
            payload["type"],
            payload["source"],
            payload["authority_note"],
        )

    def delete_exact(self, name: str, exact_name: str) -> str:
        """Delete only the exact named index, and only when authorized to destroy."""
        self._require_target(name)
        if name != exact_name:
            raise PromotionError(PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN)
        if self._operation_gate is None:
            message = f"deleting index {name} requires explicit destructive authorization"
            raise PromotionError(PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN, message)
        self._operation_gate.require_delete(f"deleting index {name}")
        self._send(
            "INDEX_DELETE",
            "DELETE",
            f"{self._config.control_plane_host}/indexes/{name}",
        )
        self._hosts.pop(name, None)
        return _stable_id("efr", "retire", name)

    def contains(self, name: str) -> bool:
        """Report whether the exact index exists in this project."""
        self._require_target(name)
        return self._index_entry(name) is not None

    def verify_queries(self, name: str, expected_record_ids: tuple[str, ...]) -> None:
        """Prove every expected record is returned by an exact semantic query."""
        self._require_target(name)
        if not expected_record_ids:
            return
        host = self._data_plane(name)
        expected = {
            record.record_id: record for record in self._fetch(host, list(expected_record_ids))
        }
        if set(expected) != set(expected_record_ids):
            message = "expected query witnesses are absent from target readback"
            raise PromotionError(PromotionErrorCode.RETRIEVAL_GATE_FAILED, message)
        for record_id in expected_record_ids:
            record = expected[record_id]
            response = self._send(
                "VECTOR_QUERY",
                "POST",
                f"{host}/query",
                {
                    "filter": {"text": {"$eq": record.metadata_text}},
                    "includeMetadata": True,
                    "includeValues": True,
                    "namespace": self._namespace,
                    "topK": 1,
                    "vector": list(record.vector),
                },
            )
            body = _object(response.payload, "query result must be a JSON object")
            matches = body.get("matches")
            if not isinstance(matches, list) or len(matches) != 1:
                raise PromotionError(PromotionErrorCode.RETRIEVAL_GATE_FAILED, "query cardinality")
            match = _object(matches[0], "query match must be an object")
            if match.get("id") != record_id:
                raise PromotionError(PromotionErrorCode.RETRIEVAL_GATE_FAILED, "query identity")
            returned = self._record_from_vector(record_id, match)
            if returned != record:
                raise PromotionError(PromotionErrorCode.RETRIEVAL_GATE_FAILED, "query readback")

    def describe_stats(self, name: str) -> dict[str, JsonValue]:
        """Return the target's own statistics, for reconciliation and reporting."""
        self._require_target(name)
        response = self._send(
            "INDEX_STATS",
            "POST",
            f"{self._data_plane(name)}/describe_index_stats",
            {},
        )
        body = _object(response.payload, "index stats must be a JSON object")
        result: dict[str, JsonValue] = {}
        result.update(body)
        return result

    def namespace_vector_count(self, name: str) -> int:
        """Return the exact count for this adapter's namespace, never the global count."""
        statistics = self.describe_stats(name)
        namespaces = statistics.get("namespaces")
        if not isinstance(namespaces, dict):
            raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "namespace statistics")
        raw = namespaces.get(self._namespace)
        if raw is None:
            return 0
        if not isinstance(raw, dict):
            raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "namespace statistics")
        count = raw.get("vectorCount")
        if type(count) is not int or count < 0:
            raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, "namespace vector count")
        return count
