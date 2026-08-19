"""Client for the HKeL gazette register grid.

Implements the contract in `docs/design/HKEL_GAZETTE_GRID_CONTRACT.md`, observed
by Patchright discovery on 2026-08-19 under the Department of Justice clearance
the project user reported.

This is deliberately not part of `OfficialHttpConnector`. That connector is the
inert acquisition boundary — GET and HEAD, no body, no redirects — and it stays
that way. The gazette register is a publisher API: `POST`-only, gated on a
capability check, and it issues a CSRF token through a rendered page. Mixing the
two would give source bytes a route into the inert path.

Nothing here is evidence. The grid yields locators; the documents they point at
must still be fetched through the inert connector and preserved through the
ordinary manifest-last flow, per ADR 0100.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlencode

from .official_http import OfficialTransportFailure, PublisherCall

if TYPE_CHECKING:
    from collections.abc import Iterator

GAZETTE_HOST = "www.elegislation.gov.hk"
GAZETTE_PATH = "/gazette"
GRID_PATH = "/grid"
CLIENT_CHECK_PATH = "/client-check"

_LEGAL_SUPPLEMENTS = ("1", "2", "3")
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_CSRF_PATTERN = re.compile(r'["\']csrfToken["\']\s*:\s*["\']([^"\']+)["\']')

CAPABILITY_CLAIM: dict[str, str] = {
    "OS": "Linux",
    "OS_S": "false",
    "BR": "Chrome",
    "BR_S": "true",
    "BRV": "151.0",
    "BRV_S": "true",
    "JS_S": "true",
    "C_S": "true",
}
"""Capability values sent to the HKeL client check.

