"""Bounded credential-free HTTP transport for configured official sources."""

from __future__ import annotations

import re
import ssl
from dataclasses import dataclass, field, replace
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
    substitutions: tuple[tuple[str, str], ...] = ()
    """Values for a templated endpoint URL, as `(placeholder, value)` pairs.

    A registered template such as `.../hk/{legal_item_locator}` names the shape
    of an address without knowing the item. The value comes from a listing the
    publisher itself returned, so it is data, and it is checked accordingly: the
    resolved URL must keep the template's fixed prefix, so no substitution can
    move a fetch to another host or another path root.
    """

    def __post_init__(self) -> None:
        exact_identifier(self.endpoint_id, "endpoint_id", "sep")
        if type(self.substitutions) is not tuple or any(
            type(pair) is not tuple
            or len(pair) != 2
            or not all(type(item) is str and item for item in pair)
            for pair in self.substitutions
        ):
            raise TypeError("substitutions must be exact (placeholder, value) string pairs")
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
        for attribute in ("final_url", "media_type", "character_encoding"):
            exact_text(getattr(self, attribute), attribute)
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
        endpoint = _resolve_template(endpoint, request.substitutions)
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

    It also follows a bounded number of redirects and keeps cookies within one
    fetch, both of which the strict transport refuses. Several Hong Kong
    government sites answer a plain GET with a 302 to a configuration or session
    check on the same host, which sets a cookie and sends the client back; without
    both, the second request loops and the document never arrives. Refusing them
    made five otherwise-open endpoints look blocked.

    The loosening is deliberately narrow. Redirects are same host only, so a
    redirect can never move a fetch to a host the register has not admitted, and
    at most `max_redirects` hops. Cookies live for the duration of one fetch and
    are discarded with it: nothing persists between endpoints, so a session cannot
    carry identity from one capture into the next.
    """

    def __init__(
        self,
        proxy_host: str,
        proxy_port: int,
        max_redirects: int = 3,
        session_cookies: dict[str, str] | None = None,
    ) -> None:
        """Create a transport pinned to one proxy with default trust.

        `session_cookies` seeds every fetch with a session the caller already
        established. Some publishers gate their documents behind a capability
        check, so an address obtained legitimately still redirects to that gate
        unless the session travels with it. This does not make the transport less
        inert: it is still GET and HEAD only, executes nothing, and follows
        redirects only on the same host. It carries a session; it does not create
        one.
        """
        self._context = ssl.create_default_context()
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        self._max_redirects = max_redirects
        self._session_cookies = dict(session_cookies or {})

    def with_session(self, cookies: dict[str, str]) -> ProxiedOfficialHttpTransport:
        """Return a transport identical to this one but carrying `cookies`."""
        return ProxiedOfficialHttpTransport(
            self._proxy_host,
            self._proxy_port,
            self._max_redirects,
            cookies,
        )

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Fetch at most max_bytes plus one sentinel byte through the proxy."""
        return self._fetch(
            endpoint,
            method,
            timeout_seconds,
            _FetchState(cookies=dict(self._session_cookies)),
        )

    def exchange(
        self,
        call: PublisherCall,
        cookies: dict[str, str] | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        """Send one bounded request to an exact host and return status, body, cookies.

        Deliberately outside `OfficialHttpTransport`. That protocol is the inert
        acquisition boundary — GET and HEAD, no body, no redirects — and it should
        stay that way, because source bytes must never gain authority through it.
        This is the separate surface used by clients that must talk to a
        publisher's own API, such as the HKeL gazette register grid, which is
        `POST`-only and issues a CSRF token through a rendered page.

        The caller names the host, and it is compared against nothing here: the
        caller is responsible for having resolved it from an admitted endpoint.
        """
        jar = dict(cookies or {})
        connection = HTTPSConnection(
            self._proxy_host,
            port=self._proxy_port,
            timeout=call.timeout_seconds,
            context=self._context,
        )
        headers = {
            "User-Agent": "AskLegal-Official-Source-Acquisition/1.0",
            "Accept": "application/json, text/html, */*",
        }
        if call.content_type:
            headers["Content-Type"] = call.content_type
        if jar:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
        try:
            connection.set_tunnel(call.host, 443)
            connection.request(call.method, call.path, body=call.body, headers=headers)
            response = connection.getresponse()
            for name, value in response.getheaders():
                if name.lower() == "set-cookie":
                    _collect_cookies(value, jar)
            payload = response.read(call.max_bytes)
            status = response.status
            location = response.getheader("Location")
        except (OSError, TimeoutError) as error:
            raise OfficialTransportFailure("BOUNDED_TRANSPORT_FAILURE") from error
        finally:
            connection.close()
        if _is_redirect(status) and location:
            target = _same_host_redirect(location, call.host)
            follow = replace(call, method="GET", path=target, body=None, content_type=None)
            return self.exchange(follow, jar)
        return (status, payload, jar)

    def _fetch(
        self,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
        state: _FetchState,
    ) -> OfficialTransportResponse:
        parsed = urlsplit(endpoint.url)
        if parsed.scheme != "https" or parsed.hostname is None:
            raise OfficialTransportFailure("ENDPOINT_SCHEME_INVALID")
        request_target = parsed.path or "/"
        if parsed.query:
            request_target = f"{request_target}?{parsed.query}"
        if state.target is not None:
            request_target = state.target
        connection = HTTPSConnection(
            self._proxy_host,
            port=self._proxy_port,
            timeout=timeout_seconds,
            context=self._context,
        )
        try:
            connection.set_tunnel(parsed.hostname, parsed.port or 443)
            headers = {
                "Accept": ", ".join(endpoint.media_types),
                "User-Agent": "AskLegal-Official-Source-Acquisition/1.0",
            }
            if state.cookies:
                headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in state.cookies.items())
            connection.request(method.value, request_target, headers=headers)
            response = connection.getresponse()
            for name, value in response.getheaders():
                if name.lower() == "set-cookie":
                    _collect_cookies(value, state.cookies)
            location = response.getheader("Location") if _is_redirect(response.status) else None
            if location is None:
                return _read_response(response, endpoint.url, endpoint.max_bytes)
            response.read()
            target = _same_host_redirect(location, parsed.hostname)
        except (OSError, TimeoutError) as error:
            raise OfficialTransportFailure("BOUNDED_TRANSPORT_FAILURE") from error
        finally:
            connection.close()
        if state.depth >= self._max_redirects:
            raise OfficialTransportFailure("REDIRECT_LIMIT_EXCEEDED")
        return self._fetch(
            endpoint,
            method,
            timeout_seconds,
            _FetchState(target, state.depth + 1, state.cookies),
        )


