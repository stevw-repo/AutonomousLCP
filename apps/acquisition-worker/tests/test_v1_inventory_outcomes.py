"""Schedulable complete-inventory acquisition and coverage-accounting tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import asklegal_acquisition_worker.v1_pipeline as pipeline
import pytest
from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure
from asklegal_application_runtime import CredentialMaterial
from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import SourceCoverageDisposition, SourceCoverageOutcomeCode
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import VaultName
from asklegal_source_connectors import (
    HttpMethod,
    OfficialEndpointContract,
    OfficialHttpConnector,
    OfficialInventoryCode,
    OfficialTransportFailure,
    OfficialTransportResponse,
    load_hk_legislation_source_register,
)

_SOURCE_ID = "HK-LEG-HKEL-CURRENT-INVENTORY"
_CUTOFF = "2026-08-21T12:00:00Z"
_UNKNOWN_ENDPOINT = "sep_0000000000000000000000000000000000000000000000ff"

type JsonObject = dict[str, JsonValue]


def _empty_calls() -> list[str]:
    return []


class _Vault:
    def __init__(self) -> None:
        self.writes: dict[str, bytes] = {}
        self.versions: dict[str, str] = {}

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
            self.versions[logical_key] = f"v{sha256(content).hexdigest()}"
        return SimpleNamespace(
            created=existing is None,
            read_back_verified=True,
            reference=SimpleNamespace(
                byte_length=len(content),
                vault=VaultName.PRIMARY,
                version_id=self.versions[logical_key],
            ),
        )


@dataclass(slots=True)
class _InventoryTransport:
    unavailable_endpoint: str | None = None
    changed_endpoint: str | None = None
    unsafe_endpoint: str | None = None
    calls: list[str] = field(default_factory=_empty_calls, init=False)

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        assert method is HttpMethod.GET
        assert timeout_seconds == 45
        self.calls.append(endpoint.endpoint_id)
        if endpoint.endpoint_id == self.unavailable_endpoint:
            message = "bounded failure"
            raise OfficialTransportFailure(message)
        body = f"<Listing endpoint='{endpoint.endpoint_id}'/>".encode()
        if endpoint.endpoint_id == self.unsafe_endpoint:
            body = b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><x>&e;</x>"
        return OfficialTransportResponse(
            status_code=404 if endpoint.endpoint_id == self.changed_endpoint else 200,
            final_url=endpoint.url,
            media_type="application/xml",
            character_encoding="utf-8",
            body=body,
            declared_length=len(body),
            truncated=False,
        )


def _context() -> ActivityContext:
    return ActivityContext("inventory-test", 1)


def _activities(
    transport: _InventoryTransport,
) -> tuple[pipeline.AcquisitionActivities, _Vault]:
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
    connector = OfficialHttpConnector(load_hk_legislation_source_register(), transport)
    object.__setattr__(activities, "_connector", connector)
    return activities, vault


def _payload(*, priors: dict[str, str] | None = None) -> dict[str, object]:
    return {
        "observation_cutoff": _CUTOFF,
        "prior_fingerprints": priors or {},
        "source_id": _SOURCE_ID,
    }


def _object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def _objects(value: JsonValue) -> list[JsonObject]:
    assert isinstance(value, list)
    return [_object(item) for item in value]


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _capture(
    activities: pipeline.AcquisitionActivities,
    payload: object,
) -> JsonObject:
    return _object(checked_json_value(activities.capture_inventory(_context(), payload)))


def _coverage(result: JsonObject) -> JsonObject:
    return _object(result["coverage_report"])


def _manifest(result: JsonObject, vault: _Vault) -> JsonObject:
    reference = _object(result["observation_manifest"])
    logical_key = _text(reference["logical_key"])
    raw = vault.writes[logical_key]
    return _object(parse_json_bytes(raw, max_bytes=len(raw)))


def test_complete_current_inventory_retains_both_members_and_clear_coverage() -> None:
    """A complete bilingual set becomes retained evidence with clear coverage."""
    transport = _InventoryTransport()
    activities, vault = _activities(transport)

    result = _capture(activities, _payload())

    assert result["code"] == OfficialInventoryCode.COMPLETE_CAPTURED.value
    assert result["source_id"] == _SOURCE_ID
    assert result["source_version"] == "1.2.0"
    assert result["retained"] == 2
    assert result["failed"] == 0
    assert _text(result["inventory_fingerprint"]).startswith("sha256:")
    assert len(transport.calls) == 2
    assert transport.calls == sorted(transport.calls)
    coverage = _coverage(result)
    assert coverage["outcome"] == SourceCoverageOutcomeCode.COMPLETE.value
    assert coverage["disposition"] == SourceCoverageDisposition.COMPLETE.value
    assert coverage["release_blocking"] is False
    manifest = _manifest(result, vault)
    assert manifest["complete"] is True
    assert _text(manifest["source_register_fingerprint"]).startswith("sha256:")
    assert all(member["evidence"] is not None for member in _objects(manifest["members"]))


def test_identical_inventory_is_complete_and_adopts_member_evidence() -> None:
    """Exact prior fingerprints produce no-change without skipping source reads."""
    transport = _InventoryTransport()
    activities, _vault = _activities(transport)
    first = _capture(activities, _payload())
    members = _objects(first["members"])
    priors = {
        _text(member["endpoint_id"]): _text(member["response_fingerprint"]) for member in members
    }

    repeated = _capture(activities, _payload(priors=priors))

    assert repeated["code"] == OfficialInventoryCode.COMPLETE_CAPTURED_IDENTICAL.value
    assert repeated["retained"] == 2
    assert repeated["failed"] == 0
    assert _coverage(repeated)["release_blocking"] is False
    repeated_members = _objects(repeated["members"])
    assert all(_object(member["evidence"])["created"] is False for member in repeated_members)


def test_activity_restart_adopts_inventory_evidence_manifest_and_coverage() -> None:
    """Replaying one checkpoint-lost activity does not create parallel accounting."""
    transport = _InventoryTransport()
    activities, _vault = _activities(transport)

    first = _capture(activities, _payload())
    replayed = _capture(activities, _payload())

    assert first["code"] == OfficialInventoryCode.COMPLETE_CAPTURED.value
    assert replayed["code"] == OfficialInventoryCode.COMPLETE_CAPTURED.value
    assert all(
        _object(member["evidence"])["created"] is False for member in _objects(replayed["members"])
    )
    assert _object(replayed["observation_manifest"])["created"] is False
    assert _object(replayed["coverage_report"])["created"] is False


@pytest.mark.parametrize(
    ("failure_mode", "inventory_code", "outcome", "disposition", "isolated"),
    [
        (
            "unavailable_endpoint",
            OfficialInventoryCode.SOURCE_UNAVAILABLE,
            SourceCoverageOutcomeCode.SOURCE_UNAVAILABLE,
            SourceCoverageDisposition.COVERAGE_GAP,
            False,
        ),
        (
            "changed_endpoint",
            OfficialInventoryCode.SOURCE_CONTRACT_CHANGED,
            SourceCoverageOutcomeCode.SOURCE_CONTRACT_CHANGED,
            SourceCoverageDisposition.SOURCE_CONTRACT_REVIEW,
            True,
        ),
        (
            "unsafe_endpoint",
            OfficialInventoryCode.UNSAFE_RESPONSE,
            SourceCoverageOutcomeCode.UNSAFE_RESPONSE,
            SourceCoverageDisposition.QUARANTINE,
            True,
        ),
    ],
)
def test_partial_inventory_is_accounted_isolated_and_release_blocking(
    failure_mode: str,
    inventory_code: OfficialInventoryCode,
    outcome: SourceCoverageOutcomeCode,
    disposition: SourceCoverageDisposition,
    *,
    isolated: bool,
) -> None:
    """Any failed required member blocks release and preserves exact accounting."""
    required_endpoints = [
        item.endpoint_id
        for item in load_hk_legislation_source_register().endpoints
        if item.source_id == _SOURCE_ID and item.complete_inventory_required
    ]
    failed_endpoint = required_endpoints[-1]
    transport = _InventoryTransport(
        unavailable_endpoint=(failed_endpoint if failure_mode == "unavailable_endpoint" else None),
        changed_endpoint=failed_endpoint if failure_mode == "changed_endpoint" else None,
        unsafe_endpoint=failed_endpoint if failure_mode == "unsafe_endpoint" else None,
    )
    activities, vault = _activities(transport)

    result = _capture(activities, _payload())

    assert result["code"] == inventory_code.value
    assert result["retained"] == 1
    assert result["failed"] == 1
    coverage = _coverage(result)
    assert coverage["outcome"] == outcome.value
    assert coverage["disposition"] == disposition.value
    assert coverage["release_blocking"] is True
    manifest = _manifest(result, vault)
    assert manifest["complete"] is False
    failed_members = [
        member for member in _objects(manifest["members"]) if member["evidence"] is None
    ]
    assert len(failed_members) == 1
    assert (failed_members[0]["isolated_response"] is not None) is isolated


@pytest.mark.parametrize(
    "payload",
    [
        {"source_id": _SOURCE_ID},
        {"source_id": _SOURCE_ID, "observation_cutoff": "2026-08-21"},
        {
            "source_id": _SOURCE_ID,
            "observation_cutoff": _CUTOFF,
            "unknown": True,
        },
        {
            "source_id": "HK-LEG-HKEL-CURRENT-DATA",
            "observation_cutoff": _CUTOFF,
        },
        {
            "source_id": _SOURCE_ID,
            "observation_cutoff": _CUTOFF,
            "prior_fingerprints": {_UNKNOWN_ENDPOINT: f"sha256:{'a' * 64}"},
        },
        {
            "source_id": _SOURCE_ID,
            "observation_cutoff": _CUTOFF,
            "prior_fingerprints": {"endpoint": b"not-json"},
        },
    ],
)
def test_invalid_inventory_instruction_fails_before_transport(payload: object) -> None:
    """Malformed or inapplicable instructions cannot perform a source call."""
    transport = _InventoryTransport()
    activities, _vault = _activities(transport)

    with pytest.raises(pipeline.AcquisitionPipelineError):
        activities.capture_inventory(_context(), payload)

    assert transport.calls == []