**These are asserted, not measured.** This client is not Chrome and does not
execute JavaScript; `BR` and `JS_S` are stated because the gate refuses service
without them, and the project owner decided on 2026-08-19 to state them. Recorded
here rather than buried at the call site so the claim stays visible to whoever
reads this next. The grid returns JSON and is never rendered, so the values do
not change how any document is produced or interpreted.
"""


class PublisherExchange(Protocol):
    """The transport surface this client needs, so a test can supply its own."""

    def exchange(
        self,
        call: PublisherCall,
        cookies: dict[str, str] | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        """Send one bounded call and return status, body, and cookies."""
        ...


class GazetteRegisterError(RuntimeError):
    """One exact gazette-register failure, safe to log."""


@dataclass(frozen=True, slots=True)
class GazetteEntry:
    """One row of the gazette register, with its artifact locator."""

    gazette_id: str
    year: str
    supplement: str
    gazette_number: str
    title_english: str
    title_chinese: str
    locator: str
    gazette_date: str
    has_english_pdf: bool
    has_chinese_pdf: bool
    has_bilingual_pdf: bool

    @property
    def item_url(self) -> str:
        """Return the absolute legal-item URL this row points at."""
        return f"https://{GAZETTE_HOST}/{self.locator.lstrip('/')}"


@dataclass(frozen=True, slots=True)
class GazettePage:
    """One page of the register, and what the server said about paging."""

    entries: tuple[GazetteEntry, ...]
    page_number: int
    first_page: int
    last_page: int
    row_offset: int

    @property
    def has_more(self) -> bool:
        """Report whether a later page exists."""
        return self.page_number < self.last_page


def _rows_to_entries(payload: dict[str, object]) -> tuple[GazetteEntry, ...]:
    columns = payload.get("columns")
    rows = payload.get("rowData")
    if not isinstance(columns, list) or not isinstance(rows, list):
        message = "grid reply has no columns or rowData"
        raise GazetteRegisterError(message)
    index = {str(name): position for position, name in enumerate(columns)}
    required = ("GAZETTE_ID", "VIRTUAL_URL", "GAZETTE_DATE")
    missing = [name for name in required if name not in index]
    if missing:
        message = f"grid reply is missing columns: {', '.join(missing)}"
        raise GazetteRegisterError(message)

    def cell(row: list[object], name: str) -> str:
        position = index.get(name)
        if position is None or position >= len(row):
            return ""
        value = row[position]
        return "" if value is None else str(value)

    entries: list[GazetteEntry] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        entries.append(
            GazetteEntry(
                gazette_id=cell(row, "GAZETTE_ID"),
                year=cell(row, "YEAR"),
                supplement=cell(row, "GAZETTE_SUPPLEMENT_NO"),
                gazette_number=cell(row, "DISP_GAZETTE_NO"),
                title_english=cell(row, "GAZETTE_TITLE_ENG"),
                title_chinese=cell(row, "GAZETTE_TITLE_CHI"),
                locator=cell(row, "VIRTUAL_URL"),
                gazette_date=cell(row, "GAZETTE_DATE"),
                # Flags, not URLs: "E", "C", or absent.
                has_english_pdf=bool(cell(row, "ENG_PDF")),
                has_chinese_pdf=bool(cell(row, "CHI_PDF")),
                has_bilingual_pdf=bool(cell(row, "BI_PDF")),
            )
        )
    return tuple(entries)


class HkelGazetteRegisterClient:
    """Read the gazette register through its own grid API."""

    def __init__(
        self,
        transport: PublisherExchange,
        *,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> None:
        """Bind the client to one proxied transport and a bounded page size."""
        if not 1 <= page_size <= _MAX_PAGE_SIZE:
            message = f"page_size must be between 1 and {_MAX_PAGE_SIZE}"
            raise GazetteRegisterError(message)
        self._transport = transport
        self._page_size = page_size
        self._cookies: dict[str, str] = {}
        self._csrf: str | None = None

    def open_session(self) -> str:
        """Pass the capability gate and return the page's CSRF token.

        The gate is satisfied with query parameters rather than an applet. The
        token cannot be guessed or reused across sessions: the grid rejects a call
        without the one its own page issued.
        """
        query = urlencode(CAPABILITY_CLAIM)
        status, _, cookies = self._transport.exchange(
            PublisherCall(GAZETTE_HOST, "GET", f"{CLIENT_CHECK_PATH}?{query}"),
            self._cookies,
        )
        self._cookies = cookies
        status, body, cookies = self._transport.exchange(
            PublisherCall(GAZETTE_HOST, "GET", f"{GAZETTE_PATH}?{query}"),
            self._cookies,
        )
        self._cookies = cookies
        if status != 200:
            message = f"gazette page returned HTTP {status}"
            raise GazetteRegisterError(message)
        found = _CSRF_PATTERN.search(body.decode("utf-8", "replace"))
        if found is None:
            message = "gazette page issued no csrfToken"
            raise GazetteRegisterError(message)
        self._csrf = found.group(1)
        return self._csrf

    def _grid_body(self, page_number: int) -> bytes:
        if self._csrf is None:
            message = "open_session must run before the grid is called"
            raise GazetteRegisterError(message)
        return json.dumps(
            {
                "gridId": "GAZETTE_REGISTER_LIST",
                "gsId": "GAZETTE_REGISTER_LIST",
                "gridIndex": "0",
                "functionId": "LRTS10",
                "queryId": "GAZETTE_REGISTER_QRY",
                "screenId": "ERTS0502",
                "gridBd": "hk.gov.doj.hkel.grid.lrt.LRTS1002GridBd",
                "namespace": "hk.gov.doj.hkel.bd.ert.ERTS0502Bd",
                "pkFields": "GAZETTE_ID",
                "pageNo": str(page_number),
                "pageSize": str(self._page_size),
                # A list of KEY=VALUE strings, not an object. A repeated key is
                # how a multi-valued filter is expressed, which is why the three
                # supplement entries select Legal Supplements 1, 2 and 3.
                "queryParams": [
                    "GAZETTE_NO=",
                    "GAZETTE_NAME=",
                    *(f"GAZETTE_SUPPLEMENT_NO={value}" for value in _LEGAL_SUPPLEMENTS),
                    "GAZETTE_DATE_FR=",
                    "GAZETTE_DATE_TO=",
                    "SER_FLD=E",
                    "GN_TYP=N",
                    "GN_PFX=-",
                    "GN_SFX=",
                    "GN_NO=",
                    "GN_YR=",
                ],
                "columns": [
                    "GAZETTE_SUPPLEMENT_NO",
                    "GAZETTE_DATE",
                    "DISP_GAZETTE_NO",
                    "GAZETTE_NAME",
                    "ENG_PDF",
                    "CHI_PDF",
                    "BI_PDF",
                ],
                "csrfToken": self._csrf,
                "MODE": "1",
            },
            separators=(",", ":"),
        ).encode()

    def page(self, page_number: int = 1) -> GazettePage:
        """Read one page of the register."""
        if page_number < 1:
            message = "page_number starts at 1"
            raise GazetteRegisterError(message)
        try:
            status, body, cookies = self._transport.exchange(
                PublisherCall(
                    GAZETTE_HOST,
                    "POST",
                    GRID_PATH,
                    body=self._grid_body(page_number),
                    content_type="application/json",
                ),
                self._cookies,
            )
        except OfficialTransportFailure as error:
            message = f"grid transport failed on page {page_number}"
            raise GazetteRegisterError(message) from error
        self._cookies = cookies
        if status != 200:
            message = f"grid returned HTTP {status} on page {page_number}"
            raise GazetteRegisterError(message)
        payload = json.loads(body)
        if not isinstance(payload, dict):
            message = "grid reply was not a JSON object"
            raise GazetteRegisterError(message)
        return GazettePage(
            entries=_rows_to_entries(payload),
            page_number=page_number,
            first_page=int(payload.get("firstPage", 1) or 1),
            last_page=int(payload.get("lastPage", 1) or 1),
            row_offset=int(payload.get("rowOffset", 0) or 0),
        )

    def iter_entries(self, *, max_pages: int | None = None) -> Iterator[GazetteEntry]:
        """Walk the register from the first page, counting what actually arrives.

        `totalRecords` is not used and must not be: it reported 100 against a
        `lastPage` of 1415, so it is not a row count. `lastPage` is re-read on
        every page because it can move while paging.
        """
        page_number = 1
        seen = 0
        while True:
            page = self.page(page_number)
            for entry in page.entries:
                seen += 1
                yield entry
            if not page.entries or not page.has_more:
                return
            page_number += 1
            if max_pages is not None and page_number > max_pages:
                return
