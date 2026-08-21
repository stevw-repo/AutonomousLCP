"""Isolated Patchright adapter for non-controlling official-source discovery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from json import dumps
from typing import Protocol
from urllib.parse import SplitResult, urlsplit

from asklegal_source_connectors import (
    EndpointAccessMode,
    OfficialEndpointContract,
    OfficialTransportFailure,
    OfficialTransportResponse,
    SignalUse,
)
from patchright.sync_api import Error as PatchrightError
from patchright.sync_api import Request, Route, sync_playwright


class _BrowserRequest(Protocol):
    @property
    def method(self) -> str: ...

    @property
    def resource_type(self) -> str: ...

    @property
    def url(self) -> str: ...


class _Route(Protocol):
    @property
    def request(self) -> _BrowserRequest: ...

    def abort(self) -> None: ...

    def continue_(self) -> None: ...


class _PatchrightRunner(Protocol):
    def run(
        self,
        *,
        url: str,
        timeout_seconds: int,
        settle_milliseconds: int,
        max_bytes: int,
        route_handler: Callable[[_Route], None],
    ) -> tuple[int, str, bytes, bool]: ...


class _PatchrightRequestAdapter:
    def __init__(self, request: Request) -> None:
        self._request = request

    @property
    def method(self) -> str:
        return self._request.method

    @property
    def resource_type(self) -> str:
        return self._request.resource_type

    @property
    def url(self) -> str:
        return self._request.url


class _PatchrightRouteAdapter:
    def __init__(self, route: Route) -> None:
        self._route = route

    @property
    def request(self) -> _BrowserRequest:
        return _PatchrightRequestAdapter(self._route.request)

    def abort(self) -> None:
        self._route.abort()

    def continue_(self) -> None:
        self._route.continue_()


class _DefaultPatchrightRunner:
    def run(
        self,
        *,
        url: str,
        timeout_seconds: int,
        settle_milliseconds: int,
        max_bytes: int,
        route_handler: Callable[[_Route], None],
    ) -> tuple[int, str, bytes, bool]:
        with sync_playwright() as engine:
            browser = engine.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    accept_downloads=False,
                    ignore_https_errors=False,
                    java_script_enabled=True,
                    service_workers="block",
                )

                def handle_patchright_route(route: Route) -> None:
                    route_handler(_PatchrightRouteAdapter(route))

                context.route("**/*", handle_patchright_route)
                page = context.new_page()
                response = page.goto(
                    url,
                    timeout=float(timeout_seconds * 1_000),
                    wait_until="domcontentloaded",
                )
                if response is None:
                    raise OfficialTransportFailure("navigation returned no response")
                if settle_milliseconds:
                    page.wait_for_timeout(float(settle_milliseconds))
                page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=float(timeout_seconds * 1_000),
                )
                page.wait_for_timeout(250.0)
                try:
                    body = page.content().encode("utf-8")
                    truncated = len(body) > max_bytes
                    if truncated:
                        body = body[:max_bytes]
                except PatchrightError:
                    body = b""
                    truncated = True
                return response.status, page.url, body, truncated
            finally:
                browser.close()


_HKEL_GAZETTE_DISCOVERY_ENDPOINT_ID = "sep_000000000000000000000000000000000000000000000041"
_NPC_LAWS_DISCOVERY_ENDPOINT_ID = "sep_000000000000000000000000000000000000000000000046"
_PATCHRIGHT_POST_PATHS = {
    _HKEL_GAZETTE_DISCOVERY_ENDPOINT_ID: (
        "/checkconfig/submitClientConfig.do",
        "/client-check",
        "/grid",
    ),
    _NPC_LAWS_DISCOVERY_ENDPOINT_ID: (),
}


@dataclass(frozen=True, slots=True)
class PatchrightDiscoveryPolicy:
    """Exact network and resource limits for one ephemeral discovery browser."""

    allowed_hosts: tuple[str, ...]
    allowed_post_paths: tuple[str, ...] = ()
    settle_milliseconds: int = 1_000
    max_observed_requests: int = 2_000

    def __post_init__(self) -> None:
        """Reject implicit network or resource-limit expansion."""
        if (
            type(self.allowed_hosts) is not tuple
            or not self.allowed_hosts
            or any(not _valid_host(host) for host in self.allowed_hosts)
            or len(set(self.allowed_hosts)) != len(self.allowed_hosts)
        ):
            raise ValueError("allowed_hosts must be unique lowercase DNS hosts")
        if (
            type(self.allowed_post_paths) is not tuple
            or any(
                type(path) is not str or not path.startswith("/") or "?" in path or "#" in path
                for path in self.allowed_post_paths
            )
            or len(set(self.allowed_post_paths)) != len(self.allowed_post_paths)
        ):
            raise ValueError("allowed POST paths must be unique absolute paths")
        if type(self.settle_milliseconds) is not int or not 0 <= self.settle_milliseconds <= 5_000:
            raise ValueError("settle_milliseconds must be between zero and 5000")
        if (
            type(self.max_observed_requests) is not int
            or not 1 <= self.max_observed_requests <= 10_000
        ):
            raise ValueError("max_observed_requests must be between one and 10000")


@dataclass(frozen=True, slots=True)
class PatchrightObservedRequest:
    """Sanitized request fact; headers, cookies, and bodies are never retained."""

    method: str
    url: str
    resource_type: str
    allowed: bool


@dataclass(frozen=True, slots=True)
class PatchrightDiscovery:
    """Rendered discovery output that is never controlling source evidence."""

    status_code: int
    final_url: str
    rendered_html: bytes
    observed_requests: tuple[PatchrightObservedRequest, ...]
    truncated: bool


class PatchrightDiscoveryTransport:
    """Run Patchright in an ephemeral, allowlisted, discovery-only context."""

    def __init__(
        self,
        policy: PatchrightDiscoveryPolicy,
        *,
        runner: _PatchrightRunner | None = None,
    ) -> None:
        """Bind an exact policy and replaceable Patchright runner."""
        if type(policy) is not PatchrightDiscoveryPolicy:
            raise TypeError("policy must be an exact PatchrightDiscoveryPolicy")
        self.policy = policy
        self._runner = runner or _DefaultPatchrightRunner()
        self._last_discovery: PatchrightDiscovery | None = None

    @property
    def last_discovery(self) -> PatchrightDiscovery | None:
        """Return the most recent non-controlling discovery for immediate inspection."""
        return self._last_discovery

    def capture(
        self,
        *,
        endpoint: OfficialEndpointContract,
        url: str,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Render a discovery endpoint and return only bounded inert HTML bytes."""
        discovery = self._discover(
            endpoint=endpoint,
            url=url,
            timeout_seconds=timeout_seconds,
        )
        self._last_discovery = discovery
        summary = _discovery_summary(discovery)
        return OfficialTransportResponse(
            discovery.status_code,
            discovery.final_url,
            "text/html",
            "utf-8",
            summary,
            len(summary),
            discovery.truncated,
        )

    def _discover(
        self,
        *,
        endpoint: OfficialEndpointContract,
        url: str,
        timeout_seconds: int,
    ) -> PatchrightDiscovery:
        """Execute one exact discovery page without persisting browser state."""
        _validate_discovery_request(endpoint, url, timeout_seconds, self.policy)
        observations: list[PatchrightObservedRequest] = []
        observation_limit_exceeded = False

        def handle_route(route: _Route) -> None:
            nonlocal observation_limit_exceeded
            request = route.request
            allowed = _browser_request_allowed(request, self.policy)
            if len(observations) < self.policy.max_observed_requests:
                observations.append(
                    PatchrightObservedRequest(
                        request.method,
                        _sanitized_url(request.url),
                        request.resource_type,
                        allowed,
                    )
                )
            else:
                observation_limit_exceeded = True
                allowed = False
            if allowed:
                route.continue_()
            else:
                route.abort()

        try:
            status, final_url, body, truncated = self._runner.run(
                url=url,
                timeout_seconds=timeout_seconds,
                settle_milliseconds=self.policy.settle_milliseconds,
                max_bytes=endpoint.max_bytes,
                route_handler=handle_route,
            )
            return PatchrightDiscovery(
                status,
                final_url,
                body,
                tuple(observations),
                truncated or observation_limit_exceeded,
            )
        except OfficialTransportFailure:
            raise
        except Exception as error:
            raise OfficialTransportFailure("bounded Patchright discovery failed") from error


