"""Bounded real-source HTTP connector tests with an inert fake transport."""

from dataclasses import dataclass, replace
from enum import StrEnum

import asklegal_source_connectors.official_http as official_http_module
import pytest
from asklegal_source_connectors import (
    HttpMethod,
    OfficialEndpointContract,
    OfficialFetchCode,
    OfficialFetchRequest,
    OfficialHttpConnector,
    OfficialObservationGate,
    OfficialTransportFailure,
    OfficialTransportResponse,
    PolicyBoundOfficialHttpTransport,
    ProxiedOfficialHttpTransport,
    StdlibOfficialHttpTransport,
    hkel_authentic,
    load_hk_legislation_source_register,
    official_observation_profile,
)


@dataclass(slots=True)
class FakeTransport:
    """Inert deterministic transport with no network capability."""

    response: OfficialTransportResponse | None
    fail: bool = False
    calls: int = 0

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Return one scripted response or one closed transport failure."""
        assert endpoint.enabled
        assert method in endpoint.methods
        assert 1 <= timeout_seconds <= 120
        self.calls += 1
        if self.fail:
            raise OfficialTransportFailure
        if self.response is None:
            raise AssertionError
        return self.response


@dataclass(slots=True)
class FakeClock:
    """Deterministic monotonic clock and sleeper for polite-rate proof."""

    now: float = 0.0
    sleeps: list[float] | None = None

    def monotonic(self) -> float:
        """Return the deterministic current time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance time while recording the exact requested delay."""
        if self.sleeps is None:
            self.sleeps = []
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass(slots=True)
class SequenceTransport:
    """Return a bounded sequence of inert replies and record exact timeouts."""

    responses: list[OfficialTransportResponse]
    timeouts: list[int] | None = None

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Return the next reply under the exact supplied timeout."""
        del endpoint, method
        if self.timeouts is None:
            self.timeouts = []
        self.timeouts.append(timeout_seconds)
        return self.responses.pop(0)


@dataclass(slots=True)
class PermissiveTransport:
    """Record every delegation while deliberately enforcing no method policy."""

    response: OfficialTransportResponse
    calls: int = 0

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: object,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Return the scripted reply for any method presented by the wrapper."""
        del endpoint, method, timeout_seconds
        self.calls += 1
        return self.response


class LookalikeHttpMethod(StrEnum):
    """Hostile enum whose value compares equal to a generic method."""

    GET = "GET"


class HttpMethodStringSubclass(str):
    """Hostile string subclass whose value compares equal to a generic method."""

    __slots__ = ()


def _endpoint(suffix: str) -> OfficialEndpointContract:
    register = load_hk_legislation_source_register()
    return next(item for item in register.endpoints if item.url.endswith(suffix))


def _request(endpoint: OfficialEndpointContract, prior: str | None = None) -> OfficialFetchRequest:
    return OfficialFetchRequest(
        endpoint.endpoint_id,
        endpoint.version,
        HttpMethod.GET,
        prior,
        20,
    )


def _response(
    endpoint: OfficialEndpointContract,
    *,
    body: bytes = b"<Listing><Chapter><CapNo>1</CapNo></Chapter></Listing>",
    media_type: str = "application/xml",
) -> OfficialTransportResponse:
    return OfficialTransportResponse(
        200,
        endpoint.url,
        media_type,
        "utf-8",
        body,
        len(body),
        False,
    )


def test_exact_configured_inventory_is_captured_and_fingerprinted() -> None:
    endpoint = _endpoint("hkel_list_c_all_en.xml")
    transport = FakeTransport(_response(endpoint))
    result = OfficialHttpConnector(load_hk_legislation_source_register(), transport).fetch(
        _request(endpoint)
    )

    assert result.code is OfficialFetchCode.CAPTURED
    assert result.fingerprint == (
        "sha256:7bdc70f70685724f4380db50cf42eb0124d83d88a96078a41c29ba418ce4c7b5"
    )
    assert result.classification is not None
    assert result.classification.admitted
    assert result.body.startswith(b"<Listing>")
    assert transport.calls == 1


def test_generic_stdlib_transport_cannot_issue_the_specialized_session_post() -> None:
    """Registering the exact POST target does not grant body-free generic POST authority."""
    endpoint = _endpoint("/checkconfig/submitClientConfig.do")
    session_method_type = getattr(hkel_authentic, "HkelSessionMethod", HttpMethod)
    session_post = session_method_type("POST")

    with pytest.raises(TypeError, match="method must be an exact HttpMethod"):
        StdlibOfficialHttpTransport().request(
            endpoint=endpoint,
            method=session_post,
            timeout_seconds=20,
        )


def test_identical_full_capture_is_not_inferred_from_http_metadata() -> None:
    endpoint = _endpoint("hkel_list_c_all_en.xml")
    transport = FakeTransport(_response(endpoint))
    connector = OfficialHttpConnector(load_hk_legislation_source_register(), transport)
    first = connector.fetch(_request(endpoint))
    assert first.fingerprint is not None

    repeated = connector.fetch(_request(endpoint, first.fingerprint))
    assert repeated.code is OfficialFetchCode.CAPTURED_IDENTICAL
    assert transport.calls == 2


def test_rss_is_always_a_discovery_capture_even_when_identical() -> None:
    endpoint = _endpoint("data_rss_en.xml")
    body = b"<rss version='2.0'><channel><title>DATA.GOV.HK</title></channel></rss>"
    transport = FakeTransport(_response(endpoint, body=body, media_type="application/rss+xml"))
    connector = OfficialHttpConnector(load_hk_legislation_source_register(), transport)
    first = connector.fetch(_request(endpoint))
    assert first.fingerprint is not None

    repeated = connector.fetch(_request(endpoint, first.fingerprint))
    assert first.code is OfficialFetchCode.DISCOVERY_SIGNAL_CAPTURED
    assert repeated.code is OfficialFetchCode.DISCOVERY_SIGNAL_CAPTURED


def test_blocked_rights_and_browser_endpoints_fail_before_transport() -> None:
    endpoint = _endpoint("/en/list-of-gazette")
    transport = FakeTransport(None)
    connector = OfficialHttpConnector(load_hk_legislation_source_register(), transport)

    with pytest.raises(PermissionError, match="not operationally configured"):
        connector.fetch(_request(endpoint))
    assert transport.calls == 0


def test_proxied_transport_zero_redirect_budget_issues_exactly_one_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redirect response cannot turn one authorized GLD listing request into two hops."""
    requested: list[str] = []

    class Socket:
        def settimeout(self, _seconds: float) -> None:
            return None

    class Response:
        status = 302

        def getheaders(self) -> list[tuple[str, str]]:
            return []

        def getheader(self, name: str) -> str | None:
            return "/second-hop" if name == "Location" else None

    class Connection:
        sock = Socket()

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def set_tunnel(self, _host: str, _port: int) -> None:
            return None

        def request(self, _method: str, path: str, *, headers: dict[str, str]) -> None:
            del headers
            requested.append(path)

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            return None

    monkeypatch.setattr(official_http_module, "HTTPSConnection", Connection)
    endpoint = _endpoint("/en/list-of-gazette")
    transport = ProxiedOfficialHttpTransport("proxy", 3128, max_redirects=0)

    with pytest.raises(OfficialTransportFailure, match="REDIRECT_LIMIT_EXCEEDED"):
        transport.request(endpoint=endpoint, method=HttpMethod.GET, timeout_seconds=15)
    assert requested == ["/en/list-of-gazette"]


