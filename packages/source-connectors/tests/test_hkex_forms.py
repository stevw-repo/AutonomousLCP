"""Tests for exact HKEX Forms root and member membership."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict, cast

import pytest
from asklegal_source_connectors.hk_regulatory_official import HKEXPublisherBoard
from asklegal_source_connectors.hkex_dom import HKEXMembershipRelation
from asklegal_source_connectors.hkex_forms import (
    parse_hkex_form_member,
    parse_hkex_forms_membership,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "hkex"
_ROOTS = _FIXTURES / "role-roots"
_SECTIONS = _FIXTURES / "role-sections"
_MEMBERS = _FIXTURES / "form-members"


class _FormFixture(TypedDict):
    node_id: str
    requested_url: str
    final_url: str
    redirect_count: int
    pdf_filename: str
    observed_byte_length: int | None
    body_retained: bool
    fixture_filename: str
    fixture_sha256: str


def _manifest() -> tuple[_FormFixture, ...]:
    raw: object = json.loads((_MEMBERS / "direct-probe-manifest.json").read_bytes())
    assert isinstance(raw, dict)
    fixtures = cast("dict[str, object]", raw).get("fixtures")
    assert isinstance(fixtures, list)
    return tuple(cast("_FormFixture", item) for item in cast("list[object]", fixtures))


def test_member_manifest_binds_all_17_text_free_projections() -> None:
    fixtures = _manifest()
    assert len(fixtures) == 17
    for item in fixtures:
        body = (_MEMBERS / item["fixture_filename"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == item["fixture_sha256"]
        assert item["body_retained"] is False


@pytest.mark.parametrize(
    ("board", "root_file", "section_file", "root_url", "section_url", "nodes"),
    [
        (
            HKEXPublisherBoard.MAIN,
            "endpoint-305.html",
            "forms-main-6190.html",
            "https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
            "https://en-rules.hkex.com.hk/entiresection/6190",
            (3756, 3757, 3759, 3760, 3761, 3762, 3763, 3764, 3765, 3766),
        ),
        (
            HKEXPublisherBoard.GEM,
            "endpoint-306.html",
            "forms-gem-6191.html",
            "https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms",
            "https://en-rules.hkex.com.hk/entiresection/6191",
            (1812, 1813, 1814, 1815, 1831, 1816, 1817),
        ),
    ],
)
def test_forms_root_emits_only_exact_ordered_form_nodes(  # noqa: PLR0917
    board: HKEXPublisherBoard,
    root_file: str,
    section_file: str,
    root_url: str,
    section_url: str,
    nodes: tuple[int, ...],
) -> None:
    plan = parse_hkex_forms_membership(
        (_ROOTS / root_file).read_bytes(),
        (_SECTIONS / section_file).read_bytes(),
        root_url=root_url,
        complete_section_url=section_url,
        board=board,
        capture_id_by_url={},
    )
    assert [item.relation for item in plan.associations] == [
        HKEXMembershipRelation.FORM_NODE
    ] * len(nodes)
    assert [item.source_order for item in plan.associations] == list(range(len(nodes)))
    assert [item.target_url for item in plan.associations] == [
        f"https://en-rules.hkex.com.hk/node/{node}" for node in nodes
    ]
    assert all(
        item.capture_endpoint_id is not None
        and item.capture_endpoint_id.startswith("hkex-html-sha256-")
        for item in plan.associations
    )
    assert plan.attachment_occurrences == ()


@pytest.mark.parametrize("index", range(17))
def test_each_form_member_emits_its_one_node_bound_pdf(index: int) -> None:
    item = _manifest()[index]
    node_id = item["node_id"]
    board = HKEXPublisherBoard.MAIN if int(node_id) >= 3000 else HKEXPublisherBoard.GEM
    capture = parse_hkex_form_member(
        (_MEMBERS / item["fixture_filename"]).read_bytes(),
        requested_node_url=item["requested_url"],
        final_url=item["final_url"],
        board=board,
        capture_id_by_url={},
    )
    assert capture.requested_node_url == item["requested_url"]
    assert capture.final_url == item["final_url"]
    assert capture.identity.node_id == node_id
    assert len(capture.associations) == 1
    association = capture.associations[0]
    assert association.relation is HKEXMembershipRelation.FORM_PDF
    assert association.parent_url == item["requested_url"]
    assert association.target_url.endswith(item["pdf_filename"])


def _member(node_id: int = 3759) -> tuple[bytes, _FormFixture]:
    item = next(item for item in _manifest() if item["node_id"] == str(node_id))
    return (_MEMBERS / item["fixture_filename"]).read_bytes(), item


_MEMBER_MUTATIONS: tuple[Callable[[bytes], bytes], ...] = (
    lambda body: body.replace(b'rel="canonical"', b'rel="alternate"', 1),
    lambda body: body.replace(b"/node/3759", b"/node/3760", 1),
    lambda body: body.replace(b'data-history-node-id="3759"', b'data-history-node-id="3760"', 1),
    lambda body: body.replace(b"/entiresection/3759", b"/entiresection/3760", 1),
    lambda body: body.replace(b'id="block-associatedpdfblock"', b'id="not-associated"', 1),
    lambda body: body.replace(
        b'<div id="block-associatedpdfblock">',
        b'<div id="block-associatedpdfblock"></div><div id="block-associatedpdfblock">',
        1,
    ),
    lambda body: body.replace(b'class="submenu icopdf"', b'class="submenu"', 1),
    lambda body: body.replace(b'title="View Current PDF"', b'title="Other"', 1),
    lambda body: body.replace(b'target="_blank"', b'target="_self"', 1),
    lambda body: body.replace(b"HKEX4476_3759_", b"HKEX4476_3760_", 1),
)


@pytest.mark.parametrize("mutation", _MEMBER_MUTATIONS)
def test_member_identity_and_dedicated_pdf_mutations_fail_closed(
    mutation: Callable[[bytes], bytes],
) -> None:
    body, item = _member()
    with pytest.raises(ValueError, match="HKEX_FORM_MEMBER_INVALID"):
        parse_hkex_form_member(
            mutation(body),
            requested_node_url=item["requested_url"],
            final_url=item["final_url"],
            board=HKEXPublisherBoard.MAIN,
            capture_id_by_url={},
        )


@pytest.mark.parametrize(
    ("requested", "final"),
    [
        (
            "https://en-rules.hkex.com.hk/node/3759",
            "https://en-rules.hkex.com.hk/node/3759",
        ),
        (
            "https://en-rules.hkex.com.hk/node/3759",
            "https://external.invalid/rulebook/formal-application-equity-securities",
        ),
        (
            "https://en-rules.hkex.com.hk/node/3760",
            "https://en-rules.hkex.com.hk/rulebook/formal-application-equity-securities",
        ),
    ],
)
def test_member_redirect_or_requested_identity_disagreement_fails(
    requested: str, final: str
) -> None:
    body, _ = _member()
    with pytest.raises(ValueError, match="HKEX_FORM_MEMBER_INVALID"):
        parse_hkex_form_member(
            body,
            requested_node_url=requested,
            final_url=final,
            board=HKEXPublisherBoard.MAIN,
            capture_id_by_url={},
        )


@pytest.mark.parametrize("node_id", [3759, 3765])
def test_body_and_stale_revision_pdfs_are_ignored(node_id: int) -> None:
    body, item = _member(node_id)
    body = body.replace(
        b"</article>",
        b'<a href="https://noise.invalid/body.pdf">INERT_NOISE</a></article>',
        1,
    )
    capture = parse_hkex_form_member(
        body,
        requested_node_url=item["requested_url"],
        final_url=item["final_url"],
        board=HKEXPublisherBoard.MAIN,
        capture_id_by_url={},
    )
    assert len(capture.associations) == 1
    assert "noise.invalid" not in capture.associations[0].target_url
    assert "stale.invalid" not in capture.associations[0].target_url