def patchright_policy_for_endpoint(
    endpoint: OfficialEndpointContract,
) -> PatchrightDiscoveryPolicy:
    """Return the closed reviewed Patchright policy for one exact endpoint."""
    if type(endpoint) is not OfficialEndpointContract:
        raise TypeError("endpoint must be an exact OfficialEndpointContract")
    post_paths = _PATCHRIGHT_POST_PATHS.get(endpoint.endpoint_id)
    if post_paths is None:
        raise LookupError("endpoint has no reviewed Patchright discovery policy")
    host = urlsplit(endpoint.url).hostname
    if host is None:
        raise ValueError("Patchright endpoint must have one DNS host")
    return PatchrightDiscoveryPolicy((host,), allowed_post_paths=post_paths)


def _validate_discovery_request(
    endpoint: OfficialEndpointContract,
    url: str,
    timeout_seconds: int,
    policy: PatchrightDiscoveryPolicy,
) -> None:
    if type(endpoint) is not OfficialEndpointContract:
        raise TypeError("endpoint must be an exact OfficialEndpointContract")
    if endpoint.access_mode is not EndpointAccessMode.BROWSER_SESSION:
        raise PermissionError("Patchright is limited to browser-session endpoints")
    if endpoint.signal_use is not SignalUse.DISCOVERY_ONLY:
        raise PermissionError("Patchright output is discovery-only")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be between one and 60")
    parsed = urlsplit(url)
    if policy.allowed_hosts != (parsed.hostname,):
        raise PermissionError("Patchright policy cannot expand beyond the endpoint host")
    if (
        parsed.scheme != "https"
        or parsed.hostname not in policy.allowed_hosts
        or _safe_port(parsed) not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise PermissionError("navigation URL is outside the exact HTTPS allowlist")


def _browser_request_allowed(
    request: _BrowserRequest,
    policy: PatchrightDiscoveryPolicy,
) -> bool:
    parsed = urlsplit(request.url)
    method_allowed = request.method in {"GET", "HEAD"} or (
        request.method == "POST" and parsed.path in policy.allowed_post_paths
    )
    return (
        method_allowed
        and parsed.scheme == "https"
        and parsed.hostname in policy.allowed_hosts
        and _safe_port(parsed) in {None, 443}
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
        and request.resource_type not in {"eventsource", "websocket"}
    )


def _sanitized_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname
    port = _safe_port(parsed)
    if host is None or port == -1:
        return ""
    authority = host if port is None else f"{host}:{port}"
    return parsed._replace(netloc=authority, query="", fragment="").geturl()


def _safe_port(parsed: SplitResult) -> int | None:
    try:
        return parsed.port
    except ValueError:
        return -1


def _discovery_summary(discovery: PatchrightDiscovery) -> bytes:
    observed_requests = tuple(
        sorted(
            discovery.observed_requests,
            key=lambda item: (item.method, item.url, item.resource_type, item.allowed),
        )
    )
    payload = dumps(
        {
            "final_url": _sanitized_url(discovery.final_url),
            "observed_requests": [
                {
                    "allowed": item.allowed,
                    "method": item.method,
                    "resource_type": item.resource_type,
                    "url": item.url,
                }
                for item in observed_requests
            ],
            "status_code": discovery.status_code,
            "truncated": discovery.truncated,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"<html><body><pre>{escape(payload)}</pre></body></html>".encode()


def _valid_host(host: object) -> bool:
    return (
        type(host) is str
        and bool(host)
        and host == host.lower()
        and not host.startswith(".")
        and not host.endswith(".")
        and all(character.isalnum() or character in {"-", "."} for character in host)
    )
