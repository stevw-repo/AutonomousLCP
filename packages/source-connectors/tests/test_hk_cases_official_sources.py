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
    EndpointInvocationKind,
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


def test_register_freezes_all_roles_without_claiming_complete_admission() -> None:
    register = load_hk_cases_source_register()

    assert register.register_version == "2026-09-06.1"
    assert register.fingerprint == (
        "sha256:a697a7f7b9b1327169d368ebdef722ee71d6dae447057c8da2a502b5bcdbe13e"
    )
    assert tuple(source.source_id for source in register.sources) == tuple(
        sorted(HK_CASE_SOURCE_IDS)
    )
    assert len(register.endpoints) == 6
    assert not register.operationally_admitted
    assert register.access_boundary.forbidden_effects == (HK_CASE_SOURCE_ACCESS_FORBIDDEN_EFFECTS)
    assert all(source.blockers for source in register.sources)


def test_user_attested_authority_binds_exact_judiciary_and_hklii_endpoints() -> None:
    """Task 7 exposes only exact observed routes and keeps baseline gaps visible."""
    register = load_hk_cases_source_register()
    sources = {source.source_id: source for source in register.sources}

    assert sources["HK-CASE-HKLII-DISCOVERY"].rights_state is (
        PublisherRightsState.USER_ATTESTED_PERMISSION_DOCUMENT_PENDING
    )
    assert sources["HK-CASE-JUDICIARY-LRS-INVENTORY"].operational_state is (
        OfficialSourceState.PARTIALLY_CONFIGURED
    )
    assert "YEAR_QUERY_BINDING_AND_TRAVERSAL_PROOF_PENDING" not in (
        sources["HK-CASE-JUDICIARY-LRS-INVENTORY"].blockers
    )

    endpoints = {endpoint.name: endpoint for endpoint in register.endpoints}
    assert endpoints["JUDICIARY_CURRENT_JUDGMENTS"].url == (
        "https://legalref.judiciary.hk/lrs/common/index.jsp?target=newjudgments&lan=en"
    )
    assert endpoints["JUDICIARY_ALL_COURTS_RSS"].url == (
        "https://legalref.judiciary.hk/lrs/common/rss/newjudgments.all.xml"
    )
    assert endpoints["JUDICIARY_ADVANCED_YEAR_SEARCH"].url == (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "isadvsearch=1&stem=1&selall2=1&selallct=1"
    )
    assert endpoints["JUDICIARY_ADVANCED_YEAR_SEARCH"].version == "1.0.13"
    assert endpoints["JUDICIARY_DYNAMIC_JUDGMENT_DETAIL"].source_id == (
        "HK-CASE-JUDICIARY-JUDGMENT"
    )
    assert endpoints["JUDICIARY_DYNAMIC_JUDGMENT_DETAIL"].evidence_role == (
        "DYNAMIC_LISTING_DERIVED_JUDGMENT_LOCATOR_BOUNDARY"
    )
    assert endpoints["HKLII_CASES_DISCOVERY"].url == "https://www.hklii.hk/en/cases"
    for endpoint in endpoints.values():
        if endpoint.invocation_kind is EndpointInvocationKind.REDIRECT_TARGET_ONLY:
            continue
        source, resolved = register.resolve_endpoint(endpoint.endpoint_id, endpoint.version)
        assert resolved is endpoint
        assert source.source_id == endpoint.source_id


def test_judiciary_current_listing_uses_the_exact_session_entry_and_registered_final_target() -> (
    None
):
    """Direct final-JSP bootstrap must not replace the one published session entry."""
    register = load_hk_cases_source_register()
    endpoints = {endpoint.name: endpoint for endpoint in register.endpoints}

    entry = endpoints["JUDICIARY_CURRENT_JUDGMENTS"]
    assert entry.url == (
        "https://legalref.judiciary.hk/lrs/common/index.jsp?target=newjudgments&lan=en"
    )
    assert entry.methods == (HttpMethod.GET,)
    final = endpoints["JUDICIARY_CURRENT_JUDGMENTS_SESSION_TARGET"]
    assert final.endpoint_id == "sep_000000000000000000000000000000000000000000000205"
    assert final.url == "https://legalref.judiciary.hk/lrs/common/ju/newjudgments.jsp"
    assert final.methods == (HttpMethod.GET,)
    assert final.access_mode is EndpointAccessMode.DIRECT_HTTP
    assert final.enabled is True
    assert final.invocation_kind is EndpointInvocationKind.REDIRECT_TARGET_ONLY

    with pytest.raises(PermissionError, match="directly invoked"):
        register.resolve_endpoint(final.endpoint_id, final.version)

    assert (
        register.resolve_redirect_target(
            entry_endpoint_id=entry.endpoint_id,
            method=HttpMethod.GET,
            target_endpoint_id=final.endpoint_id,
        )
        is final
    )

    for entry_endpoint_id, method, target_endpoint_id in (
        (entry.endpoint_id, HttpMethod.HEAD, final.endpoint_id),
        (entry.endpoint_id, HttpMethod.GET, entry.endpoint_id),
        ("sep_000000000000000000000000000000000000000000000203", HttpMethod.GET, final.endpoint_id),
    ):
        with pytest.raises(PermissionError, match="redirect transition"):
            register.resolve_redirect_target(
                entry_endpoint_id=entry_endpoint_id,
                method=method,
                target_endpoint_id=target_endpoint_id,
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
    assert package_manifest["package_fingerprint"] == (
        "sha256:ce81651ac8c7952a8c3a0099ba68f7085a179d9cb75a2b420b25cbe4e1cce329"
    )
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


def test_unknown_endpoint_cannot_resolve_or_reach_transport() -> None:
    register = load_hk_cases_source_register()

    with pytest.raises(LookupError, match="unavailable"):
        register.resolve_endpoint(
            "sep_000000000000000000000000000000000000000000000299",
            "1.0.0",
        )


def test_shared_endpoint_contract_accepts_cases_only_as_a_disabled_future_contract() -> None:
    endpoint = OfficialEndpointContract(
        endpoint_id="sep_000000000000000000000000000000000000000000000299",
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
        replace(source, endpoint_ids=(*source.endpoint_ids, endpoint.endpoint_id))
        if source is lrs
        else source
        for source in register.sources
    )
    with pytest.raises(ValueError, match="every endpoint"):
        replace(register, sources=sources, endpoints=(replace(endpoint, enabled=True),))


def test_source_authority_or_operational_drift_fails_closed() -> None:
    register = load_hk_cases_source_register()
    lrs = next(
        source
        for source in register.sources
        if source.source_id == "HK-CASE-JUDICIARY-LRS-INVENTORY"
    )

    with pytest.raises(ValueError, match="authority"):
        replace(lrs, operational_state=OfficialSourceState.CONFIGURED)
    with pytest.raises(ValueError, match="authority"):
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
