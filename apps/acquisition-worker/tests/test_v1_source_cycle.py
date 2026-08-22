"""Complete periodic source-cycle planning, attempts, and manifest-last accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import asklegal_acquisition_worker.v1_pipeline as pipeline
import pytest
from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure
from asklegal_application_runtime import CredentialMaterial
from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import ExactObjectReference, LocalImmutableVault, VaultName
from asklegal_source_connectors import (
    HttpMethod,
    OfficialEndpointContract,
    OfficialHttpConnector,
    OfficialTransportResponse,
    load_hk_legislation_source_register,
)

_CUTOFF = "2026-08-21T12:00:00Z"
_CURRENT = "HK-LEG-HKEL-CURRENT-INVENTORY"

type JsonObject = dict[str, JsonValue]


def _empty_calls() -> list[str]:
    return []


@dataclass(slots=True)
class _Transport:
    calls: list[str] = field(default_factory=_empty_calls)

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
        body = f"<Listing endpoint='{endpoint.endpoint_id}'/>".encode()
        return OfficialTransportResponse(
            status_code=200,
            final_url=endpoint.url,
            media_type="application/xml",
            character_encoding="utf-8",
            body=body,
            declared_length=len(body),
            truncated=False,
        )


def _context() -> ActivityContext:
    return ActivityContext("source-cycle-test", 1)


def _object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def _objects(value: JsonValue) -> list[JsonObject]:
    assert isinstance(value, list)
    return [_object(item) for item in value]


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _integer(value: JsonValue) -> int:
    assert type(value) is int
    return value


def _activities(
    tmp_path: Path,
) -> tuple[pipeline.AcquisitionActivities, _Transport, LocalImmutableVault]:
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    infrastructure = V1AcquisitionInfrastructure.__new__(V1AcquisitionInfrastructure)
    object.__setattr__(
        infrastructure,
        "source_egress_proxy_credential",
        CredentialMaterial(b"http://proxy.invalid:3128"),
    )
    object.__setattr__(infrastructure, "primary_vault", vault)
    activities = pipeline.AcquisitionActivities(infrastructure)
    transport = _Transport()
    connector = OfficialHttpConnector(load_hk_legislation_source_register(), transport)
    object.__setattr__(activities, "_connector", connector)
    return activities, transport, vault


def _cycle_payload() -> dict[str, object]:
    return {
        "cycle": "FULL_PERIODIC",
        "observation_cutoff": _CUTOFF,
        "prior_fingerprints": {},
    }


def _reference(result: JsonObject) -> JsonObject:
    coverage = _object(result["coverage_report"])
    return {
        field: coverage[field]
        for field in ("byte_length", "fingerprint", "logical_key", "vault", "version_id")
    }


def _run_attempts(
    activities: pipeline.AcquisitionActivities,
    plan: JsonObject,
) -> tuple[list[JsonObject], list[JsonObject]]:
    results: list[JsonObject] = []
    references: list[JsonObject] = []
    for requirement in _objects(plan["requirements"]):
        source_id = _text(requirement["source_id"])
        result = _object(
            checked_json_value(
                activities.capture_due_source(
                    _context(),
                    {
                        "cycle": "FULL_PERIODIC",
                        "observation_cutoff": _CUTOFF,
                        "prior_fingerprints": {},
                        "source_id": source_id,
                    },
                )
            )
        )
        results.append(result)
        references.append(_reference(result))
    return results, references


def _assemble_payload(plan: JsonObject, references: list[JsonObject]) -> dict[str, object]:
    return {
        "cycle": "FULL_PERIODIC",
        "observation_cutoff": _CUTOFF,
        "report_references": references,
        "requirements": plan["requirements"],
        "source_register_fingerprint": plan["source_register_fingerprint"],
    }


def test_full_periodic_cycle_accounts_every_due_source_and_blocks_known_gaps(
    tmp_path: Path,
) -> None:
    """All five in-scope periodic roles receive exact durable accounting."""
    activities, transport, vault = _activities(tmp_path)
    plan = _object(checked_json_value(activities.plan_source_cycle(_context(), _cycle_payload())))
    results, references = _run_attempts(activities, plan)

    cycle = _object(
        checked_json_value(
            activities.assemble_source_cycle(
                _context(),
                _assemble_payload(plan, references),
            )
        )
    )

    assert len(_objects(plan["requirements"])) == 5
    assert len(results) == 5
    assert cycle["accounting_complete"] is True
    assert cycle["release_blocking"] is True
    assert cycle["missing_source_ids"] == []
    assert cycle["gap_source_ids"] == [
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
    ]
    current = next(item for item in results if item["source_id"] == _CURRENT)
    assert current["code"] == "COMPLETE_CAPTURED"
    assert len(transport.calls) == 2

    reference = ExactObjectReference(
        VaultName(_text(cycle["vault"])),
        _text(cycle["logical_key"]),
        _text(cycle["version_id"]),
        _text(cycle["fingerprint"]),
        _integer(cycle["byte_length"]),
    )
    document = parse_json_bytes(vault.read_exact(reference), max_bytes=65_536)
    assert isinstance(document, dict)
    source_reports = document["source_reports"]
    assert isinstance(source_reports, list)
    assert len(source_reports) == 5

    replayed = _object(
        checked_json_value(
            activities.assemble_source_cycle(
                _context(),
                _assemble_payload(plan, references),
            )
        )
    )
    assert replayed["created"] is False
    assert replayed["coverage_status_binding"] == cycle["coverage_status_binding"]


def test_missing_release_required_report_remains_visible_and_release_blocking(
    tmp_path: Path,
) -> None:
    """A lost required activity cannot disappear from the final cycle result."""
    activities, _transport, _vault = _activities(tmp_path)
    plan = _object(checked_json_value(activities.plan_source_cycle(_context(), _cycle_payload())))
    _results, references = _run_attempts(activities, plan)
    references = [
        reference
        for reference in references
        if "/hk-leg-hkel-current-inventory/" not in _text(reference["logical_key"])
    ]

    cycle = _object(
        checked_json_value(
            activities.assemble_source_cycle(
                _context(),
                _assemble_payload(plan, references),
            )
        )
    )

    assert cycle["accounting_complete"] is False
    assert cycle["missing_source_ids"] == [_CURRENT]
    assert cycle["release_blocking"] is True


def test_caller_cannot_add_an_on_demand_source_or_change_the_planned_requirements(
    tmp_path: Path,
) -> None:
    """The scheduler payload cannot weaken or broaden the accepted due set."""
    activities, transport, _vault = _activities(tmp_path)
    payload = _cycle_payload()
    payload["prior_fingerprints"] = {"HK-LEG-HKEL-CURRENT-DATA": {}}

    with pytest.raises(pipeline.AcquisitionPipelineError, match="outside its due set"):
        activities.plan_source_cycle(_context(), payload)

    plan = _object(checked_json_value(activities.plan_source_cycle(_context(), _cycle_payload())))
    _results, references = _run_attempts(activities, plan)
    assembly = _assemble_payload(plan, references)
    assembly["requirements"] = _objects(plan["requirements"])[:-1]
    with pytest.raises(pipeline.AcquisitionPipelineError, match="drifted from the register"):
        activities.assemble_source_cycle(
            _context(),
            assembly,
        )
    assert len(transport.calls) == 2
