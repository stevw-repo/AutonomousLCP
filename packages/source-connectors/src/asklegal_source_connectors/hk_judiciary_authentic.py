"""Authentic Judiciary LRS year/page enumeration and DIS artifact binding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from .hk_judiciary import (
    JudiciaryObservationContract,
    JudiciaryObservationKind,
    registered_judiciary_observation_contract,
)

_TOTAL_RESULTS = re.compile(r"(?P<count>[0-9][0-9,]*)\s+(?:results?|records?)", re.IGNORECASE)
_TOTAL_PAGES = re.compile(r"(?P<count>[0-9][0-9,]*)\s+pages?", re.IGNORECASE)
_MAX_RESULTS = 1_000_000
_MAX_PAGES = 100_000
_MAX_BODY = 16_777_216
_COURT_CODES = ("FA", "CA", "HC", "CT", "DC", "FC", "LD", "OT")
_DECISION_DATE = re.compile(r"\b(?P<day>[0-9]{2})/(?P<month>[0-9]{2})/(?P<year>[0-9]{4})\b")
_V1_START = date(1997, 7, 1)


class _ResultPageParser(HTMLParser):
    """Collect inert visible text and link locators without executing source markup."""

    def __init__(
        self,
        *,
        allow_current_duplicate_multiple: bool = False,
        scope_current_page_form: bool = False,
        current_form_page: int | None = None,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.hrefs: list[str] = []
        self.rows: list[tuple[str, tuple[str, ...]]] = []
        self.current_rows: list[
            tuple[
                str,
                tuple[str, ...],
                tuple[str, ...],
                tuple[str, ...],
                int,
                tuple[str, ...],
            ]
        ] = []
        self.current_counts: dict[str, str] = {}
        self.page_controls: list[tuple[str | None, str | None]] = []
        self.ignored_page_controls: list[tuple[str | None, str | None]] = []
        self.advertised_pages: list[int] = []
        self.duplicate_multiple_controls: set[str] = set()
        self._row_text: list[str] | None = None
        self._row_hrefs: list[str] | None = None
        self._row_raw_anchors: list[str] | None = None
        self._row_anchor_events: list[str] | None = None
        self._row_scripts: list[str] | None = None
        self._script_text: list[str] | None = None
        self._count_tag: str | None = None
        self._count_id: str | None = None
        self._count_text: list[str] | None = None
        self._current_table = False
        self._current_table_seen = False
        self._row_in_current_table = False
        self._row_td_count = 0
        self._allow_current_duplicate_multiple = allow_current_duplicate_multiple
        self._scope_current_page_form = scope_current_page_form
        self._current_form_page = current_form_page
        self._active_page_form: str | None = None
        self._active_page_control_count = 0
        self._primary_page_form_seen = False
        self._org_value_form_count = 0
        self._disabled_fieldsets: list[bool] = []
        self._template_depth = 0

    def _validate_duplicate_attributes(
        self,
        *,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attribute_names = [key.lower() for key, _value in attrs]
        duplicate_names = {
            attribute_name
            for attribute_name in attribute_names
            if attribute_names.count(attribute_name) > 1
        }
        control_name = next(
            (value for key, value in attrs if key.lower() == "name"),
            None,
        )
        exact_duplicate_multiple = (
            self._allow_current_duplicate_multiple
            and tag == "select"
            and duplicate_names == {"multiple"}
            and attribute_names.count("multiple") == 2
            and [value for key, value in attrs if key.lower() == "multiple"] == ["", None]
            and control_name in {"selSchct", "selDatabase2"}
        )
        if duplicate_names and not exact_duplicate_multiple:
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        if exact_duplicate_multiple and control_name is not None:
            self.duplicate_multiple_controls.add(control_name)

    def _handle_scoped_form_start(self, values: dict[str, str | None]) -> None:
        if self._active_page_form is not None:
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        self._active_page_control_count = 0
        if values.get("name") == "frm_search":
            if self._primary_page_form_seen or values != {
                "name": "frm_search",
                "id": "frm_search",
                "method": "get",
                "action": "",
                "onsubmit": "javascript:return FORM_SUBMIT(this);",
            }:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self._active_page_form = "PRIMARY"
            self._primary_page_form_seen = True
            return
        if values.get("name") == "org_value":
            if not self._primary_page_form_seen or values != {
                "method": "post",
                "name": "org_value",
                "action": "",
            }:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self._active_page_form = "IGNORED_POST"
            self._org_value_form_count += 1
            return
        raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")

    def _handle_page_control(self, values: dict[str, str | None]) -> None:
        if values.get("name") != "page":
            return
        if not self._scope_current_page_form:
            self.page_controls.append((values.get("type"), values.get("value")))
            return
        if any(self._disabled_fieldsets) or self._template_depth:
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        if set(values) != {"type", "name", "value"} or values.get("type") != "hidden":
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        control = (values.get("type"), values.get("value"))
        if self._active_page_form == "PRIMARY":
            self.page_controls.append(control)
        elif self._active_page_form == "IGNORED_POST":
            self.ignored_page_controls.append(control)
        else:
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        self._active_page_control_count += 1

    def _handle_ancestry_start(self, name: str, values: dict[str, str | None]) -> None:
        self._append_row_text_boundary()
        if not self._scope_current_page_form:
            return
        if name == "fieldset":
            self._disabled_fieldsets.append("disabled" in values)
        elif name == "template":
            self._template_depth += 1

    def _append_row_text_boundary(self) -> None:
        """Separate semantic markup boundaries without depending on feed chunks."""
        if self._row_text is not None:
            self._row_text.append(" ")

    def _reject_non_input_page_control(self, name: str, values: dict[str, str | None]) -> None:
        if (
            self._scope_current_page_form
            and name in {"button", "object", "select", "textarea"}
            and values.get("name") == "page"
        ):
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")

    def _handle_anchor(self, attrs: list[tuple[str, str | None]]) -> None:
        raw_anchor = self.get_starttag_text()
        if raw_anchor is None:
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        if self._row_anchor_events is not None:
            self._row_anchor_events.append(raw_anchor)
        for name, value in attrs:
            if name.lower() != "href" or value is None:
                continue
            self.hrefs.append(value)
            if self._row_hrefs is not None:
                self._row_hrefs.append(value)
                if self._row_raw_anchors is None:
                    raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
                self._row_raw_anchors.append(raw_anchor)
            if "pagesubmit" in value:
                match = re.fullmatch(r"javascript:pagesubmit\('([1-9][0-9]*)',this\.form\)", value)
                if match is None:
                    raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
                self.advertised_pages.append(int(match.group(1)))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        self._validate_duplicate_attributes(tag=name, attrs=attrs)
        if self._count_id is not None:
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        values = {key.lower(): value for key, value in attrs}
        self._handle_ancestry_start(name, values)
        self._reject_non_input_page_control(name, values)
        if name == "form" and self._scope_current_page_form:
            self._handle_scoped_form_start(values)
        count_id = values.get("id")
        if count_id in {"searchresult-total", "searchresult-totalpages"}:
            if name != "span" or count_id in self.current_counts:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self._count_tag = name
            self._count_id = count_id
            self._count_text = []
        if name == "table":
            if self._current_table:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            if count_id == "table":
                if self._current_table_seen:
                    raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
                self._current_table = True
                self._current_table_seen = True
        if name == "tr":
            if self._row_text is not None:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self._row_text = []
            self._row_hrefs = []
            self._row_raw_anchors = []
            self._row_anchor_events = []
            self._row_scripts = []
            self._row_in_current_table = self._current_table
            self._row_td_count = 0
        elif name == "td" and self._row_text is not None:
            self._row_td_count += 1
        elif name == "script" and self._row_text is not None:
            if self._script_text is not None:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self._script_text = []
        if name == "input":
            self._handle_page_control(values)
        if name != "a":
            return
        self._handle_anchor(attrs)

    def parse_endtag(self, i: int) -> int:
        """Preserve anchor closes and reject malformed form closes before normalization."""
        end = self.rawdata.find(">", i + 2)
        if end >= 0:
            token = self.rawdata[i : end + 1]
            if self._row_anchor_events is not None and re.match(r"</a\b", token, re.IGNORECASE):
                self._row_anchor_events.append(token)
            if (
                self._scope_current_page_form
                and re.match(r"</form\b", token, re.IGNORECASE)
                and not re.fullmatch(r"</form\s*>", token, re.IGNORECASE)
            ):
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        return super().parse_endtag(i)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        self._append_row_text_boundary()
        if name == "fieldset" and self._scope_current_page_form:
            if not self._disabled_fieldsets:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self._disabled_fieldsets.pop()
        elif name == "template" and self._scope_current_page_form:
            if not self._template_depth:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self._template_depth -= 1
        if name == "form" and self._scope_current_page_form:
            if self._active_page_form is None:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            expected_page_controls = (
                0
                if self._active_page_form == "IGNORED_POST" and self._current_form_page == 1
                else 1
            )
            if self._active_page_control_count != expected_page_controls:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self._active_page_form = None
            self._active_page_control_count = 0
        if name == "script" and self._script_text is not None:
            if self._row_scripts is None:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self._row_scripts.append("".join(self._script_text))
            self._script_text = None
        if name == self._count_tag:
            if self._count_id is None or self._count_text is None:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
            self.current_counts[self._count_id] = "".join(self._count_text).strip()
            self._count_tag = None
            self._count_id = None
            self._count_text = None
        if name == "table" and self._current_table:
            self._current_table = False
        if name != "tr":
            return
        if (
            self._row_text is None
            or self._row_hrefs is None
            or self._row_raw_anchors is None
            or self._row_anchor_events is None
            or self._row_scripts is None
            or self._script_text is not None
        ):
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        normalized_row_text = re.sub(r"\s+", " ", "".join(self._row_text)).strip()
        self.rows.append((normalized_row_text, tuple(self._row_hrefs)))
        if self._row_in_current_table:
            self.current_rows.append(
                (
                    normalized_row_text,
                    tuple(self._row_hrefs),
                    tuple(self._row_raw_anchors),
                    tuple(self._row_anchor_events),
                    self._row_td_count,
                    tuple(self._row_scripts),
                )
            )
        self._row_text = None
        self._row_hrefs = None
        self._row_raw_anchors = None
        self._row_anchor_events = None
        self._row_scripts = None
        self._row_in_current_table = False
        self._row_td_count = 0

    def handle_data(self, data: str) -> None:
        if self._script_text is not None:
            self._script_text.append(data)
        if self._count_text is not None:
            self._count_text.append(data)
        if self._row_text is not None:
            self._row_text.append(data)
        if data.strip():
            self.text.append(data.strip())

    @property
    def current_contract_closed(self) -> bool:
        """Report whether the observed current table/count/row boundaries closed exactly."""
        return (
            self._current_table_seen
            and not self._current_table
            and self._count_id is None
            and self._row_text is None
            and self._script_text is None
            and (
                not self._scope_current_page_form
                or (
                    self._primary_page_form_seen
                    and self._org_value_form_count == 2
                    and not self._disabled_fieldsets
                    and not self._template_depth
                    and self._active_page_form is None
                )
            )
        )


class _LegacyAdvancedFormParser(HTMLParser):
    """Preserve the 1.0.0 form projection for immutable historical replay only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.method: str | None = None
        self.controls: list[tuple[str, str]] = []
        self._select_name: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value for name, value in attrs if value is not None}
        name = tag.lower()
        if name == "form" and self.action is None:
            self.action = values.get("action", "")
            self.method = values.get("method", "get").lower()
        elif self.action is not None and name == "input":
            control_name = values.get("name")
            if control_name is not None:
                self.controls.append((control_name, values.get("value", "")))
        elif self.action is not None and name == "select":
            self._select_name = values.get("name")
        elif self._select_name is not None and name == "option":
            value = values.get("value")
            if value is not None:
                self.controls.append((self._select_name, value))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "select":
            self._select_name = None


