"""Bounded, text-free HKEX role DOM and locator contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

from .hk_regulatory_official import HKEXPublisherBoard

_HKEX_ORIGIN = "https://en-rules.hkex.com.hk"
_MAX_HTML_BYTES = 33_554_432
_MAX_DOM_NODES = 100_000
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_RAW_ATTRIBUTE = re.compile(
    r"(?:^|\s)(?P<name>[A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s\"'=<>`]+))"
)
_POSITIVE_DECIMAL = re.compile(r"[1-9][0-9]*\Z")
_FORM_NODE_PATH = re.compile(r"/node/[1-9][0-9]*\Z")
_ROLE_MEMBER_PATH = re.compile(r"/rulebook/[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_ATTACHMENT_PATH = re.compile(
    r"/sites/default/files/net_file_store/[A-Za-z0-9][A-Za-z0-9._-]*\.pdf\Z"
)
_SECTION_PATH = re.compile(r"/entiresection/[1-9][0-9]*\Z")

_ROOT_NODE_BY_URL = {
    "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules": "3783",
    "https://en-rules.hkex.com.hk/rulebook/gem-fees-rules": "1836",
    "https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms": "6190",
    "https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms": "6191",
    "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules": "2",
    "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules": "49",
}
_FORM_NODES_BY_ROOT = {
    "https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms": (
        "3756",
        "3757",
        "3759",
        "3760",
        "3761",
        "3762",
        "3763",
        "3764",
        "3765",
        "3766",
    ),
    "https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms": (
        "1812",
        "1813",
        "1814",
        "1815",
        "1831",
        "1816",
        "1817",
    ),
}


class HKEXMembershipRelation(StrEnum):
    """Closed relationship kinds emitted by role parsers."""

    FEES_PDF = "FEES_PDF"
    FORM_NODE = "FORM_NODE"
    FORM_PDF = "FORM_PDF"
    UPDATE_CONTAINER = "UPDATE_CONTAINER"
    UPDATE_PAGE = "UPDATE_PAGE"
    UPDATE_ATTACHMENT_PDF = "UPDATE_ATTACHMENT_PDF"


class HKEXAuthorityClass(StrEnum):
    """Whether a target is admitted on-host or needs separate authority."""

    SAME_HOST_ADMITTED = "SAME_HOST_ADMITTED"
    EXTERNAL_AUTHORITY_REQUIRED = "EXTERNAL_AUTHORITY_REQUIRED"


class HKEXFetchDisposition(StrEnum):
    """Whether a relationship has or can produce a capture."""

    SEMANTIC_ONLY = "SEMANTIC_ONLY"
    PLANNED_OR_REUSED = "PLANNED_OR_REUSED"
    UNFETCHED_EXTERNAL_REFERENCE = "UNFETCHED_EXTERNAL_REFERENCE"


class HKEXLocatorNormalization(StrEnum):
    """Closed Updates-only raw-locator normalization codes."""

    NONE = "NONE"
    TRIM_ASCII_EDGE = "TRIM_ASCII_EDGE"
    COLLAPSE_ADMITTED_PREFIX_SLASH = "COLLAPSE_ADMITTED_PREFIX_SLASH"
    TRIM_AND_COLLAPSE = "TRIM_AND_COLLAPSE"


class HKEXLocatorKind(StrEnum):
    """Closed ordinary same-host locator grammars."""

    FORM_NODE = "FORM_NODE"
    ROLE_MEMBER = "ROLE_MEMBER"
    ATTACHMENT = "ATTACHMENT"


@dataclass(frozen=True, slots=True)
class HKEXRootIdentity:
    """Exact canonical, shortlink, article-node, and complete-section identity."""

    canonical_url: str
    shortlink_url: str
    node_id: str
    entire_section_url: str


@dataclass(frozen=True, slots=True)
class HKEXUpdatePosition:
    """One exact zero-based position in the two-level Updates tree."""

    container_order: int
    child_order: int | None
    relation: HKEXMembershipRelation

    def __post_init__(self) -> None:
        if type(self.container_order) is not int or self.container_order < 0:
            raise ValueError("HKEX_UPDATE_POSITION_INVALID")
        if self.relation is HKEXMembershipRelation.UPDATE_CONTAINER:
            if self.child_order is not None:
                raise ValueError("HKEX_UPDATE_POSITION_INVALID")
        elif self.relation is HKEXMembershipRelation.UPDATE_PAGE:
            if type(self.child_order) is not int or self.child_order < 0:
                raise ValueError("HKEX_UPDATE_POSITION_INVALID")
        else:
            raise ValueError("HKEX_UPDATE_POSITION_INVALID")


@dataclass(frozen=True, slots=True)
class HKEXUpdateMember:
    """One text-free Updates hierarchy target and its exact position."""

    target_url: str
    position: HKEXUpdatePosition


@dataclass(frozen=True, slots=True)
class HKEXUpdateAttachmentSlot:
    """One raw PDF locator owned by an exact Updates page position."""

    parent_position: HKEXUpdatePosition
    occurrence_order: int
    raw_locator: str


@dataclass(frozen=True, slots=True)
class HKEXUpdateSectionStructure:
    """Text-free positional shape and raw attachment slots from one section."""

    child_count_vector: tuple[int, ...]
    attachment_slots: tuple[HKEXUpdateAttachmentSlot, ...]


@dataclass(frozen=True, slots=True)
class HKEXRootStructure:
    """Text-free structural slots projected from one role root."""

    identity: HKEXRootIdentity
    fees_pdf_raw_locators: tuple[str, ...]
    form_node_urls: tuple[str, ...]
    update_members: tuple[HKEXUpdateMember, ...]


@dataclass(frozen=True, slots=True)
class HKEXCompleteSectionIdentity:
    """Structural identity of one Fees or Forms complete section."""

    section_url: str
    node_id: str


@dataclass(frozen=True, slots=True)
class HKEXDedicatedPDFSlot:
    """One exact page-owned associated-PDF anchor without display text."""

    raw_locator: str
    classes: tuple[str, ...]
    title: str
    target: str


@dataclass(frozen=True, slots=True)
class HKEXMembershipAssociation:
    """One checked role/board/parent relationship to a target."""

    association_id: str
    source_id: str
    board: HKEXPublisherBoard
    relation: HKEXMembershipRelation
    parent_url: str
    target_url: str
    source_order: int
    occurrence_ids: tuple[str, ...]
    authority_class: HKEXAuthorityClass
    fetch_disposition: HKEXFetchDisposition
    capture_endpoint_id: str | None


@dataclass(frozen=True, slots=True)
class HKEXAttachmentOccurrence:
    """One retained raw Updates attachment occurrence."""

    occurrence_id: str
    source_id: str
    board: HKEXPublisherBoard
    parent_relation: HKEXMembershipRelation
    parent_url: str
    parent_position: HKEXUpdatePosition
    occurrence_order: int
    raw_locator: str
    normalization_code: HKEXLocatorNormalization
    target_url: str
    authority_class: HKEXAuthorityClass
    fetch_disposition: HKEXFetchDisposition


@dataclass(frozen=True, slots=True)
class HKEXRoleMembershipPlan:
    """One pure role parser's complete ordered membership projection."""

    identity: HKEXRootIdentity
    associations: tuple[HKEXMembershipAssociation, ...]
    attachment_occurrences: tuple[HKEXAttachmentOccurrence, ...]


