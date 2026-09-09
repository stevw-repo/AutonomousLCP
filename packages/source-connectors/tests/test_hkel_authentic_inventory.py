"""Authentic HKeL DATA.GOV.HK current-inventory reconciliation."""

from __future__ import annotations

import pytest
from asklegal_source_connectors.basic_law_authentic import (
    parse_historical_basic_law_root_membership,
    require_basic_law_member_url,
)
from asklegal_source_connectors.hkel_authentic import (
    parse_hkel_client_configuration_form,
    parse_hkel_current_inventory_xml,
    parse_hkel_dataset_catalogue,
    reconcile_hkel_current_inventories,
    validate_hkel_policy_pages,
)


def test_bilingual_current_inventory_reconciles_exact_chapter_membership() -> None:
    """English and Traditional Chinese XML must enumerate the same unique universe."""
    english = parse_hkel_current_inventory_xml(
        b'<Listing lang="en" pointOfTime="c" legislationType="ALL"><DataSet>'
        b'<DataResource url="https://resource.data.one.gov.hk/doj/data/en.zip" />'
        b"</DataSet><Chapter><CapNo>1</CapNo>"
        b"<ChapterTitleEnglish>Public Finance Ordinance</ChapterTitleEnglish></Chapter>"
        b"<Chapter><CapNo>1A</CapNo></Chapter></Listing>",
        language="en",
    )
    chinese = parse_hkel_current_inventory_xml(
        b'<Listing lang="zh-Hant" pointOfTime="c" legislationType="ALL"><DataSet>'
        b'<DataResource url="https://resource.data.one.gov.hk/doj/data/zh-Hant.zip" />'
        b"</DataSet><Chapter><CapNo>1A</CapNo></Chapter>"
        b"<Chapter><CapNo>1</CapNo></Chapter></Listing>",
        language="zh-Hant",
    )

    inventory = reconcile_hkel_current_inventories(english, chinese)

    assert inventory.complete
    assert inventory.chapter_ids == ("1", "1A")
    assert inventory.required_data_endpoint_ids == (
        "sep_00000000000000000000000000000000000000000000000a",
        "sep_00000000000000000000000000000000000000000000000b",
        "sep_00000000000000000000000000000000000000000000000c",
        "sep_00000000000000000000000000000000000000000000000d",
        "sep_00000000000000000000000000000000000000000000000e",
        "sep_00000000000000000000000000000000000000000000000f",
        "sep_000000000000000000000000000000000000000000000010",
        "sep_000000000000000000000000000000000000000000000011",
        "sep_000000000000000000000000000000000000000000000012",
        "sep_000000000000000000000000000000000000000000000013",
        "sep_000000000000000000000000000000000000000000000014",
        "sep_000000000000000000000000000000000000000000000015",
    )


def test_current_inventory_rejects_entity_duplicate_and_bilingual_mismatch() -> None:
    """Unsafe XML and divergent membership remain fail-visible."""
    with pytest.raises(ValueError, match="HKEL_INVENTORY_UNSAFE_XML"):
        parse_hkel_current_inventory_xml(
            b'<!DOCTYPE x [<!ENTITY y "1">]><Listing lang="en" pointOfTime="c" '
            b'legislationType="ALL"><Chapter>'
            b"<CapNo>&y;</CapNo></Chapter></Listing>",
            language="en",
        )
    with pytest.raises(ValueError, match="HKEL_INVENTORY_DUPLICATE_CHAPTER"):
        parse_hkel_current_inventory_xml(
            b'<Listing lang="en" pointOfTime="c" legislationType="ALL">'
            b"<Chapter><CapNo>1</CapNo></Chapter>"
            b"<Chapter><CapNo>1</CapNo></Chapter></Listing>",
            language="en",
        )
    english = parse_hkel_current_inventory_xml(
        b'<Listing lang="en" pointOfTime="c" legislationType="ALL">'
        b"<Chapter><CapNo>1</CapNo></Chapter></Listing>",
        language="en",
    )
    chinese = parse_hkel_current_inventory_xml(
        b'<Listing lang="zh-Hant" pointOfTime="c" legislationType="ALL">'
        b"<Chapter><CapNo>2</CapNo></Chapter></Listing>",
        language="zh-Hant",
    )
    with pytest.raises(ValueError, match="HKEL_BILINGUAL_INVENTORY_MISMATCH"):
        reconcile_hkel_current_inventories(english, chinese)

    with pytest.raises(ValueError, match="HKEL_INVENTORY_IDENTITY_INVALID"):
        parse_hkel_current_inventory_xml(
            b'<Listing lang="zh-Hant" pointOfTime="c" legislationType="ALL">'
            b"<Chapter><CapNo>1</CapNo></Chapter></Listing>",
            language="en",
        )