def test_proxied_transport_decreases_one_deadline_through_response_read(  # noqa: C901
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection stages cannot each mint a fresh timeout inside one listing request."""
    ticks = iter((0.0, 0.6, 1.2, 1.8, 2.4))
    reads = 0

    class Socket:
        def settimeout(self, _seconds: float) -> None:
            return None

    class Headers:
        def get(self, _name: str) -> None:
            return None

        def get_content_type(self) -> str:
            return "text/html"

        def get_content_charset(self) -> str:
            return "utf-8"

    class Response:
        status = 200
        headers = Headers()

        def getheaders(self) -> list[tuple[str, str]]:
            return []

        def getheader(self, _name: str) -> None:
            return None

        def read(self, _size: int) -> bytes:
            nonlocal reads
            reads += 1
            return b"publisher bytes"

    class Connection:
        sock = Socket()

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def set_tunnel(self, _host: str, _port: int) -> None:
            return None

        def request(self, _method: str, _path: str, *, headers: dict[str, str]) -> None:
            del headers

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            return None

    monkeypatch.setattr(official_http_module, "HTTPSConnection", Connection)
    endpoint = _endpoint("/en/list-of-gazette")
    transport = ProxiedOfficialHttpTransport(
        "proxy", 3128, max_redirects=0, monotonic_clock=lambda: next(ticks)
    )

    with pytest.raises(OfficialTransportFailure, match="BOUNDED_TRANSPORT_DEADLINE_EXCEEDED"):
        transport.request(endpoint=endpoint, method=HttpMethod.GET, timeout_seconds=2)
    assert reads == 0


def test_redirect_media_and_status_drift_return_source_contract_changed() -> None:
    endpoint = _endpoint("hkel_list_c_all_en.xml")
    original = _response(endpoint)
    connector = OfficialHttpConnector(
        load_hk_legislation_source_register(),
        FakeTransport(replace(original, final_url="https://changed.invalid/source.xml")),
    )
    result = connector.fetch(_request(endpoint))
    assert result.code is OfficialFetchCode.SOURCE_CONTRACT_CHANGED
    assert result.transport_response is not None
    assert result.body == original.body

    connector = OfficialHttpConnector(
        load_hk_legislation_source_register(),
        FakeTransport(replace(original, media_type="text/html")),
    )
    assert connector.fetch(_request(endpoint)).code is OfficialFetchCode.SOURCE_CONTRACT_CHANGED

    connector = OfficialHttpConnector(
        load_hk_legislation_source_register(),
        FakeTransport(replace(original, status_code=404)),
    )
    assert connector.fetch(_request(endpoint)).code is OfficialFetchCode.SOURCE_CONTRACT_CHANGED

    connector = OfficialHttpConnector(
        load_hk_legislation_source_register(),
        FakeTransport(replace(original, status_code=503)),
    )
    unavailable = connector.fetch(_request(endpoint))
    assert unavailable.code is OfficialFetchCode.SOURCE_UNAVAILABLE
    assert unavailable.transport_response is None


def test_policy_bound_transport_enforces_timeout_rate_and_transient_retry() -> None:
    """One source profile serially retries 429 and paces the next observation."""
    register = load_hk_legislation_source_register()
    endpoint = _endpoint("hkel_list_c_all_en.xml")
    profile = official_observation_profile(register, endpoint.source_id)
    throttled = replace(_response(endpoint), status_code=429)
    transport = SequenceTransport([throttled, _response(endpoint), _response(endpoint)])
    clock = FakeClock()
    gate = OfficialObservationGate(monotonic=clock.monotonic, sleep=clock.sleep)
    connector = OfficialHttpConnector(
        register,
        PolicyBoundOfficialHttpTransport(register, transport, gate),
    )
    request = replace(_request(endpoint), timeout_seconds=profile.timeout_seconds)

    first = connector.fetch(request)
    second = connector.fetch(request)

    assert first.code is OfficialFetchCode.CAPTURED
    assert second.code is OfficialFetchCode.CAPTURED
    assert transport.timeouts == [45, 45, 45]
    assert clock.sleeps == [20.0, 1.0]


@pytest.mark.parametrize(
    "hostile_method",
    [
        hkel_authentic.HkelSessionMethod.POST,
        LookalikeHttpMethod.GET,
        HttpMethodStringSubclass("GET"),
    ],
)
def test_policy_bound_transport_rejects_non_exact_generic_methods_before_delegation(
    hostile_method: HttpMethod,
) -> None:
    """A permissive injected transport cannot widen the generic method boundary."""
    register = load_hk_legislation_source_register()
    endpoint = _endpoint("hkel_list_c_all_en.xml")
    profile = official_observation_profile(register, endpoint.source_id)
    transport = PermissiveTransport(_response(endpoint))
    wrapper = PolicyBoundOfficialHttpTransport(register, transport)

    with pytest.raises(TypeError, match="method must be an exact HttpMethod"):
        wrapper.request(
            endpoint=endpoint,
            method=hostile_method,
            timeout_seconds=profile.timeout_seconds,
        )

    assert transport.calls == 0


@pytest.mark.parametrize("method", [HttpMethod.GET, HttpMethod.HEAD])
def test_policy_bound_transport_preserves_exact_generic_methods(method: HttpMethod) -> None:
    """The wrapper continues to delegate both closed generic methods."""
    register = load_hk_legislation_source_register()
    endpoint = _endpoint("hkel_list_c_all_en.xml")
    profile = official_observation_profile(register, endpoint.source_id)
    expected = _response(endpoint)
    transport = PermissiveTransport(expected)

    actual = PolicyBoundOfficialHttpTransport(register, transport).request(
        endpoint=endpoint,
        method=method,
        timeout_seconds=profile.timeout_seconds,
    )

    assert actual is expected
    assert transport.calls == 1


def test_active_xml_truncation_and_transport_failure_fail_closed() -> None:
    endpoint = _endpoint("hkel_list_c_all_en.xml")
    active = b"<!DOCTYPE x [<!ENTITY leak SYSTEM 'file:///etc/passwd'>]><x>&leak;</x>"
    connector = OfficialHttpConnector(
        load_hk_legislation_source_register(),
        FakeTransport(_response(endpoint, body=active)),
    )
    unsafe = connector.fetch(_request(endpoint))
    assert unsafe.code is OfficialFetchCode.UNSAFE_RESPONSE
    assert unsafe.transport_response is not None

    truncated = replace(_response(endpoint), truncated=True)
    connector = OfficialHttpConnector(
        load_hk_legislation_source_register(), FakeTransport(truncated)
    )
    assert connector.fetch(_request(endpoint)).code is OfficialFetchCode.UNSAFE_RESPONSE

    unavailable = FakeTransport(None, fail=True)
    connector = OfficialHttpConnector(load_hk_legislation_source_register(), unavailable)
    unavailable_result = connector.fetch(_request(endpoint))
    assert unavailable_result.code is OfficialFetchCode.SOURCE_UNAVAILABLE
    assert unavailable_result.transport_response is None
