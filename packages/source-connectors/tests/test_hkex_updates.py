"""Tests for positional HKEX Updates membership and attachment ownership."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict, cast

import pytest
from asklegal_source_connectors.hk_regulatory_official import HKEXPublisherBoard
from asklegal_source_connectors.hkex_dom import (
    HKEXAuthorityClass,
    HKEXFetchDisposition,
    HKEXLocatorNormalization,
    HKEXMembershipRelation,
    HKEXRoleMembershipPlan,
)
from asklegal_source_connectors.hkex_updates import parse_hkex_updates_membership

_REPO = Path(__file__).parents[3]
_FIXTURES = Path(__file__).parent / "fixtures" / "hkex"
_ROOT_FIXTURES = _FIXTURES / "role-roots"
_STRUCTURE_MANIFEST = _FIXTURES / "role-sections" / "retained-structure-manifest.json"
_EVIDENCE = _REPO / "var/hk-v1/source-admission/hkex/authentic-baseline-20260901c/objects"


class _BoardFacts(TypedDict):
    board: str
    root_endpoint_id: str
    section_endpoint_id: str
    section_object_sha256: str
    section_byte_length: int
    container_count: int
    page_count: int
    child_count_vector: list[int]
    raw_pdf_occurrences: int
    same_host_parent_associations: int
    external_parent_associations: int


def _facts(board: HKEXPublisherBoard) -> _BoardFacts:
    raw: object = json.loads(_STRUCTURE_MANIFEST.read_bytes())
    assert isinstance(raw, dict)
    boards = cast("dict[str, object]", raw).get("boards")
    assert isinstance(boards, list)
    for item in cast("list[object]", boards):
        facts = cast("_BoardFacts", item)
        if facts["board"] == board.value:
            return facts
    raise AssertionError(board)


def _inputs(board: HKEXPublisherBoard) -> tuple[bytes, bytes, str, str, dict[str, str]]:
    facts = _facts(board)
    endpoint = 307 if board is HKEXPublisherBoard.MAIN else 308
    root_url = {
        HKEXPublisherBoard.MAIN: "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules",
        HKEXPublisherBoard.GEM: "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules",
    }[board]
    section_url = {
        HKEXPublisherBoard.MAIN: "https://en-rules.hkex.com.hk/entiresection/2",
        HKEXPublisherBoard.GEM: "https://en-rules.hkex.com.hk/entiresection/49",
    }[board]
    section_path = _EVIDENCE / f"{facts['section_object_sha256']}.bin"
    if not section_path.is_file():
        pytest.skip("frozen Attempt-C section object unavailable")
    static_url = {
        HKEXPublisherBoard.MAIN: "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_154_Attachment.pdf",
        HKEXPublisherBoard.GEM: "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_87_Attachment.pdf",
    }[board]
    return (
        (_ROOT_FIXTURES / f"endpoint-{endpoint}.html").read_bytes(),
        section_path.read_bytes(),
        root_url,
        section_url,
        {static_url: "sep_static"},
    )


@pytest.mark.parametrize("board", [HKEXPublisherBoard.MAIN, HKEXPublisherBoard.GEM])
def test_authentic_positional_projection_matches_frozen_counts(board: HKEXPublisherBoard) -> None:
    root, section, root_url, section_url, static = _inputs(board)
    facts = _facts(board)
    plan = parse_hkex_updates_membership(
        root,
        section,
        root_url=root_url,
        complete_section_url=section_url,
        board=board,
        capture_id_by_url=static,
    )
    hierarchy = [
        item
        for item in plan.associations
        if item.relation
        in {HKEXMembershipRelation.UPDATE_CONTAINER, HKEXMembershipRelation.UPDATE_PAGE}
    ]
    same_host = [
        item
        for item in plan.associations
        if item.relation is HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF
        and item.authority_class is HKEXAuthorityClass.SAME_HOST_ADMITTED
    ]
    external = [
        item
        for item in plan.associations
        if item.authority_class is HKEXAuthorityClass.EXTERNAL_AUTHORITY_REQUIRED
    ]
    assert len(hierarchy) == facts["container_count"] + facts["page_count"]
    assert len(plan.attachment_occurrences) == facts["raw_pdf_occurrences"]
    assert len(same_host) == facts["same_host_parent_associations"]
    assert len(external) == facts["external_parent_associations"]
    assert all(
        item.fetch_disposition is HKEXFetchDisposition.SEMANTIC_ONLY
        and item.capture_endpoint_id is None
        and item.occurrence_ids == ()
        for item in hierarchy
    )
    assert all(
        item.fetch_disposition is HKEXFetchDisposition.UNFETCHED_EXTERNAL_REFERENCE
        and item.capture_endpoint_id is None
        and item.occurrence_ids
        for item in external
    )
    assert any(item.capture_endpoint_id == "sep_static" for item in same_host)


def test_combined_authentic_projection_preserves_aliases_normalization_and_external_refs() -> None:
    plans: list[HKEXRoleMembershipPlan] = []
    for board in (HKEXPublisherBoard.MAIN, HKEXPublisherBoard.GEM):
        root, section, root_url, section_url, static = _inputs(board)
        plans.append(
            parse_hkex_updates_membership(
                root,
                section,
                root_url=root_url,
                complete_section_url=section_url,
                board=board,
                capture_id_by_url=static,
            )
        )
    occurrences = [item for plan in plans for item in plan.attachment_occurrences]
    same_host = {
        item.target_url
        for plan in plans
        for item in plan.associations
        if item.authority_class is HKEXAuthorityClass.SAME_HOST_ADMITTED
        and item.relation is HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF
    }
    external = {
        item.target_url
        for plan in plans
        for item in plan.associations
        if item.authority_class is HKEXAuthorityClass.EXTERNAL_AUTHORITY_REQUIRED
    }
    assert len(occurrences) == 536
    assert len(same_host) == 247
    assert len(external) == 7
    assert any(target.startswith("http://www.hkex.com.hk/") for target in external)
    assert {item.normalization_code for item in occurrences} >= {
        HKEXLocatorNormalization.TRIM_ASCII_EDGE,
        HKEXLocatorNormalization.COLLAPSE_ADMITTED_PREFIX_SLASH,
    }
    attachment_associations = [
        item
        for plan in plans
        for item in plan.associations
        if item.relation is HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF
    ]
    assert any(len(item.occurrence_ids) > 1 for item in attachment_associations)


_HOSTILES: tuple[Callable[[bytes, bytes], tuple[bytes, bytes]], ...] = (
    lambda root, section: (
        root.replace(b"/rulebook/update-no-154", b"/rulebook/update-no-153", 1),
        section,
    ),
    lambda root, section: (
        root,
        section.replace(b"/Update_154_Attachment.pdf", b"/Update_999_Attachment.pdf"),
    ),
    lambda root, section: (
        root,
        section.replace(
            b"https://www.hkex.com.hk/-/media/HKEX-Market/Services/Settlement-and-"
            b"Depository/USM/Listing-Information-Paper-and-Schedules-(20250602)(Final).pdf",
            b"https://user@www.hkex.com.hk/-/media/HKEX-Market/Services/Settlement-and-"
            b"Depository/USM/Listing-Information-Paper-and-Schedules-(20250602)(Final).pdf",
            1,
        ),
    ),
    lambda root, section: (
        root,
        section.replace(
            b"/sites/default/files/net_file_store/Update_154_Attachment.pdf",
            b"/sites/default/files/net_file_store///Update_154_Attachment.pdf",
            1,
        ),
    ),
)


@pytest.mark.parametrize("mutation", _HOSTILES)
def test_updates_hostiles_fail_closed_before_any_request_plan(
    mutation: Callable[[bytes, bytes], tuple[bytes, bytes]],
) -> None:
    root, section, root_url, section_url, static = _inputs(HKEXPublisherBoard.MAIN)
    root, section = mutation(root, section)
    with pytest.raises(ValueError, match="HKEX_UPDATES_MEMBERSHIP_INVALID"):
        parse_hkex_updates_membership(
            root,
            section,
            root_url=root_url,
            complete_section_url=section_url,
            board=HKEXPublisherBoard.MAIN,
            capture_id_by_url=static,
        )
