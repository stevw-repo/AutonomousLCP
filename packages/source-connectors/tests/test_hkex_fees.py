"""Tests for exact HKEX Fees root membership."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from asklegal_source_connectors.hk_regulatory_official import HKEXPublisherBoard
from asklegal_source_connectors.hkex_dom import (
    HKEXAuthorityClass,
    HKEXFetchDisposition,
    HKEXMembershipRelation,
)
from asklegal_source_connectors.hkex_fees import parse_hkex_fees_membership

_FIXTURES = Path(__file__).parent / "fixtures" / "hkex"
_ROOTS = _FIXTURES / "role-roots"
_SECTIONS = _FIXTURES / "role-sections"

_CASES = (
    (
        HKEXPublisherBoard.MAIN,
        "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
        "https://en-rules.hkex.com.hk/entiresection/3783",
        "endpoint-303.html",
        "fees-main-3783.html",
        "HKEX4476_3783_VER36106.pdf",
    ),
    (
        HKEXPublisherBoard.GEM,
        "https://en-rules.hkex.com.hk/rulebook/gem-fees-rules",
        "https://en-rules.hkex.com.hk/entiresection/1836",
        "endpoint-304.html",
        "fees-gem-1836.html",
        "HKEX4476_1836_VER27714.pdf",
    ),
)


@pytest.mark.parametrize(
    ("board", "root_url", "section_url", "root_fixture", "section_fixture", "filename"),
    _CASES,
)
def test_fees_parser_emits_one_exact_page_owned_pdf(  # noqa: PLR0917
    board: HKEXPublisherBoard,
    root_url: str,
    section_url: str,
    root_fixture: str,
    section_fixture: str,
    filename: str,
) -> None:
    target = f"https://en-rules.hkex.com.hk/sites/default/files/net_file_store/{filename}"
    plan = parse_hkex_fees_membership(
        (_ROOTS / root_fixture).read_bytes(),
        (_SECTIONS / section_fixture).read_bytes(),
        root_url=root_url,
        complete_section_url=section_url,
        board=board,
        capture_id_by_url={target: "sep_pdf"},
    )
    assert plan.identity.canonical_url == root_url
    assert plan.attachment_occurrences == ()
    assert len(plan.associations) == 1
    association = plan.associations[0]
    assert association.source_id == "HK-REG-HKEX-FEES-RULES"
    assert association.board is board
    assert association.relation is HKEXMembershipRelation.FEES_PDF
    assert association.parent_url == root_url
    assert association.target_url == target
    assert association.source_order == 0
    assert association.occurrence_ids == ()
    assert association.authority_class is HKEXAuthorityClass.SAME_HOST_ADMITTED
    assert association.fetch_disposition is HKEXFetchDisposition.PLANNED_OR_REUSED
    assert association.capture_endpoint_id == "sep_pdf"


def _main() -> tuple[bytes, bytes]:
    return (
        (_ROOTS / "endpoint-303.html").read_bytes(),
        (_SECTIONS / "fees-main-3783.html").read_bytes(),
    )


_ROOT_MUTATIONS: tuple[Callable[[bytes], bytes], ...] = (
    lambda body: body.replace(b'id="block-associatedpdfblock"', b'id="not-associated"', 1),
    lambda body: body.replace(
        b'<div id="block-associatedpdfblock">',
        b'<div id="block-associatedpdfblock"></div><div id="block-associatedpdfblock">',
        1,
    ),
    lambda body: body.replace(
        b'<div id="block-associatedpdfblock">',
        b'<nav><div id="block-associatedpdfblock">',
        1,
    ).replace(b"</div>\n<nav>", b"</div></nav>\n<nav>", 1),
    lambda body: body.replace(b'class="submenu icopdf"', b'class="submenu"', 1),
    lambda body: body.replace(b'title="View Current PDF"', b'title="Other"', 1),
    lambda body: body.replace(b'target="_blank"', b'target="_self"', 1),
    lambda body: body.replace(b"/sites/default/files/", b" /sites/default/files/", 1),
    lambda body: body.replace(b'.pdf"', b'.pdf?download=1"', 1),
    lambda body: body.replace(
        b"</div>\n<nav>",
        b'<a href="/sites/default/files/net_file_store/extra.pdf">INERT</a></div>\n<nav>',
        1,
    ),
)


@pytest.mark.parametrize("mutation", _ROOT_MUTATIONS)
def test_fees_parser_rejects_missing_duplicate_moved_or_malformed_owned_pdf(
    mutation: Callable[[bytes], bytes],
) -> None:
    root, section = _main()
    with pytest.raises(ValueError, match="HKEX_FEES_MEMBERSHIP_INVALID"):
        parse_hkex_fees_membership(
            mutation(root),
            section,
            root_url="https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
            complete_section_url="https://en-rules.hkex.com.hk/entiresection/3783",
            board=HKEXPublisherBoard.MAIN,
            capture_id_by_url={},
        )


def test_body_pdf_outside_owned_block_is_ignored() -> None:
    root, section = _main()
    plan = parse_hkex_fees_membership(
        root,
        section,
        root_url="https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
        complete_section_url="https://en-rules.hkex.com.hk/entiresection/3783",
        board=HKEXPublisherBoard.MAIN,
        capture_id_by_url={},
    )
    assert len(plan.associations) == 1
    assert "evil.invalid" not in plan.associations[0].target_url


def test_complete_section_pdf_is_contract_drift() -> None:
    root, section = _main()
    section = section.replace(
        b"</div></body>",
        b'<a href="/sites/default/files/net_file_store/injected.pdf">INERT</a></div></body>',
    )
    with pytest.raises(ValueError, match="HKEX_FEES_MEMBERSHIP_INVALID"):
        parse_hkex_fees_membership(
            root,
            section,
            root_url="https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
            complete_section_url="https://en-rules.hkex.com.hk/entiresection/3783",
            board=HKEXPublisherBoard.MAIN,
            capture_id_by_url={},
        )


@pytest.mark.parametrize(
    ("root_url", "section_url", "board"),
    [
        (
            "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
            "https://en-rules.hkex.com.hk/entiresection/1836",
            HKEXPublisherBoard.MAIN,
        ),
        (
            "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
            "https://en-rules.hkex.com.hk/entiresection/3783",
            HKEXPublisherBoard.GEM,
        ),
    ],
)
def test_fees_parser_rejects_board_or_section_disagreement(
    root_url: str, section_url: str, board: HKEXPublisherBoard
) -> None:
    root, section = _main()
    with pytest.raises(ValueError, match="HKEX_FEES_MEMBERSHIP_INVALID"):
        parse_hkex_fees_membership(
            root,
            section,
            root_url=root_url,
            complete_section_url=section_url,
            board=board,
            capture_id_by_url={},
        )
