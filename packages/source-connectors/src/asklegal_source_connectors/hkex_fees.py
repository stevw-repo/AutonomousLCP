"""Pure role-aware HKEX Fees membership parser."""

from __future__ import annotations

from collections.abc import Mapping

from .hk_regulatory_official import HKEXPublisherBoard
from .hkex_dom import (
    HKEXAuthorityClass,
    HKEXFetchDisposition,
    HKEXLocatorKind,
    HKEXMembershipRelation,
    HKEXRoleMembershipPlan,
    build_hkex_membership_association,
    parse_hkex_complete_section_identity,
    parse_hkex_dedicated_pdf_slots,
    parse_hkex_root_structure,
    require_hkex_raw_locator,
    resolve_hkex_capture_endpoint_id,
)

_SOURCE_ID = "HK-REG-HKEX-FEES-RULES"
_ROOT_BY_BOARD = {
    HKEXPublisherBoard.MAIN: "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
    HKEXPublisherBoard.GEM: "https://en-rules.hkex.com.hk/rulebook/gem-fees-rules",
}
_SECTION_BY_BOARD = {
    HKEXPublisherBoard.MAIN: "https://en-rules.hkex.com.hk/entiresection/3783",
    HKEXPublisherBoard.GEM: "https://en-rules.hkex.com.hk/entiresection/1836",
}


def _require(*, condition: bool) -> None:
    if not condition:
        raise ValueError


def parse_hkex_fees_membership(  # noqa: PLR0913 - mirrors the frozen pure interface
    root_body: bytes,
    complete_section_body: bytes,
    *,
    root_url: str,
    complete_section_url: str,
    board: HKEXPublisherBoard,
    capture_id_by_url: Mapping[str, str],
) -> HKEXRoleMembershipPlan:
    """Require one exact root-owned Fees PDF and structural section corroboration."""
    try:
        _require(
            condition=type(board) is HKEXPublisherBoard
            and _ROOT_BY_BOARD.get(board) == root_url
            and _SECTION_BY_BOARD.get(board) == complete_section_url
        )
        root = parse_hkex_root_structure(root_body, root_url=root_url)
        section = parse_hkex_complete_section_identity(
            complete_section_body, section_url=complete_section_url
        )
        _require(condition=section.node_id == root.identity.node_id)
        slots = parse_hkex_dedicated_pdf_slots(root_body)
        _require(condition=len(slots) == 1)
        target_url = require_hkex_raw_locator(slots[0].raw_locator, kind=HKEXLocatorKind.ATTACHMENT)
        capture_id = resolve_hkex_capture_endpoint_id(
            target_url,
            media_type="application/pdf",
            capture_id_by_url=capture_id_by_url,
        )
        association = build_hkex_membership_association(
            source_id=_SOURCE_ID,
            board=board,
            relation=HKEXMembershipRelation.FEES_PDF,
            parent_url=root_url,
            target_url=target_url,
            source_order=0,
            occurrence_ids=(),
            authority_class=HKEXAuthorityClass.SAME_HOST_ADMITTED,
            fetch_disposition=HKEXFetchDisposition.PLANNED_OR_REUSED,
            capture_endpoint_id=capture_id,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("HKEX_FEES_MEMBERSHIP_INVALID") from error
    return HKEXRoleMembershipPlan(root.identity, (association,), ())
