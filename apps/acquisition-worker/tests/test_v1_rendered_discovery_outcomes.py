"""Schedulable non-controlling rendered-discovery outcome tests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace

import asklegal_acquisition_worker.v1_pipeline as pipeline
import pytest
from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure
from asklegal_application_runtime import CredentialMaterial
from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import ActivityContext
from asklegal_source_connectors import (
    HongKongLegislationSourceRegister,
    OfficialEndpointContract,
    OfficialFetchCode,
    OfficialRenderedSessionTransport,
    OfficialSourceState,
    OfficialTransportFailure,
    OfficialTransportResponse,
    load_hk_legislation_source_register,
)

_SOURCE_ID = "HK-LEG-HKEL-GAZETTE-BACKCAPTURE"
_ENDPOINT_ID = "sep_000000000000000000000000000000000000000000000041"
_ENDPOINT_VERSION = "1.0.0"
_CUTOFF = "2026-08-21T13:00:00Z"
_SUMMARY = b"<html><body><pre>{&quot;observed_requests&quot;:[]}</pre></body></html>"

type JsonObject = dict[str, JsonValue]


def _empty_calls() -> list[str]:
    return []


class _Vault:
    def __init__(self) -> None:
        self.writes: dict[str, bytes] = {}

    def conditional_create(
        self,
        logical_key: str,
        content: bytes,
        _retention: object,
    ) -> SimpleNamespace:
        existing = self.writes.get(logical_key)
        if existing is not None:
            assert existing == content
        else:
            self.writes[logical_key] = content
        return SimpleNamespace(
            created=existing is None,
            read_back_verified=True,
            reference=SimpleNamespace(version_id=f"version-{len(self.writes)}"),
        )


@dataclass(slots=True)
class _RenderedTransport:
    outcome: str = "success"
    calls: list[str] = field(default_factory=_empty_calls, init=False)

    def capture(
        self,
        *,
        endpoint: OfficialEndpointContract,
        url: str,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        assert timeout_seconds == 45
        self.calls.append(endpoint.endpoint_id)
        if self.outcome == "unavailable":
            message = "bounded render failure"
            raise OfficialTransportFailure(message)
        return OfficialTransportResponse(
            status_code=503 if self.outcome == "changed" else 200,
            final_url=url,
            media_type="text/html",
            character_encoding="utf-8",
            body=_SUMMARY,
            declared_length=len(_SUMMARY),
            truncated=self.outcome == "unsafe",
        )


@dataclass(slots=True)
class _TransportFactory:
    transport: _RenderedTransport
    calls: list[str] = field(default_factory=_empty_calls, init=False)

    def __call__(
        self,
        endpoint: OfficialEndpointContract,
    ) -> OfficialRenderedSessionTransport:
        self.calls.append(endpoint.endpoint_id)
        return self.transport


def _context() -> ActivityContext:
    return ActivityContext("rendered-discovery-test", 1)


def _payload() -> dict[str, object]:
    return {
        "endpoint_id": _ENDPOINT_ID,
        "endpoint_version": _ENDPOINT_VERSION,
        "observation_cutoff": _CUTOFF,
    }


def _object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _enabled_register() -> HongKongLegislationSourceRegister:
    register = load_hk_legislation_source_register()
    sources = tuple(
        replace(item, operational_state=OfficialSourceState.CONFIGURED, blockers=())
        if item.source_id == _SOURCE_ID
        else item
        for item in register.sources
    )
    endpoints = tuple(
        replace(item, enabled=True) if item.source_id == _SOURCE_ID else item
        for item in register.endpoints
    )
    return replace(register, sources=sources, endpoints=endpoints)


def _activities(
    transport: _RenderedTransport,
    *,
    enable_reviewed_endpoint: bool = True,
) -> tuple[pipeline.AcquisitionActivities, _Vault, _TransportFactory]:
    vault = _Vault()
    infrastructure = V1AcquisitionInfrastructure.__new__(V1AcquisitionInfrastructure)
    object.__setattr__(
        infrastructure,
        "source_egress_proxy_credential",
        CredentialMaterial(b"http://proxy.invalid:3128"),
    )
    object.__setattr__(infrastructure, "primary_vault", vault)
    object.__setattr__(infrastructure, "due_cycle_state_root", Path("/dev/null"))
    activities = pipeline.AcquisitionActivities(infrastructure)
    if enable_reviewed_endpoint:
        register = _enabled_register()
        object.__setattr__(activities, "_register", register)
        object.__setattr__(
            activities,
            "_endpoints",
            {item.endpoint_id: item for item in register.endpoints},
        )
        object.__setattr__(
            activities,
            "_sources",
            {item.source_id: item for item in register.sources},
        )
    factory = _TransportFactory(transport)
    object.__setattr__(activities, "_discovery_transport_for_endpoint", factory)
    return activities, vault, factory


def _capture(
    activities: pipeline.AcquisitionActivities,
    payload: object,
) -> JsonObject:
    return _object(checked_json_value(activities.capture_rendered_discovery(_context(), payload)))


def _retained_document(reference_value: JsonValue, vault: _Vault) -> JsonObject:
    reference = _object(reference_value)
    raw = vault.writes[_text(reference["logical_key"])]
    return _object(parse_json_bytes(raw, max_bytes=len(raw)))


def test_reviewed_discovery_retains_only_summary_and_no_authority() -> None:
    """The successful result is a report reference, never source evidence."""
    transport = _RenderedTransport()
    activities, vault, factory = _activities(transport)

    result = _capture(activities, _payload())

    assert result["code"] == OfficialFetchCode.DISCOVERY_SIGNAL_CAPTURED.value
    assert result["source_id"] == _SOURCE_ID
    assert result["controlling_evidence"] is False
    assert result["completeness_supported"] is False
    assert result["coverage_satisfied"] is False
    assert result["no_change_supported"] is False
    assert result["processing_authorized"] is False
    assert result["isolated_response"] is None
    summary = _object(result["discovery_summary"])
    assert _text(summary["logical_key"]).startswith("poc/report/source-discovery-summary/")
    assert vault.writes[_text(summary["logical_key"])] == _SUMMARY
    attempt = _retained_document(result["attempt_report"], vault)
    assert attempt["controlling_evidence"] is False
    assert attempt["coverage_satisfied"] is False
    assert attempt["processing_authorized"] is False
    assert attempt["discovery_summary"] is not None
    assert "coverage_report" not in result
    assert "evidence" not in result
    assert factory.calls == [_ENDPOINT_ID]
    assert transport.calls == [_ENDPOINT_ID]


def test_identical_discovery_attempt_adopts_summary_and_report() -> None:
    """Exact replay adopts both fingerprinted writes without changing authority."""
    transport = _RenderedTransport()
    activities, vault, _factory = _activities(transport)
    first = _capture(activities, _payload())

    repeated = _capture(activities, _payload())

    first_summary = _object(first["discovery_summary"])
    repeated_summary = _object(repeated["discovery_summary"])
    first_attempt = _object(first["attempt_report"])
    repeated_attempt = _object(repeated["attempt_report"])
    assert repeated_summary["fingerprint"] == first_summary["fingerprint"]
    assert repeated_attempt["fingerprint"] == first_attempt["fingerprint"]
    assert repeated_summary["created"] is False
    assert repeated_attempt["created"] is False
    assert repeated["no_change_supported"] is False
    assert len(vault.writes) == 2


@pytest.mark.parametrize(
    ("outcome", "code", "isolated", "write_count"),
    [
        ("unavailable", OfficialFetchCode.SOURCE_UNAVAILABLE, False, 1),
        ("changed", OfficialFetchCode.SOURCE_CONTRACT_CHANGED, True, 2),
        ("unsafe", OfficialFetchCode.UNSAFE_RESPONSE, True, 2),
    ],
)
def test_failed_discovery_is_accounted_without_gaining_authority(
    outcome: str,
    code: OfficialFetchCode,
    *,
    isolated: bool,
    write_count: int,
) -> None:
    """Every terminal failure stays non-authoritative and explicitly accounted."""
    transport = _RenderedTransport(outcome)
    activities, vault, _factory = _activities(transport)

    result = _capture(activities, _payload())

    assert result["code"] == code.value
    assert result["discovery_summary"] is None
    assert (result["isolated_response"] is not None) is isolated
    assert result["controlling_evidence"] is False
    assert result["coverage_satisfied"] is False
    assert result["processing_authorized"] is False
    assert len(vault.writes) == write_count
    attempt = _retained_document(result["attempt_report"], vault)
    assert attempt["code"] == code.value
    assert attempt["controlling_evidence"] is False


def test_currently_disabled_reviewed_endpoint_fails_before_browser_start() -> None:
    """A reviewed policy cannot override the active register's disabled state."""
    transport = _RenderedTransport()
    activities, vault, factory = _activities(
        transport,
        enable_reviewed_endpoint=False,
    )

    with pytest.raises(pipeline.AcquisitionPipelineError, match="not operationally enabled"):
        activities.capture_rendered_discovery(_context(), _payload())

    assert factory.calls == []
    assert transport.calls == []
    assert vault.writes == {}


