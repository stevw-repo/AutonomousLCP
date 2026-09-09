"""Pure positional HKEX Rule Updates membership parser."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

from .hk_regulatory_official import HKEXPublisherBoard
from .hkex_dom import (
    HKEXAttachmentOccurrence,
    HKEXAuthorityClass,
    HKEXFetchDisposition,
    HKEXLocatorKind,
    HKEXLocatorNormalization,
    HKEXMembershipAssociation,
    HKEXMembershipRelation,
    HKEXRoleMembershipPlan,
    HKEXUpdateMember,
    HKEXUpdatePosition,
    build_hkex_attachment_occurrence,
    build_hkex_membership_association,
    parse_hkex_root_structure,
    parse_hkex_update_section_structure,
    require_hkex_raw_locator,
    resolve_hkex_capture_endpoint_id,
)

_SOURCE_ID = "HK-REG-HKEX-RULE-UPDATES"
_ORIGIN = "https://en-rules.hkex.com.hk"
_ROOT_BY_BOARD = {
    HKEXPublisherBoard.MAIN: "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules",
    HKEXPublisherBoard.GEM: "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules",
}
_SECTION_BY_BOARD = {
    HKEXPublisherBoard.MAIN: "https://en-rules.hkex.com.hk/entiresection/2",
    HKEXPublisherBoard.GEM: "https://en-rules.hkex.com.hk/entiresection/49",
}
_STATIC_TARGET_BY_BOARD = {
    HKEXPublisherBoard.MAIN: (
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_154_Attachment.pdf"
    ),
    HKEXPublisherBoard.GEM: (
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_87_Attachment.pdf"
    ),
}
_PREFIX_DOUBLE = "/sites/default/files/net_file_store//"
_PREFIX_SINGLE = "/sites/default/files/net_file_store/"


def _require(*, condition: bool) -> None:
    if not condition:
        raise ValueError


def _required_member(
    members: Mapping[HKEXUpdatePosition, HKEXUpdateMember],
    position: HKEXUpdatePosition,
) -> HKEXUpdateMember:
    member = members.get(position)
    if member is None:
        raise ValueError
    return member


def _external_reference(raw: str) -> str:
    if type(raw) is not str or not raw or not raw.isascii():
        raise ValueError
    if any(character.isspace() or not character.isprintable() for character in raw):
        raise ValueError
    if "%" in raw or "&" in raw or "\\" in raw or "?" in raw or "#" in raw:
        raise ValueError
    parsed = urlsplit(raw)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError from error
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.netloc != parsed.netloc.lower()
        or parsed.hostname in {None, "en-rules.hkex.com.hk"}
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path.endswith(".pdf")
        or any(segment in {"", ".", ".."} for segment in parsed.path.removeprefix("/").split("/"))
        or urlunsplit(parsed) != raw
        or (parsed.scheme == "http" and parsed.hostname != "www.hkex.com.hk")
    ):
        raise ValueError
    return raw


def _attachment_target(
    raw_locator: str,
) -> tuple[str, HKEXLocatorNormalization, HKEXAuthorityClass, HKEXFetchDisposition]:
    if type(raw_locator) is not str or not raw_locator.isascii():
        raise ValueError
    trimmed = raw_locator.strip(" \t\r\n")
    trimmed_changed = trimmed != raw_locator
    if any(character.isspace() or not character.isprintable() for character in trimmed):
        raise ValueError
    collapsed_changed = False
    if _PREFIX_DOUBLE in trimmed:
        if trimmed.count(_PREFIX_DOUBLE) != 1:
            raise ValueError
        trimmed = trimmed.replace(_PREFIX_DOUBLE, _PREFIX_SINGLE, 1)
        collapsed_changed = True
    if trimmed.startswith(("/", _ORIGIN + "/")):
        target = require_hkex_raw_locator(trimmed, kind=HKEXLocatorKind.ATTACHMENT)
        normalization = {
            (False, False): HKEXLocatorNormalization.NONE,
            (True, False): HKEXLocatorNormalization.TRIM_ASCII_EDGE,
            (False, True): HKEXLocatorNormalization.COLLAPSE_ADMITTED_PREFIX_SLASH,
            (True, True): HKEXLocatorNormalization.TRIM_AND_COLLAPSE,
        }[(trimmed_changed, collapsed_changed)]
        return (
            target,
            normalization,
            HKEXAuthorityClass.SAME_HOST_ADMITTED,
            HKEXFetchDisposition.PLANNED_OR_REUSED,
        )
    if trimmed_changed or collapsed_changed:
        raise ValueError
    return (
        _external_reference(trimmed),
        HKEXLocatorNormalization.NONE,
        HKEXAuthorityClass.EXTERNAL_AUTHORITY_REQUIRED,
        HKEXFetchDisposition.UNFETCHED_EXTERNAL_REFERENCE,
    )


def parse_hkex_updates_membership(  # noqa: PLR0913 - mirrors the frozen pure interface
    root_body: bytes,
    complete_section_body: bytes,
    *,
    root_url: str,
    complete_section_url: str,
    board: HKEXPublisherBoard,
    capture_id_by_url: Mapping[str, str],
) -> HKEXRoleMembershipPlan:
    """Reconcile the exact root tree with positional section attachment ownership."""
    try:
        _require(
            condition=type(board) is HKEXPublisherBoard
            and _ROOT_BY_BOARD.get(board) == root_url
            and _SECTION_BY_BOARD.get(board) == complete_section_url
        )
        root = parse_hkex_root_structure(root_body, root_url=root_url)
        members = root.update_members
        _require(
            condition=bool(members) and len({item.target_url for item in members}) == len(members)
        )
        section = parse_hkex_update_section_structure(complete_section_body)
        root_vector = tuple(
            sum(
                item.position.container_order == container_order
                and item.position.relation is HKEXMembershipRelation.UPDATE_PAGE
                for item in members
            )
            for container_order in range(
                sum(
                    item.position.relation is HKEXMembershipRelation.UPDATE_CONTAINER
                    for item in members
                )
            )
        )
        _require(condition=section.child_count_vector == root_vector)
        member_by_position = {item.position: item for item in members}
        hierarchy: list[HKEXMembershipAssociation] = []
        container_url_by_order: dict[int, str] = {}
        for source_order, member in enumerate(members):
            if member.position.relation is HKEXMembershipRelation.UPDATE_CONTAINER:
                parent_url = root_url
                container_url_by_order[member.position.container_order] = member.target_url
            else:
                parent_url = container_url_by_order[member.position.container_order]
            hierarchy.append(
                build_hkex_membership_association(
                    source_id=_SOURCE_ID,
                    board=board,
                    relation=member.position.relation,
                    parent_url=parent_url,
                    target_url=member.target_url,
                    source_order=source_order,
                    occurrence_ids=(),
                    authority_class=HKEXAuthorityClass.SAME_HOST_ADMITTED,
                    fetch_disposition=HKEXFetchDisposition.SEMANTIC_ONLY,
                    capture_endpoint_id=None,
                )
            )
        occurrences: list[HKEXAttachmentOccurrence] = []
        grouped: dict[tuple[str, str, HKEXAuthorityClass, HKEXFetchDisposition], list[str]] = (
            defaultdict(list)
        )
        for slot in section.attachment_slots:
            parent = _required_member(member_by_position, slot.parent_position)
            target, normalization, authority, disposition = _attachment_target(slot.raw_locator)
            occurrence = build_hkex_attachment_occurrence(
                source_id=_SOURCE_ID,
                board=board,
                parent_relation=HKEXMembershipRelation.UPDATE_PAGE,
                parent_url=parent.target_url,
                parent_position=slot.parent_position,
                occurrence_order=slot.occurrence_order,
                raw_locator=slot.raw_locator,
                normalization_code=normalization,
                target_url=target,
                authority_class=authority,
                fetch_disposition=disposition,
            )
            occurrences.append(occurrence)
            grouped[(parent.target_url, target, authority, disposition)].append(
                occurrence.occurrence_id
            )
        attachments: list[HKEXMembershipAssociation] = []
        for source_order, (key, occurrence_ids) in enumerate(grouped.items(), start=len(hierarchy)):
            parent_url, target_url, authority, disposition = key
            capture_id = (
                resolve_hkex_capture_endpoint_id(
                    target_url,
                    media_type="application/pdf",
                    capture_id_by_url=capture_id_by_url,
                )
                if authority is HKEXAuthorityClass.SAME_HOST_ADMITTED
                else None
            )
            attachments.append(
                build_hkex_membership_association(
                    source_id=_SOURCE_ID,
                    board=board,
                    relation=HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF,
                    parent_url=parent_url,
                    target_url=target_url,
                    source_order=source_order,
                    occurrence_ids=tuple(occurrence_ids),
                    authority_class=authority,
                    fetch_disposition=disposition,
                    capture_endpoint_id=capture_id,
                )
            )
        _require(
            condition=any(item.target_url == _STATIC_TARGET_BY_BOARD[board] for item in attachments)
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("HKEX_UPDATES_MEMBERSHIP_INVALID") from error
    return HKEXRoleMembershipPlan(
        root.identity,
        (*hierarchy, *attachments),
        tuple(occurrences),
    )