def test_data_catalogue_and_configured_session_contracts_are_exact_and_secret_free() -> None:
    """Publisher resources and the narrow CSRF form bind execution without leaking its token."""
    catalogue = parse_hkel_dataset_catalogue(
        b'{"success":true,"result":{"name":"hkel-current","resources":'
        b'[{"url":"https://resource.data.one.gov.hk/a.xml"},'
        b'{"url":"https://resource.data.one.gov.hk/b.zip"}]}}',
        expected_dataset_name="hkel-current",
        required_urls=(
            "https://resource.data.one.gov.hk/a.xml",
            "https://resource.data.one.gov.hk/b.zip",
        ),
    )
    assert catalogue.declared_urls == (
        "https://resource.data.one.gov.hk/a.xml",
        "https://resource.data.one.gov.hk/b.zip",
    )

    configuration = parse_hkel_client_configuration_form(
        b"""<form name="clientConfigForm" method="post"
        action="/checkconfig/submitClientConfig.do">
        <input type="hidden" name="applicationId" value="RA001">
        <input type="hidden" name="branchCode" value="hkel">
        <input type="hidden" name="jvmVendor" value="publisher-vendor">
        <input type="hidden" name="jvmVersion" value="publisher-version">
        <input type="hidden" name="javascriptEnabled" value="false">
        <input type="hidden" name="cookieEnabled" value="false">
        <input type="hidden" name="appletLoadFailed" value="false">
        <input type="hidden" name="isIpv4Verified" value="false">
        <input type="hidden" name="isIpv6Verified" value="false">
        <input type="hidden" name="language" value="en">
        <input type="hidden" name="country" value="HK">
        <input type="hidden" name="_CSRF_TOKEN" value="site-secret">
        </form>""",
        page_url=(
            "https://www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?applicationId=RA001"
        ),
    )
    assert configuration.action_url == (
        "https://www.elegislation.gov.hk/checkconfig/submitClientConfig.do"
    )
    assert configuration.field_names == (
        "_CSRF_TOKEN",
        "appletLoadFailed",
        "applicationId",
        "branchCode",
        "cookieEnabled",
        "country",
        "isIpv4Verified",
        "isIpv6Verified",
        "javascriptEnabled",
        "jvmVendor",
        "jvmVersion",
        "language",
    )
    assert "site-secret" not in repr(configuration)
    assert "publisher-vendor" not in repr(configuration)


@pytest.mark.parametrize(
    "mutation",
    [
        '<input type="hidden" name="branchCode" value="duplicate">',
        '<input type="hidden" name="unknownCapability" value="true">',
        '<input type="password" name="branchCode" value="hkel">',
        '<button name="branchCode" value="hkel">submit</button>',
    ],
)
def test_current_configuration_form_rejects_duplicate_unknown_and_forbidden_controls(
    mutation: str,
) -> None:
    """Only the closed hidden-input inventory may reach the session POST boundary."""
    fields = """<input type="hidden" name="applicationId" value="RA001">
    <input type="hidden" name="branchCode" value="hkel">
    <input type="hidden" name="jvmVendor" value="publisher-vendor">
    <input type="hidden" name="jvmVersion" value="publisher-version">
    <input type="hidden" name="javascriptEnabled" value="false">
    <input type="hidden" name="cookieEnabled" value="false">
    <input type="hidden" name="appletLoadFailed" value="false">
    <input type="hidden" name="isIpv4Verified" value="false">
    <input type="hidden" name="isIpv6Verified" value="false">
    <input type="hidden" name="language" value="en">
    <input type="hidden" name="country" value="HK">
    <input type="hidden" name="_CSRF_TOKEN" value="dummy-token">"""
    if 'type="password"' in mutation or mutation.startswith("<button"):
        fields = fields.replace('<input type="hidden" name="branchCode" value="hkel">', mutation)
    else:
        fields += mutation
    body = (
        '<form method="post" action="/checkconfig/submitClientConfig.do">' + fields + "</form>"
    ).encode()

    with pytest.raises(ValueError, match=r"HKEL_CLIENT_CONFIGURATION_(?:FORM|FIELDS)_INVALID"):
        parse_hkel_client_configuration_form(
            body,
            page_url=(
                "https://www.elegislation.gov.hk/checkconfig/"
                "checkClientConfig.jsp?applicationId=RA001"
            ),
        )


