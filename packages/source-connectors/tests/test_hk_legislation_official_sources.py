"""Complete fail-closed Hong Kong Legislation official-source register tests."""

from dataclasses import replace
from json import dumps
from pathlib import Path

import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_source_connectors import (
    HK_LEGISLATION_SOURCE_IDS,
    OfficialSourceState,
    PublisherRightsState,
    SignalUse,
    load_hk_legislation_source_register,
)


def _register_path() -> Path:
    return (
        Path(__file__).parents[1]
        / "src/asklegal_source_connectors/hk_legislation_source_register.json"
    )


def test_register_binds_the_complete_14_role_universe_and_stays_fail_closed() -> None:
    register = load_hk_legislation_source_register()

    assert len(register.sources) == 14
    assert len(register.endpoints) == 78
    assert {item.source_id for item in register.sources} == HK_LEGISLATION_SOURCE_IDS
    assert set(register.authorization.source_ids) == HK_LEGISLATION_SOURCE_IDS
    assert register.authorization.rss_policy == "DISCOVERY_OR_CHANGE_SIGNAL_ONLY"
    assert register.status == "PARTIALLY_CONFIGURED_FAIL_CLOSED"
    assert register.operationally_admitted is False
    assert register.fingerprint == (
        "sha256:2bbad109451b9b47c63179c8b527934239dac399989087ed74c95a00bbeedf0d"
    )
    assert register.legal_clearance.authority == "ASKLEGAL_LEGAL_TEAM"
    assert register.legal_clearance.reported_by == "PROJECT_USER"
    assert set(register.legal_clearance.source_ids) == HK_LEGISLATION_SOURCE_IDS


def test_technically_complete_basic_law_role_joins_the_configured_sources() -> None:
    register = load_hk_legislation_source_register()

    assert register.configured_source_ids == (
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-PAST-DATA",
        "HK-LEG-HKEL-PAST-INVENTORY",
    )
    assert register.partially_configured_source_ids == (
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        "HK-LEG-HKEL-VERIFIED-COPIES",
        )
    assert len(register.blocked_source_ids) == 2
    configured = {
        item.source_id: item
        for item in register.sources
        if item.operational_state is OfficialSourceState.CONFIGURED
    }
    assert configured["HK-LEG-BASIC-LAW-PORTAL"].rights_state is (
        PublisherRightsState.LEGAL_TEAM_CLEARED
    )
    assert all(not item.blockers for item in configured.values())
    assert all(
        endpoint.enabled for endpoint in register.endpoints if endpoint.source_id in configured
    )
    assert all(
        not endpoint.enabled
        for endpoint in register.endpoints
        if endpoint.source_id in register.blocked_source_ids
    )
    for source_id in register.partially_configured_source_ids:
        enabled = tuple(
            endpoint.enabled for endpoint in register.endpoints if endpoint.source_id == source_id
        )
        assert any(enabled)
        assert not all(enabled)


def test_every_rss_endpoint_is_discovery_only_and_never_proves_no_change() -> None:
    register = load_hk_legislation_source_register()
    rss = tuple(
        endpoint
        for endpoint in register.endpoints
        if any("rss" in media_type for media_type in endpoint.media_types)
    )

    assert {item.url for item in rss} == {
        "https://data.gov.hk/filestore/feeds/data_rss_en.xml",
        "https://www.elegislation.gov.hk/editorialrecord!en.rss.xml",
    }
    assert all(item.signal_use is SignalUse.DISCOVERY_ONLY for item in rss)
    assert all(not item.complete_inventory_required for item in rss)
    assert all(not item.proves_no_change for item in rss)


def test_retired_roles_are_out_of_scope_rather_than_blocked() -> None:
    """A role we chose not to pursue must not masquerade as one we cannot reach.

    The two NPC roles are mainland sources the project does not need, and the
    Gazette archive needs a physical holding procedure nobody will carry out.
    Recording these as BLOCKED would imply work is pending; OUT_OF_SCOPE_V1 says
    the decision was taken.
    """
    register = load_hk_legislation_source_register()
    retired = {
        item.source_id
        for item in register.sources
        if item.operational_state is OfficialSourceState.OUT_OF_SCOPE_V1
    }

    assert retired == {
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
        "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
        "HK-LEG-OFFICIAL-GAZETTE-ARCHIVE",
    }
    assert all(
        not endpoint.enabled
        for endpoint in register.endpoints
        if endpoint.source_id in retired
    )
    assert all(
        item.blockers
        for item in register.sources
        if item.operational_state is OfficialSourceState.OUT_OF_SCOPE_V1
    )