@dataclass(frozen=True, slots=True)
class PublisherCall:
    """One bounded request to a publisher's own API on an already-admitted host."""

    host: str
    method: str
    path: str
    body: bytes | None = None
    content_type: str | None = None
    timeout_seconds: int = 45
    max_bytes: int = 8_000_000


@dataclass(slots=True)
class _FetchState:
    """Mutable state carried across the redirect hops of one fetch."""

    target: str | None = None
    depth: int = 0
    cookies: dict[str, str] = field(default_factory=dict)


def _collect_cookies(header: str | None, jar: dict[str, str]) -> None:
    """Record cookies from one response, keeping only the name and value.

    Attributes are dropped on purpose. This jar exists to complete one fetch, not
    to emulate a browser, so expiry, domain, and path scoping would be honoured
    inconsistently and give a false impression of fidelity.
    """
    if not header:
        return
    for chunk in header.split(","):
        pair = chunk.split(";", 1)[0].strip()
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        name = name.strip()
        # A comma inside an Expires attribute splits into a fragment with no
        # usable name; skip those rather than storing rubbish.
        if name and " " not in name:
            jar[name] = value.strip()


def _resolve_template(
    endpoint: OfficialEndpointContract,
    substitutions: tuple[tuple[str, str], ...],
) -> OfficialEndpointContract:
    """Fill a templated endpoint URL, refusing anything that moves the target.

    The resolved URL must still begin with the template's own fixed prefix — the
    part before its first placeholder. A value carrying a scheme, a host, or a
    parent traversal therefore cannot redirect the fetch, because it would break
    that prefix. Substituted values arrive from a publisher listing and are
    treated as data throughout.
    """
    if not substitutions:
        return endpoint
    if "{" not in endpoint.url:
        raise PermissionError("substitutions supplied for a non-templated endpoint")
    prefix = endpoint.url.split("{", 1)[0]
    resolved = endpoint.url
    for placeholder, value in substitutions:
        token = "{" + placeholder + "}"
        if token not in resolved:
            raise PermissionError("substitution names no placeholder in this endpoint")
        if any(fragment in value for fragment in ("://", "..", "\\")):
            raise PermissionError("substitution value may not carry a scheme or traversal")
        resolved = resolved.replace(token, value)
    if not resolved.startswith(prefix):
        raise PermissionError("resolved URL left the endpoint's fixed prefix")
    return replace(endpoint, url=resolved)


def _is_redirect(status: int) -> bool:
    return status in {301, 302, 303, 307, 308}


def _same_host_redirect(location: str, host: str) -> str:
    """Return the redirect target, refusing any move off the admitted host."""
    parsed = urlsplit(location)
    if not parsed.netloc:
        return location if location.startswith("/") else f"/{location}"
    if parsed.scheme != "https" or parsed.hostname != host:
        raise OfficialTransportFailure("REDIRECT_LEAVES_ADMITTED_HOST")
    target = parsed.path or "/"
    return f"{target}?{parsed.query}" if parsed.query else target


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
