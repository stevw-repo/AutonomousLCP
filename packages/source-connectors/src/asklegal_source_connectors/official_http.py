"""Bounded credential-free HTTP transport for configured official sources."""

from __future__ import annotations

import re
import ssl
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from http.client import HTTPResponse, HTTPSConnection
from typing import Protocol
from urllib.parse import urlsplit

from asklegal_evidence_vault import HostileClassification

from .admission import ContentAdmissionInput, ResponseAdmissionPolicy, classify_content
from .model import HttpMethod, exact_identifier, exact_text
from .official import (
    EndpointAccessMode,
    HongKongLegislationSourceRegister,
    OfficialEndpointContract,
    SignalUse,
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class OfficialFetchCode(StrEnum):
    """Closed outcomes for one bounded official-source fetch."""

    CAPTURED = "CAPTURED"
    CAPTURED_IDENTICAL = "CAPTURED_IDENTICAL"
    DISCOVERY_SIGNAL_CAPTURED = "DISCOVERY_SIGNAL_CAPTURED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    UNSAFE_RESPONSE = "UNSAFE_RESPONSE"


@dataclass(frozen=True, slots=True)
class OfficialFetchRequest:
    """One exact endpoint-version request without credentials or floating lookup."""

    endpoint_id: str
    endpoint_version: str
    method: HttpMethod
    prior_fingerprint: str | None
    timeout_seconds: int

    def __post_init__(self) -> None:
        exact_identifier(self.endpoint_id, "endpoint_id", "sep")
        exact_text(self.endpoint_version, "endpoint_version")
        if type(self.method) is not HttpMethod:
            raise TypeError("method must be an exact HttpMethod")
        if self.prior_fingerprint is not None and _SHA256.fullmatch(self.prior_fingerprint) is None:
            raise ValueError("prior_fingerprint must be an exact SHA-256 or None")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be an exact integer from 1 through 120")


@dataclass(frozen=True, slots=True)
class OfficialTransportResponse:
    """One inert bounded HTTP response returned by a transport adapter."""

    status_code: int
    final_url: str
    media_type: str
    character_encoding: str
    body: bytes
    declared_length: int
    truncated: bool

    def __post_init__(self) -> None:
        if type(self.status_code) is not int or not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be an exact HTTP status")
        for field in ("final_url", "media_type", "character_encoding"):
            exact_text(getattr(self, field), field)
        if type(self.body) is not bytes:
            raise TypeError("body must be exact bytes")
        if type(self.declared_length) is not int or self.declared_length < 0:
            raise TypeError("declared_length must be a non-negative exact integer")
        if type(self.truncated) is not bool:
            raise TypeError("truncated must be an exact boolean")


class OfficialHttpTransport(Protocol):
    """Injectable credential-free HTTP transport boundary."""

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Return one bounded inert response without following redirects."""
        ...


class OfficialTransportFailure(RuntimeError):
    """Closed transport failure with no ambient exception detail."""


@dataclass(frozen=True, slots=True)
class OfficialFetchResult:
    """One official fetch result whose bytes remain inert until preserved."""

    code: OfficialFetchCode
    source_id: str
    endpoint_id: str
    endpoint_version: str
    fingerprint: str | None
    body: bytes
    media_type: str | None
    classification: HostileClassification | None
    failure_code: str | None
    transport_response: OfficialTransportResponse | None

    def __post_init__(self) -> None:
        if type(self.code) is not OfficialFetchCode:
            raise TypeError("code must be an exact OfficialFetchCode")
        exact_text(self.source_id, "source_id")
        exact_identifier(self.endpoint_id, "endpoint_id", "sep")
        exact_text(self.endpoint_version, "endpoint_version")
        if self.fingerprint is not None and _SHA256.fullmatch(self.fingerprint) is None:
            raise ValueError("fingerprint must be an exact SHA-256 or None")
        if type(self.body) is not bytes:
            raise TypeError("body must be exact bytes")
        if self.media_type is not None:
            exact_text(self.media_type, "media_type")
        if (
            self.classification is not None
            and type(self.classification) is not HostileClassification
        ):
            raise TypeError("classification must be exact or None")
        if self.failure_code is not None:
            exact_text(self.failure_code, "failure_code")
        if (
            self.transport_response is not None
            and type(self.transport_response) is not OfficialTransportResponse
        ):
            raise TypeError("transport_response must be exact or None")
        if self.code in {
            OfficialFetchCode.CAPTURED,
            OfficialFetchCode.CAPTURED_IDENTICAL,
            OfficialFetchCode.DISCOVERY_SIGNAL_CAPTURED,
        } and (self.fingerprint is None or self.classification is None):
            raise ValueError("successful capture requires a fingerprint and classification")
        if self.transport_response is not None and (
            self.body != self.transport_response.body
            or self.media_type != self.transport_response.media_type
        ):
            raise ValueError("result bytes and media type must bind the transport response")
        if self.code is OfficialFetchCode.SOURCE_UNAVAILABLE:
            if self.transport_response is not None:
                raise ValueError("source-unavailable result cannot invent a response")
        elif self.transport_response is None:
            raise ValueError("response-bearing result must preserve its transport envelope")


class OfficialHttpConnector:
    """Resolve, fetch, and classify only exact configured official endpoints."""

    def __init__(
        self,
        register: HongKongLegislationSourceRegister,
        transport: OfficialHttpTransport,
        *,
        admission_policy: ResponseAdmissionPolicy | None = None,
    ) -> None:
        """Bind an exact register, transport, and hostile-content policy."""
        if type(register) is not HongKongLegislationSourceRegister:
            raise TypeError("register must be an exact HongKongLegislationSourceRegister")
        self.register = register
        self.transport = transport
        self.admission_policy = admission_policy or ResponseAdmissionPolicy()

    def fetch(self, request: OfficialFetchRequest) -> OfficialFetchResult:
        """Fetch one exact enabled direct endpoint and fail closed on every drift."""
        if type(request) is not OfficialFetchRequest:
            raise TypeError("request must be an exact OfficialFetchRequest")
        source, endpoint = self.register.resolve_endpoint(
            request.endpoint_id,
            request.endpoint_version,
        )
        if endpoint.access_mode is not EndpointAccessMode.DIRECT_HTTP:
            raise PermissionError("endpoint requires a non-HTTP acquisition procedure")
        if "{" in endpoint.url or "}" in endpoint.url:
            raise PermissionError("unresolved endpoint templates cannot be fetched")
        if request.method not in endpoint.methods:
            raise PermissionError("method is outside the endpoint contract")
        try:
            response = self.transport.request(
                endpoint=endpoint,
                method=request.method,
                timeout_seconds=request.timeout_seconds,
            )
        except OfficialTransportFailure:
            return _failure(
                OfficialFetchCode.SOURCE_UNAVAILABLE,
                source.source_id,
                endpoint,
                "BOUNDED_TRANSPORT_FAILURE",
            )
        if response.status_code != 200 or response.final_url != endpoint.url:
            return _failure(
                OfficialFetchCode.SOURCE_CONTRACT_CHANGED,
                source.source_id,
                endpoint,
                "STATUS_OR_REDIRECT_DRIFT",
                response,
            )
        if response.media_type not in endpoint.media_types:
            return _failure(
                OfficialFetchCode.SOURCE_CONTRACT_CHANGED,
                source.source_id,
                endpoint,
                "MEDIA_TYPE_DRIFT",
                response,
            )
        classification = classify_content(
            ContentAdmissionInput(
                body=response.body,
                media_type=response.media_type,
                max_bytes=endpoint.max_bytes,
                declared_length=response.declared_length,
                truncated=response.truncated,
                character_encoding=response.character_encoding,
            ),
            self.admission_policy,
        )
        fingerprint = f"sha256:{sha256(response.body).hexdigest()}"
        if not classification.admitted:
            return OfficialFetchResult(
                OfficialFetchCode.UNSAFE_RESPONSE,
                source.source_id,
                endpoint.endpoint_id,
                endpoint.version,
                fingerprint,
                response.body,
                response.media_type,
                classification,
                "HOSTILE_OR_INCOMPLETE_CONTENT",
                response,
            )
        if endpoint.signal_use is SignalUse.DISCOVERY_ONLY:
            code = OfficialFetchCode.DISCOVERY_SIGNAL_CAPTURED
        elif request.prior_fingerprint == fingerprint:
            code = OfficialFetchCode.CAPTURED_IDENTICAL
        else:
            code = OfficialFetchCode.CAPTURED
        return OfficialFetchResult(
            code,
            source.source_id,
            endpoint.endpoint_id,
            endpoint.version,
            fingerprint,
            response.body,
            response.media_type,
            classification,
            None,
            response,
        )


class StdlibOfficialHttpTransport:
    """TLS-validating, proxy-free, cookie-free transport with no redirects."""

    def __init__(self) -> None:
        """Create a default trust-store TLS context without ambient proxy use."""
        self._context = ssl.create_default_context()

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Fetch at most max_bytes plus one sentinel byte."""
        parsed = urlsplit(endpoint.url)
        if parsed.scheme != "https" or parsed.hostname is None:
            raise OfficialTransportFailure("ENDPOINT_SCHEME_INVALID")
        request_target = parsed.path or "/"
        if parsed.query:
            request_target = f"{request_target}?{parsed.query}"
        connection = HTTPSConnection(
            parsed.hostname,
            port=parsed.port or 443,
            timeout=timeout_seconds,
            context=self._context,
        )
        try:
            connection.request(
                method.value,
                request_target,
                headers={
                    "Accept": ", ".join(endpoint.media_types),
                    "User-Agent": "AskLegal-Official-Source-Acquisition/1.0",
                },
            )
            response = connection.getresponse()
            return _read_response(response, endpoint.url, endpoint.max_bytes)
        except (OSError, TimeoutError) as error:
            raise OfficialTransportFailure("BOUNDED_TRANSPORT_FAILURE") from error
        finally:
            connection.close()


class ProxiedOfficialHttpTransport:
    """TLS-validating transport that reaches every source through one egress proxy.

    Identical to `StdlibOfficialHttpTransport` except that the connection is opened
    to the proxy and tunnelled with CONNECT, so TLS is still terminated at the
    official source and the proxy sees only the host name. The proxy is a
    constructor argument, never an environment variable, so a worker cannot fall
    back to direct egress when the variable is missing.
    """

    def __init__(self, proxy_host: str, proxy_port: int) -> None:
        """Create a transport pinned to one proxy with default trust."""
        self._context = ssl.create_default_context()
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Fetch at most max_bytes plus one sentinel byte through the proxy."""
        parsed = urlsplit(endpoint.url)
        if parsed.scheme != "https" or parsed.hostname is None:
            raise OfficialTransportFailure("ENDPOINT_SCHEME_INVALID")
        request_target = parsed.path or "/"
        if parsed.query:
            request_target = f"{request_target}?{parsed.query}"
        connection = HTTPSConnection(
            self._proxy_host,
            port=self._proxy_port,
            timeout=timeout_seconds,
            context=self._context,
        )
        try:
            connection.set_tunnel(parsed.hostname, parsed.port or 443)
            connection.request(
                method.value,
                request_target,
                headers={
                    "Accept": ", ".join(endpoint.media_types),
                    "User-Agent": "AskLegal-Official-Source-Acquisition/1.0",
                },
            )
            response = connection.getresponse()
            return _read_response(response, endpoint.url, endpoint.max_bytes)
        except (OSError, TimeoutError) as error:
            raise OfficialTransportFailure("BOUNDED_TRANSPORT_FAILURE") from error
        finally:
            connection.close()


def _read_response(
    response: HTTPResponse,
    final_url: str,
    max_bytes: int,
) -> OfficialTransportResponse:
    body = response.read(max_bytes + 1)
    truncated = len(body) > max_bytes
    bounded = body[:max_bytes]
    content_length = response.headers.get("Content-Length")
    try:
        declared_length = int(content_length) if content_length is not None else len(bounded)
    except ValueError:
        declared_length = len(bounded) + 1
    media_type = response.headers.get_content_type()
    character_encoding = response.headers.get_content_charset() or (
        "utf-8" if media_type.startswith("text/") or "xml" in media_type else "binary"
    )
    return OfficialTransportResponse(
        response.status,
        final_url,
        media_type,
        character_encoding,
        bounded,
        declared_length,
        truncated,
    )


def _failure(
    code: OfficialFetchCode,
    source_id: str,
    endpoint: OfficialEndpointContract,
    failure_code: str,
    response: OfficialTransportResponse | None = None,
) -> OfficialFetchResult:
    return OfficialFetchResult(
        code,
        source_id,
        endpoint.endpoint_id,
        endpoint.version,
        None,
        b"" if response is None else response.body,
        None if response is None else response.media_type,
        None,
        failure_code,
        response,
    )
