"""Bounded real-source HTTP connector tests with an inert fake transport."""

from dataclasses import dataclass, replace

import pytest
from asklegal_source_connectors import (
    HttpMethod,
    OfficialEndpointContract,
    OfficialFetchCode,
    OfficialFetchRequest,
    OfficialHttpConnector,
    OfficialTransportFailure,
    OfficialTransportResponse,
    load_hk_legislation_source_register,
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
        FakeTransport(replace(original, status_code=503)),
    )
    assert connector.fetch(_request(endpoint)).code is OfficialFetchCode.SOURCE_CONTRACT_CHANGED


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
