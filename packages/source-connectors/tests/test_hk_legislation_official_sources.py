"""Complete fail-closed Hong Kong Legislation official-source register tests."""

from dataclasses import replace
from json import dumps
from pathlib import Path
from urllib.parse import urlencode

import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_source_connectors import (
    CAPABILITY_CLAIM,
    HK_LEGISLATION_SOURCE_IDS,
    EndpointAccessMode,
    HttpMethod,
    OfficialSourceState,
    PublisherRightsState,
    SignalUse,
    SourceOutageImpact,
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
    assert len(register.endpoints) == 104
    assert {item.source_id for item in register.sources} == HK_LEGISLATION_SOURCE_IDS
    assert set(register.authorization.source_ids) == HK_LEGISLATION_SOURCE_IDS
    assert register.authorization.rss_policy == "DISCOVERY_OR_CHANGE_SIGNAL_ONLY"
    assert register.schema_version == "1.1.0"
    assert register.register_version == "2026-08-28.3"
    assert register.effective_date == "2026-08-21"
    assert register.status == "PARTIALLY_CONFIGURED_FAIL_CLOSED"
    assert register.operationally_admitted is False
    assert register.fingerprint == (
        "sha256:be2dc02b4ef087ac2357ad96dc05be5a36127e2a7f395bffe5b7a98f6408de67"
    )
    assert register.legal_clearance.authority == "ASKLEGAL_LEGAL_TEAM"
    assert register.legal_clearance.reported_by == "PROJECT_USER"
    assert set(register.legal_clearance.source_ids) == HK_LEGISLATION_SOURCE_IDS
    assert {item.version for item in register.sources} == {"1.1.0", "1.2.0", "1.3.0"}
    assert {item.version for item in register.endpoints} == {"1.0.0", "1.1.0"}


def test_publication_specifications_registers_the_shared_direct_client_check() -> None:
    """The current HKeL session coordinate is a profile-bound exact GET."""
    register = load_hk_legislation_source_register()
    source = next(
        item
        for item in register.sources
        if item.source_id == "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS"
    )
    endpoint = next(
        item
        for item in register.endpoints
        if item.endpoint_id == "sep_000000000000000000000000000000000000000000000056"
    )

    assert source.version == "1.3.0"
    assert endpoint.endpoint_id in source.endpoint_ids
    assert endpoint.url == (
        "https://www.elegislation.gov.hk/client-check?" + urlencode(CAPABILITY_CLAIM)
    )
    assert endpoint.access_mode is EndpointAccessMode.BROWSER_SESSION
    assert endpoint.methods == (HttpMethod.GET,)
    assert endpoint.evidence_role == "SESSION_CAPABILITY_CHECK"
    assert endpoint.enabled is True


def test_every_source_preserves_its_normalized_outage_impact() -> None:
    """Bind every role to its ADR 0032 base impact without upgrading discovery."""
    actual = {
        item.source_id: item.outage_impact for item in load_hk_legislation_source_register().sources
    }

    assert actual == {
        "HK-LEG-BASIC-LAW-PORTAL": SourceOutageImpact.NONBLOCKING,
        "HK-LEG-GLD-EGAZETTE": SourceOutageImpact.RELEASE_BLOCKING,
        "HK-LEG-HKEL-ASSISTED-COPIES": SourceOutageImpact.AFFECTED_WORK_BLOCKING,
        "HK-LEG-HKEL-CURRENT-DATA": SourceOutageImpact.AFFECTED_WORK_BLOCKING,
        "HK-LEG-HKEL-CURRENT-INVENTORY": SourceOutageImpact.RELEASE_BLOCKING,
        "HK-LEG-HKEL-EDITORIAL-RECORDS": SourceOutageImpact.AFFECTED_WORK_BLOCKING,
        "HK-LEG-HKEL-GAZETTE-BACKCAPTURE": SourceOutageImpact.NONBLOCKING,
        "HK-LEG-HKEL-PAST-DATA": SourceOutageImpact.AFFECTED_WORK_BLOCKING,
        "HK-LEG-HKEL-PAST-INVENTORY": SourceOutageImpact.AFFECTED_WORK_BLOCKING,
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS": (SourceOutageImpact.AFFECTED_WORK_BLOCKING),
        "HK-LEG-HKEL-VERIFIED-COPIES": SourceOutageImpact.AFFECTED_WORK_BLOCKING,
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE": SourceOutageImpact.AFFECTED_WORK_BLOCKING,
        "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS": (SourceOutageImpact.AFFECTED_WORK_BLOCKING),
        "HK-LEG-OFFICIAL-GAZETTE-ARCHIVE": SourceOutageImpact.AFFECTED_WORK_BLOCKING,
    }


def test_basic_law_complete_membership_contract_is_configured() -> None:
    register = load_hk_legislation_source_register()

    assert register.configured_source_ids == (
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PAST-DATA",
        "HK-LEG-HKEL-PAST-INVENTORY",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
    )
    assert register.partially_configured_source_ids == (
        "HK-LEG-GLD-EGAZETTE",
        # Gazette back-capture joined once its grid, pagination, locator, and PDF
        # address were observed and implemented; only the completeness rule and
        # its date-window consequence remain.
        "HK-LEG-HKEL-GAZETTE-BACKCAPTURE",
        "HK-LEG-HKEL-VERIFIED-COPIES",
    )
    assert len(register.blocked_source_ids) == 1
    configured = {
        item.source_id: item
        for item in register.sources
        if item.operational_state is OfficialSourceState.CONFIGURED
    }
    sources = {item.source_id: item for item in register.sources}
    assert sources["HK-LEG-BASIC-LAW-PORTAL"].rights_state is (
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
        not endpoint.enabled for endpoint in register.endpoints if endpoint.source_id in retired
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
    assert {item.endpoint_id for item in endpoints if item.enabled} == {
        "sep_000000000000000000000000000000000000000000000016",
        inventory.endpoint_id,
    }
    assert all(
        not item.enabled
        for item in endpoints
        if item.endpoint_id
        in {
            "sep_000000000000000000000000000000000000000000000017",
            "sep_000000000000000000000000000000000000000000000018",
        }
    )


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
    assert sources["HK-LEG-BASIC-LAW-PORTAL"].operational_state is OfficialSourceState.CONFIGURED
    assert sources["HK-LEG-BASIC-LAW-PORTAL"].blockers == ()
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
