"""Authentic Basic Law portal category-membership enumeration."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from html.parser import HTMLParser
from pathlib import Path
from types import MappingProxyType
from typing import TypeGuard
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

_MAX_BODY = 16_777_216
_HISTORICAL_ROOT = "https://www.basiclaw.gov.hk/en/index/index.html"
CONSTITUTION_ROOT_URL = "https://www.basiclaw.gov.hk/en/constitution/index.html"
BASIC_LAW_ROOT_URL = "https://www.basiclaw.gov.hk/en/basiclaw/index.html"
CURRENT_BASIC_LAW_MEMBER_URLS = (
    "https://www.basiclaw.gov.hk/en/constitution/preamble.html",
    "https://www.basiclaw.gov.hk/en/constitution/chapter1.html",
    "https://www.basiclaw.gov.hk/en/constitution/chapter2.html",
    "https://www.basiclaw.gov.hk/en/constitution/chapter3.html",
    "https://www.basiclaw.gov.hk/en/constitution/chapter4.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/decree.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/preamble.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter1.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter2.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter3.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter4.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter5.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter6.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter7.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter8.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter9.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/annex1.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/annex2.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/annex3.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/annex-instrument.html",
)
_MEMBER_PATH = re.compile(r"/en/(?:constitution|basiclaw)/(?:[A-Za-z0-9][A-Za-z0-9._-]*/?)*\Z")
_HTML_MEDIA_TYPE = re.compile(r"text/html(?:;\s*charset=(?:utf-8|utf8))?\Z", re.IGNORECASE)
_VOID_HTML_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}
)
_NON_VISIBLE_TAGS = frozenset({"iframe", "noscript", "object", "script", "style", "template"})
_HIDE_CAPABLE_PROPERTIES = frozenset({"display", "visibility"})
_INLINE_STYLE_VALUE = re.compile(
    r"(?P<value>[a-z][a-z0-9-]*)(?:\s*!\s*important)?\Z",
    re.IGNORECASE,
)
_STRUCTURE_CONTRACT_SCHEMA = "asklegal.basic-law-content-structure"
_STRUCTURE_CONTRACT_VERSION = "1.0.0"
_STRUCTURE_PROJECTION_SCHEMA = "asklegal.basic-law.text-free-structure.v1"
_STRUCTURE_PROJECTION_VERSION = "1.0.0"
_MAX_STRUCTURE_CONTRACT_BYTES = 65_536
_SHA256_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _require_unique_attribute_names(attrs: list[tuple[str, str | None]]) -> None:
    observed: set[str] = set()
    for name, _value in attrs:
        normalized = name.lower()
        if normalized in observed:
            raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
        observed.add(normalized)


def _strip_css_comments(style: str) -> str:
    """Remove closed comments without treating comment markers inside strings as syntax."""
    stripped: list[str] = []
    offset = 0
    quote: str | None = None
    while offset < len(style):
        character = style[offset]
        if quote is not None:
            stripped.append(character)
            if character == "\\" and offset + 1 < len(style):
                offset += 1
                stripped.append(style[offset])
            elif character == quote:
                quote = None
            offset += 1
            continue
        if character in {'"', "'"}:
            quote = character
            stripped.append(character)
            offset += 1
            continue
        if style.startswith("/*", offset):
            comment_end = style.find("*/", offset + 2)
            if comment_end < 0:
                raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
            offset = comment_end + 2
            continue
        if style.startswith("*/", offset):
            raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
        stripped.append(character)
        offset += 1
    return "".join(stripped)


def _decode_css_identifier_escapes(identifier: str) -> str:
    """Decode escapes only to detect a disguised hide-capable property name."""
    decoded: list[str] = []
    offset = 0
    while offset < len(identifier):
        character = identifier[offset]
        if character != "\\":
            decoded.append(character)
            offset += 1
            continue
        offset += 1
        if offset >= len(identifier) or identifier[offset] in "\r\n\f":
            raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
        if identifier[offset] in "0123456789abcdefABCDEF":
            escape_start = offset
            while (
                offset < len(identifier)
                and offset - escape_start < 6
                and identifier[offset] in "0123456789abcdefABCDEF"
            ):
                offset += 1
            codepoint = int(identifier[escape_start:offset], 16)
            if offset < len(identifier) and identifier[offset] in " \t\r\n\f":
                if identifier[offset] == "\r" and identifier[offset : offset + 2] == "\r\n":
                    offset += 2
                else:
                    offset += 1
            decoded.append(
                "\ufffd"
                if codepoint == 0 or 0xD800 <= codepoint <= 0xDFFF or codepoint > 0x10FFFF
                else chr(codepoint)
            )
            continue
        decoded.append(identifier[offset])
        offset += 1
    return "".join(decoded)


def _normalize_inline_property_name(property_name: str) -> str:
    normalized = property_name.strip().lower()
    if "\\" not in normalized:
        return normalized
    decoded = _decode_css_identifier_escapes(normalized).strip().lower()
    if decoded in _HIDE_CAPABLE_PROPERTIES:
        raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
    return normalized


def _inline_style_hides(attrs: list[tuple[str, str | None]]) -> bool:
    """Recognize a closed hiding subset and reject ambiguous hide-capable syntax."""
    seen: set[str] = set()
    hides = False
    for name, value in attrs:
        if name.lower() != "style" or value is None:
            continue
        for declaration in _strip_css_comments(value).split(";"):
            if not declaration.strip():
                continue
            property_name, separator, property_value = declaration.partition(":")
            if not separator:
                candidate = _normalize_inline_property_name(property_name)
                if any(
                    candidate == hide_property or candidate.startswith(f"{hide_property} ")
                    for hide_property in _HIDE_CAPABLE_PROPERTIES
                ):
                    raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
                continue
            normalized_name = _normalize_inline_property_name(property_name)
            if normalized_name not in _HIDE_CAPABLE_PROPERTIES:
                continue
            if normalized_name in seen:
                raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
            seen.add(normalized_name)
            match = _INLINE_STYLE_VALUE.fullmatch(property_value.strip())
            if match is None:
                raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
            normalized_value = match.group("value").lower()
            hides = hides or (normalized_name, normalized_value) in {
                ("display", "none"),
                ("visibility", "hidden"),
            }
    return hides


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value is not None:
                self.hrefs.append(value)


class _ContentIdentityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_count = 0
        self.head_count = 0
        self.body_count = 0
        self.title_count = 0
        self.invalid = False
        self._stack: list[tuple[str, bool]] = []
        self._head_closed = False
        self._body_closed = False
        self._html_closed = False
        self._hidden_depth = 0
        self.title_text: list[str] = []
        self.body_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _require_unique_attribute_names(attrs)
        normalized = tag.lower()
        if self._html_closed:
            self.invalid = True
            return
        if normalized in _VOID_HTML_TAGS:
            if not self._stack:
                self.invalid = True
            return
        if normalized == "html":
            if self._stack or self.html_count:
                self.invalid = True
            self.html_count += 1
        elif normalized == "head":
            if [name for name, _hidden in self._stack] != ["html"] or self.head_count:
                self.invalid = True
            self.head_count += 1
        elif normalized == "body":
            if (
                [name for name, _hidden in self._stack] != ["html"]
                or self.head_count != 1
                or not self._head_closed
                or self.body_count
            ):
                self.invalid = True
            self.body_count += 1
        elif normalized == "title":
            if [name for name, _hidden in self._stack] != ["html", "head"] or self.title_count:
                self.invalid = True
            self.title_count += 1
        elif not self._stack or self._stack[0][0] != "html":
            self.invalid = True
        own_hidden = (
            normalized in _NON_VISIBLE_TAGS
            or _inline_style_hides(attrs)
            or any(
                name.lower() == "hidden"
                or (
                    name.lower() == "aria-hidden"
                    and value is not None
                    and value.strip().lower() == "true"
                )
                for name, value in attrs
            )
        )
        self._stack.append((normalized, own_hidden))
        if own_hidden:
            self._hidden_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _require_unique_attribute_names(attrs)
        if tag.lower() not in _VOID_HTML_TAGS or not self._stack:
            self.invalid = True
        del attrs

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in _VOID_HTML_TAGS:
            self.invalid = True
            return
        if not self._stack or self._stack[-1][0] != normalized:
            self.invalid = True
            return
        _name, own_hidden = self._stack.pop()
        if own_hidden:
            self._hidden_depth -= 1
        if normalized == "head":
            self._head_closed = True
        elif normalized == "body":
            self._body_closed = True
        elif normalized == "html":
            self._html_closed = True

    def handle_data(self, data: str) -> None:
        names = [name for name, _hidden in self._stack]
        if not names:
            if data.strip():
                self.invalid = True
            return
        if names[-1] == "title":
            self.title_text.append(data)
        if "body" in names and not self._hidden_depth:
            self.body_text.append(data)

    def complete(self) -> bool:
        """Require one closed HTML document with head/title before a non-empty body."""
        return bool(
            not self.invalid
            and not self._stack
            and self._html_closed
            and self._head_closed
            and self._body_closed
            and self.html_count == self.head_count == self.body_count == self.title_count == 1
        )


def _empty_structure_nodes() -> list[_StructureNode]:
    return []


@dataclass(slots=True)
class _StructureNode:
    tag: str
    attrs: list[tuple[str, str | None]]
    visibility: str
    children: list[_StructureNode] = field(default_factory=_empty_structure_nodes)
    direct_text: bool = False


class _TextFreeStructureParser(HTMLParser):
    """Project ordered publisher structure without retaining page or script text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doctype: list[str] = []
        self.roots: list[_StructureNode] = []
        self._stack: list[_StructureNode] = []

    def handle_decl(self, decl: str) -> None:
        self.doctype.append(" ".join(decl.lower().split()))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _require_unique_attribute_names(attrs)
        normalized = tag.lower()
        ancestor_hidden = bool(self._stack and self._stack[-1].visibility != "visible")
        own_hidden = (
            normalized in _NON_VISIBLE_TAGS
            or _inline_style_hides(attrs)
            or any(
                name.lower() == "hidden"
                or (
                    name.lower() == "aria-hidden"
                    and value is not None
                    and value.strip().lower() == "true"
                )
                for name, value in attrs
            )
        )
        visibility = (
            "ancestor-hidden" if ancestor_hidden else "own-hidden" if own_hidden else "visible"
        )
        node = _StructureNode(normalized, list(attrs), visibility)
        if self._stack:
            self._stack[-1].children.append(node)
        else:
            self.roots.append(node)
        if normalized not in _VOID_HTML_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized not in _VOID_HTML_TAGS and self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._stack and self._stack[-1].tag not in _NON_VISIBLE_TAGS and data.strip():
            self._stack[-1].direct_text = True