class _CurrentAdvancedFormParser(HTMLParser):
    """Read one exact primary GET form and ignore all later publisher forms."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.method: str | None = None
        self.controls: list[tuple[str, str]] = []
        self.form_attributes: dict[str, str | None] | None = None
        self.input_shapes: list[tuple[str, str, str, bool, bool]] = []
        self.select_shapes: dict[str, tuple[int, bool]] = {}
        self.option_shapes: dict[str, list[tuple[str, bool, bool]]] = {}
        self._active = False
        self._seen = False
        self._select_name: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        attribute_names = [attribute_name.lower() for attribute_name, _ in attrs]
        values = {attribute_name.lower(): value for attribute_name, value in attrs}
        if name == "form":
            if not self._seen:
                if len(attribute_names) != len(set(attribute_names)):
                    raise ValueError("JUDICIARY_SEARCH_FORM_ATTRIBUTES_INVALID")
                self._seen = True
                self._active = True
                self.form_attributes = dict(values)
                self.action = values.get("action")
                method = values.get("method")
                self.method = method.lower() if method is not None else None
            return
        if not self._active:
            return
        if name == "input":
            if len(attribute_names) != len(set(attribute_names)):
                raise ValueError("JUDICIARY_SEARCH_FORM_ATTRIBUTES_INVALID")
            control_name = values.get("name")
            if isinstance(control_name, str):
                raw_value = values.get("value", "")
                value = raw_value if isinstance(raw_value, str) else ""
                raw_type = values.get("type", "text")
                input_type = raw_type.lower() if isinstance(raw_type, str) else ""
                self.controls.append((control_name, value))
                self.input_shapes.append(
                    (
                        control_name,
                        input_type,
                        value,
                        "disabled" in values,
                        "checked" in values,
                    )
                )
        elif name == "select":
            control_name = values.get("name")
            self._select_name = control_name if isinstance(control_name, str) else None
            if self._select_name is not None:
                duplicate_names = {
                    attribute_name
                    for attribute_name in attribute_names
                    if attribute_names.count(attribute_name) > 1
                }
                if duplicate_names - {"multiple"} or attribute_names.count("multiple") > 2:
                    raise ValueError("JUDICIARY_SEARCH_FORM_ATTRIBUTES_INVALID")
                if self._select_name in self.select_shapes:
                    raise ValueError("JUDICIARY_SEARCH_FORM_SCOPE_INVALID")
                self.select_shapes[self._select_name] = (
                    attribute_names.count("multiple"),
                    "disabled" in values,
                )
                self.option_shapes[self._select_name] = []
        elif self._select_name is not None and name == "option":
            if len(attribute_names) != len(set(attribute_names)):
                raise ValueError("JUDICIARY_SEARCH_FORM_ATTRIBUTES_INVALID")
            value = values.get("value")
            if isinstance(value, str):
                self.controls.append((self._select_name, value))
                self.option_shapes[self._select_name].append(
                    (value, "disabled" in values, "selected" in values)
                )
            elif self._select_name in {
                "day1",
                "month",
                "selDatabase2",
                "selSchct",
                "year",
            }:
                raise ValueError("JUDICIARY_SEARCH_FORM_SCOPE_INVALID")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name == "select":
            self._select_name = None
        elif name == "form" and self._active:
            self._active = False
            self._select_name = None


def build_judiciary_year_result_url(  # noqa: PLR0915 - exact versioned form grammar.
    form_body: bytes, *, entry_url: str, year: int, page: int, contract_version: str = "1.0.2"
) -> str:
    """Bind the exact versioned Judiciary year-search GET from retained form controls."""
    if (
        type(form_body) is not bytes
        or not form_body
        or len(form_body) > _MAX_BODY
        or type(year) is not int
        or not 1997 <= year <= 9999
        or type(page) is not int
        or page < 1
    ):
        raise ValueError("JUDICIARY_SEARCH_FORM_INPUT_INVALID")
    if contract_version not in {
        "1.0.0",
        "1.0.1",
        "1.0.2",
        "1.0.3",
        "1.0.4",
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
    }:
        raise ValueError("JUDICIARY_SEARCH_FORM_CONTRACT_VERSION_INVALID")
    if (
        contract_version
        in {
            "1.0.1",
            "1.0.2",
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        }
        and page != 1
    ):
        raise ValueError("JUDICIARY_RESULT_PAGE_UNSUPPORTED")
    try:
        parser = (
            _LegacyAdvancedFormParser()
            if contract_version == "1.0.0"
            else _CurrentAdvancedFormParser()
        )
        parser.feed(form_body.decode("utf-8"))
        parser.close()
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("JUDICIARY_SEARCH_FORM_INVALID") from error
    if parser.action is None or parser.method != "get":
        raise ValueError("JUDICIARY_SEARCH_FORM_METHOD_INVALID")
    target = urlsplit(urljoin(entry_url, parser.action))
    entry = urlsplit(entry_url)
    if (
        target.scheme != "https"
        or target.hostname != "legalref.judiciary.hk"
        or target.hostname != entry.hostname
        or target.path != "/lrs/common/search/search_result_form.jsp"
        or target.username is not None
        or target.password is not None
        or target.fragment
    ):
        raise ValueError("JUDICIARY_SEARCH_FORM_ACTION_INVALID")
    by_value: dict[str, list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for name, value in parser.controls:
        by_value.setdefault(value, []).append(name)
        by_name.setdefault(name, []).append(value)
    if contract_version == "1.0.0":
        if len(by_value.get("JU", ())) != 1 or any(
            len(by_value.get(code, ())) != 1 for code in _COURT_CODES
        ):
            raise ValueError("JUDICIARY_SEARCH_FORM_SCOPE_INVALID")
        required_names = {"txtSearch3", "year", "page"}
        if not required_names.issubset(by_name):
            raise ValueError("JUDICIARY_SEARCH_FORM_SCOPE_INVALID")
    else:
        if not isinstance(parser, _CurrentAdvancedFormParser):
            raise ValueError("JUDICIARY_SEARCH_FORM_SCOPE_INVALID")
        current_parser = parser
        if (
            current_parser.form_attributes is None
            or current_parser.form_attributes
            != {
                "name": "frm_search",
                "id": "frm_search",
                "method": "get",
                "action": "",
                "onsubmit": "javascript:return FORM_SUBMIT(this);",
            }
            or by_name.get("selDatabase2") != ["JU", "RV", "RS", "PD"]
            or tuple(by_name.get("selSchct", ())) != _COURT_CODES
            or any(
                by_name.get(name) != ["1"]
                for name in ("isadvsearch", "stem", "selall2", "selallct")
            )
            or by_name.get("txtSearch3") != [""]
            or by_name.get("year") != ["", "0"]
            or current_parser.select_shapes.get("selDatabase2") != (2, False)
            or current_parser.select_shapes.get("selSchct") != (2, False)
            or current_parser.select_shapes.get("year") != (0, False)
            or [
                (value, disabled)
                for value, disabled, _ in current_parser.option_shapes["selDatabase2"]
            ]
            != [("JU", False), ("RV", False), ("RS", False), ("PD", False)]
            or [
                (value, disabled) for value, disabled, _ in current_parser.option_shapes["selSchct"]
            ]
            != [(code, False) for code in _COURT_CODES]
            or [(value, disabled) for value, disabled, _ in current_parser.option_shapes["year"]]
            != [("", False), ("0", False)]
            or sorted(current_parser.input_shapes)
            != sorted(
                [
                    ("isadvsearch", "hidden", "1", False, False),
                    ("selall2", "checkbox", "1", False, True),
                    ("selallct", "checkbox", "1", False, True),
                    ("stem", "checkbox", "1", False, True),
                    ("txtSearch3", "hidden", "", False, False),
                    *[
                        shape
                        for shape in current_parser.input_shapes
                        if shape[0]
                        not in {"isadvsearch", "selall2", "selallct", "stem", "txtSearch3"}
                    ],
                ]
            )
        ):
            raise ValueError("JUDICIARY_SEARCH_FORM_SCOPE_INVALID")
    if contract_version in {
        "1.0.2",
        "1.0.3",
        "1.0.4",
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
    }:
        if not isinstance(parser, _CurrentAdvancedFormParser):
            raise ValueError("JUDICIARY_SEARCH_FORM_SCOPE_INVALID")
        current_parser = parser
        if (
            by_name.get("txtselectopt3") != ["5"]
            or by_name.get("day1") != ["", *[str(value) for value in range(32)]]
            or by_name.get("month") != ["", *[str(value) for value in range(13)]]
            or current_parser.select_shapes.get("day1") != (0, False)
            or current_parser.select_shapes.get("month") != (0, False)
            or current_parser.option_shapes.get("day1")
            != [("", False, True), *[(str(value), False, False) for value in range(32)]]
            or current_parser.option_shapes.get("month")
            != [("", False, True), *[(str(value), False, False) for value in range(13)]]
            or current_parser.option_shapes.get("year") != [("", False, True), ("0", False, False)]
            or current_parser.option_shapes.get("selDatabase2")
            != [
                ("JU", False, True),
                ("RV", False, True),
                ("RS", False, True),
                ("PD", False, True),
            ]
            or current_parser.option_shapes.get("selSchct")
            != [(code, False, True) for code in _COURT_CODES]
            or [shape for shape in current_parser.input_shapes if shape[0] == "txtselectopt3"]
            != [("txtselectopt3", "hidden", "5", False, False)]
        ):
            raise ValueError("JUDICIARY_SEARCH_FORM_SCOPE_INVALID")
    entry_query = parse_qs(entry.query, keep_blank_values=True)
    for name in ("isadvsearch", "stem", "selall2", "selallct"):
        if entry_query.get(name) != ["1"]:
            raise ValueError("JUDICIARY_SEARCH_FORM_SCOPE_INVALID")
    if contract_version == "1.0.0":
        pairs = [(by_value[code][0], code) for code in _COURT_CODES]
        pairs.append((by_value["JU"][0], "JU"))
    else:
        pairs = [("selSchct", code) for code in _COURT_CODES]
        pairs.append(("selDatabase2", "JU"))
    pairs.extend(
        [
            ("isadvsearch", "1"),
            ("selall2", "1"),
            ("selallct", "1"),
            ("stem", "1"),
        ]
    )
    if contract_version in {
        "1.0.2",
        "1.0.3",
        "1.0.4",
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
    }:
        pairs.extend([("txtselectopt3", "5"), ("day1", ""), ("month", "")])
    pairs.extend([("txtSearch3", f"//{year}"), ("year", str(year))])
    if contract_version == "1.0.0":
        pairs.insert(len(_COURT_CODES) + 2, ("page", str(page)))
    elif contract_version == "1.0.13":
        pairs.append(("page", str(page)))
    return urlunsplit((target.scheme, target.netloc, target.path, urlencode(pairs), ""))


def require_judiciary_year_result_url(
    url: str, *, year: int, page: int, contract_version: str = "1.0.2"
) -> str:
    """Require the exact fixed controls emitted by the authentic year-search builder."""
    if type(url) is not str or type(year) is not int or type(page) is not int:
        raise TypeError("Judiciary result URL inputs must be exact")
    if contract_version not in {
        "1.0.0",
        "1.0.1",
        "1.0.2",
        "1.0.3",
        "1.0.4",
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
    }:
        raise ValueError("JUDICIARY_SEARCH_FORM_CONTRACT_VERSION_INVALID")
    if not 1997 <= year <= 9999 or page < 1:
        raise ValueError("JUDICIARY_RESULT_URL_INPUT_INVALID")
    if contract_version in {"1.0.1", "1.0.2"} and page != 1:
        raise ValueError("JUDICIARY_RESULT_PAGE_UNSUPPORTED")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        observed = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise ValueError("JUDICIARY_RESULT_URL_INVALID") from error
    expected = (
        {
            "court": list(_COURT_CODES),
            "database": ["JU"],
            "isadvsearch": ["1"],
            "page": [str(page)],
            "selall2": ["1"],
            "selallct": ["1"],
            "stem": ["1"],
            "txtSearch3": [f"//{year}"],
            "year": [str(year)],
        }
        if contract_version == "1.0.0"
        else {
            "selSchct": list(_COURT_CODES),
            "selDatabase2": ["JU"],
            "isadvsearch": ["1"],
            "selall2": ["1"],
            "selallct": ["1"],
            "stem": ["1"],
            "txtSearch3": [f"//{year}"],
            "year": [str(year)],
        }
    )
    if contract_version in {
        "1.0.2",
        "1.0.3",
        "1.0.4",
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
    }:
        expected.update({"txtselectopt3": ["5"], "day1": [""], "month": [""]})
    if contract_version == "1.0.13" or (
        contract_version
        in {
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        }
        and page > 1
    ):
        expected["page"] = [str(page)]
    if (
        parsed.scheme != "https"
        or parsed.netloc != "legalref.judiciary.hk"
        or parsed.hostname != "legalref.judiciary.hk"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path != "/lrs/common/search/search_result_form.jsp"
        or parsed.fragment
        or observed != expected
        or urlunsplit(parsed) != url
    ):
        raise ValueError("JUDICIARY_RESULT_URL_INVALID")
    return url


def build_judiciary_detail_url(dis_id: int) -> str:
    """Build one exact inert full-judgment detail locator from a publisher DIS identity."""
    if type(dis_id) is not int or dis_id < 0:
        raise ValueError("JUDICIARY_DIS_ID_INVALID")
    return (
        "https://legalref.judiciary.hk/lrs/common/search/"
        f"search_result_detail_body.jsp?ID=&DIS={dis_id}&QS=%2B&TP=JU"
    )


def _current_result_frame_url(*, dis_id: int, year: int) -> str:
    return (
        "https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?"
        f"AH=S&DIS={dis_id}&QS=%28%2F%2F{year}%29&TP=JU"
    )


def require_judiciary_result_frame_url(url: str, *, dis_id: int) -> str:
    """Require one exact publisher-supplied current DIS frame locator."""
    if type(url) is not str or type(dis_id) is not int or dis_id < 0:
        raise TypeError("Judiciary result frame inputs must be exact")
    match = re.fullmatch(
        r"https://legalref\.judiciary\.hk/lrs//common/ju/ju_frame\.jsp\?"
        rf"AH=S&DIS={dis_id}&QS=%28%2F%2F(?P<year>[0-9]{{4}})%29&TP=JU",
        url,
    )
    if match is None or not 1997 <= int(match.group("year")) <= 9999:
        raise ValueError("JUDICIARY_DIS_LOCATOR_INVALID")
    return url


def require_judiciary_result_detail_frame_url(
    url: str,
    *,
    dis_id: int,
    contract_version: str = "1.0.7",
) -> str:
    """Require one exact current paired-link detail-frame locator."""
    allowed_types = (
        ("JU", "RS", "RV")
        if contract_version in {"1.0.10", "1.0.11", "1.0.12"}
        else (("JU", "RS") if contract_version in {"1.0.8", "1.0.9"} else ("JU",))
    )
    expected = tuple(
        "https://legalref.judiciary.hk/lrs/common/search/"
        f"search_result_detail_frame.jsp?DIS={dis_id}&QS=%2B&TP={artifact_type}"
        for artifact_type in allowed_types
    )
    if (
        type(url) is not str
        or type(dis_id) is not int
        or dis_id < 0
        or contract_version
        not in {
            "1.0.2",
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        }
        or url not in expected
    ):
        raise ValueError("JUDICIARY_DIS_LOCATOR_INVALID")
    return url


def require_judiciary_detail_url(url: str, *, dis_id: int) -> str:
    """Require byte-for-byte equality with the authentic detail locator builder."""
    expected = build_judiciary_detail_url(dis_id)
    if type(url) is not str or url != expected:
        raise ValueError("JUDICIARY_DETAIL_URL_INVALID")
    return url


@dataclass(frozen=True, slots=True)
class JudiciaryIncrementalOccurrence:
    """One exact current-list or RSS occurrence without completeness authority."""

    dis_id: int
    decision_date: date
    artifact_url: str
    relationship_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Revalidate the exact descendant and its closed relationship identities."""
        expected = _relationship_ids(self.dis_id)
        if (
            type(self.dis_id) is not int
            or self.dis_id < 1
            or type(self.decision_date) is not date
            or type(self.artifact_url) is not str
            or _incremental_dis_id(self.artifact_url) != self.dis_id
            or self.relationship_ids != expected
        ):
            raise ValueError("JUDICIARY_INCREMENTAL_OCCURRENCE_INVALID")