@pytest.mark.parametrize("mutation", ["missing-country", "empty-csrf", "obsolete-fields"])
def test_current_configuration_form_rejects_missing_empty_token_and_obsolete_inventory(
    mutation: str,
) -> None:
    """Missing current fields, an empty token, and the retired form cannot be submitted."""
    body = """<form method="post" action="/checkconfig/submitClientConfig.do">
    <input type="hidden" name="applicationId" value="RA001">
    <input type="hidden" name="branchCode" value="hkel">
    <input type="hidden" name="jvmVendor" value="publisher-vendor">
    <input type="hidden" name="jvmVersion" value="publisher-version">
    <input type="hidden" name="javascriptEnabled" value="false">
    <input type="hidden" name="cookieEnabled" value="false">
    <input type="hidden" name="appletLoadFailed" value="false">
    <input type="hidden" name="isIpv4Verified" value="false">
    <input type="hidden" name="isIpv6Verified" value="false">
    <input type="hidden" name="language" value="en">
    <input type="hidden" name="country" value="HK">
    <input type="hidden" name="_CSRF_TOKEN" value="dummy-token">
    </form>"""
    if mutation == "missing-country":
        body = body.replace('<input type="hidden" name="country" value="HK">', "")
    elif mutation == "empty-csrf":
        body = body.replace('value="dummy-token"', 'value=""')
    else:
        body = """<form method="post" action="/checkconfig/submitClientConfig.do">
        <input type="hidden" name="applicationId" value="RA001">
        <input type="hidden" name="OS"><input type="hidden" name="OS_S">
        <input type="hidden" name="BR"><input type="hidden" name="BR_S">
        <input type="hidden" name="BRV"><input type="hidden" name="BRV_S">
        <input type="hidden" name="JS_S"><input type="hidden" name="C_S">
        <input type="hidden" name="_CSRF_TOKEN" value="dummy-token"></form>"""

    with pytest.raises(ValueError, match="HKEL_CLIENT_CONFIGURATION_FIELDS_INVALID"):
        parse_hkel_client_configuration_form(
            body.encode(),
            page_url=(
                "https://www.elegislation.gov.hk/checkconfig/"
                "checkClientConfig.jsp?applicationId=RA001"
            ),
        )


@pytest.mark.parametrize(
    ("action", "method"),
    [
        ("https://attacker.example/checkconfig/submitClientConfig.do", "post"),
        ("https://www.elegislation.gov.hk:443/checkconfig/submitClientConfig.do", "post"),
        ("https://www.elegislation.gov.hk:444/checkconfig/submitClientConfig.do", "post"),
        ("https://[invalid/checkconfig/submitClientConfig.do", "post"),
        ("/checkconfig/changed.do", "post"),
        ("/checkconfig/submitClientConfig.do?next=terms", "post"),
        ("/checkconfig/submitClientConfig.do", "get"),
    ],
)
def test_current_configuration_form_rejects_hostile_action_or_method(
    action: str, method: str
) -> None:
    """The session form stays on its one exact same-origin POST action."""
    body = f"""<form method="{method}" action="{action}">
    <input type="hidden" name="applicationId" value="RA001">
    <input type="hidden" name="branchCode" value="hkel">
    <input type="hidden" name="jvmVendor" value="publisher-vendor">
    <input type="hidden" name="jvmVersion" value="publisher-version">
    <input type="hidden" name="javascriptEnabled" value="false">
    <input type="hidden" name="cookieEnabled" value="false">
    <input type="hidden" name="appletLoadFailed" value="false">
    <input type="hidden" name="isIpv4Verified" value="false">
    <input type="hidden" name="isIpv6Verified" value="false">
    <input type="hidden" name="language" value="en">
    <input type="hidden" name="country" value="HK">
    <input type="hidden" name="_CSRF_TOKEN" value="dummy-token">
    </form>""".encode()

    with pytest.raises(ValueError, match=r"HKEL_CLIENT_CONFIGURATION_(?:FORM|ACTION)_INVALID"):
        parse_hkel_client_configuration_form(
            body,
            page_url=(
                "https://www.elegislation.gov.hk/checkconfig/"
                "checkClientConfig.jsp?applicationId=RA001"
            ),
        )