@dataclass(frozen=True, slots=True)
class _BasicLawStructureIdentity:
    title: str
    projection_fingerprint: str


@dataclass(frozen=True, slots=True)
class BasicLawMembership:
    """Every accepted English constitutional-content link from the current root."""

    member_urls: tuple[str, ...]


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
        document[key] = value
    return document


def _is_exact_dict(value: object) -> TypeGuard[dict[str, object]]:
    return type(value) is dict


def _is_exact_list(value: object) -> TypeGuard[list[object]]:
    return type(value) is list


def _exact_object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if not _is_exact_dict(value) or frozenset(value) != keys:
        raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
    return value


def _required_string(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
    return value


def read_basic_law_structure_contract(
    path: Path,
) -> Mapping[str, _BasicLawStructureIdentity]:
    """Load one exact, self-fingerprinted Basic Law structural contract."""
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > _MAX_STRUCTURE_CONTRACT_BYTES:
            raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
        parsed = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID") from error
    document = _exact_object(
        parsed,
        frozenset(
            {
                "schema_id",
                "schema_version",
                "projection_version",
                "fingerprint",
                "members",
            }
        ),
    )
    if (
        document["schema_id"] != _STRUCTURE_CONTRACT_SCHEMA
        or document["schema_version"] != _STRUCTURE_CONTRACT_VERSION
        or document["projection_version"] != _STRUCTURE_PROJECTION_VERSION
    ):
        raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
    fingerprint = _required_string(document["fingerprint"])
    unsigned = dict(document)
    del unsigned["fingerprint"]
    if _SHA256_FINGERPRINT.fullmatch(fingerprint) is None or fingerprint != _sha256(
        _canonical_json(unsigned)
    ):
        raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
    raw_members = document["members"]
    if not _is_exact_list(raw_members):
        raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
    if len(raw_members) != len(CURRENT_BASIC_LAW_MEMBER_URLS):
        raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
    members: dict[str, _BasicLawStructureIdentity] = {}
    fingerprints: set[str] = set()
    ordered_urls: list[str] = []
    for raw_member in raw_members:
        member = _exact_object(
            raw_member,
            frozenset({"url", "title", "projection_fingerprint"}),
        )
        url = _required_string(member["url"])
        title = _required_string(member["title"])
        projection_fingerprint = _required_string(member["projection_fingerprint"])
        if (
            url in members
            or _SHA256_FINGERPRINT.fullmatch(projection_fingerprint) is None
            or projection_fingerprint in fingerprints
        ):
            raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
        try:
            require_basic_law_member_url(url)
        except ValueError as error:
            raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID") from error
        members[url] = _BasicLawStructureIdentity(title, projection_fingerprint)
        fingerprints.add(projection_fingerprint)
        ordered_urls.append(url)
    if tuple(ordered_urls) != CURRENT_BASIC_LAW_MEMBER_URLS:
        raise ValueError("BASIC_LAW_STRUCTURE_CONTRACT_INVALID")
    return MappingProxyType(members)


@cache
def _default_structure_contract() -> Mapping[str, _BasicLawStructureIdentity]:
    return read_basic_law_structure_contract(
        Path(__file__).with_name("basic_law_content_structure.json")
    )


def _normalized_locator(value: str, *, base_url: str) -> list[object]:
    if value == "javascript:;":
        return ["control", "javascript-empty"]
    parsed = urlsplit(urljoin(base_url, value))
    if parsed.scheme.lower() == "javascript":
        return ["control", "javascript-other"]
    return [
        "url",
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        parsed.query,
        parsed.fragment,
    ]


def _projected_attributes(
    node: _StructureNode,
    *,
    base_url: str,
) -> list[list[object]]:
    attributes = {name.lower(): value for name, value in node.attrs}
    projected: list[list[object]] = []
    class_value = attributes.get("class")
    if class_value is not None:
        projected.append(["class", sorted(class_value.split())])
    for name in ("id", "role"):
        value = attributes.get(name)
        if value is not None:
            projected.append([name, " ".join(value.split())])
    language = attributes.get("lang")
    if node.tag == "html" and language is not None:
        projected.append(["lang", language.strip().lower()])
    if node.tag == "meta":
        for name in ("charset", "name", "http-equiv"):
            value = attributes.get(name)
            if value is not None:
                projected.append([name, value.strip().lower()])
    if node.tag == "script":
        script_type = attributes.get("type")
        if script_type is not None:
            projected.append(["type", script_type.strip().lower()])
        source = attributes.get("src")
        if source is not None:
            projected.append(["src", _normalized_locator(source, base_url=base_url)])
    if node.tag == "a":
        href = attributes.get("href")
        if href is not None:
            projected.append(["href", _normalized_locator(href, base_url=base_url)])
        target = attributes.get("target")
        if target is not None:
            projected.append(["target", target.strip().lower()])
    observed = {"class", "id", "role"}
    if node.tag == "html":
        observed.add("lang")
    if node.tag == "meta":
        observed.update({"charset", "name", "http-equiv", "content"})
    if node.tag == "script":
        observed.update({"type", "src"})
    if node.tag == "a":
        observed.update({"href", "target"})
    event_names = sorted(name for name in attributes if name.startswith("on"))
    other_names = sorted(
        name
        for name in attributes
        if name not in observed
        and name not in {"aria-hidden", "hidden", "style"}
        and not name.startswith("on")
    )
    if other_names:
        projected.append(["other-attribute-names", other_names])
    if event_names:
        projected.append(["event-handler-names", event_names])
    return sorted(projected, key=lambda item: str(item[0]))


def _project_structure_node(node: _StructureNode, *, base_url: str) -> dict[str, object]:
    return {
        "attrs": _projected_attributes(node, base_url=base_url),
        "children": [_project_structure_node(child, base_url=base_url) for child in node.children],
        "direct_text": node.direct_text,
        "tag": node.tag,
        "visibility": node.visibility,
    }


def _structure_projection(
    parser: _TextFreeStructureParser,
    *,
    url: str,
    title: str,
) -> dict[str, object]:
    return {
        "doctype": parser.doctype,
        "schema": _STRUCTURE_PROJECTION_SCHEMA,
        "title": title,
        "tree": [_project_structure_node(node, base_url=url) for node in parser.roots],
        "url": url,
    }


def require_basic_law_member_url(url: str) -> str:
    """Bind one generated locator to the exact current twenty-member inventory."""
    _require_safe_basic_law_url(url)
    if url not in CURRENT_BASIC_LAW_MEMBER_URLS:
        raise ValueError("BASIC_LAW_MEMBER_URL_INVALID")
    return url


def validate_basic_law_content_page(body: bytes, *, url: str, media_type: str) -> None:
    """Require the exact URL/title-bound text-free publisher structure."""
    require_basic_law_member_url(url)
    if type(media_type) is not str or _HTML_MEDIA_TYPE.fullmatch(media_type.strip()) is None:
        raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
    if type(body) is not bytes or not body or len(body) > _MAX_BODY:
        raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
    try:
        parser = _ContentIdentityParser()
        parser.feed(body.decode("utf-8"))
        parser.close()
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID") from error
    if not parser.complete():
        raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
    title = re.sub(r"\s+", " ", " ".join(parser.title_text)).strip()
    expected = _default_structure_contract().get(url)
    if expected is None or title != expected.title:
        raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")
    try:
        structure = _TextFreeStructureParser()
        structure.feed(body.decode("utf-8"))
        structure.close()
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID") from error
    projection = _structure_projection(structure, url=url, title=title)
    if _sha256(_canonical_json(projection)) != expected.projection_fingerprint:
        raise ValueError("BASIC_LAW_CONTENT_PAGE_INVALID")


def _require_safe_basic_law_url(url: str) -> str:
    """Reject non-canonical locators before exact current or historical membership."""
    if type(url) is not str:
        raise ValueError("BASIC_LAW_MEMBER_URL_INVALID")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise ValueError("BASIC_LAW_MEMBER_URL_INVALID") from error
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.basiclaw.gov.hk"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or "%" in parsed.path
        or "\\" in parsed.path
        or _MEMBER_PATH.fullmatch(parsed.path) is None
        or ".." in parsed.path.split("/")
        or urlunsplit(parsed) != url
    ):
        raise ValueError("BASIC_LAW_MEMBER_URL_INVALID")
    return url


