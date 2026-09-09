"""Authentic DATA.GOV.HK HKeL bilingual current-inventory reconciliation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from asklegal_contracts import parse_json_bytes

_MAX_BYTES = 32_000_000
_CHAPTER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,31}\Z")
_FORBIDDEN_XML = (b"<!DOCTYPE", b"<!ENTITY")
_LANGUAGES = frozenset({"en", "zh-Hant"})
_CURRENT_DATA_ENDPOINT_IDS = (
    "sep_00000000000000000000000000000000000000000000000a",
    "sep_00000000000000000000000000000000000000000000000b",
    "sep_00000000000000000000000000000000000000000000000c",
    "sep_00000000000000000000000000000000000000000000000d",
    "sep_00000000000000000000000000000000000000000000000e",
    "sep_00000000000000000000000000000000000000000000000f",
    "sep_000000000000000000000000000000000000000000000010",
    "sep_000000000000000000000000000000000000000000000011",
    "sep_000000000000000000000000000000000000000000000012",
    "sep_000000000000000000000000000000000000000000000013",
    "sep_000000000000000000000000000000000000000000000014",
    "sep_000000000000000000000000000000000000000000000015",
)
_CONFIG_FIELD_NAMES = (
    "applicationId",
    "branchCode",
    "jvmVendor",
    "jvmVersion",
    "javascriptEnabled",
    "cookieEnabled",
    "appletLoadFailed",
    "isIpv4Verified",
    "isIpv6Verified",
    "language",
    "country",
    "_CSRF_TOKEN",
)
_CONFIG_FIELDS = frozenset(_CONFIG_FIELD_NAMES)
_CONFIG_ACTION_URL = "https://www.elegislation.gov.hk/checkconfig/submitClientConfig.do"
_FORBIDDEN_FORM_FIELD = re.compile(r"(?:email|user|login|password|phone|address)", re.IGNORECASE)
_POLICY_WORD = re.compile(r"[a-z0-9]+")
_NON_VISIBLE_POLICY_TAGS = frozenset({"noscript", "script", "style", "template"})
_POLICY_VOID_TAGS = frozenset(
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


class HkelSessionMethod(StrEnum):
    """Method available only inside the exact HKeL configured-session procedure."""

    POST = "POST"


@dataclass(frozen=True, slots=True)
class HkelCurrentLanguageInventory:
    """One exact language inventory projected from authentic publisher XML."""

    language: str
    chapter_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HkelBilingualCurrentInventory:
    """One bilingual membership universe and the exact required current-data archives."""

    chapter_ids: tuple[str, ...]
    required_data_endpoint_ids: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """Return true only for a non-empty reconciled construction."""
        return bool(self.chapter_ids)


@dataclass(frozen=True, slots=True)
class HkelDatasetCatalogue:
    """One exact DATA.GOV.HK resource membership declaration."""

    declared_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HkelClientConfigurationForm:
    """Sanitized description plus non-rendered values for one approved session POST."""

    action_url: str
    field_names: tuple[str, ...]
    _fields: tuple[tuple[str, str], ...] = dataclass_field(repr=False)

    def post_fields(self) -> tuple[tuple[str, str], ...]:
        """Return a short-lived exact copy for the session transport only."""
        return tuple(self._fields)


class _ConfigurationFormParser(HTMLParser):
    """Read one inert form without exposing its source-issued token in diagnostics."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.method: str | None = None
        self.fields: list[tuple[str, str]] = []
        self.form_count = 0
        self.in_form = False
        self.invalid = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        attribute_names = tuple(name.lower() for name, _value in attrs)
        if len(attribute_names) != len(set(attribute_names)):
            self.invalid = True
            return
        values = {name.lower(): value for name, value in attrs if value is not None}
        if tag_name == "form":
            self.form_count += 1
            if self.in_form or self.form_count != 1:
                self.invalid = True
            self.in_form = True
            if self.action is None:
                self.action = values.get("action")
                self.method = values.get("method", "get").lower()
            return
        if not self.in_form:
            return
        if tag_name in {"button", "select", "textarea"}:
            self.invalid = True
            return
        if tag_name != "input":
            return
        name = values.get("name")
        if name is None or values.get("type", "text").lower() != "hidden":
            self.invalid = True
            return
        self.fields.append((name, values.get("value", "")))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "form":
            return
        if not self.in_form:
            self.invalid = True
        self.in_form = False