def test_unreviewed_or_non_discovery_endpoint_fails_before_browser_start() -> None:
    """The activity cannot render arbitrary enabled source endpoints."""
    transport = _RenderedTransport()
    activities, vault, factory = _activities(transport)
    register = load_hk_legislation_source_register()
    endpoint = next(
        item
        for item in register.endpoints
        if item.source_id == "HK-LEG-HKEL-CURRENT-DATA" and item.enabled
    )
    payload = {
        "endpoint_id": endpoint.endpoint_id,
        "endpoint_version": endpoint.version,
        "observation_cutoff": _CUTOFF,
    }

    with pytest.raises(pipeline.AcquisitionPipelineError, match="non-controlling"):
        activities.capture_rendered_discovery(_context(), payload)

    assert factory.calls == []
    assert transport.calls == []
    assert vault.writes == {}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"endpoint_id": _ENDPOINT_ID, "endpoint_version": _ENDPOINT_VERSION},
        {
            "endpoint_id": _ENDPOINT_ID,
            "endpoint_version": _ENDPOINT_VERSION,
            "observation_cutoff": "2026-08-21",
        },
        {**_payload(), "url": "https://outside.invalid/"},
        {**_payload(), "endpoint_version": "0.0.0"},
        {**_payload(), "endpoint_id": b"not-json"},
    ],
)
def test_invalid_discovery_instruction_fails_before_browser_start(payload: object) -> None:
    """Malformed identity, cutoff, or URL override attempts perform no effect."""
    transport = _RenderedTransport()
    activities, vault, factory = _activities(transport)

    with pytest.raises(pipeline.AcquisitionPipelineError):
        activities.capture_rendered_discovery(_context(), payload)

    assert factory.calls == []
    assert transport.calls == []
    assert vault.writes == {}
