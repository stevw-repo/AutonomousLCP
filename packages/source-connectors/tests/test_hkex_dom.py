"""Tests for the text-free bounded HKEX DOM contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from asklegal_source_connectors.hk_regulatory_official import HKEXPublisherBoard
from asklegal_source_connectors.hkex_dom import (
    HKEXAuthorityClass,
    HKEXFetchDisposition,
    HKEXLocatorKind,
    HKEXLocatorNormalization,
    HKEXMembershipRelation,
    HKEXUpdatePosition,
    build_hkex_attachment_occurrence,
    build_hkex_membership_association,
    parse_hkex_complete_section_identity,
    parse_hkex_root_structure,
    require_hkex_raw_locator,
    resolve_hkex_capture_endpoint_id,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "hkex"
_ROOTS = _FIXTURES / "role-roots"
_SECTIONS = _FIXTURES / "role-sections"

_ROOT_IDENTITY_MUTATIONS: tuple[Callable[[bytes], bytes], ...] = (
    lambda body: body.replace(b'<link rel="canonical"', b'<link rel="alternate"', 1),
    lambda body: body.replace(
        b"</head>",
        b'<link rel="canonical" href="https://en-rules.hkex.com.hk/'
        b'rulebook/main-board-fees-rules"></head>',
        1,
    ),
    lambda body: body.replace(b"/node/3783", b"/node/1836", 1),
    lambda body: body.replace(b'data-history-node-id="3783"', b'data-history-node-id="1836"', 1),
    lambda body: body.replace(b"/entiresection/3783", b"/entiresection/1836", 1),
    lambda body: body.replace(
        b'<article class="published"', b'<template><article class="published"', 1
    ).replace(b"</article>", b"</article></template>", 1),
)


def _body(endpoint: int) -> bytes:
    return (_ROOTS / f"endpoint-{endpoint}.html").read_bytes()


@pytest.mark.parametrize(
    "manifest_path", [_ROOTS / "manifest.json", _SECTIONS / "direct-probe-manifest.json"]
)
def test_projection_manifests_bind_every_fixture(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["projection_version"].endswith("1.0.0")
    for item in manifest["fixtures"]:
        body = (manifest_path.parent / item["fixture_filename"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == item["fixture_sha256"]


@pytest.mark.parametrize(
    ("endpoint", "root_url", "node_id", "entire_section_url"),
    [
        (
            303,
            "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
            "3783",
            "https://en-rules.hkex.com.hk/entiresection/3783",
        ),
        (
            304,
            "https://en-rules.hkex.com.hk/rulebook/gem-fees-rules",
            "1836",
            "https://en-rules.hkex.com.hk/entiresection/1836",
        ),
        (
            305,
            "https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
            "6190",
            "https://en-rules.hkex.com.hk/entiresection/6190",
        ),
        (
            306,
            "https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms",
            "6191",
            "https://en-rules.hkex.com.hk/entiresection/6191",
        ),
        (
            307,
            "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules",
            "2",
            "https://en-rules.hkex.com.hk/entiresection/2",
        ),
        (
            308,
            "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules",
            "49",
            "https://en-rules.hkex.com.hk/entiresection/49",
        ),
    ],
)
def test_six_root_identities_are_exact(
    endpoint: int, root_url: str, node_id: str, entire_section_url: str
) -> None:
    structure = parse_hkex_root_structure(_body(endpoint), root_url=root_url)
    assert structure.identity.canonical_url == root_url
    assert structure.identity.shortlink_url == f"https://en-rules.hkex.com.hk/node/{node_id}"
    assert structure.identity.node_id == node_id
    assert structure.identity.entire_section_url == entire_section_url


def test_forms_nodes_preserve_non_numeric_publisher_order() -> None:
    main = parse_hkex_root_structure(
        _body(305),
        root_url="https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
    )
    gem = parse_hkex_root_structure(
        _body(306),
        root_url="https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms",
    )
    assert main.form_node_urls == tuple(
        f"https://en-rules.hkex.com.hk/node/{node}"
        for node in (3756, 3757, 3759, 3760, 3761, 3762, 3763, 3764, 3765, 3766)
    )
    assert gem.form_node_urls == tuple(
        f"https://en-rules.hkex.com.hk/node/{node}"
        for node in (1812, 1813, 1814, 1815, 1831, 1816, 1817)
    )


@pytest.mark.parametrize(("endpoint", "containers", "pages"), [(307, 22, 80), (308, 22, 74)])
def test_update_members_preserve_exact_depth_parent_and_order(
    endpoint: int, containers: int, pages: int
) -> None:
    root_url = {
        307: "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules",
        308: "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules",
    }[endpoint]
    members = parse_hkex_root_structure(_body(endpoint), root_url=root_url).update_members
    assert (
        sum(item.position.relation is HKEXMembershipRelation.UPDATE_CONTAINER for item in members)
        == containers
    )
    assert (
        sum(item.position.relation is HKEXMembershipRelation.UPDATE_PAGE for item in members)
        == pages
    )
    assert members[0].position == HKEXUpdatePosition(
        0, None, HKEXMembershipRelation.UPDATE_CONTAINER
    )
    assert members[1].position == HKEXUpdatePosition(0, 0, HKEXMembershipRelation.UPDATE_PAGE)
    assert members[-1].position.container_order == 21


@pytest.mark.parametrize(
    ("filename", "url", "node_id"),
    [
        ("fees-main-3783.html", "https://en-rules.hkex.com.hk/entiresection/3783", "3783"),
        ("fees-gem-1836.html", "https://en-rules.hkex.com.hk/entiresection/1836", "1836"),
        ("forms-main-6190.html", "https://en-rules.hkex.com.hk/entiresection/6190", "6190"),
        ("forms-gem-6191.html", "https://en-rules.hkex.com.hk/entiresection/6191", "6191"),
    ],
)
def test_complete_sections_are_structural_only(filename: str, url: str, node_id: str) -> None:
    identity = parse_hkex_complete_section_identity(
        (_SECTIONS / filename).read_bytes(), section_url=url
    )
    assert identity.node_id == node_id
    assert identity.section_url == url


def test_complete_section_ignores_marketing_breadcrumb_div() -> None:
    body = (
        (_SECTIONS / "fees-main-3783.html")
        .read_bytes()
        .replace(
            b"<body>",
            b'<body><div class="section_container_in breadcrumb">'
            b'<a href="https://www.hkex.com.hk/">INERT_MARKETING</a></div>',
            1,
        )
    )

    identity = parse_hkex_complete_section_identity(
        body, section_url="https://en-rules.hkex.com.hk/entiresection/3783"
    )

    assert identity.node_id == "3783"


def test_complete_section_rejects_duplicate_authoritative_breadcrumb_nav() -> None:
    body = (
        (_SECTIONS / "fees-main-3783.html")
        .read_bytes()
        .replace(
            b'<nav class="breadcrumb">',
            b'<nav class="breadcrumb"><a href="/entiresection/3783">INERT</a></nav>'
            b'<nav class="breadcrumb">',
            1,
        )
    )

    with pytest.raises(ValueError, match="HKEX_SECTION_IDENTITY_INVALID"):
        parse_hkex_complete_section_identity(
            body, section_url="https://en-rules.hkex.com.hk/entiresection/3783"
        )


@pytest.mark.parametrize(
    "mutation",
    _ROOT_IDENTITY_MUTATIONS,
)
def test_root_identity_mutations_fail_closed(mutation: Callable[[bytes], bytes]) -> None:
    with pytest.raises(ValueError, match="HKEX_ROOT_IDENTITY_INVALID"):
        parse_hkex_root_structure(
            mutation(_body(303)),
            root_url="https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
        )


@pytest.mark.parametrize(
    ("raw", "kind", "expected"),
    [
        ("/node/3756", HKEXLocatorKind.FORM_NODE, "https://en-rules.hkex.com.hk/node/3756"),
        (
            "/rulebook/update-no-154",
            HKEXLocatorKind.ROLE_MEMBER,
            "https://en-rules.hkex.com.hk/rulebook/update-no-154",
        ),
        (
            "/sites/default/files/net_file_store/A.pdf",
            HKEXLocatorKind.ATTACHMENT,
            "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/A.pdf",
        ),
        (
            "https://en-rules.hkex.com.hk/node/3756",
            HKEXLocatorKind.FORM_NODE,
            "https://en-rules.hkex.com.hk/node/3756",
        ),
    ],
)
def test_ordinary_raw_locator_accepts_only_canonical_forms(
    raw: str, kind: HKEXLocatorKind, expected: str
) -> None:
    assert require_hkex_raw_locator(raw, kind=kind) == expected


@pytest.mark.parametrize(
    "raw",
    [
        " /node/3756",
        "/node/3756\t",
        "/node/../3756",
        "/node//3756",
        "/node/%33%37%35%36",
        "/node/3756?x=1",
        "/node/3756#x",
        "//en-rules.hkex.com.hk/node/3756",
        "https://user@en-rules.hkex.com.hk/node/3756",
        "https://en-rules.hkex.com.hk:443/node/3756",
        "https://EN-RULES.hkex.com.hk/node/3756",
        "/node\\3756",
        "/node/&num;3756",
    ],
)
def test_ordinary_raw_locator_rejects_before_join(raw: str) -> None:
    with pytest.raises(ValueError, match="HKEX_RAW_LOCATOR_INVALID"):
        require_hkex_raw_locator(raw, kind=HKEXLocatorKind.FORM_NODE)


def test_capture_id_resolver_reuses_static_or_derives_media_typed_full_digest() -> None:
    static = {"https://en-rules.hkex.com.hk/node/3756": "sep_static"}
    assert (
        resolve_hkex_capture_endpoint_id(
            "https://en-rules.hkex.com.hk/node/3756",
            media_type="text/html",
            capture_id_by_url=static,
        )
        == "sep_static"
    )
    derived = resolve_hkex_capture_endpoint_id(
        "https://en-rules.hkex.com.hk/node/3757", media_type="text/html", capture_id_by_url=static
    )
    assert derived.startswith("hkex-html-sha256-")
    assert len(derived.removeprefix("hkex-html-sha256-")) == 64
    assert static == {"https://en-rules.hkex.com.hk/node/3756": "sep_static"}


def test_checked_association_factory_enforces_complete_disposition_matrix() -> None:
    semantic = build_hkex_membership_association(
        source_id="HK-REG-HKEX-RULE-UPDATES",
        board=HKEXPublisherBoard.MAIN,
        relation=HKEXMembershipRelation.UPDATE_CONTAINER,
        parent_url="https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules",
        target_url="https://en-rules.hkex.com.hk/rulebook/2026-1",
        source_order=0,
        occurrence_ids=(),
        authority_class=HKEXAuthorityClass.SAME_HOST_ADMITTED,
        fetch_disposition=HKEXFetchDisposition.SEMANTIC_ONLY,
        capture_endpoint_id=None,
    )
    planned = build_hkex_membership_association(
        source_id="HK-REG-HKEX-FEES-RULES",
        board=HKEXPublisherBoard.MAIN,
        relation=HKEXMembershipRelation.FEES_PDF,
        parent_url="https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
        target_url="https://en-rules.hkex.com.hk/sites/default/files/net_file_store/A.pdf",
        source_order=0,
        occurrence_ids=(),
        authority_class=HKEXAuthorityClass.SAME_HOST_ADMITTED,
        fetch_disposition=HKEXFetchDisposition.PLANNED_OR_REUSED,
        capture_endpoint_id="sep_pdf",
    )
    external = build_hkex_membership_association(
        source_id="HK-REG-HKEX-RULE-UPDATES",
        board=HKEXPublisherBoard.GEM,
        relation=HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF,
        parent_url="https://en-rules.hkex.com.hk/rulebook/update-no-1",
        target_url="https://external.invalid/A.pdf",
        source_order=1,
        occurrence_ids=("occ-1",),
        authority_class=HKEXAuthorityClass.EXTERNAL_AUTHORITY_REQUIRED,
        fetch_disposition=HKEXFetchDisposition.UNFETCHED_EXTERNAL_REFERENCE,
        capture_endpoint_id=None,
    )
    assert semantic.capture_endpoint_id is None
    assert planned.capture_endpoint_id == "sep_pdf"
    assert external.occurrence_ids == ("occ-1",)
    for changes in (
        {"fetch_disposition": HKEXFetchDisposition.PLANNED_OR_REUSED},
        {"capture_endpoint_id": "invented"},
        {"occurrence_ids": ("occ",)},
        {"authority_class": HKEXAuthorityClass.EXTERNAL_AUTHORITY_REQUIRED},
    ):
        values = {
            name: getattr(semantic, name)
            for name in semantic.__dataclass_fields__
            if name != "association_id"
        }
        values.update(changes)
        with pytest.raises(ValueError, match="HKEX_ASSOCIATION_INVALID"):
            build_hkex_membership_association(**values)


def test_attachment_occurrence_rejects_semantic_only() -> None:
    with pytest.raises(ValueError, match="HKEX_ATTACHMENT_OCCURRENCE_INVALID"):
        build_hkex_attachment_occurrence(
            source_id="HK-REG-HKEX-RULE-UPDATES",
            board=HKEXPublisherBoard.MAIN,
            parent_relation=HKEXMembershipRelation.UPDATE_PAGE,
            parent_url="https://en-rules.hkex.com.hk/rulebook/update-no-154",
            parent_position=HKEXUpdatePosition(0, 0, HKEXMembershipRelation.UPDATE_PAGE),
            occurrence_order=0,
            raw_locator="/sites/default/files/net_file_store/A.pdf",
            normalization_code=HKEXLocatorNormalization.NONE,
            target_url="https://en-rules.hkex.com.hk/sites/default/files/net_file_store/A.pdf",
            authority_class=HKEXAuthorityClass.SAME_HOST_ADMITTED,
            fetch_disposition=HKEXFetchDisposition.SEMANTIC_ONLY,
        )