class _VisiblePolicyTextParser(HTMLParser):
    """Collect visible inert text while excluding executable or hidden containers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0
        self._open_elements: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name in _POLICY_VOID_TAGS:
            return
        own_hidden = tag_name in _NON_VISIBLE_POLICY_TAGS or any(
            name.lower() == "hidden"
            or (
                name.lower() == "aria-hidden"
                and value is not None
                and value.strip().lower() == "true"
            )
            for name, value in attrs
        )
        self._open_elements.append((tag_name, own_hidden))
        if own_hidden:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        for index in range(len(self._open_elements) - 1, -1, -1):
            if self._open_elements[index][0] != tag_name:
                continue
            closed = self._open_elements[index:]
            del self._open_elements[index:]
            self.hidden_depth -= sum(own_hidden for _name, own_hidden in closed)
            return

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def parse_hkel_dataset_catalogue(
    body: bytes, *, expected_dataset_name: str, required_urls: tuple[str, ...]
) -> HkelDatasetCatalogue:
    """Require every exact bilingual resource URL in one bounded CKAN package reply."""
    if type(body) is not bytes or not body or len(body) > _MAX_BYTES:
        raise ValueError("HKEL_DATA_CATALOGUE_INVALID")
    if type(expected_dataset_name) is not str or not expected_dataset_name:
        raise ValueError("HKEL_DATA_CATALOGUE_REQUIREMENT_INVALID")
    if (
        type(required_urls) is not tuple
        or not required_urls
        or len(required_urls) != len(set(required_urls))
    ):
        raise ValueError("HKEL_DATA_CATALOGUE_REQUIREMENT_INVALID")
    try:
        document = parse_json_bytes(body, max_bytes=_MAX_BYTES)
    except (TypeError, ValueError) as error:
        raise ValueError("HKEL_DATA_CATALOGUE_INVALID") from error
    if type(document) is not dict or document.get("success") is not True:
        raise ValueError("HKEL_DATA_CATALOGUE_INVALID")
    result = document.get("result")
    if type(result) is not dict:
        raise ValueError("HKEL_DATA_CATALOGUE_INVALID")
    if result.get("name") != expected_dataset_name:
        raise ValueError("HKEL_DATA_CATALOGUE_IDENTITY_INVALID")
    resources = result.get("resources")
    if type(resources) is not list:
        raise ValueError("HKEL_DATA_CATALOGUE_INVALID")
    url_values: list[str] = []
    for value in resources:
        if type(value) is not dict:
            raise ValueError("HKEL_DATA_CATALOGUE_INVALID")
        url = value.get("url")
        if type(url) is not str:
            raise ValueError("HKEL_DATA_CATALOGUE_INVALID")
        url_values.append(url)
    urls = tuple(url_values)
    if len(urls) != len(set(urls)):
        raise ValueError("HKEL_DATA_CATALOGUE_DUPLICATE")
    for url in urls:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "resource.data.one.gov.hk"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("HKEL_DATA_CATALOGUE_LOCATOR_INVALID")
    if not set(required_urls).issubset(urls):
        raise ValueError("HKEL_DATA_CATALOGUE_INCOMPLETE")
    if set(required_urls) != set(urls):
        raise ValueError("HKEL_DATA_CATALOGUE_MEMBERSHIP_MISMATCH")
    return HkelDatasetCatalogue(tuple(sorted(urls)))


def parse_hkel_client_configuration_form(
    body: bytes, *, page_url: str
) -> HkelClientConfigurationForm:
    """Parse only the approved CSRF/client-configuration POST on the HKeL host."""
    if type(body) is not bytes or not body or len(body) > 2_000_000:
        raise ValueError("HKEL_CLIENT_CONFIGURATION_FORM_INVALID")
    try:
        parser = _ConfigurationFormParser()
        parser.feed(body.decode("utf-8"))
        parser.close()
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("HKEL_CLIENT_CONFIGURATION_FORM_INVALID") from error
    if (
        parser.action is None
        or parser.method != "post"
        or parser.form_count != 1
        or parser.in_form
        or parser.invalid
    ):
        raise ValueError("HKEL_CLIENT_CONFIGURATION_FORM_INVALID")
    try:
        action = urlsplit(urljoin(page_url, parser.action))
    except ValueError:
        raise ValueError("HKEL_CLIENT_CONFIGURATION_ACTION_INVALID") from None
    if (
        action.geturl() != _CONFIG_ACTION_URL
        or action.scheme != "https"
        or action.hostname != "www.elegislation.gov.hk"
        or action.path != "/checkconfig/submitClientConfig.do"
        or action.username is not None
        or action.password is not None
        or action.query
        or action.fragment
    ):
        raise ValueError("HKEL_CLIENT_CONFIGURATION_ACTION_INVALID")
    names = tuple(name for name, _ in parser.fields)
    if (
        len(names) != len(set(names))
        or frozenset(names) != _CONFIG_FIELDS
        or any(_FORBIDDEN_FORM_FIELD.search(name) for name in names)
        or not dict(parser.fields).get("_CSRF_TOKEN")
    ):
        raise ValueError("HKEL_CLIENT_CONFIGURATION_FIELDS_INVALID")
    return HkelClientConfigurationForm(action.geturl(), tuple(sorted(names)), tuple(parser.fields))


def _visible_policy_words(body: bytes) -> tuple[str, ...]:
    """Return normalized visible words without retaining publisher prose."""
    parser = _VisiblePolicyTextParser()
    try:
        parser.feed(body.decode("utf-8"))
        parser.close()
    except (UnicodeDecodeError, TypeError, ValueError) as error:
        raise ValueError("HKEL_POLICY_PAGE_INVALID") from error
    words = tuple(_POLICY_WORD.findall(" ".join(parser.parts).lower()))
    if not words or parser.hidden_depth:
        raise ValueError("HKEL_POLICY_PAGE_INVALID")
    return words


def _has_policy_sequence(words: tuple[str, ...], stems: tuple[str, ...], *, max_span: int) -> bool:
    """Require one ordered, bounded relationship between normalized policy words."""
    if not stems or max_span < len(stems):
        return False
    for start, word in enumerate(words):
        if not word.startswith(stems[0]):
            continue
        if len(stems) == 1:
            return True
        matched = 1
        end_limit = min(len(words), start + max_span)
        for candidate in words[start + 1 : end_limit]:
            if candidate.startswith(stems[matched]):
                matched += 1
                if matched == len(stems):
                    return True
    return False


def _has_policy_alternative(
    words: tuple[str, ...], alternatives: tuple[tuple[tuple[str, ...], int], ...]
) -> bool:
    return any(
        _has_policy_sequence(words, stems, max_span=max_span) for stems, max_span in alternatives
    )


def validate_hkel_policy_pages(terms_body: bytes, copyright_body: bytes) -> None:
    """Require visible current terms and replication conditions on their exact pages."""
    if type(terms_body) is not bytes or type(copyright_body) is not bytes:
        raise ValueError("HKEL_POLICY_PAGE_INVALID")
    terms_words = _visible_policy_words(terms_body)
    copyright_words = _visible_policy_words(copyright_body)
    terms_requirements = (
        (("terms", "use"), 3),
        (("april", "2026"), 2),
        (("automat", "extract"), 8),
    )
    copyright_requirements = (
        ((("copyright", "policy"), 3),),
        ((("april", "2026"), 2),),
        ((("mass", "replic"), 4),),
        (
            (("product", "database", "reproduc"), 5),
            (("database", "product", "reproduc"), 12),
        ),
        ((("version",), 1),),
        (
            (("non", "endorse"), 2),
            (("government", "does", "not", "endorse", "product"), 6),
            (
                ("must", "not", "state", "imply", "product", "approved", "endorse", "government"),
                18,
            ),
        ),
        ((("indem",), 1),),
        ((("third", "party", "rights"), 4),),
    )
    attribution_present = _has_policy_alternative(
        copyright_words,
        (
            (("attribut",), 1),
            (("accur", "government", "copyright", "refer"), 4),
            (
                ("reproduc", "provision", "product", "reproduc", "hkel", "licen", "government"),
                21,
            ),
        ),
    )
    if (
        any(
            not _has_policy_sequence(terms_words, stems, max_span=max_span)
            for stems, max_span in terms_requirements
        )
        or any(
            not _has_policy_alternative(copyright_words, alternatives)
            for alternatives in copyright_requirements
        )
        or not attribution_present
    ):
        raise ValueError("HKEL_POLICY_PAGE_INVALID")


class _InventoryParser(HTMLParser):
    """Parse Listing/Chapter/CapNo without exposing an XML entity engine."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._stack: list[str] = []
        self._cap_text: list[str] | None = None
        self._chapter_caps: list[str] | None = None
        self.chapter_ids: list[str] = []
        self.listing_identity: tuple[str | None, str | None, str | None] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.rsplit(":", 1)[-1]
        if not self._stack and name != "listing":
            raise ValueError("HKEL_INVENTORY_ROOT_INVALID")
        if not self._stack:
            if self.listing_identity is not None:
                raise ValueError("HKEL_INVENTORY_ROOT_INVALID")
            values = {key.lower(): value for key, value in attrs}
            self.listing_identity = (
                values.get("lang"),
                values.get("pointoftime"),
                values.get("legislationtype"),
            )
        self._stack.append(name)
        if name == "chapter":
            if self._chapter_caps is not None:
                raise ValueError("HKEL_INVENTORY_CHAPTER_INVALID")
            self._chapter_caps = []
        elif name == "capno":
            if self._chapter_caps is None or self._cap_text is not None:
                raise ValueError("HKEL_INVENTORY_CHAPTER_INVALID")
            self._cap_text = []

    def handle_endtag(self, tag: str) -> None:
        name = tag.rsplit(":", 1)[-1]
        if not self._stack or self._stack.pop() != name:
            raise ValueError("HKEL_INVENTORY_XML_INVALID")
        if name == "capno":
            if self._cap_text is None or self._chapter_caps is None:
                raise ValueError("HKEL_INVENTORY_CHAPTER_INVALID")
            self._chapter_caps.append("".join(self._cap_text).strip())
            self._cap_text = None
        elif name == "chapter":
            if self._chapter_caps is None or len(self._chapter_caps) != 1:
                raise ValueError("HKEL_INVENTORY_CHAPTER_INVALID")
            self.chapter_ids.append(self._chapter_caps[0])
            self._chapter_caps = None

    def handle_data(self, data: str) -> None:
        if self._cap_text is not None:
            self._cap_text.append(data)

    def handle_entityref(self, name: str) -> None:
        del name
        raise ValueError("HKEL_INVENTORY_UNSAFE_XML")

    def handle_charref(self, name: str) -> None:
        del name
        raise ValueError("HKEL_INVENTORY_UNSAFE_XML")

    def complete(self) -> tuple[str, ...]:
        """Return chapter IDs only after exact structural closure."""
        if (
            self._stack
            or self._cap_text is not None
            or self._chapter_caps is not None
            or self.listing_identity is None
        ):
            raise ValueError("HKEL_INVENTORY_XML_INVALID")
        return tuple(self.chapter_ids)