@pytest.mark.parametrize(
    ("resources", "dataset_name", "code"),
    [
        (["https://resource.data.one.gov.hk/a.xml"], "hkel-current", "INCOMPLETE"),
        (
            [
                "https://resource.data.one.gov.hk/a.xml",
                "https://resource.data.one.gov.hk/b.zip",
                "https://resource.data.one.gov.hk/extra.zip",
            ],
            "hkel-current",
            "MEMBERSHIP_MISMATCH",
        ),
        (
            [
                "https://resource.data.one.gov.hk/a.xml",
                "https://resource.data.one.gov.hk/b.zip",
            ],
            "another-dataset",
            "IDENTITY_INVALID",
        ),
    ],
)
def test_data_catalogue_rejects_partial_extra_and_identity_mismatch(
    resources: list[str], dataset_name: str, code: str
) -> None:
    """Only the exact publisher dataset and resource universe can reconcile."""
    body = (
        '{"success":true,"result":{"name":"'
        + dataset_name
        + '","resources":['
        + ",".join('{"url":"' + url + '"}' for url in resources)
        + "]}}"
    ).encode()

    with pytest.raises(ValueError, match="HKEL_DATA_CATALOGUE_" + code):
        parse_hkel_dataset_catalogue(
            body,
            expected_dataset_name="hkel-current",
            required_urls=(
                "https://resource.data.one.gov.hk/a.xml",
                "https://resource.data.one.gov.hk/b.zip",
            ),
        )


def test_data_catalogue_rejects_a_malformed_resource_member() -> None:
    """Malformed catalogue entries cannot disappear during membership comparison."""
    with pytest.raises(ValueError, match="HKEL_DATA_CATALOGUE_INVALID"):
        parse_hkel_dataset_catalogue(
            b'{"success":true,"result":{"name":"hkel-current","resources":'
            b'[{"url":"https://resource.data.one.gov.hk/a.xml"},{}]}}',
            expected_dataset_name="hkel-current",
            required_urls=("https://resource.data.one.gov.hk/a.xml",),
        )


def test_hkel_policy_pages_require_current_replication_and_database_terms() -> None:
    """A configured session cannot turn an unrelated HTML page into policy evidence."""
    validate_hkel_policy_pages(
        b"Terms of Use last reviewed April 2026 automatic extraction",
        (
            b"Copyright Policy April 2026 mass replication product/database reproduction "
            b"attribution version non-endorsement indemnity third-party rights"
        ),
    )
    with pytest.raises(ValueError, match="HKEL_POLICY_PAGE_INVALID"):
        validate_hkel_policy_pages(b"gateway", b"gateway")


def test_hkel_policy_pages_accept_visible_current_semantics_across_markup() -> None:
    """Publisher markup and inflection cannot hide an unchanged required condition."""
    validate_hkel_policy_pages(
        b"""<html><body><h1>Terms of Use</h1><p>Last reviewed April 2026.</p>
        <p>Automatic bulk <strong>extraction</strong> may be blocked.</p>
        <p>Use the verified official PDF and read the Copyright Policy.</p></body></html>""",
        b"""<html><body><h1>Copyright Policy</h1><p>Last reviewed April 2026.</p>
        <p>Mass <strong>replication</strong> and product or database reproduction.</p>
        <p>Keep an accurate Government copyright reference and version date.</p>
        <p>The Government does not endorse the product; HKeL remains free and available.</p>
        <p>Indemnification applies, while third party rights remain excluded.</p></body></html>""",
    )


def test_hkel_policy_pages_reject_required_words_hidden_in_script() -> None:
    """Executable page content cannot satisfy visible publisher-policy evidence."""
    hidden = b"""<html><body>gateway<script>April 2026 automatic extraction
    mass replication product/database attribution version non-endorsement
    indemnity third-party rights</script></body></html>"""
    with pytest.raises(ValueError, match="HKEL_POLICY_PAGE_INVALID"):
        validate_hkel_policy_pages(hidden, hidden)


