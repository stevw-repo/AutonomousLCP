"""Offline tests for the HKeL gazette register client.

The transport is stubbed so the suite never leaves the machine. What is proved
here is the contract in `docs/design/HKEL_GAZETTE_GRID_CONTRACT.md`: the gate is
passed before the grid is called, the request carries the filters and the
page-issued token, rows become locators, and paging is driven by `lastPage`
rather than by `totalRecords`, which is not a row count.
"""

from __future__ import annotations

import json

import pytest
from asklegal_source_connectors.hkel_gazette import (
    CAPABILITY_CLAIM,
    GazetteRegisterError,
    HkelGazetteRegisterClient,
)
from asklegal_source_connectors.official_http import (
    ProxiedOfficialHttpTransport,
    PublisherCall,
)

_COLUMNS = [
    "GAZETTE_ID", "YEAR", "GAZETTE_SUPPLEMENT_NO", "DISP_GAZETTE_NO", "GAZETTE_NO",
    "GAZETTE_NAME", "GAZETTE_TITLE_ENG", "GAZETTE_TITLE_CHI",
    "ENG_PDF", "CHI_PDF", "BI_PDF", "GZ_NO", "VIRTUAL_URL", "GAZETTE_DATE",
]
_ROW = [
    "30056", "2026", "Legal Supplement No. 1", "1 of 2026", "1 of 2026", None,
    "Appropriation Ordinance 2026", "《2026年撥款條例》",
    "E", "C", None, "1", "hk/2026/1", "08/05/2026",
]
# Shaped like the real served page: the token is a hidden form input.
_PAGE_HTML = (
    b'<html><form name="proj_form" method="post" action="/gazette">'
    b'<input type="hidden" name="MODE" value="1" />'
    b'<input type="hidden" name="_CSRF_TOKEN" value="TOKEN-FROM-PAGE" />'
    b"</form></html>"
)


