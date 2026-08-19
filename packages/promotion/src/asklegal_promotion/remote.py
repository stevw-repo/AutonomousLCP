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
from urllib.parse import urlsplit

from .model import (
    EmbeddedVector,
    EmbeddingReceipt,
    PromotionError,
    PromotionErrorCode,
    TargetDefinition,
    TargetRecord,
)

if TYPE_CHECKING:
    from .model import EmbeddingProfile, EmbeddingRequest

AZURE_OPENAI_PROVIDER = "AZURE_OPENAI"
"""The only provider value this embedding adapter will serve."""

PINECONE_API_VERSION = "2025-04"
"""The Pinecone REST contract version these calls are written against."""

_DEFAULT_TIMEOUT_SECONDS = 60
_UPSERT_BATCH_LIMIT = 100
_LIST_PAGE_LIMIT = 100
_FETCH_BATCH_LIMIT = 100
_MAX_ERROR_BODY_BYTES = 600
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
    payload: object
    request_id: str
    latency_milliseconds: int


class ProviderCall(Protocol):
    """The transport surface an adapter needs, so a test can supply its own."""

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: object | None = None,
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

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: object | None = None,
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
            raw = response.read()
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
        payload = json.loads(raw) if raw else {}
        return ProviderResponse(status, payload, request_id, elapsed)


def _request_id(getheader: Callable[[str], str | None]) -> str:
    for name in ("apim-request-id", "x-request-id", "x-ms-request-id", "x-pinecone-request-id"):
        value = getheader(name)
        if value:
            return str(value)
    return "unreported"


def _object(payload: object, detail: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, detail)
    return payload


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
        parsed = _object(json.loads(raw), "azure credential must be a JSON object")
        missing = {"endpoint", "deployment", "api_version", "api_key"} - set(parsed)
        if missing:
            message = f"azure credential missing: {', '.join(sorted(missing))}"
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
        return cls(
            str(parsed["endpoint"]).rstrip("/"),
            str(parsed["deployment"]),
            str(parsed["api_version"]),
            str(parsed["api_key"]),
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

    def __init__(self, config: AzureOpenAIConfig, transport: ProviderCall) -> None:
        """Bind the adapter to one deployment and one proxied transport."""
        self._config = config
        self._transport = transport
        self.calls: list[str] = []

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
                f"provider returned {len(values)} dimensions, "
                f"profile declares {profile.dimensions}"
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
    def _extract_vector(payload: object) -> tuple[float, ...]:
        body = _object(payload, "embedding reply must be a JSON object")
        data = body.get("data")
        if not isinstance(data, list) or not data:
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "no embedding data")
        first = _object(data[0], "embedding entry must be an object")
        vector = first.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise PromotionError(PromotionErrorCode.VECTOR_INVALID, "empty embedding")
        return tuple(float(value) for value in vector)

    @staticmethod
    def _input_tokens(payload: object, declared: int) -> int:
        body = payload if isinstance(payload, dict) else {}
        usage = body.get("usage")
        if isinstance(usage, dict):
            reported = usage.get("prompt_tokens", usage.get("total_tokens"))
            if isinstance(reported, int):
                return reported
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
        return ("" if content is None else str(content), response)