def test_verified_copy_inventory_is_direct_but_item_copy_paths_stay_disabled() -> None:
    register = load_hk_legislation_source_register()
    endpoints = tuple(
        item for item in register.endpoints if item.source_id == "HK-LEG-HKEL-VERIFIED-COPIES"
    )

    inventory = next(item for item in endpoints if item.url.endswith("?_lang=en"))
    assert inventory.enabled
    assert inventory.complete_inventory_required
    assert inventory.signal_use is SignalUse.COMPLETE_INVENTORY
    assert all(not item.enabled for item in endpoints if item is not inventory)


def test_all_enumerated_data_gov_resources_are_bound_exactly_once() -> None:
    register = load_hk_legislation_source_register()
    data_resources = {
        endpoint.url
        for endpoint in register.endpoints
        if endpoint.url.startswith("https://resource.data.one.gov.hk/doj/data/")
    }

    assert len(data_resources) == 39
    assert {
        "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_en.xml",
        "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_zh-Hant.xml",
        "https://resource.data.one.gov.hk/doj/data/hkel_c_instruments_en.zip",
        "https://resource.data.one.gov.hk/doj/data/hkel_c_instruments_zh-Hant.zip",
        "https://resource.data.one.gov.hk/doj/data/hkel_list_p_all_en.xml",
        "https://resource.data.one.gov.hk/doj/data/hkel_list_p_all_zh-Hant.xml",
        "https://resource.data.one.gov.hk/doj/data/hkel_p_instruments_en.zip",
        "https://resource.data.one.gov.hk/doj/data/hkel_p_instruments_zh-Hant.zip",
    }.issubset(data_resources)
    assert (
        sum(
            endpoint.url.startswith("https://resource.data.one.gov.hk/doj/data/")
            for endpoint in register.endpoints
        )
        == 39
    )


def test_legal_clearance_does_not_rewrite_observed_publisher_notices() -> None:
    register = load_hk_legislation_source_register()
    sources = {item.source_id: item for item in register.sources}
    rights = {item.publisher: item for item in register.rights_evidence}

    assert sources["HK-LEG-GLD-EGAZETTE"].rights_state is (PublisherRightsState.LEGAL_TEAM_CLEARED)
    assert sources["HK-LEG-BASIC-LAW-PORTAL"].rights_state is (
        PublisherRightsState.LEGAL_TEAM_CLEARED
    )
    assert sources["HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS"].rights_state is (
        PublisherRightsState.LEGAL_TEAM_CLEARED
    )
    assert sources["HK-LEG-NPC-NATIONAL-LAWS-DATABASE"].rights_state is (
        PublisherRightsState.LEGAL_TEAM_CLEARED
    )
    assert sources["HK-LEG-OFFICIAL-GAZETTE-ARCHIVE"].rights_state is (
        PublisherRightsState.LEGAL_TEAM_CLEARED
    )
    assert rights["Government Logistics Department e-Gazette"].conclusion is (
        PublisherRightsState.PRIOR_WRITTEN_AUTHORIZATION_REQUIRED
    )
    assert rights["National People's Congress"].conclusion is (PublisherRightsState.UNVERIFIED)
    assert sources["HK-LEG-BASIC-LAW-PORTAL"].operational_state is (OfficialSourceState.CONFIGURED)
    assert sources["HK-LEG-GLD-EGAZETTE"].blockers == ("RENDERED_SESSION_TRANSPORT_REQUIRED",)


def test_register_fingerprint_detects_any_checked_in_contract_change(tmp_path: Path) -> None:
    raw = _register_path().read_bytes()
    document = parse_json_bytes(raw, max_bytes=1_000_000)
    assert isinstance(document, dict)
    document["register_version"] = "2099-01-01.1"
    tampered = tmp_path / "source-register.json"
    tampered.write_text(dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint"):
        load_hk_legislation_source_register(tampered)


def test_discovery_signal_and_rights_guards_fail_closed() -> None:
    register = load_hk_legislation_source_register()
    rss = next(
        item for item in register.endpoints if item.url.endswith("editorialrecord!en.rss.xml")
    )
    with pytest.raises(ValueError, match="discovery"):
        replace(rss, complete_inventory_required=True)

    blocked = next(item for item in register.sources if item.source_id == "HK-LEG-GLD-EGAZETTE")
    with pytest.raises(ValueError, match="admitted rights"):
        replace(
            blocked,
            rights_state=PublisherRightsState.PRIOR_WRITTEN_AUTHORIZATION_REQUIRED,
            operational_state=OfficialSourceState.CONFIGURED,
            blockers=(),
        )
