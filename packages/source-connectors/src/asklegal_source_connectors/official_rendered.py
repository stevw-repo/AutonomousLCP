"""Fail-closed rendered-session boundary for official JavaScript source products."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from .admission import ContentAdmissionInput, ResponseAdmissionPolicy, classify_content
from .model import HttpMethod
from .official import (
    EndpointAccessMode,
    HongKongLegislationSourceRegister,
    OfficialEndpointContract,
    SignalUse,
)
from .official_binding import BoundOfficialEndpoint
from .official_http import (
    OfficialFetchCode,
    OfficialFetchRequest,
    OfficialFetchResult,
    OfficialTransportFailure,
    OfficialTransportResponse,
)


class OfficialRenderedSessionTransport(Protocol):
    """Injectable sandboxed renderer returning inert bounded response bytes."""

    def capture(
        self,
        *,
        endpoint: OfficialEndpointContract,
        url: str,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Capture one exact URL without returning cookies or active session state."""
        ...


@dataclass(frozen=True, slots=True)
class OfficialRenderedFetchRequest:
    """One exact rendered endpoint request with optional item locator binding."""

    fetch: OfficialFetchRequest
    bound_endpoint: BoundOfficialEndpoint | None

    def __post_init__(self) -> None:
        if type(self.fetch) is not OfficialFetchRequest:
            raise TypeError("fetch must be an exact OfficialFetchRequest")
        if (
            self.bound_endpoint is not None
            and type(self.bound_endpoint) is not BoundOfficialEndpoint
        ):
            raise TypeError("bound_endpoint must be exact or None")


class OfficialRenderedSessionConnector:
    """Resolve rights first, then capture one non-controlling discovery response."""

    def __init__(
        self,
        register: HongKongLegislationSourceRegister,
        transport: OfficialRenderedSessionTransport,
        *,
        admission_policy: ResponseAdmissionPolicy | None = None,
    ) -> None:
        """Bind an exact register, renderer port, and hostile-content policy."""
        if type(register) is not HongKongLegislationSourceRegister:
            raise TypeError("register must be an exact HongKongLegislationSourceRegister")
        self.register = register
        self.transport = transport
        self.admission_policy = admission_policy or ResponseAdmissionPolicy()

    def fetch(self, request: OfficialRenderedFetchRequest) -> OfficialFetchResult:
        """Capture one discovery-only rendered endpoint and fail closed on drift."""
        if type(request) is not OfficialRenderedFetchRequest:
            raise TypeError("request must be an exact OfficialRenderedFetchRequest")
        source, endpoint = self.register.resolve_endpoint(
            request.fetch.endpoint_id,
            request.fetch.endpoint_version,
        )
        if endpoint.access_mode is not EndpointAccessMode.BROWSER_SESSION:
            raise PermissionError("endpoint does not use a rendered-session procedure")
        if endpoint.signal_use is not SignalUse.DISCOVERY_ONLY:
            raise PermissionError(
                "rendered-session output is discovery-only and cannot be source evidence"
            )
        if request.fetch.method is not HttpMethod.GET or HttpMethod.GET not in endpoint.methods:
            raise PermissionError("rendered-session acquisition requires declared GET")
        expected_url = _expected_url(endpoint, request.bound_endpoint)
        try:
            response = self.transport.capture(
                endpoint=endpoint,
                url=expected_url,
                timeout_seconds=request.fetch.timeout_seconds,
            )
        except OfficialTransportFailure:
            return _failure(
                OfficialFetchCode.SOURCE_UNAVAILABLE,
                source.source_id,
                endpoint,
                "BOUNDED_RENDER_FAILURE",
            )
        if response.status_code != 200 or response.final_url != expected_url:
            return _failure(
                OfficialFetchCode.SOURCE_CONTRACT_CHANGED,
                source.source_id,
                endpoint,
                "STATUS_OR_RENDERED_URL_DRIFT",
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
                "HOSTILE_OR_INCOMPLETE_RENDERED_CONTENT",
                response,
            )
        return OfficialFetchResult(
            OfficialFetchCode.DISCOVERY_SIGNAL_CAPTURED,
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


def _expected_url(
    endpoint: OfficialEndpointContract,
    bound: BoundOfficialEndpoint | None,
) -> str:
    templated = "{" in endpoint.url or "}" in endpoint.url
    if not templated:
        if bound is not None:
            raise ValueError("fixed endpoint cannot receive a locator binding")
        return endpoint.url
    if bound is None:
        raise ValueError("templated endpoint requires an exact locator binding")
    if bound.endpoint_id != endpoint.endpoint_id or bound.endpoint_version != endpoint.version:
        raise ValueError("locator binding does not match the endpoint contract")
    return bound.url


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
