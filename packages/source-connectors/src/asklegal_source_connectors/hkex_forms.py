"""Pure role-aware HKEX Regulatory Forms membership parsers."""

from __future__ import annotations

import re
from collections.abc import Mapping

from .hk_regulatory_official import HKEXPublisherBoard
from .hkex_dom import (
    HKEXAuthorityClass,
    HKEXFetchDisposition,
    HKEXFormMemberCapture,
    HKEXLocatorKind,
    HKEXMembershipRelation,
    HKEXRoleMembershipPlan,
    build_hkex_membership_association,
    parse_hkex_complete_section_identity,
    parse_hkex_dedicated_pdf_slots,
    parse_hkex_form_member_identity,
    parse_hkex_root_structure,
    require_hkex_raw_locator,
    resolve_hkex_capture_endpoint_id,
)

_SOURCE_ID = "HK-REG-HKEX-REGULATORY-FORMS"
_ROOT_BY_BOARD = {
    HKEXPublisherBoard.MAIN: "https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
    HKEXPublisherBoard.GEM: "https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms",
}
_SECTION_BY_BOARD = {
    HKEXPublisherBoard.MAIN: "https://en-rules.hkex.com.hk/entiresection/6190",
    HKEXPublisherBoard.GEM: "https://en-rules.hkex.com.hk/entiresection/6191",
}
_NODES_BY_BOARD = {
    HKEXPublisherBoard.MAIN: frozenset(
        {"3756", "3757", "3759", "3760", "3761", "3762", "3763", "3764", "3765", "3766"}
    ),
    HKEXPublisherBoard.GEM: frozenset({"1812", "1813", "1814", "1815", "1831", "1816", "1817"}),
}


def _require(*, condition: bool) -> None:
    if not condition:
        raise ValueError


def parse_hkex_forms_membership(  # noqa: PLR0913 - mirrors the frozen pure interface
    root_body: bytes,
    complete_section_body: bytes,
    *,
    root_url: str,
    complete_section_url: str,
    board: HKEXPublisherBoard,
    capture_id_by_url: Mapping[str, str],
) -> HKEXRoleMembershipPlan:
    """Emit only the exact ordered Forms node tier from one role root."""
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
        _require(
            condition=section.node_id == root.identity.node_id
            and bool(root.form_node_urls)
            and frozenset(url.rsplit("/", 1)[1] for url in root.form_node_urls)
            == _NODES_BY_BOARD[board]
        )
        associations = tuple(
            build_hkex_membership_association(
                source_id=_SOURCE_ID,
                board=board,
                relation=HKEXMembershipRelation.FORM_NODE,
                parent_url=root_url,
                target_url=target_url,
                source_order=source_order,
                occurrence_ids=(),
                authority_class=HKEXAuthorityClass.SAME_HOST_ADMITTED,
                fetch_disposition=HKEXFetchDisposition.PLANNED_OR_REUSED,
                capture_endpoint_id=resolve_hkex_capture_endpoint_id(
                    target_url,
                    media_type="text/html",
                    capture_id_by_url=capture_id_by_url,
                ),
            )
            for source_order, target_url in enumerate(root.form_node_urls)
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("HKEX_FORMS_MEMBERSHIP_INVALID") from error
    return HKEXRoleMembershipPlan(root.identity, associations, ())


def parse_hkex_form_member(
    body: bytes,
    *,
    requested_node_url: str,
    final_url: str,
    board: HKEXPublisherBoard,
    capture_id_by_url: Mapping[str, str],
) -> HKEXFormMemberCapture:
    """Emit the one exact node-bound PDF from a coherent redirected member page."""
    try:
        _require(condition=type(board) is HKEXPublisherBoard)
        identity = parse_hkex_form_member_identity(
            body, requested_node_url=requested_node_url, final_url=final_url
        )
        _require(condition=identity.node_id in _NODES_BY_BOARD[board])
        slots = parse_hkex_dedicated_pdf_slots(body)
        _require(condition=len(slots) == 1)
        target_url = require_hkex_raw_locator(slots[0].raw_locator, kind=HKEXLocatorKind.ATTACHMENT)
        filename = target_url.rsplit("/", 1)[1]
        _require(
            condition=re.fullmatch(
                rf"HKEX4476_{re.escape(identity.node_id)}_VER[1-9][0-9]*\.pdf", filename
            )
            is not None
        )
        association = build_hkex_membership_association(
            source_id=_SOURCE_ID,
            board=board,
            relation=HKEXMembershipRelation.FORM_PDF,
            parent_url=requested_node_url,
            target_url=target_url,
            source_order=0,
            occurrence_ids=(),
            authority_class=HKEXAuthorityClass.SAME_HOST_ADMITTED,
            fetch_disposition=HKEXFetchDisposition.PLANNED_OR_REUSED,
            capture_endpoint_id=resolve_hkex_capture_endpoint_id(
                target_url,
                media_type="application/pdf",
                capture_id_by_url=capture_id_by_url,
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("HKEX_FORM_MEMBER_INVALID") from error
    return HKEXFormMemberCapture(identity, requested_node_url, final_url, (association,))