@dataclass(frozen=True, slots=True)
class PineconeConfig:
    """Exact coordinates of one Pinecone project and index."""

    api_key: str
    control_plane_host: str
    index: str

    @classmethod
    def from_credential_json(cls, raw: bytes) -> PineconeConfig:
        """Parse the credential this repository stages for Pinecone."""
        parsed = _object(json.loads(raw), "pinecone credential must be a JSON object")
        missing = {"api_key", "control_plane_host", "index"} - set(parsed)
        if missing:
            message = f"pinecone credential missing: {', '.join(sorted(missing))}"
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)
        return cls(
            str(parsed["api_key"]),
            str(parsed["control_plane_host"]).rstrip("/"),
            str(parsed["index"]),
        )

    def headers(self) -> dict[str, str]:
        """Return the authentication headers for this project."""
        return {
            "Api-Key": self.api_key,
            "X-Pinecone-API-Version": PINECONE_API_VERSION,
            "Accept": "application/json",
        }


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

    Writes require `write_authorized`. Deleting an index additionally requires
    `destructive_authorized`, because losing an index is not recoverable here.
    """

    def __init__(
        self,
        config: PineconeConfig,
        transport: ProviderCall,
        *,
        write_authorized: bool = False,
        destructive_authorized: bool = False,
    ) -> None:
        """Bind the store to one project, transport, and authorization level."""
        self._config = config
        self._transport = transport
        self._write_authorized = write_authorized
        self._destructive_authorized = destructive_authorized
        self._hosts: dict[str, str] = {}

    def _require_write(self, operation: str) -> None:
        if not self._write_authorized:
            message = f"{operation} requires explicit write authorization"
            raise PromotionError(PromotionErrorCode.PROFILE_INVALID, message)

    def _indexes(self) -> tuple[dict[str, object], ...]:
        response = self._transport.send(
            "GET",
            f"{self._config.control_plane_host}/indexes",
            self._config.headers(),
        )
        body = _object(response.payload, "index list must be a JSON object")
        listed = body.get("indexes")
        entries = listed if isinstance(listed, list) else []
        return tuple(entry for entry in entries if isinstance(entry, dict))

    def _index_entry(self, name: str) -> dict[str, object] | None:
        for entry in self._indexes():
            if entry.get("name") == name:
                return entry
        return None

    def _data_plane(self, name: str) -> str:
        cached = self._hosts.get(name)
        if cached:
            return cached
        entry = self._index_entry(name)
        if entry is None:
            message = f"index {name} does not exist"
            raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID, message)
        host = entry.get("host")
        if not host:
            message = f"index {name} reports no data-plane host"
            raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID, message)
        resolved = f"https://{host}"
        self._hosts[name] = resolved
        return resolved

    def create(self, definition: TargetDefinition) -> None:
        """Create the target, or replay exactly if it already matches."""
        entry = self._index_entry(definition.name)
        if entry is not None:
            existing = self._definition_from_entry(entry, definition.namespace)
            if existing != definition:
                message = f"index {definition.name} exists with a different configuration"
                raise PromotionError(PromotionErrorCode.TARGET_COLLISION, message)
            return
        self._require_write(f"creating index {definition.name}")
        self._transport.send(
            "POST",
            f"{self._config.control_plane_host}/indexes",
            self._config.headers(),
            {
                "name": definition.name,
                "dimension": definition.dimensions,
                "metric": definition.metric,
                "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}},
            },
        )

    def describe(self, name: str) -> TargetDefinition:
        """Return the exact immutable configuration of one existing target."""
        entry = self._index_entry(name)
        if entry is None:
            message = f"index {name} does not exist"
            raise PromotionError(PromotionErrorCode.INDEX_NAME_INVALID, message)
        return self._definition_from_entry(entry, "")

    @staticmethod
    def _definition_from_entry(entry: dict[str, object], namespace: str) -> TargetDefinition:
        name = str(entry.get("name", ""))
        dimensions = int(entry.get("dimension", 0) or 0)
        metric = str(entry.get("metric", ""))
        return TargetDefinition(
            name,
            target_state_fingerprint(name, dimensions, metric, namespace),
            dimensions,
            metric,
            namespace,
        )

    def upsert_batch(self, name: str, records: tuple[TargetRecord, ...]) -> None:
        """Write one bounded batch of records into the target."""
        if not records:
            return
        self._require_write(f"upserting into {name}")
        if len(records) > _UPSERT_BATCH_LIMIT:
            message = f"batch of {len(records)} exceeds the {_UPSERT_BATCH_LIMIT} record limit"
            raise PromotionError(PromotionErrorCode.INVENTORY_MISMATCH, message)
        namespace = self._namespace_of(records)
        self._transport.send(
            "POST",
            f"{self._data_plane(name)}/vectors/upsert",
            self._config.headers(),
            {
                "namespace": namespace,
                "vectors": [
                    {
                        "id": record.record_id,
                        "values": list(record.vector),
                        "metadata": {
                            "content_fingerprint": record.content_fingerprint,
                            "text": record.metadata_text,
                        },
                    }
                    for record in records
                ],
            },
        )

    @staticmethod
    def _namespace_of(records: tuple[TargetRecord, ...]) -> str:
        del records
        return ""

    def enumerate(self, name: str) -> tuple[TargetRecord, ...]:
        """Return the complete actual inventory in identity order."""
        host = self._data_plane(name)
        identifiers = self._list_identifiers(host)
        records: list[TargetRecord] = []
        for start in range(0, len(identifiers), _FETCH_BATCH_LIMIT):
            records.extend(self._fetch(host, identifiers[start : start + _FETCH_BATCH_LIMIT]))
        return tuple(sorted(records, key=lambda record: record.record_id))

    def _list_identifiers(self, host: str) -> list[str]:
        identifiers: list[str] = []
        token = ""
        while True:
            url = f"{host}/vectors/list?limit={_LIST_PAGE_LIMIT}"
            if token:
                url = f"{url}&paginationToken={token}"
            response = self._transport.send("GET", url, self._config.headers())
            body = _object(response.payload, "vector list must be a JSON object")
            listed = body.get("vectors")
            if isinstance(listed, list):
                identifiers.extend(
                    str(item["id"]) for item in listed if isinstance(item, dict) and "id" in item
                )
            pagination = body.get("pagination")
            token = ""
            if isinstance(pagination, dict):
                token = str(pagination.get("next", "") or "")
            if not token:
                return identifiers

    def _fetch(self, host: str, identifiers: list[str]) -> list[TargetRecord]:
        if not identifiers:
            return []
        query = "&".join(f"ids={identifier}" for identifier in identifiers)
        response = self._transport.send(
            "GET", f"{host}/vectors/fetch?{query}", self._config.headers()
        )
        body = _object(response.payload, "vector fetch must be a JSON object")
        vectors = body.get("vectors")
        if not isinstance(vectors, dict):
            return []
        records: list[TargetRecord] = []
        for identifier, raw in vectors.items():
            if not isinstance(raw, dict):
                continue
            metadata = raw.get("metadata")
            fields = metadata if isinstance(metadata, dict) else {}
            values = raw.get("values")
            records.append(
                TargetRecord(
                    str(identifier),
                    str(fields.get("content_fingerprint", "")),
                    tuple(float(value) for value in values) if isinstance(values, list) else (),
                    str(fields.get("text", "")),
                )
            )
        return records

    def delete_exact(self, name: str, exact_name: str) -> str:
        """Delete only the exact named index, and only when authorized to destroy."""
        if name != exact_name:
            raise PromotionError(PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN)
        if not self._destructive_authorized:
            message = f"deleting index {name} requires explicit destructive authorization"
            raise PromotionError(PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN, message)
        self._transport.send(
            "DELETE",
            f"{self._config.control_plane_host}/indexes/{name}",
            self._config.headers(),
        )
        self._hosts.pop(name, None)
        return _stable_id("efr", "retire", name)

    def contains(self, name: str) -> bool:
        """Report whether the exact index exists in this project."""
        return self._index_entry(name) is not None

    def verify_queries(self, name: str, expected_record_ids: tuple[str, ...]) -> None:
        """Prove every expected record is actually retrievable from the target."""
        if not expected_record_ids:
            return
        host = self._data_plane(name)
        found = {record.record_id for record in self._fetch(host, list(expected_record_ids))}
        missing = set(expected_record_ids) - found
        if missing:
            message = f"{len(missing)} expected record(s) not retrievable: {sorted(missing)[:5]}"
            raise PromotionError(PromotionErrorCode.RETRIEVAL_GATE_FAILED, message)

    def describe_stats(self, name: str) -> dict[str, object]:
        """Return the target's own statistics, for reconciliation and reporting."""
        response = self._transport.send(
            "POST",
            f"{self._data_plane(name)}/describe_index_stats",
            self._config.headers(),
            {},
        )
        return _object(response.payload, "index stats must be a JSON object")
