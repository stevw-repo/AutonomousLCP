"""Rendered-session connector tests with an inert fake renderer."""

from dataclasses import dataclass, replace

import pytest
from asklegal_source_connectors import (
    HongKongLegislationSourceRegister,
    HttpMethod,
    OfficialEndpointContract,
    OfficialFetchCode,
    OfficialFetchRequest,
    OfficialRenderedFetchRequest,
    OfficialRenderedSessionConnector,
    OfficialSourceState,
    OfficialTransportResponse,
    PublisherRightsState,
    load_hk_legislation_source_register,
)


@dataclass(slots=True)
class RenderTransport:
    """Return one inert response and record the exact requested URL."""

    body: bytes
    media_type: str
    final_url: str | None = None
    calls: int = 0

    def capture(
        self,
        *,
        endpoint: OfficialEndpointContract,
        url: str,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Return deterministic bytes without running a real browser."""
        assert endpoint.endpoint_id.startswith("sep_")
        assert timeout_seconds == 20
        self.calls += 1
        return OfficialTransportResponse(
            200,
            self.final_url or url,
            self.media_type,
            "utf-8" if self.media_type.startswith("text/") else "binary",
            self.body,
            len(self.body),
            False,
        )


def _configured_rendered_register(
    *, templated: bool
) -> tuple[HongKongLegislationSourceRegister, OfficialEndpointContract]:
    register = load_hk_legislation_source_register()
    if templated:
        source_id = "HK-LEG-HKEL-VERIFIED-COPIES"
        endpoint = next(
            item for item in register.endpoints if item.url.endswith("/{verified_copy_locator}.pdf")
        )
        sources = tuple(
            replace(
                item,
                rights_state=PublisherRightsState.PUBLISHED_TERMS_PERMIT,
                operational_state=OfficialSourceState.CONFIGURED,
                blockers=(),
            )
            if item.source_id == source_id
            else item
            for item in register.sources
        )
        endpoints = tuple(
            replace(item, enabled=True) if item.source_id == source_id else item
            for item in register.endpoints
        )
        return replace(register, sources=sources, endpoints=endpoints), endpoint
    source_id = "HK-LEG-NPC-NATIONAL-LAWS-DATABASE"
    endpoint = next(
        item for item in register.endpoints if item.url == "https://flk.npc.gov.cn/index"
    )
    sources = tuple(
        replace(
            item,
            rights_state=PublisherRightsState.LEGAL_TEAM_CLEARED,
            operational_state=OfficialSourceState.PARTIALLY_CONFIGURED,
            blockers=("TEST_OTHER_ENDPOINTS_DISABLED",),
        )
        if item.source_id == source_id
        else item
        for item in register.sources
    )
    rendered = replace(endpoint, enabled=True)
    endpoints = tuple(
        rendered if item.endpoint_id == endpoint.endpoint_id else item
        for item in register.endpoints
    )
    return replace(register, sources=sources, endpoints=endpoints), rendered


def _fetch_request(endpoint: OfficialEndpointContract) -> OfficialFetchRequest:
    return OfficialFetchRequest(endpoint.endpoint_id, endpoint.version, HttpMethod.GET, None, 20)


def test_fixed_rendered_endpoint_captures_only_discovery_bytes() -> None:
    register, endpoint = _configured_rendered_register(templated=False)
    transport = RenderTransport(b"<html><body>discovery</body></html>", "text/html")
    result = OfficialRenderedSessionConnector(register, transport).fetch(
        OfficialRenderedFetchRequest(_fetch_request(endpoint), None)
    )

    assert result.code is OfficialFetchCode.DISCOVERY_SIGNAL_CAPTURED
    assert result.fingerprint is not None
    assert transport.calls == 1


def test_browser_output_cannot_stand_in_for_verified_pdf_evidence() -> None:
    register, endpoint = _configured_rendered_register(templated=True)
    transport = RenderTransport(b"%PDF-1.7\n%%EOF", "application/pdf")
    connector = OfficialRenderedSessionConnector(register, transport)

    with pytest.raises(PermissionError, match="discovery-only"):
        connector.fetch(OfficialRenderedFetchRequest(_fetch_request(endpoint), None))
    assert transport.calls == 0


def test_active_render_and_final_url_drift_fail_closed() -> None:
    register, endpoint = _configured_rendered_register(templated=False)
    active = RenderTransport(b"<html><script>alert(1)</script></html>", "text/html")
    result = OfficialRenderedSessionConnector(register, active).fetch(
        OfficialRenderedFetchRequest(_fetch_request(endpoint), None)
    )
    assert result.code is OfficialFetchCode.UNSAFE_RESPONSE

    drift = RenderTransport(
        b"<html><body>drift</body></html>",
        "text/html",
        final_url="https://changed.invalid/source",
    )
    result = OfficialRenderedSessionConnector(register, drift).fetch(
        OfficialRenderedFetchRequest(_fetch_request(endpoint), None)
    )
    assert result.code is OfficialFetchCode.SOURCE_CONTRACT_CHANGED


def test_real_blocked_rendered_source_fails_before_renderer() -> None:
    register = load_hk_legislation_source_register()
    endpoint = next(item for item in register.endpoints if item.url.endswith("/en/list-of-gazette"))
    transport = RenderTransport(b"<html/>", "text/html")

    with pytest.raises(PermissionError, match="not operationally configured"):
        OfficialRenderedSessionConnector(register, transport).fetch(
            OfficialRenderedFetchRequest(_fetch_request(endpoint), None)
        )
    assert transport.calls == 0
