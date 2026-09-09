"""Authentic HKEX catalogue and role-membership traversal parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

_MAX_BODY = 16_777_216
_ROLE_ROOTS = frozenset(
    {
        "https://en-rules.hkex.com.hk/rulebook/main-board-listing-rules",
        "https://en-rules.hkex.com.hk/rulebook/gem-listing-rules",
        "https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
        "https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms",
        "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
        "https://en-rules.hkex.com.hk/rulebook/gem-fees-rules",
        "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules",
        "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules",
    }
)
_MEMBER_PATH = re.compile(r"/rulebook/[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_AMENDMENT_PDF_PATH = re.compile(
    r"/sites/default/files/net_file_store/[A-Za-z0-9][A-Za-z0-9._-]*\.pdf\Z"
)
_AMENDMENT_SECTION_URLS = frozenset(
    {
        "https://en-rules.hkex.com.hk/entiresection/2",
        "https://en-rules.hkex.com.hk/entiresection/49",
    }
)


class _LinkParser(HTMLParser):
    """Collect inert anchor locators in publisher order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value is not None:
                self.hrefs.append(value)


@dataclass(frozen=True, slots=True)
class HKEXCatalogue:
    """The exact Main/GEM role roots enumerated by the official catalogue."""

    role_roots: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKEXRoleMembership:
    """One role root, its complete-section locator, and every listed member."""

    root_url: str
    entire_section_url: str
    member_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKEXCompleteRoleCapture:
    """One exactly reconciled role traversal."""

    root_url: str
    declared_member_count: int
    captured_urls: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """Return true only for a non-empty factory-reconciled capture."""
        return self.declared_member_count > 0


def _links(body: bytes) -> tuple[str, ...]:
    if type(body) is not bytes or not body or len(body) > _MAX_BODY:
        raise ValueError("HKEX_MEMBERSHIP_BYTES_INVALID")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("HKEX_MEMBERSHIP_ENCODING_INVALID") from error
    parser = _LinkParser()
    parser.feed(text)
    parser.close()
    return tuple(parser.hrefs)


def _canonical_url(base: str, href: str) -> str:
    parsed = urlsplit(urljoin(base, href))
    if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
        raise ValueError("HKEX_MEMBER_LOCATOR_INVALID")
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, parsed.query, ""))


def require_hkex_member_url(url: str) -> str:
    """Require one canonical rulebook member locator on the exact admitted publisher host."""
    if type(url) is not str:
        raise ValueError("HKEX_MEMBER_LOCATOR_INVALID")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise ValueError("HKEX_MEMBER_LOCATOR_INVALID") from error
    if (
        parsed.scheme != "https"
        or parsed.netloc != "en-rules.hkex.com.hk"
        or parsed.hostname != "en-rules.hkex.com.hk"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or "%" in parsed.path
        or "\\" in parsed.path
        or any(segment in {"", ".", ".."} for segment in parsed.path.removeprefix("/").split("/"))
        or _MEMBER_PATH.fullmatch(parsed.path) is None
        or urlunsplit(parsed) != url
    ):
        raise ValueError("HKEX_MEMBER_LOCATOR_INVALID")
    return url


def parse_hkex_catalogue(body: bytes) -> HKEXCatalogue:
    """Require the official catalogue to expose all eight accepted board/role roots."""
    observed = {
        _canonical_url("https://www.hkex.com.hk/", href)
        for href in _links(body)
        if "en-rules.hkex.com.hk" in href
    }
    if not _ROLE_ROOTS.issubset(observed):
        raise ValueError("HKEX_CATALOGUE_ROLE_ROOT_MISSING")
    return HKEXCatalogue(tuple(sorted(_ROLE_ROOTS)))


def parse_hkex_role_membership(
    body: bytes, *, root_url: str, entire_section_url: str
) -> HKEXRoleMembership:
    """Enumerate every member link following one exact complete-section marker."""
    if root_url not in _ROLE_ROOTS:
        raise ValueError("HKEX_ROLE_ROOT_UNREGISTERED")
    canonical_entire = _canonical_url(root_url, entire_section_url)
    canonical_links = tuple(_canonical_url(root_url, href) for href in _links(body))
    try:
        start = canonical_links.index(canonical_entire)
    except ValueError as error:
        raise ValueError("HKEX_ENTIRE_SECTION_MISSING") from error
    members: list[str] = []
    for locator in canonical_links[start + 1 :]:
        try:
            require_hkex_member_url(locator)
        except ValueError:
            continue
        if locator in _ROLE_ROOTS:
            continue
        if locator not in members:
            members.append(locator)
    if not members:
        raise ValueError("HKEX_ROLE_MEMBERSHIP_EMPTY")
    return HKEXRoleMembership(root_url, canonical_entire, tuple(members))