@pytest.mark.parametrize(
    ("page", "present", "replacement"),
    [
        ("terms", b"Terms", b"Conditions"),
        ("terms", b"April", b"March"),
        ("terms", b"Automatic", b"Manual"),
        ("copyright", b"copyright", b"ownership"),
        ("copyright", b"April", b"March"),
        ("copyright", b"Mass", b"Limited"),
        ("copyright", b"database", b"document"),
        ("copyright", b"accurate", b"unclear"),
        ("copyright", b"version", b"edition"),
        ("copyright", b"endorse", b"sponsor"),
        ("copyright", b"Indemnification", b"Responsibility"),
        ("copyright", b"third party rights", b"external material"),
    ],
)
def test_hkel_policy_pages_reject_each_missing_visible_semantic_group(
    page: str,
    present: bytes,
    replacement: bytes,
) -> None:
    """Every accepted publisher-policy concept remains independently mandatory."""
    terms = b"""<h1>Terms of Use</h1><p>Last reviewed April 2026.</p>
    <p>Automatic bulk extraction may be blocked.</p>"""
    copyright_page = b"""<h1>copyright Policy</h1><p>Last reviewed April 2026.</p>
    <p>Mass replication and product or database reproduction.</p>
    <p>Keep an accurate Government copyright reference and version date.</p>
    <p>The Government does not endorse the product.</p>
    <p>Indemnification applies; third party rights remain excluded.</p>"""
    if page == "terms":
        terms = terms.replace(present, replacement)
    else:
        copyright_page = copyright_page.replace(present, replacement)

    with pytest.raises(ValueError, match="HKEL_POLICY_PAGE_INVALID"):
        validate_hkel_policy_pages(terms, copyright_page)


def _current_policy_terms_fixture() -> bytes:
    return b"""<h1>Terms of Use</h1><p>Last reviewed April 2026.</p>
    <p>Automatic bulk extraction may be blocked.</p>"""


def _current_policy_copyright_fixture(*, endorsement: bytes) -> bytes:
    return (
        b"""<h1>Copyright Policy</h1><p>Last reviewed April 2026.</p>
    <p>Mass replication and product or database reproduction.</p>
    <p>Keep an accurate Government copyright reference and version date.</p>
    <p>The Government """
        + endorsement
        + b""" the product.</p>
    <p>Indemnification applies; third party rights remain excluded.</p>"""
    )


def test_hkel_policy_pages_reject_opposite_endorsement_polarity() -> None:
    """A positive endorsement statement cannot satisfy the required negative condition."""
    with pytest.raises(ValueError, match="HKEL_POLICY_PAGE_INVALID"):
        validate_hkel_policy_pages(
            _current_policy_terms_fixture(),
            _current_policy_copyright_fixture(endorsement=b"does endorse"),
        )


def test_hkel_policy_pages_reject_unrelated_reordered_reproduction_words() -> None:
    """Page-wide words cannot be recombined into one product/database licence condition."""
    copyright_page = _current_policy_copyright_fixture(endorsement=b"does not endorse").replace(
        b"Mass replication and product or database reproduction.",
        b"Mass replication. Reproduction differs. Database notice. Product announcement.",
    )
    with pytest.raises(ValueError, match="HKEL_POLICY_PAGE_INVALID"):
        validate_hkel_policy_pages(_current_policy_terms_fixture(), copyright_page)


def test_hkel_policy_pages_reject_accuracy_without_attribution_or_reference() -> None:
    """An accurate-copy statement is not an acknowledgement or source reference."""
    copyright_page = _current_policy_copyright_fixture(endorsement=b"does not endorse").replace(
        b"Keep an accurate Government copyright reference and version date.",
        b"Copies of legislation are accurate. Keep the version date.",
    )
    with pytest.raises(ValueError, match="HKEL_POLICY_PAGE_INVALID"):
        validate_hkel_policy_pages(_current_policy_terms_fixture(), copyright_page)


def test_hkel_policy_pages_accept_bounded_current_source_acknowledgement() -> None:
    """The current source-and-licence acknowledgement satisfies the same policy role."""
    copyright_page = _current_policy_copyright_fixture(endorsement=b"does not endorse").replace(
        b"Keep an accurate Government copyright reference and version date.",
        (
            b"Reproduced provisions in the product are reproduced from HKeL under a licence "
            b"granted by the Government. Keep the version date."
        ),
    )
    validate_hkel_policy_pages(_current_policy_terms_fixture(), copyright_page)