@dataclass(frozen=True, slots=True)
class JudiciaryIncrementalObservation:
    """A parsed registered signal which can discover work but prove no terminal state."""

    kind: JudiciaryObservationKind
    contract: JudiciaryObservationContract
    body_fingerprint: str
    occurrences: tuple[JudiciaryIncrementalOccurrence, ...]
    proves_complete: bool = False
    proves_no_change: bool = False

    def __post_init__(self) -> None:
        """Keep signal authority closed even when the observation is empty."""
        if (
            type(self.kind) is not JudiciaryObservationKind
            or self.kind
            not in {JudiciaryObservationKind.CURRENT_LIST, JudiciaryObservationKind.RSS}
            or type(self.contract) is not JudiciaryObservationContract
            or self.contract != registered_judiciary_observation_contract(self.kind)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.body_fingerprint) is None
            or type(self.occurrences) is not tuple
            or any(type(item) is not JudiciaryIncrementalOccurrence for item in self.occurrences)
            or self.proves_complete is not False
            or self.proves_no_change is not False
        ):
            raise ValueError("JUDICIARY_INCREMENTAL_OBSERVATION_INVALID")


class _CurrentListParser(HTMLParser):
    """Read only exact DIS rows inside the registered current-list table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html = 0
        self.body = 0
        self.table = 0
        self.in_table = False
        self.in_row = False
        self.row_text: list[str] = []
        self.row_hrefs: list[str] = []
        self.rows: list[tuple[str, tuple[str, ...]]] = []
        self.drift = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        names = [name.casefold() for name, _value in attrs]
        if len(names) != len(set(names)):
            self.drift = True
            return
        values = {name.casefold(): value for name, value in attrs}
        if tag == "html":
            self.html += 1
        elif tag == "body":
            self.body += 1
        elif tag == "table" and values.get("id") == "newjudgments":
            if self.in_table:
                self.drift = True
            self.table += 1
            self.in_table = True
        elif tag == "tr" and self.in_table:
            if self.in_row:
                self.drift = True
            self.in_row = True
            self.row_text = []
            self.row_hrefs = []
        elif tag == "a":
            href = values.get("href")
            if href is not None and "DIS=" in href:
                if not self.in_row:
                    self.drift = True
                else:
                    self.row_hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self.in_row:
            self.rows.append((" ".join(self.row_text), tuple(self.row_hrefs)))
            self.in_row = False
        elif tag == "table" and self.in_table:
            if self.in_row:
                self.drift = True
            self.in_table = False

    def handle_data(self, data: str) -> None:
        if self.in_row:
            self.row_text.append(data)


def parse_judiciary_current_list_observation(
    body: bytes, *, contract: JudiciaryObservationContract
) -> JudiciaryIncrementalObservation:
    """Parse one registered current-list body without granting completeness."""
    _require_incremental_contract(contract, JudiciaryObservationKind.CURRENT_LIST)
    text = _incremental_text(body)
    parser = _CurrentListParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as error:
        raise ValueError("JUDICIARY_INCREMENTAL_CURRENT_LIST_INVALID") from error
    if (
        parser.drift
        or parser.html != 1
        or parser.body != 1
        or parser.table != 1
        or parser.in_table
        or parser.in_row
    ):
        raise ValueError("JUDICIARY_INCREMENTAL_CURRENT_LIST_INVALID")
    occurrences: list[JudiciaryIncrementalOccurrence] = []
    for row_text, hrefs in parser.rows:
        if not hrefs:
            continue
        dates = tuple(_DECISION_DATE.finditer(row_text))
        if len(hrefs) != 1 or len(dates) != 1:
            raise ValueError("JUDICIARY_INCREMENTAL_CURRENT_LIST_INVALID")
        match = dates[0]
        try:
            decision_date = date(
                int(match.group("year")), int(match.group("month")), int(match.group("day"))
            )
            dis_id = _incremental_dis_id(hrefs[0])
        except (TypeError, ValueError) as error:
            raise ValueError("JUDICIARY_INCREMENTAL_CURRENT_LIST_INVALID") from error
        occurrences.append(
            JudiciaryIncrementalOccurrence(
                dis_id, decision_date, hrefs[0], _relationship_ids(dis_id)
            )
        )
    if "DIS=" in text and not occurrences:
        raise ValueError("JUDICIARY_INCREMENTAL_CURRENT_LIST_INVALID")
    return JudiciaryIncrementalObservation(
        JudiciaryObservationKind.CURRENT_LIST,
        contract,
        f"sha256:{sha256(body).hexdigest()}",
        tuple(occurrences),
    )


def parse_judiciary_rss_observation(
    body: bytes, *, contract: JudiciaryObservationContract
) -> JudiciaryIncrementalObservation:
    """Parse one bounded RSS 2.0 signal without treating silence as no change."""
    _require_incremental_contract(contract, JudiciaryObservationKind.RSS)
    text = _incremental_text(body)
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID")
    try:
        root = ET.fromstring(text)  # noqa: S314 - entities/DOCTYPE rejected; body is bounded.
    except ET.ParseError as error:
        raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID") from error
    if root.tag != "rss" or root.attrib != {"version": "2.0"}:
        raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID")
    channels = list(root)
    if len(channels) != 1 or channels[0].tag != "channel" or channels[0].attrib:
        raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID")
    allowed_channel = {
        "title",
        "link",
        "description",
        "language",
        "copyright",
        "lastBuildDate",
        "pubDate",
        "generator",
        "item",
    }
    if any(child.tag not in allowed_channel for child in channels[0]):
        raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID")
    occurrences: list[JudiciaryIncrementalOccurrence] = []
    for item in (child for child in channels[0] if child.tag == "item"):
        if item.attrib or any(child.attrib or list(child) for child in item):
            raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID")
        by_tag: dict[str, str] = {}
        for child in item:
            if child.tag not in {"title", "link", "guid", "pubDate", "description"}:
                raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID")
            if child.tag in by_tag or child.text is None:
                raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID")
            by_tag[child.tag] = child.text.strip()
        if set(by_tag) < {"link", "guid", "pubDate"} or not all(by_tag.values()):
            raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID")
        try:
            dis_id = _incremental_dis_id(by_tag["link"])
            published = _require_aware_rss_datetime(by_tag["pubDate"])
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID") from error
        occurrences.append(
            JudiciaryIncrementalOccurrence(
                dis_id, published.date(), by_tag["link"], _relationship_ids(dis_id)
            )
        )
    return JudiciaryIncrementalObservation(
        JudiciaryObservationKind.RSS,
        contract,
        f"sha256:{sha256(body).hexdigest()}",
        tuple(occurrences),
    )


def _require_aware_rss_datetime(value: str) -> datetime:
    published = parsedate_to_datetime(value)
    if published.tzinfo is None:
        raise ValueError("JUDICIARY_INCREMENTAL_RSS_INVALID")
    return published


def _require_incremental_contract(
    contract: JudiciaryObservationContract, kind: JudiciaryObservationKind
) -> None:
    if (
        type(contract) is not JudiciaryObservationContract
        or contract.kind is not kind
        or contract != registered_judiciary_observation_contract(kind)
        or contract.proves_complete
        or contract.proves_no_change
    ):
        raise ValueError("JUDICIARY_INCREMENTAL_CONTRACT_INVALID")


def _incremental_text(body: bytes) -> str:
    if type(body) is not bytes or not body or len(body) > _MAX_BODY:
        raise ValueError("JUDICIARY_INCREMENTAL_BODY_INVALID")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("JUDICIARY_INCREMENTAL_BODY_INVALID") from error


def _incremental_dis_id(url: str) -> int:
    if type(url) is not str:
        raise ValueError("JUDICIARY_INCREMENTAL_LOCATOR_INVALID")
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
        port = parsed.port
    except ValueError as error:
        raise ValueError("JUDICIARY_INCREMENTAL_LOCATOR_INVALID") from error
    values = query.get("DIS")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "legalref.judiciary.hk"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
        or values is None
        or len(values) != 1
        or not values[0].isdigit()
    ):
        raise ValueError("JUDICIARY_INCREMENTAL_LOCATOR_INVALID")
    dis_id = int(values[0])
    expected = (
        build_judiciary_detail_url(dis_id),
        *(
            "https://legalref.judiciary.hk/lrs/common/search/"
            f"search_result_detail_frame.jsp?DIS={dis_id}&QS=%2B&TP={kind}"
            for kind in ("JU", "RS", "RV")
        ),
    )
    if url not in expected:
        raise ValueError("JUDICIARY_INCREMENTAL_LOCATOR_INVALID")
    return dis_id


def _relationship_ids(dis_id: int) -> tuple[str, ...]:
    return tuple(
        f"judiciary-dis-{dis_id}-{role}"
        for role in (
            "judgment",
            "correction",
            "reissue",
            "language",
            "translation",
            "alias",
            "proceeding-identity",
        )
    )


@dataclass(frozen=True, slots=True)
class JudiciaryListingOccurrence:
    """One exact source row and its non-fetching canonical relationship identities.

    The result-table contract proves one canonical detail locator and, on the
    direct-Word shape, one presentation locator.  It does not prove separate
    correction, reissue, language, translation, alias, or proceeding URLs.
    Those identities are therefore durable relationship work, not invented
    transport locators.
    """

    dis_id: int
    artifact_url: str
    presentation_url: str | None
    relationship_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Keep the occurrence projection exact and one-to-one with a DIS row."""
        expected = tuple(
            f"judiciary-dis-{self.dis_id}-{role}"
            for role in (
                "judgment",
                "correction",
                "reissue",
                "language",
                "translation",
                "alias",
                "proceeding-identity",
            )
        )
        if (
            type(self.dis_id) is not int
            or self.dis_id < 1
            or type(self.artifact_url) is not str
            or not self.artifact_url
            or (self.presentation_url is not None and type(self.presentation_url) is not str)
            or self.relationship_ids != expected
        ):
            raise ValueError("JUDICIARY_LISTING_OCCURRENCE_INVALID")


