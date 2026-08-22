"""Complete bilingual inventory capture tests with an inert transport."""

from dataclasses import dataclass

import pytest
from asklegal_source_connectors import (
    HttpMethod,
    OfficialEndpointContract,
    OfficialHttpConnector,
    OfficialInventoryCode,
    OfficialInventoryConnector,
    OfficialInventoryRequest,
    OfficialTransportResponse,
    load_hk_legislation_source_register,
)


@dataclass(slots=True)
class InventoryTransport:
    """Return one deterministic response per required endpoint."""

    status_by_endpoint: dict[str, int]
    calls: list[str]

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        """Return exact inert XML for the requested endpoint."""
        assert method is HttpMethod.GET
        assert timeout_seconds == 20
        self.calls.append(endpoint.endpoint_id)
        body = f"<Listing endpoint='{endpoint.endpoint_id}'/>".encode()
        return OfficialTransportResponse(
            self.status_by_endpoint.get(endpoint.endpoint_id, 200),
            endpoint.url,
            "application/xml",
            "utf-8",
            body,
            len(body),
            False,
        )


def _request(source_id: str, *, priors: bool = False) -> OfficialInventoryRequest:
    register = load_hk_legislation_source_register()
    endpoints = tuple(
        sorted(
            (item.endpoint_id, item.version)
            for item in register.endpoints
            if item.source_id == source_id and item.complete_inventory_required
        )
    )
    fingerprints: tuple[tuple[str, str], ...] = ()
    if priors:
        transport = InventoryTransport({}, [])
        first = OfficialInventoryConnector(OfficialHttpConnector(register, transport)).capture(
            OfficialInventoryRequest(source_id, endpoints, (), 20)
        )
        fingerprints = tuple(
            sorted(
                (item.endpoint_id, item.fingerprint)
                for item in first.member_results
                if item.fingerprint is not None
            )
        )
    return OfficialInventoryRequest(source_id, endpoints, fingerprints, 20)


def test_current_bilingual_inventory_is_complete_only_after_both_members_capture() -> None:
    register = load_hk_legislation_source_register()
    transport = InventoryTransport({}, [])
    result = OfficialInventoryConnector(OfficialHttpConnector(register, transport)).capture(
        _request("HK-LEG-HKEL-CURRENT-INVENTORY")
    )

    assert result.code is OfficialInventoryCode.COMPLETE_CAPTURED
    assert result.inventory_fingerprint is not None
    assert len(result.member_results) == 2
    assert transport.calls == sorted(transport.calls)
    assert all(item.body.startswith(b"<Listing") for item in result.member_results)


def test_complete_identical_result_requires_every_member_to_match() -> None:
    register = load_hk_legislation_source_register()
    transport = InventoryTransport({}, [])
    result = OfficialInventoryConnector(OfficialHttpConnector(register, transport)).capture(
        _request("HK-LEG-HKEL-PAST-INVENTORY", priors=True)
    )

    assert result.code is OfficialInventoryCode.COMPLETE_CAPTURED_IDENTICAL
    assert result.inventory_fingerprint is not None


def test_one_failed_member_cannot_produce_a_complete_fingerprint() -> None:
    register = load_hk_legislation_source_register()
    request = _request("HK-LEG-HKEL-CURRENT-INVENTORY")
    failed_endpoint = request.endpoint_versions[1][0]
    transport = InventoryTransport({failed_endpoint: 404}, [])
    result = OfficialInventoryConnector(OfficialHttpConnector(register, transport)).capture(request)

    assert result.code is OfficialInventoryCode.SOURCE_CONTRACT_CHANGED
    assert result.inventory_fingerprint is None
    assert result.failure_code == "REQUIRED_MEMBER_SOURCE_CONTRACT_CHANGED"
    assert len(result.member_results) == 2


def test_wrong_member_set_and_non_inventory_source_fail_before_transport() -> None:
    register = load_hk_legislation_source_register()
    transport = InventoryTransport({}, [])
    connector = OfficialInventoryConnector(OfficialHttpConnector(register, transport))
    current = _request("HK-LEG-HKEL-CURRENT-INVENTORY")

    with pytest.raises(ValueError, match="exact complete-inventory"):
        connector.capture(
            OfficialInventoryRequest(
                current.source_id,
                current.endpoint_versions[:1],
                (),
                20,
            )
        )
    with pytest.raises(ValueError, match="no complete-inventory"):
        connector.capture(_request("HK-LEG-HKEL-CURRENT-DATA"))
    assert transport.calls == []


def test_blocked_source_fails_before_transport_even_if_it_declares_members() -> None:
    register = load_hk_legislation_source_register()
    transport = InventoryTransport({}, [])
    connector = OfficialInventoryConnector(OfficialHttpConnector(register, transport))
    editorial = next(
        item for item in register.endpoints if item.source_id == "HK-LEG-HKEL-EDITORIAL-RECORDS"
    )

    with pytest.raises(PermissionError, match="not operationally configured"):
        connector.capture(
            OfficialInventoryRequest(
                "HK-LEG-HKEL-EDITORIAL-RECORDS",
                ((editorial.endpoint_id, editorial.version),),
                (),
                20,
            )
        )
    assert transport.calls == []