@pytest.mark.parametrize(
    "opening_tag",
    [
        b"<div hidden>",
        b'<div HIDDEN = " hidden ">',
        b'<div aria-hidden="true">',
        b'<div ArIa-HiDdEn = " TRUE ">',
    ],
)
def test_hkel_policy_pages_reject_semantics_in_hidden_attribute_containers(
    opening_tag: bytes,
) -> None:
    """HTML and ARIA-hidden policy words are never visible evidence."""
    hidden_copyright = (
        b"<body>gateway"
        + opening_tag
        + _current_policy_copyright_fixture(endorsement=b"does not endorse")
        + b"</div></body>"
    )
    with pytest.raises(ValueError, match="HKEL_POLICY_PAGE_INVALID"):
        validate_hkel_policy_pages(_current_policy_terms_fixture(), hidden_copyright)


def test_hkel_policy_pages_reject_semantics_in_properly_nested_hidden_containers() -> None:
    """Nested visible tags cannot escape an outer hidden-policy container."""
    hidden_copyright = (
        b"<div hidden><section><span>"
        + _current_policy_copyright_fixture(endorsement=b"does not endorse")
        + b"</span></section></div>"
    )
    with pytest.raises(ValueError, match="HKEL_POLICY_PAGE_INVALID"):
        validate_hkel_policy_pages(_current_policy_terms_fixture(), hidden_copyright)


@pytest.mark.parametrize("container", [b"script", b"style", b"noscript", b"template"])
def test_hkel_policy_pages_reject_semantics_in_each_non_visible_container(
    container: bytes,
) -> None:
    """Each non-visible HTML container is independently excluded."""
    copyright_page = (
        b"<"
        + container
        + b">"
        + _current_policy_copyright_fixture(endorsement=b"does not endorse")
        + b"</"
        + container
        + b">"
    )
    with pytest.raises(ValueError, match="HKEL_POLICY_PAGE_INVALID"):
        validate_hkel_policy_pages(_current_policy_terms_fixture(), copyright_page)


def test_basic_law_root_requires_constitution_chapters_annexes_and_national_laws() -> None:
    """The live root yields only its exact two English content-category roots."""
    membership = parse_historical_basic_law_root_membership(
        b'<a href="../constitution/index.html">Constitution</a>'
        b'<a href="../basiclaw/index.html">Basic Law</a>'
        b'<a href="https://attacker.example/en/basiclaw/index.html">off host</a>'
        b'<a href="javascript:alert(1)">script</a>'
        b'<a href="../../outside.html">traversal</a>'
        b'<a href="../promotion/activities.html">irrelevant</a>',
        root_url="https://www.basiclaw.gov.hk/en/index/index.html",
    )
    assert membership.member_urls == (
        "https://www.basiclaw.gov.hk/en/constitution/index.html",
        "https://www.basiclaw.gov.hk/en/basiclaw/index.html",
    )
    with pytest.raises(ValueError, match="BASIC_LAW_CATEGORY_MISSING"):
        parse_historical_basic_law_root_membership(
            b'<a href="../basiclaw/index.html">Basic Law</a>',
            root_url="https://www.basiclaw.gov.hk/en/index/index.html",
        )


def test_basic_law_root_rejects_relative_traversal_before_url_normalization() -> None:
    """Traversal syntax cannot normalize into an otherwise admitted category URL."""
    with pytest.raises(ValueError, match="BASIC_LAW_CATEGORY_MISSING"):
        parse_historical_basic_law_root_membership(
            b'<a href="../constitution/index.html">Constitution</a>'
            b'<a href="../../en/basiclaw/index.html">Traversal</a>',
            root_url="https://www.basiclaw.gov.hk/en/index/index.html",
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example/en/basiclaw/index.html",
        "https://www.basiclaw.gov.hk/en/basiclaw/../outside.html",
        "https://www.basiclaw.gov.hk/en/basiclaw/%2e%2e/outside.html",
        "javascript:alert(1)",
        "https://www.basiclaw.gov.hk/en/notices/index.html",
        "https://www.basiclaw.gov.hk/en/basiclaw/index.html?drift=1",
    ],
)
def test_basic_law_generated_member_binding_rejects_hostile_or_irrelevant_urls(
    url: str,
) -> None:
    """Every generated member is checked before the executor may request it."""
    with pytest.raises(ValueError, match="BASIC_LAW_MEMBER_URL_INVALID"):
        require_basic_law_member_url(url)