def _parse_links(body: bytes) -> tuple[str, ...]:
    if type(body) is not bytes or not body or len(body) > _MAX_BODY:
        raise ValueError("BASIC_LAW_ROOT_INVALID")
    try:
        parser = _LinkParser()
        parser.feed(body.decode("utf-8"))
        parser.close()
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("BASIC_LAW_ROOT_INVALID") from error
    return tuple(parser.hrefs)


def _category_members(
    body: bytes,
    *,
    root_url: str,
    expected_urls: tuple[str, ...],
) -> tuple[str, ...]:
    members: list[str] = []
    for href in _parse_links(body):
        try:
            raw = urlsplit(href)
            parsed = urlsplit(urljoin(root_url, href))
        except ValueError as error:
            raise ValueError("BASIC_LAW_MEMBER_URL_INVALID") from error
        decoded_raw_path = unquote(raw.path)
        encoded_family_shaped = "%" in raw.path and decoded_raw_path.startswith(
            ("/en/constitution/", "/en/basiclaw/")
        )
        if encoded_family_shaped:
            raise ValueError("BASIC_LAW_MEMBER_URL_INVALID")
        content_shaped = raw.path.startswith(("/en/constitution/", "/en/basiclaw/")) or (
            parsed.path.startswith(("/en/constitution/", "/en/basiclaw/"))
        )
        if not content_shaped:
            continue
        if ".." in raw.path.split("/") or "%" in raw.path or "\\" in raw.path:
            raise ValueError("BASIC_LAW_MEMBER_URL_INVALID")
        locator = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment)
        )
        _require_safe_basic_law_url(locator)
        if locator not in CURRENT_BASIC_LAW_MEMBER_URLS:
            raise ValueError("BASIC_LAW_MEMBERSHIP_INVALID")
        if locator not in expected_urls:
            raise ValueError("BASIC_LAW_MEMBER_URL_INVALID")
        if locator in members:
            raise ValueError("BASIC_LAW_MEMBERSHIP_INVALID")
        members.append(locator)
    if frozenset(members) != frozenset(expected_urls) or len(members) != len(expected_urls):
        raise ValueError("BASIC_LAW_MEMBERSHIP_INVALID")
    return tuple(members)