def reconcile_hkex_role_capture(
    membership: HKEXRoleMembership, captured_urls: tuple[str, ...]
) -> HKEXCompleteRoleCapture:
    """Require the complete-section bytes and every enumerated member capture."""
    if type(membership) is not HKEXRoleMembership or type(captured_urls) is not tuple:
        raise TypeError("HKEX role reconciliation inputs must be exact")
    if len(captured_urls) != len(set(captured_urls)):
        raise ValueError("HKEX_ROLE_CAPTURE_DUPLICATE")
    required = {membership.entire_section_url, *membership.member_urls}
    if not required.issubset(captured_urls):
        raise ValueError("HKEX_ROLE_CAPTURE_TRUNCATED")
    return HKEXCompleteRoleCapture(
        membership.root_url,
        len(membership.member_urls),
        tuple(sorted(required)),
    )


def require_hkex_amendment_pdf_membership(body: bytes, *, section_url: str, pdf_url: str) -> str:
    """Require one registered PDF to be an exact safe link in its captured section."""
    if section_url not in _AMENDMENT_SECTION_URLS or type(pdf_url) is not str:
        raise ValueError("HKEX_AMENDMENT_PDF_MEMBERSHIP_INVALID")
    try:
        parsed_pdf = urlsplit(pdf_url)
        port = parsed_pdf.port
    except ValueError as error:
        raise ValueError("HKEX_AMENDMENT_PDF_MEMBERSHIP_INVALID") from error
    if (
        parsed_pdf.scheme != "https"
        or parsed_pdf.netloc != "en-rules.hkex.com.hk"
        or parsed_pdf.hostname != "en-rules.hkex.com.hk"
        or parsed_pdf.username is not None
        or parsed_pdf.password is not None
        or port is not None
        or parsed_pdf.query
        or parsed_pdf.fragment
        or "%" in parsed_pdf.path
        or "\\" in parsed_pdf.path
        or any(
            segment in {"", ".", ".."} for segment in parsed_pdf.path.removeprefix("/").split("/")
        )
        or _AMENDMENT_PDF_PATH.fullmatch(parsed_pdf.path) is None
        or urlunsplit(parsed_pdf) != pdf_url
    ):
        raise ValueError("HKEX_AMENDMENT_PDF_MEMBERSHIP_INVALID")
    for href in _links(body):
        if (
            any(character.isspace() or not character.isprintable() for character in href)
            or (not href.startswith("https://") and not href.startswith("/"))
            or href.startswith("//")
        ):
            continue
        try:
            raw = urlsplit(href)
        except ValueError:
            continue
        if (
            (href.startswith("https://") and (raw.scheme != "https" or not raw.netloc))
            or (href.startswith("/") and (raw.scheme or raw.netloc))
            or any(segment in {"", ".", ".."} for segment in raw.path.removeprefix("/").split("/"))
            or urlunsplit(raw) != href
        ):
            continue
        candidate = urljoin(section_url, href)
        try:
            parsed_candidate = urlsplit(candidate)
            candidate_port = parsed_candidate.port
        except ValueError:
            continue
        if (
            parsed_candidate.scheme != "https"
            or parsed_candidate.netloc != "en-rules.hkex.com.hk"
            or parsed_candidate.hostname != "en-rules.hkex.com.hk"
            or parsed_candidate.username is not None
            or parsed_candidate.password is not None
            or candidate_port is not None
            or parsed_candidate.query
            or parsed_candidate.fragment
            or "%" in parsed_candidate.path
            or "\\" in parsed_candidate.path
            or any(
                segment in {"", ".", ".."}
                for segment in parsed_candidate.path.removeprefix("/").split("/")
            )
            or _AMENDMENT_PDF_PATH.fullmatch(parsed_candidate.path) is None
            or urlunsplit(parsed_candidate) != candidate
        ):
            continue
        if candidate == pdf_url:
            return pdf_url
    raise ValueError("HKEX_AMENDMENT_PDF_MEMBERSHIP_INVALID")


def require_hkex_pdf(body: bytes) -> int:
    """Accept one bounded non-empty PDF body and return its retained byte count."""
    if type(body) is not bytes or not body.startswith(b"%PDF-") or len(body) > 67_108_864:
        raise ValueError("HKEX_PDF_BYTES_INVALID")
    return len(body)
