"""Strict fail-closed Hong Kong Cases source-register conformance."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import SourceOutageImpact
from asklegal_source_connectors import (
    HK_CASE_SOURCE_ACCESS_FORBIDDEN_EFFECTS,
    HK_CASE_SOURCE_IDS,
    EndpointAccessMode,
    HttpMethod,
    OfficialEndpointContract,
    OfficialSourceState,
    PublisherRightsState,
    SignalUse,
    load_hk_cases_source_register,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REGISTER_PATH = (
    REPOSITORY_ROOT
    / "packages/source-connectors/src/asklegal_source_connectors/hk_cases_source_register.json"
)
PACKAGE_ROOT = REPOSITORY_ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_cases_package"


def _json(path: Path) -> dict[str, JsonValue]:
    raw = path.read_bytes()
    document = parse_json_bytes(raw, max_bytes=len(raw))
    assert isinstance(document, dict)
    return document


def test_register_freezes_all_roles_without_claiming_endpoint_admission() -> None:
    register = load_hk_cases_source_register()

    assert register.fingerprint == (
        "sha256:c1c22ab94bb7ebdc95b6597c74856c430572a3887900deb1d57645fa186c33e4"
    )
    assert tuple(source.source_id for source in register.sources) == tuple(
        sorted(HK_CASE_SOURCE_IDS)
    )
    assert register.endpoints == ()
    assert not register.operationally_admitted
    assert register.access_boundary.forbidden_effects == (HK_CASE_SOURCE_ACCESS_FORBIDDEN_EFFECTS)
    assert all(
        source.operational_state is OfficialSourceState.BLOCKED
        and source.rights_state is PublisherRightsState.UNVERIFIED
        and source.endpoint_ids == ()
        and source.blockers
        for source in register.sources
    )


def test_package_and_access_register_freeze_the_same_fact_authority() -> None:
    register = load_hk_cases_source_register()
    source_universe = _json(PACKAGE_ROOT / "sources/source-universe.json")
    raw_sources = source_universe["sources"]
    assert isinstance(raw_sources, list)
    package_sources: dict[str, dict[str, JsonValue]] = {}
    for raw_source in raw_sources:
        assert isinstance(raw_source, dict)
        source_id = raw_source.get("source_id")
        assert isinstance(source_id, str)
        package_sources[source_id] = raw_source

    assert frozenset(package_sources) == HK_CASE_SOURCE_IDS
    for source in register.sources:
        package_source = package_sources[source.source_id]
        assert package_source["permitted_use"] == source.fact_authority
        assert package_source["completeness_rule"] == source.completeness_authority
    package_manifest = _json(PACKAGE_ROOT / "package.json")
    contract_locks = package_manifest["contract_locks"]
    assert isinstance(contract_locks, list)
    assert register.fingerprint in contract_locks


def test_outage_authority_keeps_inventory_and_discovery_distinct() -> None:
    register = load_hk_cases_source_register()
    sources = {source.source_id: source for source in register.sources}

    assert sources["HK-CASE-JUDICIARY-LRS-INVENTORY"].outage_impact is (
        SourceOutageImpact.RELEASE_BLOCKING
    )
    assert sources["HK-CASE-JUDICIARY-JUDGMENT"].outage_impact is (
        SourceOutageImpact.AFFECTED_WORK_BLOCKING
    )
    assert sources["HK-CASE-HKLII-DISCOVERY"].outage_impact is (SourceOutageImpact.NONBLOCKING)
    assert sources["HK-CASE-JUDICIARY-TRANSLATION"].outage_impact is (
        SourceOutageImpact.NONBLOCKING
    )


def test_no_endpoint_can_resolve_or_reach_transport() -> None:
    register = load_hk_cases_source_register()

    with pytest.raises(LookupError, match="unavailable"):
        register.resolve_endpoint(
            "sep_000000000000000000000000000000000000000000000201",
            "1.0.0",
        )


def test_shared_endpoint_contract_accepts_cases_only_as_a_disabled_future_contract() -> None:
    endpoint = OfficialEndpointContract(
        endpoint_id="sep_000000000000000000000000000000000000000000000201",
        source_id="HK-CASE-JUDICIARY-LRS-INVENTORY",
        version="1.0.0",
        name="TEST_ONLY_DISABLED_CASES_ENDPOINT",
        url="https://example.invalid/cases",
        access_mode=EndpointAccessMode.DIRECT_HTTP,
        methods=(HttpMethod.GET,),
        media_types=("text/html",),
        max_bytes=1_000,
        complete_inventory_required=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        proves_no_change=False,
        evidence_role="TEST_ONLY_NO_SOURCE_AUTHORITY",
        enabled=False,
    )

    assert not endpoint.enabled
    register = load_hk_cases_source_register()
    lrs = next(
        source
        for source in register.sources
        if source.source_id == "HK-CASE-JUDICIARY-LRS-INVENTORY"
    )
    sources = tuple(
        replace(source, endpoint_ids=(endpoint.endpoint_id,)) if source is lrs else source
        for source in register.sources
    )
    with pytest.raises(ValueError, match="no Cases endpoint"):
        replace(register, sources=sources, endpoints=(replace(endpoint, enabled=True),))


def test_source_authority_or_operational_drift_fails_closed() -> None:
    register = load_hk_cases_source_register()
    lrs = next(
        source
        for source in register.sources
        if source.source_id == "HK-CASE-JUDICIARY-LRS-INVENTORY"
    )

    with pytest.raises(ValueError, match="blocked"):
        replace(lrs, operational_state=OfficialSourceState.CONFIGURED)
    with pytest.raises(ValueError, match="unverified"):
        replace(lrs, rights_state=PublisherRightsState.LEGAL_TEAM_CLEARED)
    with pytest.raises(ValueError, match="authority drift"):
        replace(
            register,
            sources=tuple(
                replace(source, fact_authority="DISCOVERY_ONLY") if source is lrs else source
                for source in register.sources
            ),
        )


def test_register_fingerprint_and_closed_shape_detect_tampering(tmp_path: Path) -> None:
    document = _json(REGISTER_PATH)
    document["register_version"] = "2099-01-01.1"
    tampered = tmp_path / "hk-cases-source-register.json"
    tampered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint"):
        load_hk_cases_source_register(tampered)

    document = _json(REGISTER_PATH)
    document["unknown"] = True
    document["fingerprint"] = "PENDING"
    raw_projection = dict(document)
    raw_projection.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(raw_projection))).hexdigest()
    )
    unknown = tmp_path / "unknown-field.json"
    unknown.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown or missing"):
        load_hk_cases_source_register(unknown)