@dataclass(frozen=True, slots=True)
class HKEXFormMemberCapture:
    """One Forms member identity and its checked dedicated PDF association."""

    identity: HKEXRootIdentity
    requested_node_url: str
    final_url: str
    associations: tuple[HKEXMembershipAssociation, ...]


def _node_children() -> list[_Node]:
    return []


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str | None]
    raw_attrs: dict[str, str]
    children: list[_Node] = field(default_factory=_node_children)
    parent: _Node | None = None

    def has_class(self, value: str) -> bool:
        return value in (self.attrs.get("class") or "").split()


class _InertTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = _Node("__root__", {}, {})
        self.stack = [self.root]
        self.node_count = 0
        self.identifiers: set[str] = set()
        self.invalid = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        start_tag = self.get_starttag_text()
        if start_tag is None:
            self.invalid = True
            start_tag = ""
        raw_attrs = _raw_attributes(start_tag)
        names = [name.lower() for name, _ in attrs]
        if len(names) != len(set(names)):
            self.invalid = True
        values = {name.lower(): value for name, value in attrs}
        identifier = values.get("id")
        if identifier is not None:
            if identifier in self.identifiers:
                self.invalid = True
            self.identifiers.add(identifier)
        node = _Node(lowered, values, raw_attrs, parent=self.stack[-1])
        self.stack[-1].children.append(node)
        self.node_count += 1
        if self.node_count > _MAX_DOM_NODES:
            self.invalid = True
        if lowered not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in _VOID_TAGS:
            return
        if len(self.stack) == 1 or self.stack[-1].tag != lowered:
            self.invalid = True
            return
        self.stack.pop()

    def finish(self) -> _Node:
        self.close()
        if len(self.stack) != 1 or self.invalid:
            raise ValueError("HKEX_DOM_INVALID")
        return self.root