class StubTransport:
    """Records every call and replays queued replies in order."""

    def __init__(self, replies: list[tuple[int, bytes]]) -> None:
        """Queue the replies this transport will return."""
        self._replies = list(replies)
        self.calls: list[PublisherCall] = []

    def exchange(
        self,
        call: PublisherCall,
        cookies: dict[str, str] | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        """Return the next queued reply and record the call."""
        self.calls.append(call)
        status, body = self._replies.pop(0) if self._replies else (200, b"{}")
        return (status, body, dict(cookies or {}))


def _grid_reply(*, last_page: int = 3, rows: int = 1) -> bytes:
    return json.dumps(
        {
            "rowOffset": 0,
            "firstPage": 1,
            "lastPage": last_page,
            # Deliberately wrong as a row count, exactly as the live service
            # reports it. Nothing may rely on this value.
            "totalRecords": 100,
            "columns": _COLUMNS,
            "rowData": [_ROW for _ in range(rows)],
        }
    ).encode()


def _client(replies: list[tuple[int, bytes]]) -> tuple[HkelGazetteRegisterClient, StubTransport]:
    transport = StubTransport(replies)
    return (HkelGazetteRegisterClient(transport), transport)


def test_session_passes_the_capability_gate_then_reads_the_token() -> None:
    """The client check comes first; the token is taken from the page, not invented."""
    client, transport = _client([(200, b""), (200, _PAGE_HTML)])

    token = client.open_session()

    assert token == "TOKEN-FROM-PAGE"
    assert transport.calls[0].path.startswith("/client-check?")
    assert transport.calls[1].path.startswith("/gazette?")
    for key in ("JS_S", "C_S", "BR"):
        assert f"{key}={CAPABILITY_CLAIM[key]}" in transport.calls[0].path


def test_grid_cannot_be_called_before_the_gate() -> None:
    """Without a page-issued token the grid would reject the call anyway."""
    client, _ = _client([])

    with pytest.raises(GazetteRegisterError):
        client.page(1)


def test_grid_request_carries_the_supplement_filters_and_the_token() -> None:
    """A repeated key is how the API expresses a multi-valued filter."""
    client, transport = _client([(200, b""), (200, _PAGE_HTML), (200, _grid_reply())])
    client.open_session()

    client.page(1)

    grid = transport.calls[-1]
    assert grid.method == "POST"
    assert grid.path == "/grid"
    assert grid.content_type == "application/json"
    body = json.loads(grid.body or b"{}")
    assert body["csrfToken"] == "TOKEN-FROM-PAGE"
    assert body["pageNo"] == "1"
    supplements = [p for p in body["queryParams"] if p.startswith("GAZETTE_SUPPLEMENT_NO=")]
    assert supplements == [
        "GAZETTE_SUPPLEMENT_NO=1",
        "GAZETTE_SUPPLEMENT_NO=2",
        "GAZETTE_SUPPLEMENT_NO=3",
    ]


def test_rows_become_entries_with_an_absolute_locator() -> None:
    """VIRTUAL_URL is site-relative; the caller needs a usable address."""
    client, _ = _client([(200, b""), (200, _PAGE_HTML), (200, _grid_reply())])
    client.open_session()

    page = client.page(1)

    entry = page.entries[0]
    assert entry.gazette_id == "30056"
    assert entry.locator == "hk/2026/1"
    assert entry.item_url == "https://www.elegislation.gov.hk/hk/2026/1"
    assert entry.title_english == "Appropriation Ordinance 2026"
    assert entry.gazette_date == "08/05/2026"


def test_pdf_columns_are_read_as_flags_not_urls() -> None:
    """ENG_PDF is "E", not an address; treating it as a URL would fetch nothing."""
    client, _ = _client([(200, b""), (200, _PAGE_HTML), (200, _grid_reply())])
    client.open_session()

    entry = client.page(1).entries[0]

    assert entry.has_english_pdf is True
    assert entry.has_chinese_pdf is True
    assert entry.has_bilingual_pdf is False


def test_paging_follows_last_page_and_ignores_total_records() -> None:
    """Live, totalRecords reported 100 against 1415 pages; it is not a row count."""
    replies = [(200, b""), (200, _PAGE_HTML)]
    replies += [(200, _grid_reply(last_page=3, rows=2)) for _ in range(3)]
    client, transport = _client(replies)
    client.open_session()

    entries = list(client.iter_entries())

    assert len(entries) == 6
    pages = [json.loads(c.body or b"{}")["pageNo"] for c in transport.calls if c.path == "/grid"]
    assert pages == ["1", "2", "3"]


def test_paging_stops_when_a_page_returns_nothing() -> None:
    """An empty page ends the walk rather than looping to lastPage regardless."""
    replies = [(200, b""), (200, _PAGE_HTML)]
    replies += [(200, _grid_reply(last_page=9, rows=1)), (200, _grid_reply(last_page=9, rows=0))]
    client, _ = _client(replies)
    client.open_session()

    assert len(list(client.iter_entries())) == 1


def test_a_reply_missing_its_columns_fails_rather_than_guessing() -> None:
    """Row data is positional, so absent columns make every cell a guess."""
    broken = json.dumps({"rowData": [_ROW], "firstPage": 1, "lastPage": 1}).encode()
    client, _ = _client([(200, b""), (200, _PAGE_HTML), (200, broken)])
    client.open_session()

    with pytest.raises(GazetteRegisterError):
        client.page(1)


def test_a_failing_grid_status_is_reported_not_swallowed() -> None:
    """A rejected token or expired session must surface, not return zero rows."""
    client, _ = _client([(200, b""), (200, _PAGE_HTML), (403, b"denied")])
    client.open_session()

    with pytest.raises(GazetteRegisterError):
        client.page(1)


def test_pdf_address_is_the_locator_a_bang_and_the_language() -> None:
    """Observed in the rendered grid: /hk/2026/1!en, no server round-trip."""
    client, _ = _client([(200, b""), (200, _PAGE_HTML), (200, _grid_reply())])
    client.open_session()

    entry = client.page(1).entries[0]

    assert entry.pdf_url("en") == "https://www.elegislation.gov.hk/hk/2026/1!en"
    assert entry.pdf_url("zh-Hant-HK") == "https://www.elegislation.gov.hk/hk/2026/1!zh-Hant-HK"


def test_an_unpublished_language_returns_none_rather_than_a_guess() -> None:
    """The grid shows a bare dash; inventing an address would fetch nothing."""
    row = list(_ROW)
    row[_COLUMNS.index("CHI_PDF")] = None
    reply = json.dumps(
        {"firstPage": 1, "lastPage": 1, "columns": _COLUMNS, "rowData": [row]}
    ).encode()
    client, _ = _client([(200, b""), (200, _PAGE_HTML), (200, reply)])
    client.open_session()

    entry = client.page(1).entries[0]

    assert entry.pdf_url("zh-Hant-HK") is None
    assert entry.pdf_url("en") is not None
    assert entry.published_pdf_urls() == ("https://www.elegislation.gov.hk/hk/2026/1!en",)


def test_an_unknown_pdf_language_is_refused() -> None:
    """Only the two languages the grid actually publishes are addressable."""
    client, _ = _client([(200, b""), (200, _PAGE_HTML), (200, _grid_reply())])
    client.open_session()
    entry = client.page(1).entries[0]

    with pytest.raises(GazetteRegisterError):
        entry.pdf_url("sc")


def test_a_date_window_is_sent_and_bounds_the_query() -> None:
    """An unbounded walk is not reproducible; the window is the completeness rule."""
    client, transport = _client([(200, b""), (200, _PAGE_HTML), (200, _grid_reply(last_page=1))])
    client.open_session()

    client.page(1, date_from="01/01/2026", date_to="30/06/2026")

    body = json.loads(transport.calls[-1].body or b"{}")
    assert "GAZETTE_DATE_FR=01/01/2026" in body["queryParams"]
    assert "GAZETTE_DATE_TO=30/06/2026" in body["queryParams"]


def test_a_malformed_date_is_refused_before_the_request() -> None:
    """A silently ignored filter would return the whole register as if bounded."""
    client, _ = _client([(200, b""), (200, _PAGE_HTML)])
    client.open_session()

    with pytest.raises(GazetteRegisterError):
        client.page(1, date_from="2026-01-01", date_to="30/06/2026")


def test_the_token_is_read_from_the_hidden_form_input() -> None:
    """The served HTML carries _CSRF_TOKEN as a hidden input, not as a JSON key.

    The lowercase `csrfToken` key appears only in the request body the page's own
    JavaScript assembles. Matching on that found nothing against the real page.
    """
    served = (
        b'<form name="proj_form" method="post" action="/gazette">'
        b'<input type="hidden" name="MODE" value="1" />'
        b'<input type="hidden" name="_CSRF_TOKEN" value="WM4YN6Pw73wVEn8Z/qvt0reo==" />'
        b'</form>'
    )
    client, _ = _client([(200, b""), (200, served)])

    assert client.open_session() == "WM4YN6Pw73wVEn8Z/qvt0reo=="


def test_a_session_transport_sends_its_session_on_both_surfaces() -> None:
    """with_session must apply to exchange too, or gated fetches get the gate page.

    This was a real defect: with_session seeded the inert `request` path only, so
    `with_session(...).exchange(...)` sent no cookies and every gated document came
    back as the capability check instead of the document.
    """
    seen: list[str] = []

    class Recorder(ProxiedOfficialHttpTransport):
        """Captures the Cookie header a real exchange would have sent."""

        def exchange(
            self,
            call: PublisherCall,
            cookies: dict[str, str] | None = None,
        ) -> tuple[int, bytes, dict[str, str]]:
            """Record which jar the base class would use."""
            del call
            jar = dict(cookies) if cookies is not None else dict(self._session_cookies)
            seen.append("; ".join(f"{k}={v}" for k, v in jar.items()))
            return (200, b"", jar)

    bound = Recorder("proxy", 3128).with_session({"JSTP1": "abc"})
    Recorder.exchange(bound, PublisherCall("h", "GET", "/x"))

    assert seen == ["JSTP1=abc"]