@dataclass(frozen=True, slots=True)
class JudiciaryYearResultPage:
    """One bounded, caller-pinned result page and its reported partition totals."""

    year: int
    page: int
    reported_results: int
    reported_pages: int
    dis_ids: tuple[int, ...]
    decision_dates: tuple[date | None, ...]
    artifact_urls: tuple[str, ...]
    advertised_next_page: int | None
    presentation_urls: tuple[str | None, ...] = ()
    occurrences: tuple[JudiciaryListingOccurrence, ...] = ()


def build_judiciary_next_result_url(
    current_url: str,
    *,
    result_page: JudiciaryYearResultPage,
    form_contract_version: str = "1.0.3",
) -> str:
    """Construct only the exact sequential GET advertised by one retained page."""
    next_page = result_page.advertised_next_page
    if (
        type(current_url) is not str
        or type(result_page) is not JudiciaryYearResultPage
        or form_contract_version
        not in {
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
            "1.0.13",
        }
        or next_page is None
        or next_page != result_page.page + 1
        or next_page > result_page.reported_pages
    ):
        raise ValueError("JUDICIARY_RESULT_NEXT_PAGE_INVALID")
    require_judiciary_year_result_url(
        current_url,
        year=result_page.year,
        page=result_page.page,
        contract_version=form_contract_version,
    )
    parsed = urlsplit(current_url)
    pairs = [
        (name, value)
        for name, values in parse_qs(parsed.query, keep_blank_values=True).items()
        for value in values
        if name != "page"
    ]
    pairs.append(("page", str(next_page)))
    next_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), ""))
    return require_judiciary_year_result_url(
        next_url,
        year=result_page.year,
        page=next_page,
        contract_version=form_contract_version,
    )