def parse_hkel_current_inventory_xml(body: bytes, *, language: str) -> HkelCurrentLanguageInventory:
    """Parse one bounded HKeL Listing/Chapter/CapNo inventory without entity expansion."""
    if language not in _LANGUAGES:
        raise ValueError("HKEL_INVENTORY_LANGUAGE_INVALID")
    if type(body) is not bytes or not body or len(body) > _MAX_BYTES:
        raise ValueError("HKEL_INVENTORY_BYTES_INVALID")
    upper = body.upper()
    if any(marker in upper for marker in _FORBIDDEN_XML):
        raise ValueError("HKEL_INVENTORY_UNSAFE_XML")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("HKEL_INVENTORY_XML_INVALID") from error
    parser = _InventoryParser()
    try:
        parser.feed(text)
        parser.close()
        chapter_ids = list(parser.complete())
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("HKEL_INVENTORY_XML_INVALID") from error
    if parser.listing_identity != (language, "c", "ALL"):
        raise ValueError("HKEL_INVENTORY_IDENTITY_INVALID")
    if any(_CHAPTER_ID.fullmatch(chapter_id) is None for chapter_id in chapter_ids):
        raise ValueError("HKEL_INVENTORY_CHAPTER_INVALID")
    if not chapter_ids:
        raise ValueError("HKEL_INVENTORY_EMPTY")
    if len(chapter_ids) != len(set(chapter_ids)):
        raise ValueError("HKEL_INVENTORY_DUPLICATE_CHAPTER")
    return HkelCurrentLanguageInventory(language, tuple(sorted(chapter_ids)))


def reconcile_hkel_current_inventories(
    english: HkelCurrentLanguageInventory,
    traditional_chinese: HkelCurrentLanguageInventory,
) -> HkelBilingualCurrentInventory:
    """Require exact English/Traditional-Chinese membership before data archives are due."""
    if (
        type(english) is not HkelCurrentLanguageInventory
        or type(traditional_chinese) is not HkelCurrentLanguageInventory
        or english.language != "en"
        or traditional_chinese.language != "zh-Hant"
    ):
        raise TypeError("HKeL inventories must be exact en and zh-Hant objects")
    if english.chapter_ids != traditional_chinese.chapter_ids:
        raise ValueError("HKEL_BILINGUAL_INVENTORY_MISMATCH")
    return HkelBilingualCurrentInventory(english.chapter_ids, _CURRENT_DATA_ENDPOINT_IDS)
