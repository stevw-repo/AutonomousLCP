"""Tests for guarded template resolution in the inert connector."""

from __future__ import annotations

import pytest
from asklegal_source_connectors.model import HttpMethod
from asklegal_source_connectors.official import (
    OfficialEndpointContract,
    load_hk_legislation_source_register,
)
from asklegal_source_connectors.official_http import (
    OfficialFetchRequest,
    OfficialHttpConnector,
    OfficialTransportResponse,
)

_GAZETTE_ARTIFACT = "sep_00000000000000000000000000000000000000000000004f"


class RecordingTransport:
    """Returns one inert reply and remembers the URL it was asked for."""

    def __init__(self) -> None:
        """Start with no recorded request."""
        self.url = ""

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Record the resolved URL and return a minimal admitted PDF."""
        del method, timeout_seconds
        self.url = endpoint.url
        body = b"%PDF-1.4 minimal"
        return OfficialTransportResponse(
            200, self.url, "application/pdf", "binary", body, len(body), False
        )


def _request(locator: str) -> OfficialFetchRequest:
    register = load_hk_legislation_source_register()
    endpoint = next(e for e in register.endpoints if e.endpoint_id == _GAZETTE_ARTIFACT)
    return OfficialFetchRequest(
        endpoint_id=endpoint.endpoint_id,
        endpoint_version=endpoint.version,
        method=HttpMethod.GET,
        prior_fingerprint=None,
        timeout_seconds=30,
        substitutions=(("gazette_artifact_locator", locator),),
    )


def _connector(transport: RecordingTransport) -> OfficialHttpConnector:
    return OfficialHttpConnector(load_hk_legislation_source_register(), transport)


def test_a_locator_resolves_the_template_and_is_fetched() -> None:
    """The address comes from the publisher's own listing, filled into the template."""
    transport = RecordingTransport()

    _connector(transport).fetch(_request("2026/1!en"))

    assert transport.url == "https://www.elegislation.gov.hk/hk/2026/1!en"


def test_a_substitution_cannot_move_the_fetch_to_another_host() -> None:
    """A value carrying a scheme would redirect the fetch if it were accepted."""
    transport = RecordingTransport()

    with pytest.raises(PermissionError):
        _connector(transport).fetch(_request("https://evil.example/x"))


def test_a_substitution_cannot_traverse_out_of_the_path_root() -> None:
    """Parent traversal would reach paths the endpoint never described."""
    transport = RecordingTransport()

    with pytest.raises(PermissionError):
        _connector(transport).fetch(_request("../../etc/passwd"))


def test_a_substitution_naming_no_placeholder_is_refused() -> None:
    """Silently ignoring it would leave an unresolved template to fail later."""
    register = load_hk_legislation_source_register()
    endpoint = next(e for e in register.endpoints if e.endpoint_id == _GAZETTE_ARTIFACT)
    request = OfficialFetchRequest(
        endpoint_id=endpoint.endpoint_id,
        endpoint_version=endpoint.version,
        method=HttpMethod.GET,
        prior_fingerprint=None,
        timeout_seconds=30,
        substitutions=(("not_a_placeholder", "x"),),
    )

    with pytest.raises(PermissionError):
        _connector(RecordingTransport()).fetch(request)