def parse_basic_law_membership(
    constitution_body: bytes,
    basic_law_body: bytes,
    *,
    constitution_root_url: str,
    basic_law_root_url: str,
) -> BasicLawMembership:
    """Require the exact retained 5+15 current English content membership."""
    if constitution_root_url != CONSTITUTION_ROOT_URL or basic_law_root_url != BASIC_LAW_ROOT_URL:
        raise ValueError("BASIC_LAW_ROOT_INVALID")
    constitution_members = _category_members(
        constitution_body,
        root_url=constitution_root_url,
        expected_urls=CURRENT_BASIC_LAW_MEMBER_URLS[:5],
    )
    basic_law_members = _category_members(
        basic_law_body,
        root_url=basic_law_root_url,
        expected_urls=CURRENT_BASIC_LAW_MEMBER_URLS[5:],
    )
    if set(constitution_members).intersection(basic_law_members):
        raise ValueError("BASIC_LAW_MEMBERSHIP_INVALID")
    return BasicLawMembership(CURRENT_BASIC_LAW_MEMBER_URLS)


def parse_historical_basic_law_root_membership(body: bytes, *, root_url: str) -> BasicLawMembership:
    """Replay the former exact two-category writer contract under its old binding."""
    if root_url != _HISTORICAL_ROOT:
        raise ValueError("BASIC_LAW_ROOT_INVALID")
    expected = (CONSTITUTION_ROOT_URL, BASIC_LAW_ROOT_URL)
    exact_relative = ("../constitution/index.html", "../basiclaw/index.html")
    members: list[str] = []
    for href in _parse_links(body):
        raw = urlsplit(href)
        if href not in exact_relative and (
            ".." in raw.path.split("/") or "%" in raw.path or "\\" in raw.path
        ):
            continue
        parsed = urlsplit(urljoin(root_url, href))
        locator = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment)
        )
        if locator not in expected:
            continue
        _require_safe_basic_law_url(locator)
        if locator not in members:
            members.append(locator)
    if frozenset(members) != frozenset(expected):
        raise ValueError("BASIC_LAW_CATEGORY_MISSING")
    return BasicLawMembership(tuple(members))


def require_historical_basic_law_category_url(url: str) -> str:
    """Bind one replay-only category locator to the former exact two-root contract."""
    _require_safe_basic_law_url(url)
    if url not in {CONSTITUTION_ROOT_URL, BASIC_LAW_ROOT_URL}:
        raise ValueError("BASIC_LAW_MEMBER_URL_INVALID")
    return url