def _raw_attributes(start_tag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in _RAW_ATTRIBUTE.finditer(start_tag):
        name = match.group("name").lower()
        value = match.group("double")
        if value is None:
            value = match.group("single")
        if value is None:
            value = match.group("bare")
        if name in result or value is None:
            continue
        result[name] = value
    return result


def _parse(body: bytes) -> _Node:
    if type(body) is not bytes or not body or len(body) > _MAX_HTML_BYTES or b"\x00" in body:
        raise ValueError("HKEX_DOM_BYTES_INVALID")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("HKEX_DOM_ENCODING_INVALID") from error
    parser = _InertTreeParser()
    try:
        parser.feed(text)
        return parser.finish()
    except (ValueError, AssertionError) as error:
        if isinstance(error, ValueError) and str(error) == "HKEX_DOM_INVALID":
            raise
        raise ValueError("HKEX_DOM_INVALID") from error


def _walk(node: _Node) -> tuple[_Node, ...]:
    result: list[_Node] = []
    pending = list(reversed(node.children))
    while pending:
        current = pending.pop()
        result.append(current)
        pending.extend(reversed(current.children))
    return tuple(result)


def _active(node: _Node) -> bool:
    current: _Node | None = node
    while current is not None:
        if current.tag == "template" or "disabled" in current.attrs:
            return False
        current = current.parent
    return True


def _descendant_of(node: _Node, ancestor: _Node) -> bool:
    current = node.parent
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def _single(nodes: list[_Node], error_code: str) -> _Node:
    if len(nodes) != 1:
        raise ValueError(error_code)
    return nodes[0]


def _raw_href(node: _Node, error_code: str) -> str:
    decoded = node.attrs.get("href")
    raw = node.raw_attrs.get("href")
    if type(decoded) is not str or type(raw) is not str or raw != decoded:
        raise ValueError(error_code)
    return raw


def _absolute_same_host(raw: str, path_pattern: re.Pattern[str]) -> str:
    if type(raw) is not str or not raw or not raw.isascii():
        raise ValueError("HKEX_RAW_LOCATOR_INVALID")
    if (
        any(character.isspace() or not character.isprintable() for character in raw)
        or "&" in raw
        or "%" in raw
        or "\\" in raw
        or "?" in raw
        or "#" in raw
        or raw.startswith("//")
    ):
        raise ValueError("HKEX_RAW_LOCATOR_INVALID")
    if raw.startswith("/"):
        if not raw.startswith("/") or raw.startswith("//"):
            raise ValueError("HKEX_RAW_LOCATOR_INVALID")
        path = raw
        target = _HKEX_ORIGIN + raw
    elif raw.startswith(_HKEX_ORIGIN + "/"):
        target = raw
        parsed = urlsplit(raw)
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("HKEX_RAW_LOCATOR_INVALID") from error
        if (
            parsed.scheme != "https"
            or parsed.netloc != "en-rules.hkex.com.hk"
            or parsed.hostname != "en-rules.hkex.com.hk"
            or parsed.username is not None
            or parsed.password is not None
            or port is not None
            or parsed.query
            or parsed.fragment
            or urlunsplit(parsed) != raw
        ):
            raise ValueError("HKEX_RAW_LOCATOR_INVALID")
        path = parsed.path
    else:
        raise ValueError("HKEX_RAW_LOCATOR_INVALID")
    if path_pattern.fullmatch(path) is None or any(
        segment in {"", ".", ".."} for segment in path.removeprefix("/").split("/")
    ):
        raise ValueError("HKEX_RAW_LOCATOR_INVALID")
    return target


def require_hkex_raw_locator(raw_locator: str, *, kind: HKEXLocatorKind) -> str:
    """Validate an ordinary locator before any join or normalization."""
    if type(kind) is not HKEXLocatorKind:
        raise ValueError("HKEX_RAW_LOCATOR_INVALID")
    pattern = {
        HKEXLocatorKind.FORM_NODE: _FORM_NODE_PATH,
        HKEXLocatorKind.ROLE_MEMBER: _ROLE_MEMBER_PATH,
        HKEXLocatorKind.ATTACHMENT: _ATTACHMENT_PATH,
    }[kind]
    return _absolute_same_host(raw_locator, pattern)


def _section_url(raw_locator: str) -> str:
    return _absolute_same_host(raw_locator, _SECTION_PATH)


def parse_hkex_root_identity(body: bytes, *, root_url: str) -> HKEXRootIdentity:
    """Parse one exact registered HKEX role-root identity."""
    root = _parse(body)
    expected_node = _ROOT_NODE_BY_URL.get(root_url)
    if expected_node is None:
        raise ValueError("HKEX_ROOT_IDENTITY_INVALID")
    nodes = _walk(root)
    canonical = _single(
        [
            node
            for node in nodes
            if node.tag == "link"
            and node.attrs.get("rel") == "canonical"
            and node.parent is not None
            and node.parent.tag == "head"
            and _active(node)
        ],
        "HKEX_ROOT_IDENTITY_INVALID",
    )
    shortlink = _single(
        [
            node
            for node in nodes
            if node.tag == "link"
            and node.attrs.get("rel") == "shortlink"
            and node.parent is not None
            and node.parent.tag == "head"
            and _active(node)
        ],
        "HKEX_ROOT_IDENTITY_INVALID",
    )
    content = _single(
        [
            node
            for node in nodes
            if node.attrs.get("id") == "block-rulebook-content" and _active(node)
        ],
        "HKEX_ROOT_IDENTITY_INVALID",
    )
    articles = [
        node
        for node in nodes
        if node.tag == "article"
        and node.has_class("published")
        and node.attrs.get("data-history-node-id") == expected_node
        and _active(node)
        and _descendant_of(node, content)
    ]
    _single(articles, "HKEX_ROOT_IDENTITY_INVALID")
    header = _single(
        [node for node in nodes if node.attrs.get("id") == "block-headerblock-2" and _active(node)],
        "HKEX_ROOT_IDENTITY_INVALID",
    )
    toolbars = [
        node
        for node in nodes
        if node.tag == "table"
        and node.has_class("disp_toolbar")
        and _active(node)
        and _descendant_of(node, header)
    ]
    toolbar = _single(toolbars, "HKEX_ROOT_IDENTITY_INVALID")
    section_links = [
        node
        for node in _walk(toolbar)
        if node.tag == "a"
        and _active(node)
        and (node.attrs.get("href") or "").startswith(
            ("/entiresection/", _HKEX_ORIGIN + "/entiresection/")
        )
    ]
    section = _single(section_links, "HKEX_ROOT_IDENTITY_INVALID")
    try:
        canonical_url = _raw_href(canonical, "HKEX_ROOT_IDENTITY_INVALID")
        shortlink_url = require_hkex_raw_locator(
            _raw_href(shortlink, "HKEX_ROOT_IDENTITY_INVALID"), kind=HKEXLocatorKind.FORM_NODE
        )
        section_url = _section_url(_raw_href(section, "HKEX_ROOT_IDENTITY_INVALID"))
    except ValueError as error:
        raise ValueError("HKEX_ROOT_IDENTITY_INVALID") from error
    if (
        canonical_url != root_url
        or shortlink_url != f"{_HKEX_ORIGIN}/node/{expected_node}"
        or section_url != f"{_HKEX_ORIGIN}/entiresection/{expected_node}"
    ):
        raise ValueError("HKEX_ROOT_IDENTITY_INVALID")
    return HKEXRootIdentity(canonical_url, shortlink_url, expected_node, section_url)


def parse_hkex_form_member_identity(
    body: bytes, *, requested_node_url: str, final_url: str
) -> HKEXRootIdentity:
    """Require one redirected Forms member's coherent four-part page identity."""
    try:
        requested = require_hkex_raw_locator(requested_node_url, kind=HKEXLocatorKind.FORM_NODE)
        final = require_hkex_raw_locator(final_url, kind=HKEXLocatorKind.ROLE_MEMBER)
    except ValueError as error:
        raise ValueError("HKEX_FORM_MEMBER_IDENTITY_INVALID") from error
    if requested == final:
        raise ValueError("HKEX_FORM_MEMBER_IDENTITY_INVALID")
    node_id = requested.rsplit("/", 1)[1]
    root = _parse(body)
    nodes = _walk(root)
    canonical = _single(
        [
            node
            for node in nodes
            if node.tag == "link"
            and node.attrs.get("rel") == "canonical"
            and node.parent is not None
            and node.parent.tag == "head"
            and _active(node)
        ],
        "HKEX_FORM_MEMBER_IDENTITY_INVALID",
    )
    shortlink = _single(
        [
            node
            for node in nodes
            if node.tag == "link"
            and node.attrs.get("rel") == "shortlink"
            and node.parent is not None
            and node.parent.tag == "head"
            and _active(node)
        ],
        "HKEX_FORM_MEMBER_IDENTITY_INVALID",
    )
    content = _single(
        [
            node
            for node in nodes
            if node.attrs.get("id") == "block-rulebook-content" and _active(node)
        ],
        "HKEX_FORM_MEMBER_IDENTITY_INVALID",
    )
    _single(
        [
            node
            for node in nodes
            if node.tag == "article"
            and node.has_class("published")
            and node.attrs.get("data-history-node-id") == node_id
            and _active(node)
            and _descendant_of(node, content)
        ],
        "HKEX_FORM_MEMBER_IDENTITY_INVALID",
    )
    header = _single(
        [node for node in nodes if node.attrs.get("id") == "block-headerblock-2" and _active(node)],
        "HKEX_FORM_MEMBER_IDENTITY_INVALID",
    )
    toolbar = _single(
        [
            node
            for node in _walk(header)
            if node.tag == "table" and node.has_class("disp_toolbar") and _active(node)
        ],
        "HKEX_FORM_MEMBER_IDENTITY_INVALID",
    )
    section = _single(
        [
            node
            for node in _walk(toolbar)
            if node.tag == "a"
            and node.attrs.get("href")
            in {f"/entiresection/{node_id}", f"{_HKEX_ORIGIN}/entiresection/{node_id}"}
        ],
        "HKEX_FORM_MEMBER_IDENTITY_INVALID",
    )
    try:
        canonical_raw = _raw_href(canonical, "HKEX_FORM_MEMBER_IDENTITY_INVALID")
        shortlink_url = require_hkex_raw_locator(
            _raw_href(shortlink, "HKEX_FORM_MEMBER_IDENTITY_INVALID"),
            kind=HKEXLocatorKind.FORM_NODE,
        )
        section_url = _section_url(_raw_href(section, "HKEX_FORM_MEMBER_IDENTITY_INVALID"))
    except ValueError as error:
        raise ValueError("HKEX_FORM_MEMBER_IDENTITY_INVALID") from error
    if (
        canonical_raw != final
        or shortlink_url != requested
        or section_url != f"{_HKEX_ORIGIN}/entiresection/{node_id}"
    ):
        raise ValueError("HKEX_FORM_MEMBER_IDENTITY_INVALID")
    return HKEXRootIdentity(final, requested, node_id, section_url)


def _update_members(root: _Node, *, root_url: str) -> tuple[HKEXUpdateMember, ...]:
    if root_url not in {
        "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules",
        "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules",
    }:
        return ()
    navigation = _single(
        [
            node
            for node in _walk(root)
            if node.attrs.get("id") == "book-navigation-1" and _active(node)
        ],
        "HKEX_UPDATE_TREE_INVALID",
    )
    top_lists = [
        node for node in navigation.children if node.tag == "ul" and node.has_class("menu")
    ]
    top_list = _single(top_lists, "HKEX_UPDATE_TREE_INVALID")
    members: list[HKEXUpdateMember] = []
    containers = [node for node in top_list.children if node.tag == "li"]
    if len(containers) != len(top_list.children):
        raise ValueError("HKEX_UPDATE_TREE_INVALID")
    for container_order, container in enumerate(containers):
        direct_anchors = [node for node in container.children if node.tag == "a"]
        container_anchor = _single(direct_anchors, "HKEX_UPDATE_TREE_INVALID")
        try:
            container_url = require_hkex_raw_locator(
                _raw_href(container_anchor, "HKEX_UPDATE_TREE_INVALID"),
                kind=HKEXLocatorKind.ROLE_MEMBER,
            )
        except ValueError as error:
            raise ValueError("HKEX_UPDATE_TREE_INVALID") from error
        members.append(
            HKEXUpdateMember(
                container_url,
                HKEXUpdatePosition(container_order, None, HKEXMembershipRelation.UPDATE_CONTAINER),
            )
        )
        child_lists = [node for node in container.children if node.tag == "ul"]
        child_list = _single(child_lists, "HKEX_UPDATE_TREE_INVALID")
        pages = [node for node in child_list.children if node.tag == "li"]
        if not pages or len(pages) != len(child_list.children):
            raise ValueError("HKEX_UPDATE_TREE_INVALID")
        for child_order, page in enumerate(pages):
            page_anchor = _single(
                [node for node in page.children if node.tag == "a"], "HKEX_UPDATE_TREE_INVALID"
            )
            if any(node.tag == "ul" for node in page.children):
                raise ValueError("HKEX_UPDATE_TREE_INVALID")
            try:
                page_url = require_hkex_raw_locator(
                    _raw_href(page_anchor, "HKEX_UPDATE_TREE_INVALID"),
                    kind=HKEXLocatorKind.ROLE_MEMBER,
                )
            except ValueError as error:
                raise ValueError("HKEX_UPDATE_TREE_INVALID") from error
            members.append(
                HKEXUpdateMember(
                    page_url,
                    HKEXUpdatePosition(
                        container_order, child_order, HKEXMembershipRelation.UPDATE_PAGE
                    ),
                )
            )
    return tuple(members)


def parse_hkex_root_structure(body: bytes, *, root_url: str) -> HKEXRootStructure:
    """Return the exact text-free identity and role-root structural slots."""
    identity = parse_hkex_root_identity(body, root_url=root_url)
    root = _parse(body)
    nodes = _walk(root)
    fees_blocks = [
        node
        for node in nodes
        if node.attrs.get("id") == "block-associatedpdfblock" and _active(node)
    ]
    fees_pdf_raw_locators: tuple[str, ...] = ()
    if fees_blocks:
        block = _single(fees_blocks, "HKEX_FEES_BLOCK_INVALID")
        fees_pdf_raw_locators = tuple(
            _raw_href(node, "HKEX_FEES_BLOCK_INVALID")
            for node in _walk(block)
            if node.tag == "a" and (node.attrs.get("href") or "").lower().endswith(".pdf")
        )
    expected_form_nodes = _FORM_NODES_BY_ROOT.get(root_url, ())
    form_node_urls: tuple[str, ...] = ()
    if expected_form_nodes:
        content = _single(
            [
                node
                for node in nodes
                if node.attrs.get("id") == "block-rulebook-content" and _active(node)
            ],
            "HKEX_FORM_ROOT_INVALID",
        )
        candidates: list[str] = []
        expected_urls = {f"{_HKEX_ORIGIN}/node/{node_id}" for node_id in expected_form_nodes}
        for node in _walk(content):
            if node.tag != "a" or not _active(node):
                continue
            raw = node.attrs.get("href")
            if not isinstance(raw, str) or not raw.startswith(("/node/", _HKEX_ORIGIN + "/node/")):
                continue
            try:
                target = require_hkex_raw_locator(
                    _raw_href(node, "HKEX_FORM_ROOT_INVALID"), kind=HKEXLocatorKind.FORM_NODE
                )
            except ValueError as error:
                raise ValueError("HKEX_FORM_ROOT_INVALID") from error
            if target in expected_urls:
                candidates.append(target)
        expected_order = tuple(f"{_HKEX_ORIGIN}/node/{node_id}" for node_id in expected_form_nodes)
        if tuple(candidates) != expected_order:
            raise ValueError("HKEX_FORM_ROOT_INVALID")
        form_node_urls = expected_order
    return HKEXRootStructure(
        identity, fees_pdf_raw_locators, form_node_urls, _update_members(root, root_url=root_url)
    )


def parse_hkex_complete_section_identity(
    body: bytes, *, section_url: str
) -> HKEXCompleteSectionIdentity:
    """Validate a Fees/Forms complete section as structural corroboration only."""
    try:
        canonical_section = _section_url(section_url)
    except ValueError as error:
        raise ValueError("HKEX_SECTION_IDENTITY_INVALID") from error
    node_id = canonical_section.rsplit("/", 1)[1]
    root = _parse(body)
    nodes = _walk(root)
    if any(
        node.tag == "link" and node.attrs.get("rel") in {"canonical", "shortlink"} for node in nodes
    ):
        raise ValueError("HKEX_SECTION_IDENTITY_INVALID")
    breadcrumbs = [
        node
        for node in nodes
        if node.tag == "nav" and node.has_class("breadcrumb") and _active(node)
    ]
    breadcrumb = _single(breadcrumbs, "HKEX_SECTION_IDENTITY_INVALID")
    self_links = [
        node
        for node in _walk(breadcrumb)
        if node.tag == "a"
        and _active(node)
        and node.attrs.get("href") in {f"/entiresection/{node_id}", canonical_section}
    ]
    _single(self_links, "HKEX_SECTION_IDENTITY_INVALID")
    header = _single(
        [node for node in nodes if node.attrs.get("id") == "block-headerblock-2" and _active(node)],
        "HKEX_SECTION_IDENTITY_INVALID",
    )
    toolbar = _single(
        [node for node in _walk(header) if node.tag == "table" and node.has_class("disp_toolbar")],
        "HKEX_SECTION_IDENTITY_INVALID",
    )
    node_links = [
        node
        for node in _walk(toolbar)
        if node.tag == "a"
        and node.attrs.get("href") in {f"/node/{node_id}", f"{_HKEX_ORIGIN}/node/{node_id}"}
    ]
    _single(node_links, "HKEX_SECTION_IDENTITY_INVALID")
    _single(
        [node for node in nodes if node.attrs.get("id") == "viewall" and _active(node)],
        "HKEX_SECTION_IDENTITY_INVALID",
    )
    if any(
        node.tag == "a"
        and isinstance(node.attrs.get("href"), str)
        and ".pdf" in (node.attrs["href"] or "").lower()
        for node in nodes
    ):
        raise ValueError("HKEX_SECTION_IDENTITY_INVALID")
    return HKEXCompleteSectionIdentity(canonical_section, node_id)


def parse_hkex_dedicated_pdf_slots(body: bytes) -> tuple[HKEXDedicatedPDFSlot, ...]:
    """Parse the one active page-owned associated-PDF block."""
    root = _parse(body)
    nodes = _walk(root)
    blocks = [
        node
        for node in nodes
        if node.attrs.get("id") == "block-associatedpdfblock" and _active(node)
    ]
    block = _single(blocks, "HKEX_DEDICATED_PDF_BLOCK_INVALID")
    current = block.parent
    while current is not None:
        if current.tag in {"article", "nav"}:
            raise ValueError("HKEX_DEDICATED_PDF_BLOCK_INVALID")
        current = current.parent
    anchors = [node for node in _walk(block) if node.tag == "a" and _active(node)]
    if len(anchors) != 1:
        raise ValueError("HKEX_DEDICATED_PDF_BLOCK_INVALID")
    anchor = anchors[0]
    classes = tuple((anchor.attrs.get("class") or "").split())
    title = anchor.attrs.get("title")
    target = anchor.attrs.get("target")
    if classes != ("submenu", "icopdf") or title != "View Current PDF" or target != "_blank":
        raise ValueError("HKEX_DEDICATED_PDF_BLOCK_INVALID")
    raw_locator = _raw_href(anchor, "HKEX_DEDICATED_PDF_BLOCK_INVALID")
    return (HKEXDedicatedPDFSlot(raw_locator, classes, title, target),)


def _ul_depth(node: _Node, *, viewall: _Node) -> int:
    depth = 0
    current = node.parent
    while current is not None and current is not viewall:
        if current.tag == "ul":
            depth += 1
        current = current.parent
    if current is not viewall:
        raise ValueError("HKEX_UPDATE_SECTION_INVALID")
    return depth


def _nearest_ul(node: _Node, *, viewall: _Node) -> _Node | None:
    current = node.parent
    while current is not None and current is not viewall:
        if current.tag == "ul":
            return current
        current = current.parent
    return None


def parse_hkex_update_section_structure(body: bytes) -> HKEXUpdateSectionStructure:
    """Parse exact two-level section ownership without using link text or node IDs."""
    root = _parse(body)
    nodes = _walk(root)
    viewall = _single(
        [node for node in nodes if node.attrs.get("id") == "viewall" and _active(node)],
        "HKEX_UPDATE_SECTION_INVALID",
    )
    lists = [node for node in _walk(viewall) if node.tag == "ul" and _active(node)]
    top = _single(
        [node for node in lists if _ul_depth(node, viewall=viewall) == 0],
        "HKEX_UPDATE_SECTION_INVALID",
    )
    containers = [
        node
        for node in lists
        if _ul_depth(node, viewall=viewall) == 1 and _nearest_ul(node, viewall=viewall) is top
    ]
    if not containers:
        raise ValueError("HKEX_UPDATE_SECTION_INVALID")
    slots: list[HKEXUpdateAttachmentSlot] = []
    child_counts: list[int] = []
    for container_order, container in enumerate(containers):
        pages = [
            node
            for node in lists
            if _ul_depth(node, viewall=viewall) == 2
            and _nearest_ul(node, viewall=viewall) is container
        ]
        if not pages:
            raise ValueError("HKEX_UPDATE_SECTION_INVALID")
        child_counts.append(len(pages))
        for child_order, page in enumerate(pages):
            occurrence_order = 0
            for node in _walk(page):
                if node.tag != "a" or not _active(node):
                    continue
                href = node.attrs.get("href")
                if not isinstance(href, str) or ".pdf" not in href.lower():
                    continue
                slots.append(
                    HKEXUpdateAttachmentSlot(
                        HKEXUpdatePosition(
                            container_order,
                            child_order,
                            HKEXMembershipRelation.UPDATE_PAGE,
                        ),
                        occurrence_order,
                        _raw_href(node, "HKEX_UPDATE_SECTION_INVALID"),
                    )
                )
                occurrence_order += 1
    return HKEXUpdateSectionStructure(tuple(child_counts), tuple(slots))


def resolve_hkex_capture_endpoint_id(
    target_url: str, *, media_type: str, capture_id_by_url: Mapping[str, str]
) -> str:
    """Reuse one immutable static ID or derive a media-typed full-digest ID."""
    if type(target_url) is not str or type(media_type) is not str:
        raise ValueError("HKEX_CAPTURE_ID_INVALID")
    existing = capture_id_by_url.get(target_url)
    if existing is not None:
        if type(existing) is not str or not existing:
            raise ValueError("HKEX_CAPTURE_ID_INVALID")
        return existing
    label = {"text/html": "html", "application/pdf": "pdf"}.get(media_type)
    if label is None:
        raise ValueError("HKEX_CAPTURE_ID_INVALID")
    digest = hashlib.sha256(f"{media_type}\0{target_url}".encode()).hexdigest()
    return f"hkex-{label}-sha256-{digest}"


def _exact_nonempty(value: object) -> bool:
    return type(value) is str and bool(value)


def _association_payload(**values: object) -> str:
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_hkex_membership_association(  # noqa: PLR0913 - mirrors the frozen report row
    *,
    source_id: str,
    board: HKEXPublisherBoard,
    relation: HKEXMembershipRelation,
    parent_url: str,
    target_url: str,
    source_order: int,
    occurrence_ids: tuple[str, ...],
    authority_class: HKEXAuthorityClass,
    fetch_disposition: HKEXFetchDisposition,
    capture_endpoint_id: str | None,
) -> HKEXMembershipAssociation:
    """Build one association only when the complete disposition row is coherent."""
    exact_types = (
        _exact_nonempty(source_id)
        and type(board) is HKEXPublisherBoard
        and type(relation) is HKEXMembershipRelation
        and _exact_nonempty(parent_url)
        and _exact_nonempty(target_url)
        and type(source_order) is int
        and source_order >= 0
        and type(occurrence_ids) is tuple
        and all(_exact_nonempty(item) for item in occurrence_ids)
        and len(occurrence_ids) == len(set(occurrence_ids))
        and type(authority_class) is HKEXAuthorityClass
        and type(fetch_disposition) is HKEXFetchDisposition
        and (capture_endpoint_id is None or _exact_nonempty(capture_endpoint_id))
    )
    semantic = (
        relation in {HKEXMembershipRelation.UPDATE_CONTAINER, HKEXMembershipRelation.UPDATE_PAGE}
        and authority_class is HKEXAuthorityClass.SAME_HOST_ADMITTED
        and fetch_disposition is HKEXFetchDisposition.SEMANTIC_ONLY
        and capture_endpoint_id is None
        and not occurrence_ids
    )
    planned = (
        relation
        in {
            HKEXMembershipRelation.FEES_PDF,
            HKEXMembershipRelation.FORM_NODE,
            HKEXMembershipRelation.FORM_PDF,
            HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF,
        }
        and authority_class is HKEXAuthorityClass.SAME_HOST_ADMITTED
        and fetch_disposition is HKEXFetchDisposition.PLANNED_OR_REUSED
        and _exact_nonempty(capture_endpoint_id)
        and (
            bool(occurrence_ids)
            if relation is HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF
            else not occurrence_ids
        )
    )
    external = (
        relation is HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF
        and authority_class is HKEXAuthorityClass.EXTERNAL_AUTHORITY_REQUIRED
        and fetch_disposition is HKEXFetchDisposition.UNFETCHED_EXTERNAL_REFERENCE
        and capture_endpoint_id is None
        and bool(occurrence_ids)
    )
    if not exact_types or sum((semantic, planned, external)) != 1:
        raise ValueError("HKEX_ASSOCIATION_INVALID")
    payload = {
        "source_id": source_id,
        "board": board.value,
        "relation": relation.value,
        "parent_url": parent_url,
        "target_url": target_url,
        "source_order": source_order,
        "occurrence_ids": occurrence_ids,
        "authority_class": authority_class.value,
        "fetch_disposition": fetch_disposition.value,
        "capture_endpoint_id": capture_endpoint_id,
    }
    association_id = "hka_" + hashlib.sha256(_association_payload(**payload).encode()).hexdigest()
    return HKEXMembershipAssociation(
        association_id,
        source_id,
        board,
        relation,
        parent_url,
        target_url,
        source_order,
        occurrence_ids,
        authority_class,
        fetch_disposition,
        capture_endpoint_id,
    )


def build_hkex_attachment_occurrence(  # noqa: PLR0913 - mirrors the frozen report row
    *,
    source_id: str,
    board: HKEXPublisherBoard,
    parent_relation: HKEXMembershipRelation,
    parent_url: str,
    parent_position: HKEXUpdatePosition,
    occurrence_order: int,
    raw_locator: str,
    normalization_code: HKEXLocatorNormalization,
    target_url: str,
    authority_class: HKEXAuthorityClass,
    fetch_disposition: HKEXFetchDisposition,
) -> HKEXAttachmentOccurrence:
    """Build one exact non-semantic Updates attachment occurrence."""
    valid = (
        _exact_nonempty(source_id)
        and type(board) is HKEXPublisherBoard
        and parent_relation
        in {HKEXMembershipRelation.UPDATE_CONTAINER, HKEXMembershipRelation.UPDATE_PAGE}
        and type(parent_position) is HKEXUpdatePosition
        and parent_position.relation is parent_relation
        and _exact_nonempty(parent_url)
        and type(occurrence_order) is int
        and occurrence_order >= 0
        and _exact_nonempty(raw_locator)
        and type(normalization_code) is HKEXLocatorNormalization
        and _exact_nonempty(target_url)
        and type(authority_class) is HKEXAuthorityClass
        and type(fetch_disposition) is HKEXFetchDisposition
        and fetch_disposition is not HKEXFetchDisposition.SEMANTIC_ONLY
        and (
            (
                authority_class is HKEXAuthorityClass.SAME_HOST_ADMITTED
                and fetch_disposition is HKEXFetchDisposition.PLANNED_OR_REUSED
            )
            or (
                authority_class is HKEXAuthorityClass.EXTERNAL_AUTHORITY_REQUIRED
                and fetch_disposition is HKEXFetchDisposition.UNFETCHED_EXTERNAL_REFERENCE
            )
        )
    )
    if not valid:
        raise ValueError("HKEX_ATTACHMENT_OCCURRENCE_INVALID")
    payload = {
        "source_id": source_id,
        "board": board.value,
        "parent_relation": parent_relation.value,
        "parent_url": parent_url,
        "parent_position": {
            "container_order": parent_position.container_order,
            "child_order": parent_position.child_order,
            "relation": parent_position.relation.value,
        },
        "occurrence_order": occurrence_order,
        "raw_locator": raw_locator,
        "normalization_code": normalization_code.value,
        "target_url": target_url,
        "authority_class": authority_class.value,
        "fetch_disposition": fetch_disposition.value,
    }
    occurrence_id = "hko_" + hashlib.sha256(_association_payload(**payload).encode()).hexdigest()
    return HKEXAttachmentOccurrence(
        occurrence_id,
        source_id,
        board,
        parent_relation,
        parent_url,
        parent_position,
        occurrence_order,
        raw_locator,
        normalization_code,
        target_url,
        authority_class,
        fetch_disposition,
    )