@dataclass(frozen=True, slots=True)
class JudiciaryYearPartition:
    """One reconciled year partition with exact originating artifact locators."""

    year: int
    reported_results: int
    reported_pages: int
    listing_count: int
    dis_ids: tuple[int, ...]
    decision_dates: tuple[date | None, ...]
    all_artifact_urls: tuple[str, ...]
    in_scope_dis_ids: tuple[int, ...]
    artifact_urls: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """Return true only for the already reconciled immutable construction."""
        return self.listing_count == self.reported_results


def _reported_count(pattern: re.Pattern[str], text: str, code: str, maximum: int) -> int:
    values = {int(match.group("count").replace(",", "")) for match in pattern.finditer(text)}
    if len(values) != 1:
        raise ValueError(code)
    value = values.pop()
    if not 0 <= value <= maximum:
        raise ValueError(code)
    return value


def _count_literal(raw: str | None, code: str, maximum: int) -> int:
    if raw is None or re.fullmatch(r"[0-9]+", raw) is None:
        raise ValueError(code)
    value = int(raw)
    if not 0 <= value <= maximum:
        raise ValueError(code)
    return value


def parse_judiciary_year_result_page(  # noqa: PLR0915 - exact versioned parser.
    body: bytes, *, year: int, page: int, contract_version: str = "1.0.0"
) -> JudiciaryYearResultPage:
    """Parse one LRS result page while preserving publisher-declared totals."""
    if type(body) is not bytes or not body or len(body) > _MAX_BODY:
        raise ValueError("JUDICIARY_RESULT_PAGE_UNSAFE")
    if type(year) is not int or not 1997 <= year <= 9999 or type(page) is not int or page < 1:
        raise ValueError("JUDICIARY_RESULT_PAGE_INPUT_INVALID")
    if contract_version not in {
        "1.0.0",
        "1.0.1",
        "1.0.2",
        "1.0.3",
        "1.0.4",
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
        "1.0.13",
    }:
        raise ValueError("JUDICIARY_RESULT_PAGE_CONTRACT_VERSION_INVALID")
    # V1.0.13 changes the admitted form's pagination grammar only; its result
    # table remains the exact V1.0.12 grammar parsed below.
    if contract_version == "1.0.13":
        contract_version = "1.0.12"
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("JUDICIARY_RESULT_PAGE_ENCODING_INVALID") from error
    parser = _ResultPageParser(
        allow_current_duplicate_multiple=contract_version
        in {
            "1.0.2",
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        },
        scope_current_page_form=contract_version
        in {
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        },
        current_form_page=(
            page
            if contract_version
            in {
                "1.0.4",
                "1.0.5",
                "1.0.6",
                "1.0.7",
                "1.0.8",
                "1.0.9",
                "1.0.10",
                "1.0.11",
                "1.0.12",
            }
            else None
        ),
    )
    try:
        parser.feed(text)
        parser.close()
    except Exception as error:
        raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID") from error
    if contract_version == "1.0.0":
        visible = " ".join(parser.text)
        reported_results = _reported_count(
            _TOTAL_RESULTS, visible, "JUDICIARY_REPORTED_RESULT_TOTAL_INVALID", _MAX_RESULTS
        )
        reported_pages = _reported_count(
            _TOTAL_PAGES, visible, "JUDICIARY_REPORTED_PAGE_TOTAL_INVALID", _MAX_PAGES
        )
    else:
        if not parser.current_contract_closed:
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        reported_results = _count_literal(
            parser.current_counts.get("searchresult-total"),
            "JUDICIARY_REPORTED_RESULT_TOTAL_INVALID",
            _MAX_RESULTS,
        )
        reported_pages = _count_literal(
            parser.current_counts.get("searchresult-totalpages"),
            "JUDICIARY_REPORTED_PAGE_TOTAL_INVALID",
            _MAX_PAGES,
        )
    if page > reported_pages:
        raise ValueError("JUDICIARY_RESULT_PAGE_OUT_OF_RANGE")
    dis_ids: list[int] = []
    artifact_urls: list[str] = []
    presentation_urls: list[str | None] = []
    for href in parser.hrefs:
        try:
            parsed_href = urlsplit(href)
        except ValueError as error:
            if "DIS" in href:
                raise ValueError("JUDICIARY_DIS_LOCATOR_INVALID") from error
            continue
        try:
            query = parse_qs(
                parsed_href.query,
                keep_blank_values=True,
                strict_parsing=contract_version
                in {
                    "1.0.1",
                    "1.0.2",
                    "1.0.3",
                    "1.0.4",
                    "1.0.5",
                    "1.0.6",
                    "1.0.7",
                    "1.0.8",
                    "1.0.9",
                    "1.0.10",
                    "1.0.11",
                    "1.0.12",
                },
            )
            port = parsed_href.port
        except ValueError as error:
            if re.search(r"(?:^|&)DIS=", parsed_href.query) is not None:
                raise ValueError("JUDICIARY_DIS_LOCATOR_INVALID") from error
            continue
        values = query.get("DIS")
        if values is None:
            continue
        if len(values) != 1 or not values[0].isdigit():
            raise ValueError("JUDICIARY_DIS_LOCATOR_INVALID")
        if contract_version == "1.0.1" and (
            parsed_href.scheme != "https"
            or parsed_href.netloc != "legalref.judiciary.hk"
            or parsed_href.hostname != "legalref.judiciary.hk"
            or parsed_href.username is not None
            or parsed_href.password is not None
            or port is not None
            or parsed_href.path != "/lrs//common/ju/ju_frame.jsp"
            or parsed_href.fragment
            or query
            != {
                "AH": ["S"],
                "DIS": values,
                "QS": [f"(//{year})"],
                "TP": ["JU"],
            }
            or href != _current_result_frame_url(dis_id=int(values[0]), year=year)
        ):
            raise ValueError("JUDICIARY_DIS_LOCATOR_INVALID")
        if contract_version not in {
            "1.0.2",
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        }:
            dis_id = int(values[0])
            dis_ids.append(dis_id)
            artifact_urls.append(
                href if contract_version == "1.0.1" else build_judiciary_detail_url(dis_id)
            )
    if len(dis_ids) != len(set(dis_ids)):
        raise ValueError("JUDICIARY_DIS_DUPLICATE")
    dated: dict[int, date] = {}
    rows = (
        tuple(
            (text, hrefs, raw_anchors, anchor_events, cells, scripts)
            for text, hrefs, raw_anchors, anchor_events, cells, scripts in parser.current_rows
        )
        if contract_version
        in {
            "1.0.1",
            "1.0.2",
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        }
        else tuple((text, hrefs, hrefs, (), 0, ()) for text, hrefs in parser.rows)
    )
    for row_text, row_hrefs, row_raw_anchors, row_anchor_events, cell_count, row_scripts in rows:
        matches = tuple(_DECISION_DATE.finditer(row_text))
        row_dis: list[int] = []
        if contract_version not in {
            "1.0.2",
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        }:
            for href in row_hrefs:
                values = parse_qs(urlsplit(href).query, keep_blank_values=True).get("DIS")
                if values is not None and len(values) == 1 and values[0].isdigit():
                    row_dis.append(int(values[0]))
        if (
            contract_version
            not in {
                "1.0.2",
                "1.0.3",
                "1.0.4",
                "1.0.5",
                "1.0.6",
                "1.0.7",
                "1.0.8",
                "1.0.9",
                "1.0.10",
                "1.0.11",
                "1.0.12",
            }
            and not row_dis
        ):
            continue
        if contract_version in {
            "1.0.2",
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        }:
            assignment_types = (
                "JU|RS|RV" if contract_version in {"1.0.10", "1.0.11", "1.0.12"} else "JU|RS"
            )
            assignments = tuple(
                match.groups()
                for script in row_scripts
                if (
                    match := re.fullmatch(
                        rf"var temp([0-9]+)='DIS=([0-9]+)&QS=%2B&TP=({assignment_types})';",
                        script,
                    )
                )
                is not None
            )
            paired: dict[str, int] = {"judpop1": 0, "judpop": 0}
            direct_words: list[str] = []
            optional_frames: list[tuple[int, str]] = []
            for href in row_hrefs:
                paired_match = re.fullmatch(
                    r"javascript:(judpop1|judpop)\('search_result_detail_frame\.jsp\?'\+"
                    r"temp([0-9]+)\);",
                    href,
                )
                if paired_match is not None:
                    paired[paired_match.group(1)] += 1
                    row_dis.append(int(paired_match.group(2)))
                    continue
                direct_word_match = (
                    re.fullmatch(
                        r"javascript:judpop1\('/doc/judg/word/vetted/other/en/"
                        r"([0-9]{4})/([A-Za-z0-9_.-]+\.doc)'\);",
                        href,
                    )
                    if contract_version == "1.0.12"
                    else None
                )
                if direct_word_match is not None:
                    path_year_text, filename = direct_word_match.groups()
                    path_year = int(path_year_text)
                    if path_year == year or (
                        1997 <= path_year < year and filename.endswith(f"_{path_year_text}.doc")
                    ):
                        direct_words.append(href)
                        continue
                frame_types = "JU|RS|RV" if contract_version in {"1.0.11", "1.0.12"} else "JU"
                frame_match = re.fullmatch(
                    r"https://legalref\.judiciary\.hk/lrs//common/ju/ju_frame\.jsp\?"
                    rf"AH=S&DIS=([0-9]+)&QS=%2B&TP=({frame_types})",
                    href,
                )
                if frame_match is not None:
                    optional_frames.append((int(frame_match.group(1)), frame_match.group(2)))
                    continue
                if "judpop" in href or "temp" in href or "DIS=" in href:
                    raise ValueError("JUDICIARY_DIS_LOCATOR_INVALID")
            if not assignments and not row_dis and not direct_words and not optional_frames:
                continue
            direct_word = direct_words[0] if len(direct_words) == 1 else None
            if direct_word is not None:
                canonical_dis = str(int(assignments[0][0])) if len(assignments) == 1 else ""
                expected_frame = (
                    '<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
                    f'AH=S&DIS={canonical_dis}&QS=%2B&TP=JU" target="_top" class=default >'
                )
                if (
                    contract_version != "1.0.12"
                    or len(row_scripts) != 1
                    or len(assignments) != 1
                    or assignments[0] != (canonical_dis, canonical_dis, "JU")
                    or paired != {"judpop1": 0, "judpop": 0}
                    or row_dis
                    or optional_frames != [(int(canonical_dis), "JU")]
                    or row_raw_anchors != (f'<a href="{direct_word}">', expected_frame)
                    or row_anchor_events
                    != (f'<a href="{direct_word}">', "</a>", expected_frame, "</a>")
                ):
                    raise ValueError("JUDICIARY_DIS_LOCATOR_INVALID")
                dis_id = int(canonical_dis)
                row_dis = [dis_id]
                dis_ids.append(dis_id)
                artifact_urls.append(
                    "https://legalref.judiciary.hk/lrs/common/search/"
                    f"search_result_detail_frame.jsp?DIS={dis_id}&QS=%2B&TP=JU"
                )
                presentation_urls.append(direct_word)
            if len(assignments) == 1 and assignments[0][2] in {"RS", "RV"}:
                canonical_dis = str(int(assignments[0][0]))
                expected_rs_href_only = (
                    (
                        f"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'"
                        f'+temp{canonical_dis});">'
                    ),
                    (
                        f"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'"
                        f'+temp{canonical_dis});">'
                    ),
                )
                expected_rs_anchors = (
                    (
                        expected_rs_href_only[0][:-1] + ' class="searchfont result-caseno">',
                        expected_rs_href_only[1][:-1] + " class=searchfont>",
                    )
                    if contract_version in {"1.0.9", "1.0.10", "1.0.11", "1.0.12"}
                    else expected_rs_href_only
                )
                expected_rs_frame = (
                    '<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
                    f'AH=S&DIS={canonical_dis}&QS=%2B&TP={assignments[0][2]}" '
                    'target="_top" class=default >'
                )
                expected_rs_raw_anchors = expected_rs_anchors + (
                    ((expected_rs_frame,) if optional_frames else ())
                    if contract_version in {"1.0.11", "1.0.12"}
                    else ()
                )
                expected_rs_anchor_events = (
                    expected_rs_anchors[0],
                    "</a>",
                    expected_rs_anchors[1],
                    "</a>",
                ) + (
                    (expected_rs_frame, "</a>")
                    if contract_version in {"1.0.11", "1.0.12"} and optional_frames
                    else ()
                )
                if (
                    assignments[0][0] != canonical_dis
                    or assignments[0][1] != canonical_dis
                    or row_raw_anchors != expected_rs_raw_anchors
                    or row_anchor_events != expected_rs_anchor_events
                ):
                    raise ValueError("JUDICIARY_DIS_LOCATOR_INVALID")
            if direct_word is None and (
                len(assignments) != 1
                or len(row_scripts) != 1
                or assignments[0][0] != assignments[0][1]
                or (
                    contract_version not in {"1.0.8", "1.0.9", "1.0.10", "1.0.11", "1.0.12"}
                    and assignments[0][2] != "JU"
                )
                or paired != {"judpop1": 1, "judpop": 1}
                or len(row_dis) != 2
                or len(set(row_dis)) != 1
                or row_dis[0] != int(assignments[0][0])
                or len(optional_frames) > 1
                or any(
                    value != row_dis[0] or frame_type != assignments[0][2]
                    for value, frame_type in optional_frames
                )
                or (
                    assignments[0][2] in {"RS", "RV"}
                    and optional_frames
                    and contract_version not in {"1.0.11", "1.0.12"}
                )
                or len(matches) != 1
                or cell_count != 3
            ):
                raise ValueError("JUDICIARY_DECISION_DATE_INVALID")
            dis_id = row_dis[0]
            if direct_word is None:
                dis_ids.append(dis_id)
                artifact_urls.append(
                    "https://legalref.judiciary.hk/lrs/common/search/"
                    f"search_result_detail_frame.jsp?DIS={dis_id}&QS=%2B&TP={assignments[0][2]}"
                )
                presentation_urls.append(None)
            row_dis = [dis_id]
        if (
            len(row_dis) != 1
            or len(matches) != 1
            or (
                contract_version
                in {
                    "1.0.1",
                    "1.0.2",
                    "1.0.3",
                    "1.0.4",
                    "1.0.5",
                    "1.0.6",
                    "1.0.7",
                    "1.0.8",
                    "1.0.9",
                    "1.0.10",
                    "1.0.11",
                    "1.0.12",
                }
                and cell_count != 3
            )
        ):
            raise ValueError("JUDICIARY_DECISION_DATE_INVALID")
        try:
            match = matches[0]
            parsed_date = date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError as error:
            raise ValueError("JUDICIARY_DECISION_DATE_INVALID") from error
        if parsed_date.year != year:
            raise ValueError("JUDICIARY_DECISION_DATE_INVALID")
        if row_dis[0] in dated and (
            contract_version not in {"1.0.7", "1.0.8", "1.0.9", "1.0.10", "1.0.11", "1.0.12"}
            or dated[row_dis[0]] != parsed_date
        ):
            raise ValueError("JUDICIARY_DECISION_DATE_INVALID")
        dated[row_dis[0]] = parsed_date
    if contract_version in {
        "1.0.1",
        "1.0.2",
        "1.0.3",
        "1.0.4",
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
    } and set(dated) != set(dis_ids):
        raise ValueError("JUDICIARY_DECISION_DATE_INVALID")
    advertised_next_page: int | None = None
    if contract_version in {
        "1.0.2",
        "1.0.3",
        "1.0.4",
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
    }:
        expected_rows = min(10, reported_results - ((page - 1) * 10))
        if (
            expected_rows < 0
            or len(dis_ids) != expected_rows
            or parser.duplicate_multiple_controls != {"selSchct", "selDatabase2"}
            or parser.page_controls != [("hidden", str(page))]
            or (
                contract_version == "1.0.3"
                and parser.ignored_page_controls != [("hidden", str(page)), ("hidden", str(page))]
            )
            or (
                contract_version
                in {
                    "1.0.4",
                    "1.0.5",
                    "1.0.6",
                    "1.0.7",
                    "1.0.8",
                    "1.0.9",
                    "1.0.10",
                    "1.0.11",
                    "1.0.12",
                }
                and parser.ignored_page_controls
                != ([] if page == 1 else [("hidden", str(page)), ("hidden", str(page))])
            )
        ):
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        if any(value > reported_pages for value in parser.advertised_pages):
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        if page < reported_pages:
            advertised_next_page = page + 1
            if advertised_next_page not in parser.advertised_pages:
                raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
        elif page + 1 in parser.advertised_pages:
            raise ValueError("JUDICIARY_RESULT_PAGE_MARKUP_INVALID")
    return JudiciaryYearResultPage(
        year,
        page,
        reported_results,
        reported_pages,
        tuple(dis_ids),
        tuple(dated.get(dis_id) for dis_id in dis_ids),
        tuple(artifact_urls),
        advertised_next_page,
        tuple(presentation_urls),
        tuple(
            JudiciaryListingOccurrence(
                dis_id=dis_id,
                artifact_url=artifact_url,
                presentation_url=presentation_url,
                relationship_ids=tuple(
                    f"judiciary-dis-{dis_id}-{role}"
                    for role in (
                        "judgment",
                        "correction",
                        "reissue",
                        "language",
                        "translation",
                        "alias",
                        "proceeding-identity",
                    )
                ),
            )
            for dis_id, artifact_url, presentation_url in zip(
                dis_ids,
                artifact_urls,
                presentation_urls or [None] * len(dis_ids),
                strict=True,
            )
        ),
    )


