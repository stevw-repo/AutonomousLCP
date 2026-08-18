"""Patchright discovery policy and ephemeral-browser adapter tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import pytest
from asklegal_acquisition_worker import (
    PatchrightDiscoveryPolicy,
    PatchrightDiscoveryTransport,
    patchright_policy_for_endpoint,
)
from asklegal_source_connectors import (
    EndpointAccessMode,
    OfficialEndpointContract,
    SignalUse,
    load_hk_legislation_source_register,
)


@dataclass(slots=True)
class FakeRequest:
    method: str
    resource_type: str
    url: str


@dataclass(slots=True)
class FakeRoute:
    request: FakeRequest
    continued: bool = False
    aborted: bool = False

    def abort(self) -> None:
        self.aborted = True

    def continue_(self) -> None:
        self.continued = True


class FakeRunner:
    def __init__(self) -> None:
        self.routes: list[FakeRoute] = []
        self.called = False
        self.closed = False

    def run(
        self,
        *,
        url: str,
        timeout_seconds: int,
        settle_milliseconds: int,
        max_bytes: int,
        route_handler: Callable[[FakeRoute], None],
    ) -> tuple[int, str, bytes, bool]:
        assert timeout_seconds == 20
        assert settle_milliseconds == 1_000
        assert max_bytes == 20_000_000
        self.called = True
        for request in (
            FakeRequest("GET", "script", f"{url}app.js?token=discard"),
            FakeRequest("POST", "xhr", f"{url}search"),
            FakeRequest("GET", "script", "https://outside.invalid/app.js"),
            FakeRequest("GET", "websocket", f"{url}socket"),
        ):
            route = FakeRoute(request)
            route_handler(route)
            self.routes.append(route)
        self.closed = True
        return 200, url, b"<html><body>rendered</body></html>", False


def _discovery_endpoint() -> OfficialEndpointContract:
    return next(
        endpoint
        for endpoint in load_hk_legislation_source_register().endpoints
        if endpoint.url == "https://flk.npc.gov.cn/index"
    )


def test_policy_rejects_implicit_network_expansion() -> None:
    with pytest.raises(ValueError, match="lowercase DNS"):
        PatchrightDiscoveryPolicy(("FLK.NPC.GOV.CN",))
    with pytest.raises(ValueError, match="absolute paths"):
        PatchrightDiscoveryPolicy(("flk.npc.gov.cn",), allowed_post_paths=("search",))


def test_patchright_discovery_is_ephemeral_bounded_and_sanitized() -> None:
    endpoint = _discovery_endpoint()
    runner = FakeRunner()
    transport = PatchrightDiscoveryTransport(
        PatchrightDiscoveryPolicy(("flk.npc.gov.cn",)),
        runner=runner,
    )

    response = transport.capture(endpoint=endpoint, url=endpoint.url, timeout_seconds=20)

    assert response.status_code == 200
    assert response.final_url == endpoint.url
    assert b"observed_requests" in response.body
    assert b"token" not in response.body
    assert runner.closed
    assert [route.continued for route in runner.routes] == [True, False, False, False]
    discovery = transport.last_discovery
    assert discovery is not None
    assert discovery.rendered_html == b"<html><body>rendered</body></html>"
    assert discovery.observed_requests[0].url == f"{endpoint.url}app.js"
    assert all("token" not in request.url for request in discovery.observed_requests)


def test_only_an_exact_declared_post_path_can_leave_the_browser() -> None:
    endpoint = _discovery_endpoint()
    runner = FakeRunner()
    transport = PatchrightDiscoveryTransport(
        PatchrightDiscoveryPolicy(
            ("flk.npc.gov.cn",),
            allowed_post_paths=("/indexsearch",),
        ),
        runner=runner,
    )

    transport.capture(endpoint=endpoint, url=endpoint.url, timeout_seconds=20)

    assert [route.continued for route in runner.routes] == [True, True, False, False]


def test_non_discovery_endpoint_fails_before_browser_start() -> None:
    endpoint = replace(
        _discovery_endpoint(),
        signal_use=SignalUse.NOT_A_SIGNAL,
    )
    runner = FakeRunner()
    transport = PatchrightDiscoveryTransport(
        PatchrightDiscoveryPolicy(("flk.npc.gov.cn",)),
        runner=runner,
    )

    with pytest.raises(PermissionError, match="discovery-only"):
        transport.capture(endpoint=endpoint, url=endpoint.url, timeout_seconds=20)
    assert not runner.called


def test_wrong_mode_and_unlisted_navigation_fail_before_browser_start() -> None:
    endpoint = _discovery_endpoint()
    runner = FakeRunner()
    transport = PatchrightDiscoveryTransport(
        PatchrightDiscoveryPolicy(("flk.npc.gov.cn",)),
        runner=runner,
    )

    with pytest.raises(PermissionError, match="endpoint host"):
        transport.capture(
            endpoint=endpoint,
            url="https://outside.invalid/",
            timeout_seconds=20,
        )
    direct = replace(endpoint, access_mode=EndpointAccessMode.DIRECT_HTTP)
    with pytest.raises(PermissionError, match="browser-session"):
        transport.capture(endpoint=direct, url=direct.url, timeout_seconds=20)
    assert not runner.called


def test_source_specific_policies_are_closed_to_reviewed_endpoints() -> None:
    npc = _discovery_endpoint()
    assert patchright_policy_for_endpoint(npc) == PatchrightDiscoveryPolicy(("flk.npc.gov.cn",))
    unknown = replace(
        npc,
        endpoint_id="sep_0000000000000000000000000000000000000000000000ff",
    )
    with pytest.raises(LookupError, match="no reviewed"):
        patchright_policy_for_endpoint(unknown)