def reconcile_judiciary_year_partition(  # noqa: PLR0915 - exact versioned reconciliation.
    pages: tuple[JudiciaryYearResultPage, ...],
    *,
    contract_version: str = "1.0.0",
) -> JudiciaryYearPartition:
    """Reconcile exact listing slots before narrowly deduplicating current overlaps."""
    if (
        type(pages) is not tuple
        or not pages
        or any(type(page) is not JudiciaryYearResultPage for page in pages)
    ):
        raise TypeError("pages must be a non-empty exact Judiciary page tuple")
    if contract_version not in {
        "1.0.0",
        "1.0.1",
        "1.0.2",
        "1.0.3",
        "1.0.4",
        "1.0.5",
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
    }:
        raise ValueError("JUDICIARY_RESULT_PAGE_CONTRACT_VERSION_INVALID")
    first = pages[0]
    if tuple(page.page for page in pages) != tuple(range(1, first.reported_pages + 1)):
        raise ValueError("JUDICIARY_YEAR_PARTITION_TRUNCATED")
    if any(
        (page.year, page.reported_results, page.reported_pages)
        != (first.year, first.reported_results, first.reported_pages)
        for page in pages
    ):
        raise ValueError("JUDICIARY_YEAR_PARTITION_DRIFT")
    listing_count = sum(len(page.dis_ids) for page in pages)
    if listing_count != first.reported_results:
        raise ValueError("JUDICIARY_REPORTED_RESULT_TOTAL_MISMATCH")
    occurrences: dict[int, list[tuple[int, int, int, date | None, str]]] = {}
    dis_ids_list: list[int] = []
    decision_dates_list: list[date | None] = []
    artifact_urls_list: list[str] = []
    seen: set[int] = set()
    for page in pages:
        for row_index, (dis_id, decision_date, artifact_url) in enumerate(
            zip(page.dis_ids, page.decision_dates, page.artifact_urls, strict=True)
        ):
            if contract_version in {"1.0.7", "1.0.8", "1.0.9", "1.0.10", "1.0.11", "1.0.12"}:
                require_judiciary_result_detail_frame_url(
                    artifact_url,
                    dis_id=dis_id,
                    contract_version=contract_version,
                )
            occurrences.setdefault(dis_id, []).append(
                (page.page, row_index, len(page.dis_ids), decision_date, artifact_url)
            )
            if dis_id not in seen:
                seen.add(dis_id)
                dis_ids_list.append(dis_id)
                decision_dates_list.append(decision_date)
                artifact_urls_list.append(artifact_url)
    duplicates = tuple(values for values in occurrences.values() if len(values) > 1)
    if (
        contract_version
        not in {
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        }
        and duplicates
    ):
        raise ValueError("JUDICIARY_DIS_DUPLICATE")
    if contract_version in {"1.0.7", "1.0.8", "1.0.9", "1.0.10", "1.0.11", "1.0.12"}:
        for values in duplicates:
            if (
                None in {value[3] for value in values}
                or len({value[3] for value in values}) != 1
                or len({value[4] for value in values}) != 1
            ):
                raise ValueError("JUDICIARY_DIS_DUPLICATE")
    else:
        shifted_overlaps = 0
        raw_locators = tuple(url for page in pages for url in page.artifact_urls)
        for values in duplicates:
            if len(values) != 2:
                raise ValueError("JUDICIARY_DIS_DUPLICATE")
            earlier, later = values
            exact_boundary = (
                earlier[1] == earlier[2] - 1
                and later[1] == 0
                and later[0] == earlier[0] + 1
                and later[3] == earlier[3]
                and later[4] == earlier[4]
            )
            if exact_boundary:
                continue
            if contract_version != "1.0.6":
                raise ValueError("JUDICIARY_DIS_DUPLICATE")
            shifted_overlaps += 1
            if shifted_overlaps > 1 or (
                earlier[1] != earlier[2] - 1
                or later[1] != 1
                or later[0] != earlier[0] + 1
                or later[3] != earlier[3]
                or later[4] != earlier[4]
            ):
                raise ValueError("JUDICIARY_DIS_DUPLICATE")
            duplicate_date = earlier[3]
            later_page = pages[later[0] - 1]
            intervening_dis_id = later_page.dis_ids[0]
            intervening_date = later_page.decision_dates[0]
            intervening_locator = later_page.artifact_urls[0]
            if (
                duplicate_date is None
                or duplicate_date >= _V1_START
                or intervening_date is None
                or intervening_date >= _V1_START
                or len(occurrences.get(intervening_dis_id, ())) != 1
                or raw_locators.count(intervening_locator) != 1
            ):
                raise ValueError("JUDICIARY_DIS_DUPLICATE")
    dis_ids = tuple(dis_ids_list)
    decision_dates = tuple(decision_dates_list)
    if any(value is None for value in decision_dates):
        code = (
            "JUDICIARY_1997_DECISION_DATE_REQUIRED"
            if first.year == 1997
            else "JUDICIARY_DECISION_DATE_REQUIRED"
        )
        raise ValueError(code)
    in_scope_dis_ids = tuple(
        dis_id
        for dis_id, decision_date in zip(dis_ids, decision_dates, strict=True)
        if first.year > 1997 or (decision_date is not None and decision_date >= _V1_START)
    )
    artifact_by_dis = dict(zip(dis_ids, artifact_urls_list, strict=True))
    if contract_version in {
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
    } and len(set(artifact_by_dis.values())) != len(artifact_by_dis):
        raise ValueError("JUDICIARY_DIS_DUPLICATE")
    artifact_urls = tuple(artifact_by_dis[dis_id] for dis_id in in_scope_dis_ids)
    return JudiciaryYearPartition(
        first.year,
        first.reported_results,
        first.reported_pages,
        listing_count,
        dis_ids,
        decision_dates,
        tuple(artifact_urls_list),
        in_scope_dis_ids,
        artifact_urls,
    )
