"""Strict authentic Judiciary year/page enumeration contracts."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

import asklegal_source_connectors.hk_judiciary_authentic as judiciary_authentic
import pytest
from asklegal_source_connectors.hk_judiciary import (
    JudiciaryObservationKind,
    registered_judiciary_observation_contract,
)
from asklegal_source_connectors.hk_judiciary_authentic import (
    JudiciaryListingOccurrence,
    build_judiciary_year_result_url,
    parse_judiciary_current_list_observation,
    parse_judiciary_rss_observation,
    parse_judiciary_year_result_page,
    reconcile_judiciary_year_partition,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def test_current_list_and_rss_parse_to_typed_discovery_only_observations() -> None:
    """Returning opaque refs instead of exact descendant facts would fail this test."""
    current = parse_judiciary_current_list_observation(
        b"""<html><body><table id="newjudgments"><tr><td>05/09/2026</td>
        <td><a href="https://legalref.judiciary.hk/lrs/common/search/search_result_detail_body.jsp?ID=&amp;DIS=901&amp;QS=%2B&amp;TP=JU">Case</a></td>
        </tr></table></body></html>""",
        contract=registered_judiciary_observation_contract(JudiciaryObservationKind.CURRENT_LIST),
    )
    rss = parse_judiciary_rss_observation(
        b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><title>Judiciary</title><item>
        <title>Case 902</title>
        <link>https://legalref.judiciary.hk/lrs/common/search/search_result_detail_body.jsp?ID=&amp;DIS=902&amp;QS=%2B&amp;TP=JU</link>
        <guid>judiciary-902</guid><pubDate>Sat, 05 Sep 2026 00:00:00 +0800</pubDate>
        </item></channel></rss>""",
        contract=registered_judiciary_observation_contract(JudiciaryObservationKind.RSS),
    )

    assert current.kind is JudiciaryObservationKind.CURRENT_LIST
    assert current.occurrences[0].dis_id == 901
    assert current.occurrences[0].decision_date == date(2026, 9, 5)
    assert rss.kind is JudiciaryObservationKind.RSS
    assert rss.occurrences[0].dis_id == 902
    assert rss.occurrences[0].relationship_ids[-1] == "judiciary-dis-902-proceeding-identity"
    assert not current.proves_complete
    assert not current.proves_no_change
    assert not rss.proves_complete
    assert not rss.proves_no_change


@pytest.mark.parametrize(
    ("parser", "kind", "body"),
    [
        (
            parse_judiciary_current_list_observation,
            JudiciaryObservationKind.CURRENT_LIST,
            b'<html><body><table id="changed"><tr><td>05/09/2026</td><td><a href="https://legalref.judiciary.hk/lrs/common/search/search_result_detail_body.jsp?ID=&amp;DIS=901&amp;QS=%2B&amp;TP=JU">Case</a></td></tr></table></body></html>',
        ),
        (
            parse_judiciary_rss_observation,
            JudiciaryObservationKind.RSS,
            b"".join(
                (
                    b'<rss version="2.0"><channel><item><link>',
                    b"https://evil.example/?DIS=902</link><guid>x</guid><pubDate>",
                    b"Sat, 05 Sep 2026 00:00:00 +0800</pubDate></item></channel></rss>",
                )
            ),
        ),
    ],
)
def test_incremental_grammar_drift_fails_before_descendant_projection(
    parser: Callable[..., object], kind: JudiciaryObservationKind, body: bytes
) -> None:
    """A changed root or locator must not produce a partly trusted observation."""
    with pytest.raises(ValueError, match="JUDICIARY_INCREMENTAL_"):
        parser(body, contract=registered_judiciary_observation_contract(kind))


def _page(*, page: int, links: str) -> bytes:
    return (
        f'<html><body><p>3 results / 2 pages</p><input name="page" value="{page}">'
        f"{links}</body></html>"
    ).encode()


def _current_advanced_search_form() -> bytes:
    """Supply a portable structure-only copy of the observed primary form and decoys."""
    return b"""<form name="frm_search" id="frm_search" method="get" action=""
      onsubmit="javascript:return FORM_SUBMIT(this);">
      <input type="hidden" name="isadvsearch" value="1">
      <input type="text" name="unrelatedPublisherField" value="">
      <input type="checkbox" name="stem" value="1" checked>
      <input type="hidden" name="txtselectopt3" value="5">
      <input type="checkbox" name="selall2" value="1" checked>
      <input type="checkbox" name="selallct" value="1" checked>
      <select name="selDatabase2" multiple="" multiple>
        <option value="JU" selected>Judgment</option><option value="RV" selected>Review</option>
        <option value="RS" selected>Sentence</option>
        <option value="PD" selected>Practice direction</option>
      </select>
      <select name="selSchct" multiple="" multiple>
        <option value="FA" selected>FA</option><option value="CA" selected>CA</option>
        <option value="HC" selected>HC</option><option value="CT" selected>CT</option>
        <option value="DC" selected>DC</option><option value="FC" selected>FC</option>
        <option value="LD" selected>LD</option><option value="OT" selected>OT</option>
      </select>
      <input type="hidden" name="txtSearch3" value="">
      <select name="day1"><option value="" selected></option><option value="0"></option>
        <option value="1"></option><option value="2"></option><option value="3"></option>
        <option value="4"></option><option value="5"></option><option value="6"></option>
        <option value="7"></option><option value="8"></option><option value="9"></option>
        <option value="10"></option><option value="11"></option><option value="12"></option>
        <option value="13"></option><option value="14"></option><option value="15"></option>
        <option value="16"></option><option value="17"></option><option value="18"></option>
        <option value="19"></option><option value="20"></option><option value="21"></option>
        <option value="22"></option><option value="23"></option><option value="24"></option>
        <option value="25"></option><option value="26"></option><option value="27"></option>
        <option value="28"></option><option value="29"></option><option value="30"></option>
        <option value="31"></option></select>
      <select name="month"><option value="" selected></option><option value="0"></option>
        <option value="1"></option><option value="2"></option><option value="3"></option>
        <option value="4"></option><option value="5"></option><option value="6"></option>
        <option value="7"></option><option value="8"></option><option value="9"></option>
        <option value="10"></option><option value="11"></option>
        <option value="12"></option></select>
      <select name="year"><option value="" selected></option><option value="0"></option></select>
    </form>
    <form method="post" action="later-submit.jsp">
      <input name="page" value="999"><input name="database" value="JU">
      <input name="court" value="FA">
    </form>
    <form method="post" action="other-submit.jsp"><input name="page" value="2"></form>"""


def _current_result_page() -> bytes:
    return b"""<html><body><div>Result:</div><span id="searchresult-total">2</span><div>found</div>
    <div>Total Pages:</div><span id="searchresult-totalpages">1</span><table id="table">
    <tr><td>Date</td><td>: 30/06/1997</td><td><a class="default"
      href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?AH=S&amp;DIS=1&amp;QS=%28%2F%2F1997%29&amp;TP=JU">one</a></td></tr>
    <tr><td>Date</td><td>: 01/07/1997</td><td><a class="default"
      href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?AH=S&amp;DIS=2&amp;QS=%28%2F%2F1997%29&amp;TP=JU">two</a></td></tr>
    </table></body></html>"""


def _attempt_d_result_page() -> bytes:
    return (_FIXTURES / "judiciary_result_page_1997_sanitized.html").read_bytes()


def _attempt_e_page_two() -> bytes:
    return (_FIXTURES / "judiciary_result_page_1997_page2_sanitized.html").read_bytes()


def _attempt_f_page_one() -> bytes:
    return (_FIXTURES / "judiciary_result_page_1997_attempt_f_sanitized.html").read_bytes()


def _attempt_j_rs_page_sanitized() -> bytes:
    """Project the retained text-free Attempt-J RS row shape onto a sanitized page."""
    original = _attempt_f_page_one()
    return original.replace(
        b"var temp18226='DIS=18226&QS=%2B&TP=JU';",
        b"var temp18226='DIS=18226&QS=%2B&TP=RS';",
        1,
    )


def _attempt_k_rs_page_sanitized() -> bytes:
    """Project the authentic text-free Attempt-K RS anchor shape onto a sanitized page."""
    body = _attempt_j_rs_page_sanitized()
    first = b"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'+temp18226);\">"
    second = b"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'+temp18226);\">"
    return body.replace(
        first,
        first[:-1] + b' class="searchfont result-caseno">',
        1,
    ).replace(
        second,
        second[:-1] + b" class=searchfont>",
        1,
    )


def _attempt_n_rv_page_sanitized() -> bytes:
    """Project the retained Attempt-N RV row shape onto the sanitized page."""
    return _attempt_k_rs_page_sanitized().replace(b"TP=RS';", b"TP=RV';", 1)


def _attempt_o_typed_optional_frames_page_sanitized() -> bytes:
    """Project Attempt O's exact RS/RV third-frame shape onto sanitized rows."""
    body = _attempt_k_rs_page_sanitized()
    body = body.replace(
        b"var temp26930='DIS=26930&QS=%2B&TP=JU';",
        b"var temp26930='DIS=26930&QS=%2B&TP=RV';",
        1,
    )
    for dis_id in (b"26930",):
        first = (
            b"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'+"
            b"temp" + dis_id + b');">'
        )
        second = (
            b"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'+temp" + dis_id + b');">'
        )
        body = body.replace(
            first,
            first[:-1] + b' class="searchfont result-caseno">',
            1,
        ).replace(second, second[:-1] + b" class=searchfont>", 1)
    for dis_id, result_type, decision_date in (
        (b"18226", b"RS", b"16/10/1997"),
        (b"26930", b"RV", b"16/10/1997"),
    ):
        row_start = body.index(b"var temp" + dis_id)
        insertion = body.index(b"</td><td>" + decision_date, row_start)
        frame = (
            b'<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
            b"AH=S&DIS="
            + dis_id
            + b"&QS=%2B&TP="
            + result_type
            + b'" target="_top" class=default >frame</a>'
        )
        body = body[:insertion] + frame + body[insertion:]
    return body


def _attempt_s_direct_word_page_sanitized() -> bytes:
    """Project the text-free Attempt-S direct-Word row onto the sanitized fixture."""
    original = (
        b"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'+temp24946);\">24946</a>"
        b"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'+temp24946);\">24946</a>"
        b'<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
        b'AH=S&amp;DIS=24946&amp;QS=%2B&amp;TP=JU">24946</a>'
    )
    replacement = (
        b"<a href=\"javascript:judpop1('/doc/judg/word/vetted/other/en/1997/sanitized.doc');\">"
        b"24946</a>"
        b'<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
        b'AH=S&DIS=24946&QS=%2B&TP=JU" target="_top" class=default >'
        b"24946</a>"
    )
    body = _attempt_f_page_one()
    assert body.count(original) == 1
    return body.replace(original, replacement, 1)


def test_result_1012_accepts_exact_attempt_s_direct_word_row_as_presentation_metadata() -> None:
    """Attempt S admits the direct Word row but returns only the canonical DIS locator."""
    body = _attempt_s_direct_word_page_sanitized()

    page = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=1,
        contract_version="1.0.12",
    )

    assert page.artifact_urls[0] == (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=24946&QS=%2B&TP=JU"
    )
    assert page.presentation_urls[0] == (
        "javascript:judpop1('/doc/judg/word/vetted/other/en/1997/sanitized.doc');"
    )
    complete_page = replace(
        page,
        reported_results=len(page.dis_ids),
        reported_pages=1,
        advertised_next_page=None,
    )
    partition = reconcile_judiciary_year_partition((complete_page,), contract_version="1.0.12")
    assert partition.artifact_urls[0] == page.artifact_urls[0]


def test_result_page_projects_occurrence_and_presentation_metadata() -> None:
    """Dropping a source row's presentation locator loses an auditable relationship."""
    page = parse_judiciary_year_result_page(
        _attempt_s_direct_word_page_sanitized(),
        year=1997,
        page=1,
        contract_version="1.0.13",
    )

    occurrence = page.occurrences[0]

    assert type(occurrence) is JudiciaryListingOccurrence
    assert occurrence.dis_id == 24946
    assert occurrence.artifact_url == (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=24946&QS=%2B&TP=JU"
    )
    assert occurrence.presentation_url == (
        "javascript:judpop1('/doc/judg/word/vetted/other/en/1997/sanitized.doc');"
    )
    assert occurrence.relationship_ids == (
        "judiciary-dis-24946-judgment",
        "judiciary-dis-24946-correction",
        "judiciary-dis-24946-reissue",
        "judiciary-dis-24946-language",
        "judiciary-dis-24946-translation",
        "judiciary-dis-24946-alias",
        "judiciary-dis-24946-proceeding-identity",
    )


def test_result_1012_accepts_prior_case_year_when_filename_repeats_that_year() -> None:
    """A decided-later listing may retain the source's earlier case-file year path."""
    body = _attempt_s_direct_word_page_sanitized().replace(b"1997", b"2011")
    body = body.replace(
        b"/en/2011/sanitized.doc",
        b"/en/2009/sanitized_2009.doc",
        1,
    )

    page = parse_judiciary_year_result_page(
        body,
        year=2011,
        page=1,
        contract_version="1.0.12",
    )

    assert page.presentation_urls[0] == (
        "javascript:judpop1('/doc/judg/word/vetted/other/en/2009/sanitized_2009.doc');"
    )


@pytest.mark.parametrize(
    "prior_path",
    [
        b"/en/1996/sanitized_1996.doc",
        b"/en/2009/sanitized.doc",
        b"/en/2009/sanitized_2008.doc",
    ],
    ids=("before-1997", "missing-path-year-suffix", "wrong-repeated-year"),
)
def test_result_1012_rejects_unbound_prior_case_year_paths(prior_path: bytes) -> None:
    """A prior-year presentation path stays bound to the admitted year and filename."""
    body = _attempt_s_direct_word_page_sanitized().replace(b"1997", b"2011")
    body = body.replace(b"/en/2011/sanitized.doc", prior_path, 1)

    with pytest.raises(ValueError, match="JUDICIARY_"):
        parse_judiciary_year_result_page(
            body,
            year=2011,
            page=1,
            contract_version="1.0.12",
        )


def test_result_1011_rejects_exact_attempt_s_direct_word_row() -> None:
    """The new direct-Word presentation shape must not alter the old result contract."""
    with pytest.raises(ValueError, match="JUDICIARY_"):
        parse_judiciary_year_result_page(
            _attempt_s_direct_word_page_sanitized(),
            year=1997,
            page=1,
            contract_version="1.0.11",
        )


def test_form_1013_maps_to_attempt_s_result_1012() -> None:
    """The current form grammar advances independently to the new result contract."""
    url = build_judiciary_year_result_url(
        _current_advanced_search_form(),
        entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        year=1997,
        page=1,
        contract_version="1.0.13",
    )

    assert url == (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
        "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
        "selallct=1&stem=1&txtselectopt3=5&day1=&month=&txtSearch3=%2F%2F1997&"
        "year=1997&page=1"
    )
    assert (
        judiciary_authentic.require_judiciary_year_result_url(
            url,
            year=1997,
            page=1,
            contract_version="1.0.13",
        )
        == url
    )


def test_form_1013_builds_the_exact_second_result_page_url() -> None:
    """The current form must preserve the explicit result-page coordinate."""
    url = build_judiciary_year_result_url(
        _current_advanced_search_form(),
        entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        year=1997,
        page=2,
        contract_version="1.0.13",
    )

    assert url == (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
        "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
        "selallct=1&stem=1&txtselectopt3=5&day1=&month=&txtSearch3=%2F%2F1997&"
        "year=1997&page=2"
    )
    assert (
        judiciary_authentic.require_judiciary_year_result_url(
            url,
            year=1997,
            page=2,
            contract_version="1.0.13",
        )
        == url
    )


_Result1012Mutation = Callable[[bytes], bytes]
_ATTEMPT_S_DIRECT_START = (
    b"<a href=\"javascript:judpop1('/doc/judg/word/vetted/other/en/1997/sanitized.doc');\">"
)
_ATTEMPT_S_DIRECT_ANCHOR = _ATTEMPT_S_DIRECT_START + b"24946</a>"
_ATTEMPT_S_FRAME_START = (
    b'<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
    b'AH=S&DIS=24946&QS=%2B&TP=JU" target="_top" class=default >'
)
_ATTEMPT_S_FRAME_ANCHOR = _ATTEMPT_S_FRAME_START + b"24946</a>"
_ATTEMPT_S_PAIRED_JUDPOP1 = (
    b"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'+temp24946);\">24946</a>"
)
_ATTEMPT_S_PAIRED_JUDPOP = (
    b"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'+temp24946);\">24946</a>"
)


def _replace_attempt_s_fixture(body: bytes, old: bytes, new: bytes) -> bytes:
    assert body.count(old) == 1
    return body.replace(old, new, 1)


_RESULT_1012_DIRECT_WORD_MUTATIONS: tuple[tuple[str, _Result1012Mutation], ...] = (
    (
        "script-tp-lowercase",
        lambda body: _replace_attempt_s_fixture(
            body,
            b"var temp24946='DIS=24946&QS=%2B&TP=JU';",
            b"var temp24946='DIS=24946&QS=%2B&TP=ju';",
        ),
    ),
    (
        "script-tp-unknown",
        lambda body: _replace_attempt_s_fixture(
            body,
            b"var temp24946='DIS=24946&QS=%2B&TP=JU';",
            b"var temp24946='DIS=24946&QS=%2B&TP=ZZ';",
        ),
    ),
    (
        "script-temp-dis-mismatch",
        lambda body: _replace_attempt_s_fixture(
            body, b"temp24946='DIS=24946", b"temp24947='DIS=24946"
        ),
    ),
    (
        "script-dis-frame-mismatch",
        lambda body: _replace_attempt_s_fixture(
            body, b"temp24946='DIS=24946", b"temp24946='DIS=24947"
        ),
    ),
    (
        "script-noncanonical-digits",
        lambda body: _replace_attempt_s_fixture(
            body, b"temp24946='DIS=24946", b"temp024946='DIS=024946"
        ),
    ),
    (
        "word-function-changed",
        lambda body: _replace_attempt_s_fixture(
            body, b"javascript:judpop1('/doc", b"javascript:judpop('/doc"
        ),
    ),
    (
        "word-call-missing",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_DIRECT_START,
            b'<a href="javascript:/doc/judg/word/vetted/other/en/1997/sanitized.doc;">',
        ),
    ),
    (
        "word-quotes-missing",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_DIRECT_START,
            b'<a href="javascript:judpop1(/doc/judg/word/vetted/other/en/1997/sanitized.doc);">',
        ),
    ),
    (
        "word-quotes-entity-encoded",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_DIRECT_START,
            b'<a href="javascript:judpop1(&#39;/doc/judg/word/vetted/other/en/1997/'
            b'sanitized.doc&#39;);">',
        ),
    ),
    (
        "word-semicolon-missing",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc');", b"sanitized.doc')"),
    ),
    (
        "word-extra-javascript",
        lambda body: _replace_attempt_s_fixture(
            body, b"sanitized.doc');", b"sanitized.doc');void 0"
        ),
    ),
    (
        "word-absolute-admitted-host",
        lambda body: _replace_attempt_s_fixture(
            body,
            b"'/doc/judg/word/vetted/other/en/1997/sanitized.doc'",
            b"'https://legalref.judiciary.hk/doc/judg/word/vetted/other/en/1997/sanitized.doc'",
        ),
    ),
    (
        "word-off-host",
        lambda body: _replace_attempt_s_fixture(
            body,
            b"'/doc/judg/word/vetted/other/en/1997/sanitized.doc'",
            b"'https://evil.example/sanitized.doc'",
        ),
    ),
    (
        "word-http",
        lambda body: _replace_attempt_s_fixture(
            body,
            b"'/doc/judg/word/vetted/other/en/1997/sanitized.doc'",
            b"'http://legalref.judiciary.hk/doc/judg/word/vetted/other/en/1997/sanitized.doc'",
        ),
    ),
    (
        "word-root-wrong",
        lambda body: _replace_attempt_s_fixture(
            body, b"/doc/judg/word/vetted/", b"/doc/judg/word/draft/"
        ),
    ),
    (
        "word-root-case-changed",
        lambda body: _replace_attempt_s_fixture(body, b"/word/", b"/Word/"),
    ),
    (
        "word-language-wrong",
        lambda body: _replace_attempt_s_fixture(body, b"/other/en/1997/", b"/other/zh/1997/"),
    ),
    (
        "word-year-wrong",
        lambda body: _replace_attempt_s_fixture(
            body, b"/en/1997/sanitized.doc", b"/en/1998/sanitized.doc"
        ),
    ),
    (
        "word-extension-wrong",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc", b"sanitized.pdf"),
    ),
    (
        "word-extension-case-wrong",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc", b"sanitized.DOC"),
    ),
    (
        "word-query",
        lambda body: _replace_attempt_s_fixture(
            body, b"sanitized.doc", b"sanitized.doc?download=1"
        ),
    ),
    (
        "word-fragment",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc", b"sanitized.doc#word"),
    ),
    (
        "word-percent-encoding",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc", b"sanitized%2edoc"),
    ),
    (
        "word-backslash",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc", b"sanitized\\.doc"),
    ),
    (
        "word-dot-traversal",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc", b"../sanitized.doc"),
    ),
    (
        "word-whitespace",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc", b"sanitized doc"),
    ),
    (
        "word-empty-filename",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc", b".doc"),
    ),
    (
        "word-empty-path-segment",
        lambda body: _replace_attempt_s_fixture(
            body, b"/1997/sanitized.doc", b"/1997//sanitized.doc"
        ),
    ),
    (
        "word-extra-path-segment",
        lambda body: _replace_attempt_s_fixture(
            body, b"/1997/sanitized.doc", b"/1997/extra/sanitized.doc"
        ),
    ),
    (
        "word-unsafe-filename",
        lambda body: _replace_attempt_s_fixture(body, b"sanitized.doc", b"sanitized~file.doc"),
    ),
    (
        "direct-anchor-attributes",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_DIRECT_START,
            _ATTEMPT_S_DIRECT_START.replace(b"<a href", b"<a class=default href"),
        ),
    ),
    (
        "direct-anchor-missing",
        lambda body: _replace_attempt_s_fixture(body, _ATTEMPT_S_DIRECT_ANCHOR, b""),
    ),
    (
        "direct-anchor-duplicated",
        lambda body: _replace_attempt_s_fixture(
            body, _ATTEMPT_S_DIRECT_ANCHOR, _ATTEMPT_S_DIRECT_ANCHOR * 2
        ),
    ),
    (
        "anchors-reordered",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_DIRECT_ANCHOR + _ATTEMPT_S_FRAME_ANCHOR,
            _ATTEMPT_S_FRAME_ANCHOR + _ATTEMPT_S_DIRECT_ANCHOR,
        ),
    ),
    (
        "anchors-nested",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_DIRECT_ANCHOR + _ATTEMPT_S_FRAME_ANCHOR,
            _ATTEMPT_S_DIRECT_START + b"24946" + _ATTEMPT_S_FRAME_START + b"24946</a></a>",
        ),
    ),
    (
        "direct-anchor-malformed",
        lambda body: _replace_attempt_s_fixture(
            body, _ATTEMPT_S_DIRECT_START, _ATTEMPT_S_DIRECT_START[:-1]
        ),
    ),
    (
        "extra-unrelated-anchor",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_FRAME_START,
            b'<a href="/extra">extra</a>' + _ATTEMPT_S_FRAME_START,
        ),
    ),
    (
        "direct-close-missing",
        lambda body: _replace_attempt_s_fixture(
            body, _ATTEMPT_S_DIRECT_ANCHOR, _ATTEMPT_S_DIRECT_START + b"24946"
        ),
    ),
    (
        "close-duplicated",
        lambda body: _replace_attempt_s_fixture(
            body, _ATTEMPT_S_FRAME_ANCHOR, _ATTEMPT_S_FRAME_ANCHOR + b"</a>"
        ),
    ),
    (
        "ordinary-judpop1-anchor",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_FRAME_START,
            _ATTEMPT_S_PAIRED_JUDPOP1 + _ATTEMPT_S_FRAME_START,
        ),
    ),
    (
        "ordinary-judpop-anchor",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_FRAME_START,
            _ATTEMPT_S_PAIRED_JUDPOP + _ATTEMPT_S_FRAME_START,
        ),
    ),
    (
        "frame-missing",
        lambda body: _replace_attempt_s_fixture(body, _ATTEMPT_S_FRAME_ANCHOR, b""),
    ),
    (
        "frame-duplicated",
        lambda body: _replace_attempt_s_fixture(
            body, _ATTEMPT_S_FRAME_ANCHOR, _ATTEMPT_S_FRAME_ANCHOR * 2
        ),
    ),
    (
        "frame-dis-mismatch",
        lambda body: _replace_attempt_s_fixture(
            body, b'AH=S&DIS=24946&QS=%2B&TP=JU"', b'AH=S&DIS=24947&QS=%2B&TP=JU"'
        ),
    ),
    (
        "frame-tp-mutated",
        lambda body: _replace_attempt_s_fixture(
            body, b'AH=S&DIS=24946&QS=%2B&TP=JU"', b'AH=S&DIS=24946&QS=%2B&TP=RS"'
        ),
    ),
    (
        "frame-host-mutated",
        lambda body: _replace_attempt_s_fixture(
            body, b"https://legalref.judiciary.hk/lrs//", b"https://evil.example/lrs//"
        ),
    ),
    (
        "frame-path-mutated",
        lambda body: _replace_attempt_s_fixture(body, b"ju_frame.jsp?", b"ju_frame.jsp/extra?"),
    ),
    (
        "frame-query-missing",
        lambda body: _replace_attempt_s_fixture(body, b'&QS=%2B&TP=JU"', b'&TP=JU"'),
    ),
    (
        "frame-query-extra",
        lambda body: _replace_attempt_s_fixture(body, b'&TP=JU" target', b'&TP=JU&X=1" target'),
    ),
    (
        "frame-query-reordered",
        lambda body: _replace_attempt_s_fixture(
            body,
            b'AH=S&DIS=24946&QS=%2B&TP=JU"',
            b'DIS=24946&AH=S&QS=%2B&TP=JU"',
        ),
    ),
    (
        "frame-extra-attribute",
        lambda body: _replace_attempt_s_fixture(
            body, b' target="_top"', b' id="extra" target="_top"'
        ),
    ),
    (
        "frame-href-quotes-mutated",
        lambda body: _replace_attempt_s_fixture(
            body,
            _ATTEMPT_S_FRAME_START,
            _ATTEMPT_S_FRAME_START.replace(b'<a href="', b"<a href='").replace(
                b'JU" target', b"JU' target"
            ),
        ),
    ),
    (
        "frame-class-missing",
        lambda body: _replace_attempt_s_fixture(body, b" class=default", b""),
    ),
    (
        "frame-class-mutated",
        lambda body: _replace_attempt_s_fixture(body, b" class=default", b" class=searchfont"),
    ),
    (
        "frame-class-quoted",
        lambda body: _replace_attempt_s_fixture(body, b" class=default", b' class="default"'),
    ),
    (
        "frame-target-missing",
        lambda body: _replace_attempt_s_fixture(body, b' target="_top"', b""),
    ),
    (
        "frame-target-mutated",
        lambda body: _replace_attempt_s_fixture(body, b'target="_top"', b'target="_blank"'),
    ),
    (
        "frame-target-unquoted",
        lambda body: _replace_attempt_s_fixture(body, b' target="_top"', b" target=_top"),
    ),
    (
        "frame-spacing-mutated",
        lambda body: _replace_attempt_s_fixture(body, b" class=default >", b" class=default>"),
    ),
    (
        "extra-script",
        lambda body: _replace_attempt_s_fixture(
            body,
            b"</script>" + _ATTEMPT_S_DIRECT_START,
            b"</script><script>void 0;</script>" + _ATTEMPT_S_DIRECT_START,
        ),
    ),
    (
        "duplicate-script",
        lambda body: _replace_attempt_s_fixture(
            body,
            b"</script>" + _ATTEMPT_S_DIRECT_START,
            b"</script><script>var temp24946='DIS=24946&QS=%2B&TP=JU';</script>"
            + _ATTEMPT_S_DIRECT_START,
        ),
    ),
    (
        "extra-cell",
        lambda body: _replace_attempt_s_fixture(
            body, b"</td><td>27/10/1997", b"</td><td>extra</td><td>27/10/1997"
        ),
    ),
    (
        "extra-date",
        lambda body: _replace_attempt_s_fixture(
            body, b"27/10/1997</td>", b"27/10/1997 26/10/1997</td>"
        ),
    ),
    (
        "date-mutated",
        lambda body: _replace_attempt_s_fixture(body, b"27/10/1997</td>", b"32/10/1997</td>"),
    ),
)


@pytest.mark.parametrize(
    "mutation",
    tuple(mutation for _, mutation in _RESULT_1012_DIRECT_WORD_MUTATIONS),
    ids=tuple(case for case, _ in _RESULT_1012_DIRECT_WORD_MUTATIONS),
)
def test_result_1012_rejects_hostile_direct_word_row_mutations(
    mutation: Callable[[bytes], bytes],
) -> None:
    """Attempt S admits no malformed direct-Word presentation variation."""
    original = _attempt_s_direct_word_page_sanitized()
    mutated = mutation(original)
    assert mutated != original

    with pytest.raises(ValueError, match="JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=1,
            contract_version="1.0.12",
        )


def test_result_1012_direct_word_events_are_incremental_feed_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every direct-Word anchor and close split leaves the parser result unchanged."""
    body = _attempt_s_direct_word_page_sanitized()
    text = body.decode("utf-8")
    expected = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=1,
        contract_version="1.0.12",
    )
    row_start = text.index("var temp24946")
    row_end = text.index("</tr>", row_start)
    row = text[row_start:row_end]
    first_anchor = row.index('<a href="javascript:judpop1')
    first_close = row.index("</a>", first_anchor) + len("</a>")
    second_anchor = row.index('<a href="https://legalref.judiciary.hk', first_close)
    second_close = row.index("</a>", second_anchor) + len("</a>")
    split_points = {
        row_start + split
        for start, end in ((first_anchor, first_close), (second_anchor, second_close))
        for split in range(start + 1, end)
    }
    original_feed = judiciary_authentic.HTMLParser.feed
    for split in sorted(split_points):

        def split_feed(
            parser: judiciary_authentic.HTMLParser,
            data: str,
            *,
            _split: int = split,
        ) -> None:
            original_feed(parser, data[:_split])
            original_feed(parser, data[_split:])

        monkeypatch.setattr(judiciary_authentic.HTMLParser, "feed", split_feed)
        assert (
            parse_judiciary_year_result_page(
                body,
                year=1997,
                page=1,
                contract_version="1.0.12",
            )
            == expected
        )


_CURRENT_RESULT_PAGE_FORM_CONTRACTS = (
    "1.0.4",
    "1.0.5",
    "1.0.6",
    "1.0.7",
    "1.0.8",
    "1.0.9",
    "1.0.10",
    "1.0.11",
    "1.0.12",
)
_CURRENT_RESULT_IDENTITY_CONTRACTS = ("1.0.8", "1.0.9", "1.0.10", "1.0.11", "1.0.12")


@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_PAGE_FORM_CONTRACTS)
def test_current_result_104_reads_authentic_attempt_f_page_one_form_grammar(
    result_contract_version: str,
) -> None:
    page = parse_judiciary_year_result_page(
        _attempt_f_page_one(),
        year=1997,
        page=1,
        contract_version=result_contract_version,
    )

    assert page.reported_results == 1627
    assert page.reported_pages == 163
    assert page.dis_ids == (24946, 18226, 26930, 18228, 19311, 25158, 18231, 22890, 22891, 35838)
    assert page.decision_dates == (
        date(1997, 10, 27),
        date(1997, 10, 16),
        date(1997, 10, 16),
        date(1997, 9, 11),
        date(1997, 9, 23),
        date(1997, 12, 18),
        date(1997, 12, 18),
        date(1997, 12, 5),
        date(1997, 12, 18),
        date(1997, 12, 1),
    )
    assert page.advertised_next_page == 2


def test_current_result_103_scopes_page_authority_to_primary_get_form() -> None:
    page = parse_judiciary_year_result_page(
        _attempt_e_page_two(),
        year=1997,
        page=2,
        contract_version="1.0.3",
    )

    assert page.reported_results == 1627
    assert page.reported_pages == 163
    assert page.dis_ids == tuple(range(2001, 2011))
    assert page.decision_dates == tuple(date(1997, 6, day) for day in range(21, 31))
    assert page.advertised_next_page == 3


def test_current_form_104_preserves_submit_grammar_and_builds_page_three() -> None:
    first_url = build_judiciary_year_result_url(
        _current_advanced_search_form(),
        entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        year=1997,
        page=1,
        contract_version="1.0.4",
    )
    retained = parse_judiciary_year_result_page(
        _attempt_e_page_two(),
        year=1997,
        page=2,
        contract_version="1.0.3",
    )

    page_two_url = f"{first_url}&page=2"
    next_url = judiciary_authentic.build_judiciary_next_result_url(
        page_two_url,
        result_page=retained,
        form_contract_version="1.0.4",
    )

    assert first_url == (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
        "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
        "selallct=1&stem=1&txtselectopt3=5&day1=&month=&txtSearch3=%2F%2F1997&"
        "year=1997"
    )
    assert next_url == f"{first_url}&page=3"


@pytest.mark.parametrize(
    ("form_contract_version", "result_contract_version"),
    [
        ("1.0.5", "1.0.4"),
        ("1.0.6", "1.0.5"),
        ("1.0.7", "1.0.6"),
        ("1.0.8", "1.0.7"),
        ("1.0.9", "1.0.8"),
        ("1.0.10", "1.0.9"),
        ("1.0.11", "1.0.10"),
        ("1.0.12", "1.0.11"),
        ("1.0.13", "1.0.12"),
    ],
)
def test_current_form_105_preserves_the_observed_submit_and_pagination_grammar(
    form_contract_version: str,
    result_contract_version: str,
) -> None:
    first_url = build_judiciary_year_result_url(
        _current_advanced_search_form(),
        entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        year=1997,
        page=1,
        contract_version=form_contract_version,
    )
    retained = parse_judiciary_year_result_page(
        _attempt_e_page_two(),
        year=1997,
        page=2,
        contract_version=result_contract_version,
    )

    page_two_url = (
        build_judiciary_year_result_url(
            _current_advanced_search_form(),
            entry_url=(
                "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
                "?isadvsearch=1&stem=1&selall2=1&selallct=1"
            ),
            year=1997,
            page=2,
            contract_version=form_contract_version,
        )
        if form_contract_version == "1.0.13"
        else f"{first_url}&page=2"
    )
    next_url = judiciary_authentic.build_judiciary_next_result_url(
        page_two_url,
        result_page=retained,
        form_contract_version=form_contract_version,
    )

    expected_suffix = "txtSearch3=%2F%2F1997&year=1997"
    if form_contract_version == "1.0.13":
        assert first_url.endswith(f"{expected_suffix}&page=1")
        assert next_url.endswith(f"{expected_suffix}&page=3")
    else:
        assert first_url.endswith(expected_suffix)
        assert next_url == f"{first_url}&page=3"


def test_result_108_preserves_exact_source_assigned_rs_detail_frame_type() -> None:
    """An exact paired RS row keeps its source type in the canonical locator."""
    body = _attempt_j_rs_page_sanitized()

    page = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=1,
        contract_version="1.0.8",
    )

    assert page.artifact_urls[1] == (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=18226&QS=%2B&TP=RS"
    )
    assert (
        judiciary_authentic.require_judiciary_result_detail_frame_url(
            page.artifact_urls[1],
            dis_id=18226,
            contract_version="1.0.8",
        )
        == page.artifact_urls[1]
    )
    with pytest.raises(ValueError, match="JUDICIARY_DECISION_DATE_INVALID"):
        parse_judiciary_year_result_page(
            body,
            year=1997,
            page=1,
            contract_version="1.0.7",
        )
    with pytest.raises(ValueError, match="JUDICIARY_DIS_LOCATOR_INVALID"):
        judiciary_authentic.require_judiciary_result_detail_frame_url(
            page.artifact_urls[1],
            dis_id=18226,
            contract_version="1.0.7",
        )


def test_result_109_preserves_exact_authentic_rs_anchor_shape_and_type() -> None:
    """The authentic paired RS starts are admitted only by the new result contract."""
    body = _attempt_k_rs_page_sanitized()

    page = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=1,
        contract_version="1.0.9",
    )

    assert page.artifact_urls[1] == (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=18226&QS=%2B&TP=RS"
    )
    assert (
        judiciary_authentic.require_judiciary_result_detail_frame_url(
            page.artifact_urls[1],
            dis_id=18226,
            contract_version="1.0.9",
        )
        == page.artifact_urls[1]
    )
    with pytest.raises(ValueError, match="JUDICIARY_DIS_LOCATOR_INVALID"):
        parse_judiciary_year_result_page(
            body,
            year=1997,
            page=1,
            contract_version="1.0.8",
        )


def test_result_1010_preserves_exact_authentic_rv_anchor_shape_and_type() -> None:
    """Attempt N's exact uppercase RV source type survives in the public locator."""
    body = _attempt_n_rv_page_sanitized()

    page = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=1,
        contract_version="1.0.10",
    )

    expected = (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=18226&QS=%2B&TP=RV"
    )
    assert page.artifact_urls[1] == expected
    assert (
        judiciary_authentic.require_judiciary_result_detail_frame_url(
            expected,
            dis_id=18226,
            contract_version="1.0.10",
        )
        == expected
    )
    for old_version in ("1.0.8", "1.0.9"):
        with pytest.raises(ValueError, match="JUDICIARY_"):
            parse_judiciary_year_result_page(
                body,
                year=1997,
                page=1,
                contract_version=old_version,
            )
        with pytest.raises(ValueError, match="JUDICIARY_DIS_LOCATOR_INVALID"):
            judiciary_authentic.require_judiciary_result_detail_frame_url(
                expected,
                dis_id=18226,
                contract_version=old_version,
            )


def test_result_1011_preserves_exact_typed_optional_frames_as_canonical_locators() -> None:
    """Attempt O's redundant frames validate but never replace canonical locators."""
    body = _attempt_o_typed_optional_frames_page_sanitized()

    page = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=1,
        contract_version="1.0.11",
    )

    assert page.artifact_urls[1] == (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=18226&QS=%2B&TP=RS"
    )
    assert page.artifact_urls[2] == (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=26930&QS=%2B&TP=RV"
    )
    for index, dis_id in ((1, 18226), (2, 26930)):
        assert (
            judiciary_authentic.require_judiciary_result_detail_frame_url(
                page.artifact_urls[index],
                dis_id=dis_id,
                contract_version="1.0.11",
            )
            == page.artifact_urls[index]
        )
    complete_page = replace(
        page,
        reported_results=len(page.dis_ids),
        reported_pages=1,
        advertised_next_page=None,
    )
    partition = reconcile_judiciary_year_partition((complete_page,), contract_version="1.0.11")
    assert partition.all_artifact_urls[1:3] == page.artifact_urls[1:3]
    with pytest.raises(ValueError, match="JUDICIARY_"):
        parse_judiciary_year_result_page(
            body,
            year=1997,
            page=1,
            contract_version="1.0.10",
        )


def _replace_in_typed_optional_frame_row(
    body: bytes,
    *,
    dis_id: bytes,
    old: bytes,
    new: bytes,
) -> bytes:
    row_start = body.index(b"var temp" + dis_id)
    row_end = body.index(b"</tr>", row_start)
    row = body[row_start:row_end]
    replaced = row.replace(old, new, 1)
    return body[:row_start] + replaced + body[row_end:]


def _mutate_attempt_o_frame(body: bytes, old: bytes, new: bytes) -> bytes:
    return _replace_in_typed_optional_frame_row(
        body,
        dis_id=b"18226",
        old=old,
        new=new,
    )


_RESULT_1011_OPTIONAL_FRAME_MUTATIONS: tuple[Callable[[bytes], bytes], ...] = (
    lambda body: _mutate_attempt_o_frame(body, b'TP=RS"', b'TP=rs"'),
    lambda body: _mutate_attempt_o_frame(body, b'TP=RS"', b'TP=Rs"'),
    lambda body: _mutate_attempt_o_frame(body, b'TP=RS"', b'TP=ZZ"'),
    lambda body: _mutate_attempt_o_frame(body, b'TP=RS"', b'TP=PD"'),
    lambda body: _mutate_attempt_o_frame(body, b'TP=RS"', b'TP=%52%53"'),
    lambda body: _mutate_attempt_o_frame(body, b"AH=S&DIS=", b"DIS=18226&AH=S&DIS="),
    lambda body: _mutate_attempt_o_frame(body, b"AH=S&", b"AH=X&"),
    lambda body: _mutate_attempt_o_frame(body, b"&QS=%2B", b"&QS=+"),
    lambda body: _mutate_attempt_o_frame(body, b"&TP=RS", b"&X=1&TP=RS"),
    lambda body: _mutate_attempt_o_frame(body, b"DIS=18226", b"DIS=18227"),
    lambda body: _mutate_attempt_o_frame(body, b"TP=RS", b"TP=RV"),
    lambda body: _mutate_attempt_o_frame(body, b"https://", b"http://"),
    lambda body: _mutate_attempt_o_frame(body, b"legalref.judiciary.hk", b"example.invalid"),
    lambda body: _mutate_attempt_o_frame(body, b"/lrs//", b"/lrs/"),
    lambda body: _mutate_attempt_o_frame(body, b"ju_frame.jsp", b"other.jsp"),
    lambda body: _mutate_attempt_o_frame(body, b' target="_top"', b""),
    lambda body: _mutate_attempt_o_frame(body, b' target="_top"', b' target="_blank"'),
    lambda body: _mutate_attempt_o_frame(body, b' target="_top"', b" target='_top'"),
    lambda body: _mutate_attempt_o_frame(
        body, b' target="_top" class=default ', b' class=default target="_top" '
    ),
    lambda body: _mutate_attempt_o_frame(body, b" class=default ", b' class="default" '),
    lambda body: _mutate_attempt_o_frame(body, b" class=default ", b" class=other "),
    lambda body: _mutate_attempt_o_frame(body, b" class=default ", b" class=default"),
    lambda body: _mutate_attempt_o_frame(body, b" class=default ", b" class=default  "),
    lambda body: _mutate_attempt_o_frame(body, b" class=default ", b" data-x=1 class=default "),
    lambda body: _mutate_attempt_o_frame(body, b">frame</a>", b">frame</A>"),
    lambda body: _mutate_attempt_o_frame(body, b">frame</a>", b">frame</a >"),
    lambda body: _mutate_attempt_o_frame(body, b">frame</a>", b">frame"),
    lambda body: _mutate_attempt_o_frame(body, b">frame</a>", b">frame</a></a>"),
    lambda body: _mutate_attempt_o_frame(body, b">frame</a>", b"><a>frame</a></a>"),
    lambda body: _mutate_attempt_o_frame(
        body,
        b">frame</a>",
        b'>frame</a><a href="https://legalref.judiciary.hk/lrs//common/ju/'
        b'ju_frame.jsp?AH=S&DIS=18226&QS=%2B&TP=RS" '
        b'target="_top" class=default >frame</a>',
    ),
)


@pytest.mark.parametrize("mutation", _RESULT_1011_OPTIONAL_FRAME_MUTATIONS)
def test_result_1011_rejects_every_typed_optional_frame_hostile(
    mutation: Callable[[bytes], bytes],
) -> None:
    original = _attempt_o_typed_optional_frames_page_sanitized()
    mutated = mutation(original)
    assert mutated != original

    with pytest.raises(ValueError, match="JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=1,
            contract_version="1.0.11",
        )


def test_result_1011_typed_optional_frame_events_are_incremental_feed_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _attempt_o_typed_optional_frames_page_sanitized()
    text = body.decode("utf-8")
    expected = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=1,
        contract_version="1.0.11",
    )
    original_feed = judiciary_authentic.HTMLParser.feed
    split_points: set[int] = set()
    for dis_id in ("18226", "26930"):
        row_start = text.index("var temp" + dis_id)
        row_end = text.index("</tr>", row_start)
        row = text[row_start:row_end]
        frame_start = row.index('<a href="https://legalref.judiciary.hk')
        frame_end = row.index("</a>", frame_start) + len("</a>")
        split_points.update(row_start + split for split in range(frame_start + 1, frame_end))
    assert split_points

    for split in sorted(split_points):

        def split_feed(
            parser: judiciary_authentic.HTMLParser,
            data: str,
            *,
            _split: int = split,
        ) -> None:
            original_feed(parser, data[:_split])
            original_feed(parser, data[_split:])

        monkeypatch.setattr(judiciary_authentic.HTMLParser, "feed", split_feed)
        assert (
            parse_judiciary_year_result_page(
                body,
                year=1997,
                page=1,
                contract_version="1.0.11",
            )
            == expected
        )


def _replace_first_authentic_rs_start(body: bytes, replacement: bytes) -> bytes:
    original = (
        b"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'+temp18226);\" "
        b'class="searchfont result-caseno">'
    )
    return _replace_in_rs_row(body, original, replacement)


_RESULT_109_RS_CLASS_MUTATIONS: tuple[Callable[[bytes], bytes], ...] = (
    lambda body: _replace_first_authentic_rs_start(
        body,
        b"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'+temp18226);\">",
    ),
    lambda body: body.replace(b'class="searchfont result-caseno"', b'class="other"', 1),
    lambda body: _replace_first_authentic_rs_start(
        body,
        b'<a class="searchfont result-caseno" '
        b"href=\"javascript:judpop1('search_result_detail_frame.jsp?'+temp18226);\">",
    ),
    lambda body: body.replace(
        b'class="searchfont result-caseno"',
        b'class="searchfont result-caseno" class="searchfont result-caseno"',
        1,
    ),
    lambda body: body.replace(
        b'class="searchfont result-caseno"', b'CLASS="searchfont result-caseno"', 1
    ),
    lambda body: body.replace(
        b'class="searchfont result-caseno"', b"class='searchfont result-caseno'", 1
    ),
    lambda body: body.replace(b"class=searchfont>", b'class="searchfont">', 1),
    lambda body: body.replace(
        b'class="searchfont result-caseno"', b'class="result-caseno searchfont"', 1
    ),
    lambda body: body.replace(b'class="searchfont result-caseno"', b'class="searchfont"', 1),
    lambda body: body.replace(
        b'class="searchfont result-caseno"', b'class="searchfont result-caseno extra"', 1
    ),
    lambda body: body.replace(
        b'class="searchfont result-caseno"', b'class="search&#102;ont result-caseno"', 1
    ),
    lambda body: body.replace(b"class=searchfont>", b'class=searchfont data-x="1">', 1),
)


@pytest.mark.parametrize("mutation", _RESULT_109_RS_CLASS_MUTATIONS)
def test_result_109_rejects_every_rs_class_attribute_variant(
    mutation: Callable[[bytes], bytes],
) -> None:
    """Only the two exact observed class suffixes are part of the authentic RS grammar."""
    original = _attempt_k_rs_page_sanitized()
    mutated = mutation(original)
    assert mutated != original

    with pytest.raises(ValueError, match="JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=1,
            contract_version="1.0.9",
        )


def _add_rs_optional_absolute_frame(body: bytes) -> bytes:
    row_start = body.index(b"var temp18226")
    insertion = body.index(b"</td><td>16/10/1997", row_start)
    frame = (
        b'<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
        b'AH=S&amp;DIS=18226&amp;QS=%2B&amp;TP=JU">frame</a>'
    )
    return body[:insertion] + frame + body[insertion:]


def _add_rs_extra_anchor(body: bytes, href: bytes) -> bytes:
    row_start = body.index(b"var temp18226")
    insertion = body.index(b"</td><td>16/10/1997", row_start)
    anchor = b'<a href="' + href + b'">extra</a>'
    return body[:insertion] + anchor + body[insertion:]


def _replace_in_rs_row(body: bytes, old: bytes, new: bytes) -> bytes:
    row_start = body.index(b"var temp18226")
    row_end = body.index(b"</tr>", row_start)
    row = body[row_start:row_end]
    replaced = row.replace(old, new, 1)
    return body[:row_start] + replaced + body[row_end:]


def _confuse_rs_raw_href_attribute(body: bytes) -> bytes:
    href = b"javascript:judpop1('search_result_detail_frame.jsp?'+temp18226);"
    original = b'<a href="' + href + b'"'
    confused = (
        b"<a data-x=' href=\""
        + href
        + b"\"' href=\"java&#115;cript:judpop1('search_result_detail_frame.jsp?'+temp18226);\""
    )
    return _replace_in_rs_row(body, original, confused)


def _add_rs_anchor_attribute(body: bytes) -> bytes:
    return _replace_in_rs_row(
        body,
        b'<a href="',
        b'<a class="x" href="',
    )


def _duplicate_second_rs_anchor(body: bytes) -> bytes:
    row_start = body.index(b"var temp18226")
    row_end = body.index(b"</tr>", row_start)
    row = body[row_start:row_end]
    anchor_start = row.index(b'<a href="javascript:judpop(')
    anchor_end = row.index(b"</a>", anchor_start) + len(b"</a>")
    anchor = row[anchor_start:anchor_end]
    duplicated = row[:anchor_end] + anchor + row[anchor_end:]
    return body[:row_start] + duplicated + body[row_end:]


def _remove_first_rs_anchor_close(body: bytes) -> bytes:
    return _replace_in_rs_row(body, b"</a>", b"")


def _add_stray_rs_anchor_close(body: bytes) -> bytes:
    return _replace_in_rs_row(body, b"</a>", b"</a></a>")


def _nest_rs_anchors(body: bytes) -> bytes:
    second = b"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'+temp18226);\">"
    nested = _replace_in_rs_row(body, b"</a>" + second, second)
    row_start = nested.index(b"var temp18226")
    row_end = nested.index(b"</td><td>16/10/1997", row_start)
    return nested[:row_end] + b"</a>" + nested[row_end:]


_Result108Mutation = Callable[[bytes], bytes]
_RESULT_108_RS_MUTATIONS: tuple[_Result108Mutation, ...] = (
    lambda body: body.replace(b"TP=RS';", b"TP=RV';", 1),
    lambda body: body.replace(b"TP=RS';", b"TP=rs';", 1),
    lambda body: body.replace(b"TP=RS';", b"TP=';", 1),
    lambda body: body.replace(
        b"DIS=18226&QS=%2B&TP=RS",
        b"QS=%2B&DIS=18226&TP=RS",
        1,
    ),
    lambda body: body.replace(b"&TP=RS';", b"&TP=RS&extra=1';", 1),
    lambda body: body.replace(b"TP=RS';", b"TP=%52%53';", 1),
    lambda body: body.replace(b"var temp18226=", b"let temp18226=", 1),
    lambda body: body.replace(b"var temp18226=", b"var temp18227=", 1),
    lambda body: body.replace(b"DIS=18226&QS=%2B&TP=RS", b"DIS=18227&QS=%2B&TP=RS", 1),
    lambda body: body.replace(b"search_result_detail_frame.jsp?", b"detail.jsp?", 1),
    lambda body: body.replace(
        b"javascript:judpop1('search_result_detail_frame.jsp?'+temp18226);",
        b"https://example.invalid/search_result_detail_frame.jsp?DIS=18226&QS=%2B&TP=RS",
        1,
    ),
    lambda body: body.replace(b"javascript:judpop1(", b"javascript:judpop(", 1),
    _duplicate_second_rs_anchor,
    _add_rs_optional_absolute_frame,
    lambda body: _add_rs_extra_anchor(body, b"https://example.invalid/plain"),
    lambda body: _add_rs_extra_anchor(body, b"other.jsp"),
    lambda body: _add_rs_extra_anchor(body, b""),
    lambda body: _replace_in_rs_row(body, b"javascript:judpop1", b"java&#115;cript:judpop1"),
    lambda body: _replace_in_rs_row(body, b"detail_frame.jsp?", b"detail_frame.jsp&#63;"),
    lambda body: body.replace(b"temp18226);", b"temp1822&#54;);", 1),
    lambda body: body.replace(b"18226", b"018226"),
    _confuse_rs_raw_href_attribute,
    _add_rs_anchor_attribute,
    _remove_first_rs_anchor_close,
    _add_stray_rs_anchor_close,
    _nest_rs_anchors,
    lambda body: _replace_in_rs_row(body, b"</a>", b"</A>"),
    lambda body: _replace_in_rs_row(body, b"</a>", b"</a >"),
    lambda body: _replace_in_rs_row(body, b"</a>", b"</a\n>"),
    lambda body: _replace_in_rs_row(body, b"</a>", b"</a/>"),
    lambda body: _replace_in_rs_row(body, b"</a>", b"</a x>"),
)

_RESULT_1010_RV_MUTATIONS: tuple[_Result108Mutation, ...] = (
    lambda body: body.replace(b"TP=RV';", b"TP=rv';", 1),
    lambda body: body.replace(b"TP=RV';", b"TP=Rv';", 1),
    lambda body: body.replace(b"TP=RV';", b"TP=ZZ';", 1),
    lambda body: body.replace(b"TP=RV';", b"TP=PD';", 1),
    lambda body: body.replace(b"TP=RV';", b"TP=%52%56';", 1),
    lambda body: body.replace(
        b"DIS=18226&QS=%2B&TP=RV",
        b"QS=%2B&DIS=18226&TP=RV",
        1,
    ),
    lambda body: body.replace(b"&TP=RV';", b"&TP=RV&extra=1';", 1),
    lambda body: body.replace(b"var temp18226=", b"var temp18227=", 1),
    lambda body: body.replace(b"DIS=18226&QS=%2B&TP=RV", b"DIS=18227&QS=%2B&TP=RV", 1),
    _add_rs_optional_absolute_frame,
    _duplicate_second_rs_anchor,
    _remove_first_rs_anchor_close,
    _add_stray_rs_anchor_close,
    _nest_rs_anchors,
    lambda body: _replace_in_rs_row(body, b"</a>", b"</A>"),
    lambda body: _replace_in_rs_row(body, b"</a>", b"</a >"),
    lambda body: _replace_in_rs_row(body, b"javascript:judpop1", b"java&#115;cript:judpop1"),
    lambda body: _replace_in_rs_row(body, b"detail_frame.jsp?", b"detail_frame.jsp&#63;"),
    lambda body: body.replace(b"temp18226);", b"temp1822&#54;);", 1),
    *_RESULT_109_RS_CLASS_MUTATIONS,
)


@pytest.mark.parametrize("mutation", _RESULT_108_RS_MUTATIONS)
def test_result_108_rejects_every_broader_rs_row_or_locator_shape(
    mutation: _Result108Mutation,
) -> None:
    """Only the exact observed uppercase RS assignment and paired links are admitted."""
    original = _attempt_j_rs_page_sanitized()
    mutated = mutation(original)
    assert mutated != original

    with pytest.raises(ValueError, match="JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=1,
            contract_version="1.0.8",
        )


@pytest.mark.parametrize("mutation", _RESULT_108_RS_MUTATIONS)
def test_result_109_rejects_every_prior_rs_locator_and_topology_hostile(
    mutation: _Result108Mutation,
) -> None:
    """The authentic class suffixes do not loosen any prior RS semantic or topology guard."""
    original = _attempt_k_rs_page_sanitized()
    mutated = mutation(original)
    assert mutated != original

    with pytest.raises(ValueError, match="JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=1,
            contract_version="1.0.9",
        )


def test_result_109_authentic_rs_raw_events_are_incremental_feed_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Splitting any authentic RS anchor token does not change its exact parsed result."""
    body = _attempt_k_rs_page_sanitized()
    text = body.decode("utf-8")
    expected = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=1,
        contract_version="1.0.9",
    )
    row_start = text.index("var temp18226")
    row_end = text.index("</tr>", row_start)
    row = text[row_start:row_end]
    token_matches = tuple(
        re.finditer(
            r'<a href="javascript:judpop1?\([^>]+>|</a>',
            row,
        )
    )
    split_points = {
        row_start + split
        for match in token_matches
        for split in range(match.start() + 1, match.end())
    }
    assert split_points
    original_feed = judiciary_authentic.HTMLParser.feed

    for split in sorted(split_points):

        def split_feed(
            parser: judiciary_authentic.HTMLParser,
            data: str,
            *,
            _split: int = split,
        ) -> None:
            original_feed(parser, data[:_split])
            original_feed(parser, data[_split:])

        monkeypatch.setattr(judiciary_authentic.HTMLParser, "feed", split_feed)
        assert (
            parse_judiciary_year_result_page(
                body,
                year=1997,
                page=1,
                contract_version="1.0.9",
            )
            == expected
        )


@pytest.mark.parametrize("mutation", _RESULT_1010_RV_MUTATIONS)
def test_result_1010_rejects_every_rv_case_encoding_type_or_topology_hostile(
    mutation: _Result108Mutation,
) -> None:
    """RV extends one exact token and inherits every raw RS row guard unchanged."""
    original = _attempt_n_rv_page_sanitized()
    mutated = mutation(original)
    assert mutated != original

    with pytest.raises(ValueError, match="JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=1,
            contract_version="1.0.10",
        )


def test_result_1010_authentic_rv_raw_events_are_incremental_feed_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every split inside the exact RV anchors preserves the same strict result."""
    body = _attempt_n_rv_page_sanitized()
    text = body.decode("utf-8")
    expected = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=1,
        contract_version="1.0.10",
    )
    row_start = text.index("var temp18226")
    row_end = text.index("</tr>", row_start)
    row = text[row_start:row_end]
    token_matches = tuple(re.finditer(r'<a href="javascript:judpop1?\([^>]+>|</a>', row))
    split_points = {
        row_start + split
        for match in token_matches
        for split in range(match.start() + 1, match.end())
    }
    assert split_points
    original_feed = judiciary_authentic.HTMLParser.feed

    for split in sorted(split_points):

        def split_feed(
            parser: judiciary_authentic.HTMLParser,
            data: str,
            *,
            _split: int = split,
        ) -> None:
            original_feed(parser, data[:_split])
            original_feed(parser, data[_split:])

        monkeypatch.setattr(judiciary_authentic.HTMLParser, "feed", split_feed)
        assert (
            parse_judiciary_year_result_page(
                body,
                year=1997,
                page=1,
                contract_version="1.0.10",
            )
            == expected
        )


_AttemptEPageMutation = Callable[[bytes], bytes]


def _move_first_org_value_form_before_primary(body: bytes) -> bytes:
    org_form = (
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>\n'
    )
    without_later_form = body.replace(org_form, b"", 1)
    return without_later_form.replace(
        b'<form name="frm_search"', org_form + b'<form name="frm_search"', 1
    )


def _prepend_form(body: bytes, form: bytes) -> bytes:
    return body.replace(b'<form name="frm_search"', form + b'<form name="frm_search"', 1)


def _append_form(body: bytes, form: bytes) -> bytes:
    return body.replace(b"</body>", form + b"</body>", 1)


def _wrap_primary_form_in_disabled_fieldset(body: bytes) -> bytes:
    wrapped_start = body.replace(
        b'<form name="frm_search"',
        b'<fieldset disabled><form name="frm_search"',
        1,
    )
    return wrapped_start.replace(
        b'</form>\n<form method="post" name="org_value"',
        b'</form></fieldset>\n<form method="post" name="org_value"',
        1,
    )


_ATTEMPT_E_PAGE_AUTHORITY_MUTATIONS: tuple[_AttemptEPageMutation, ...] = (
    _move_first_org_value_form_before_primary,
    lambda body: _prepend_form(body, b'<form name="other"></form>\n'),
    lambda body: _append_form(body, b'<form name="other"></form>\n'),
    lambda body: _prepend_form(
        body,
        b'<form name="other" id="frm_search"></form>\n',
    ),
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>\n',
        b"",
        1,
    ),
    lambda body: body.replace(
        b"</body>",
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>\n</body>',
        1,
    ),
    lambda body: body.replace(b'name="frm_search"', b'name="other"', 1),
    lambda body: body.replace(b'id="frm_search"', b'id="other"', 1),
    lambda body: body.replace(b'method="get"', b'method="post"', 1),
    lambda body: body.replace(b'action=""', b'action="other.jsp"', 1),
    lambda body: body.replace(
        b'onsubmit="javascript:return FORM_SUBMIT(this);"',
        b'onsubmit="return true;"',
        1,
    ),
    lambda body: body.replace(b'name="frm_search"', b'name="frm_search" name="other"', 1),
    lambda body: body.replace(
        b'<input type="hidden" name="page" value="2">',
        b'<input type="hidden" name="page" value="2"><input type="hidden" name="page" value="2">',
        1,
    ),
    lambda body: body.replace(b'type="hidden" name="page"', b'type="text" name="page"', 1),
    lambda body: body.replace(b'name="page" value="2"', b'name="page" value="1"', 1),
    lambda body: body.replace(
        b'<input type="hidden" name="page" value="2">',
        b'<input type="hidden" name="page" value="2" disabled>',
        1,
    ),
    lambda body: body.replace(
        b'<input type="hidden" name="page" value="2">',
        b'<input type="hidden" name="page" value="2" form="org_value">',
        1,
    ),
    lambda body: body.replace(
        b'<input type="hidden" name="page" value="2">',
        b'<input type="hidden" name="page" value="2" class="other">',
        1,
    ),
    lambda body: body.replace(
        b'<input type="hidden" name="page" value="2">',
        b'<fieldset disabled><input type="hidden" name="page" value="2"></fieldset>',
        1,
    ),
    _wrap_primary_form_in_disabled_fieldset,
    lambda body: body.replace(
        b'<input type="hidden" name="page" value="2">',
        b'<template><input type="hidden" name="page" value="2"></template>',
        1,
    ),
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>',
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="999" form="frm_search"></form>',
        1,
    ),
    lambda body: body.replace(
        b'<input type="hidden" name="page" value="2">',
        b"",
        1,
    ),
    lambda body: body.replace(
        b'<form name="frm_search"',
        b'<form name="outer"><form name="frm_search"',
        1,
    ),
    lambda body: body.replace(
        b'</form>\n<form method="post" name="org_value" action="">',
        b'<form method="post" name="org_value" action="">',
        1,
    ),
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>',
        b'<form method="post" name="other" action=""><input type="hidden" '
        b'name="page" value="2"></form>',
        1,
    ),
    lambda body: body.replace(
        b'</form>\n<form method="post" name="org_value" action="">',
        b'</form><input type="hidden" name="page" value="2">\n'
        b'<form method="post" name="org_value" action="">',
        1,
    ),
    lambda body: body.replace(
        b'</form>\n<form method="post" name="org_value" action="">',
        b'</form bogus>\n<form method="post" name="org_value" action="">',
        1,
    ),
    lambda body: body.replace(
        b'</form>\n<form method="post" name="org_value" action="">',
        b'</form/>\n<form method="post" name="org_value" action="">',
        1,
    ),
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>',
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form bogus>',
        1,
    ),
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>',
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form/>',
        1,
    ),
)


@pytest.mark.parametrize("mutation", _ATTEMPT_E_PAGE_AUTHORITY_MUTATIONS)
def test_current_result_103_rejects_non_primary_or_malformed_page_authority(
    mutation: _AttemptEPageMutation,
) -> None:
    original = _attempt_e_page_two()
    mutated = mutation(original)
    assert mutated != original

    with pytest.raises(ValueError, match=r"JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=2,
            contract_version="1.0.3",
        )


@pytest.mark.parametrize("mutation", _ATTEMPT_E_PAGE_AUTHORITY_MUTATIONS)
@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_PAGE_FORM_CONTRACTS)
def test_current_result_104_preserves_result_103_page_two_hostile_matrix(
    mutation: _AttemptEPageMutation,
    result_contract_version: str,
) -> None:
    original = _attempt_e_page_two()
    page = parse_judiciary_year_result_page(
        original,
        year=1997,
        page=2,
        contract_version=result_contract_version,
    )
    assert page.advertised_next_page == 3

    mutated = mutation(original)
    assert mutated != original
    with pytest.raises(ValueError, match=r"JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=2,
            contract_version=result_contract_version,
        )


_AttemptFPageMutation = Callable[[bytes], bytes]
_ATTEMPT_F_POST_PAGE_CONTROL_MUTATIONS: tuple[_AttemptFPageMutation, ...] = (
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""></form>',
        b'<form method="post" name="org_value" action="">'
        b'<input type="hidden" name="page" value="1"></form>',
        1,
    ),
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""></form>',
        b'<form method="post" name="org_value" action="">'
        b'<input type="hidden" name="page" value="999"></form>',
        1,
    ),
)


@pytest.mark.parametrize("mutation", _ATTEMPT_F_POST_PAGE_CONTROL_MUTATIONS)
@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_PAGE_FORM_CONTRACTS)
def test_current_result_104_rejects_any_page_one_post_page_control(
    mutation: _AttemptFPageMutation,
    result_contract_version: str,
) -> None:
    original = _attempt_f_page_one()
    assert (
        parse_judiciary_year_result_page(
            original,
            year=1997,
            page=1,
            contract_version=result_contract_version,
        ).advertised_next_page
        == 2
    )

    mutated = mutation(original)
    assert mutated != original
    with pytest.raises(ValueError, match="JUDICIARY_RESULT_PAGE_MARKUP_INVALID"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=1,
            contract_version=result_contract_version,
        )


_ATTEMPT_E_POST_PAGE_CONTROL_MUTATIONS: tuple[_AttemptEPageMutation, ...] = (
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>',
        b'<form method="post" name="org_value" action=""></form>',
        1,
    ),
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>',
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="1"></form>',
        1,
    ),
    lambda body: body.replace(
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"></form>',
        b'<form method="post" name="org_value" action=""><input type="hidden" '
        b'name="page" value="2"><input type="hidden" name="page" value="2"></form>',
        1,
    ),
)


@pytest.mark.parametrize("mutation", _ATTEMPT_E_POST_PAGE_CONTROL_MUTATIONS)
@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_PAGE_FORM_CONTRACTS)
def test_current_result_104_requires_one_matching_page_control_in_each_later_page_post(
    mutation: _AttemptEPageMutation,
    result_contract_version: str,
) -> None:
    original = _attempt_e_page_two()
    assert (
        parse_judiciary_year_result_page(
            original,
            year=1997,
            page=2,
            contract_version=result_contract_version,
        ).advertised_next_page
        == 3
    )

    mutated = mutation(original)
    assert mutated != original
    with pytest.raises(ValueError, match="JUDICIARY_RESULT_PAGE_MARKUP_INVALID"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=2,
            contract_version=result_contract_version,
        )


def _non_input_page_control(tag: str, *, page: int, reassigned: bool = False) -> bytes:
    form_attribute = b' form="frm_search"' if reassigned else b""
    if tag == "select":
        return (
            b'<select name="page"'
            + form_attribute
            + b'><option value="'
            + str(page).encode()
            + b'" selected>page</option></select>'
        )
    if tag == "textarea":
        return (
            b'<textarea name="page"' + form_attribute + b">" + str(page).encode() + b"</textarea>"
        )
    if tag == "button":
        return (
            b'<button name="page" value="'
            + str(page).encode()
            + b'"'
            + form_attribute
            + b">page</button>"
        )
    if tag == "object":
        return b'<object name="page"' + form_attribute + b"></object>"
    raise AssertionError(tag)


@pytest.mark.parametrize("tag", ["select", "textarea", "button", "object"])
@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_PAGE_FORM_CONTRACTS)
@pytest.mark.parametrize(
    ("page", "placement"),
    [
        (1, "primary"),
        (1, "post"),
        (2, "post"),
        (2, "outside_reassigned"),
    ],
)
def test_current_result_104_rejects_every_non_input_page_control(
    tag: str,
    page: int,
    placement: str,
    result_contract_version: str,
) -> None:
    original = _attempt_f_page_one() if page == 1 else _attempt_e_page_two()
    control = _non_input_page_control(
        tag,
        page=page,
        reassigned=placement == "outside_reassigned",
    )
    if placement == "primary":
        mutated = original.replace(
            b'<input type="hidden" name="page" value="1">',
            b'<input type="hidden" name="page" value="1">' + control,
            1,
        )
    elif placement == "post":
        post_open = b'<form method="post" name="org_value" action="">'
        mutated = original.replace(post_open, post_open + control, 1)
    else:
        first_post = b'<form method="post" name="org_value" action="">'
        mutated = original.replace(first_post, control + first_post, 1)
    assert mutated != original

    with pytest.raises(ValueError, match="JUDICIARY_RESULT_PAGE_MARKUP_INVALID"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=page,
            contract_version=result_contract_version,
        )


@pytest.mark.parametrize(
    ("body_factory", "page"),
    [(_attempt_f_page_one, 1), (_attempt_e_page_two, 2)],
)
@pytest.mark.parametrize("result_contract_version", ["1.0.4", "1.0.5", "1.0.6"])
def test_current_result_104_is_invariant_across_semantic_incremental_feed_splits(
    body_factory: Callable[[], bytes],
    page: int,
    result_contract_version: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = body_factory()
    text = body.decode("utf-8")
    expected = parse_judiciary_year_result_page(
        body,
        year=1997,
        page=page,
        contract_version=result_contract_version,
    )
    original_feed = judiciary_authentic.HTMLParser.feed
    semantic_tokens = re.finditer(
        r"1627|163|[0-9]{2}/[0-9]{2}/1997|var temp[0-9]+='[^']+';|</form>",
        text,
    )
    split_points = {
        split for match in semantic_tokens for split in range(match.start() + 1, match.end())
    }
    assert split_points

    for split in sorted(split_points):

        def split_feed(
            parser: judiciary_authentic.HTMLParser,
            data: str,
            *,
            _split: int = split,
        ) -> None:
            original_feed(parser, data[:_split])
            original_feed(parser, data[_split:])

        monkeypatch.setattr(judiciary_authentic.HTMLParser, "feed", split_feed)
        assert (
            parse_judiciary_year_result_page(
                body,
                year=1997,
                page=page,
                contract_version=result_contract_version,
            )
            == expected
        )


def test_current_result_contract_reads_all_attempt_d_shaped_rows_and_next_page() -> None:
    page = parse_judiciary_year_result_page(
        _attempt_d_result_page(),
        year=1997,
        page=1,
        contract_version="1.0.2",
    )

    assert page.reported_results == 1627
    assert page.reported_pages == 163
    assert page.dis_ids == tuple(range(1001, 1011))
    assert page.decision_dates == tuple(date(1997, 7, day) for day in range(1, 11))
    assert page.artifact_urls == tuple(
        "https://legalref.judiciary.hk/lrs/common/search/"
        f"search_result_detail_frame.jsp?DIS={dis_id}&QS=%2B&TP=JU"
        for dis_id in range(1001, 1011)
    )
    assert page.advertised_next_page == 2


def test_current_form_103_and_retained_result_construct_only_exact_next_page() -> None:
    first_url = build_judiciary_year_result_url(
        _current_advanced_search_form(),
        entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        year=1997,
        page=1,
        contract_version="1.0.3",
    )
    retained = parse_judiciary_year_result_page(
        _attempt_d_result_page(),
        year=1997,
        page=1,
        contract_version="1.0.2",
    )

    next_url = judiciary_authentic.build_judiciary_next_result_url(
        first_url,
        result_page=retained,
        form_contract_version="1.0.3",
    )

    assert next_url == f"{first_url}&page=2"
    assert (
        judiciary_authentic.require_judiciary_year_result_url(
            next_url,
            year=1997,
            page=2,
            contract_version="1.0.3",
        )
        == next_url
    )


@pytest.mark.parametrize(
    ("current_url", "result_page"),
    [
        ("https://example.invalid/", None),
        (None, replace),
    ],
)
def test_next_result_url_rejects_unbound_inputs(
    current_url: str | None,
    result_page: object,
) -> None:
    retained = parse_judiciary_year_result_page(
        _attempt_d_result_page(), year=1997, page=1, contract_version="1.0.2"
    )
    selected_url = (
        current_url
        if current_url is not None
        else build_judiciary_year_result_url(
            _current_advanced_search_form(),
            entry_url=(
                "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
                "?isadvsearch=1&stem=1&selall2=1&selallct=1"
            ),
            year=1997,
            page=1,
            contract_version="1.0.3",
        )
    )
    selected_page = retained if result_page is None else replace(retained, advertised_next_page=3)

    with pytest.raises((TypeError, ValueError), match=r"JUDICIARY_"):
        judiciary_authentic.build_judiciary_next_result_url(
            selected_url,
            result_page=selected_page,
            form_contract_version="1.0.3",
        )


def _remove_attempt_d_row(body: bytes, dis_id: int) -> bytes:
    marker = f"<tr><td>{dis_id - 1000}</td>".encode()
    start = body.index(marker)
    end = body.index(b"</tr>", start) + len(b"</tr>")
    return body[:start] + body[end:]


def _append_attempt_d_row(body: bytes) -> bytes:
    row = (
        b"<tr><td>11</td><td><script>var temp1011='DIS=1011&QS=%2B&TP=JU';</script>"
        b"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'+temp1011);\">"
        b"1011</a>"
        b"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'+temp1011);\">"
        b"1011</a></td><td>11/07/1997</td></tr>"
    )
    return body.replace(b"</table>", row + b"</table>", 1)


def _duplicate_attempt_d_optional_frame(body: bytes) -> bytes:
    frame = (
        b'<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
        b'AH=S&amp;DIS=1001&amp;QS=%2B&amp;TP=JU">1001</a>'
    )
    return body.replace(frame, frame + frame, 1)


_AttemptDMutation = Callable[[bytes], bytes]
_ATTEMPT_D_RESULT_MUTATIONS: tuple[_AttemptDMutation, ...] = (
    lambda body: body.replace(
        b"var temp1001='DIS=1001&QS=%2B&TP=JU';",
        b"decoy();var temp1001='DIS=1001&QS=%2B&TP=JU';",
        1,
    ),
    lambda body: body.replace(b"var temp1001=", b"var temp1000=", 1),
    lambda body: body.replace(b"DIS=1001&QS=%2B", b"DIS=1002&QS=%2B", 1),
    lambda body: body.replace(
        b"var temp1001='DIS=1001&QS=%2B&TP=JU';",
        b"var temp1001='DIS=1001&QS=%2B&TP=JU';var temp1001='DIS=1001&QS=%2B&TP=JU';",
        1,
    ),
    lambda body: body.replace(b"var temp1001='DIS=1001&QS=%2B&TP=JU';", b"", 1),
    lambda body: body.replace(b"javascript:judpop1(", b"javascript:judpop(", 1),
    lambda body: body.replace(b"+temp1001);", b"+temp1002);", 1),
    lambda body: body.replace(b"search_result_detail_frame.jsp?", b"detail.jsp?", 1),
    lambda body: body.replace(b"DIS=1001&QS=%2B&TP=JU", b"QS=%2B&DIS=1001&TP=JU", 1),
    lambda body: body.replace(b"QS=%2B", b"QS=%2b", 1),
    lambda body: body.replace(
        b"https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp",
        b"https://example.invalid/lrs//common/ju/ju_frame.jsp",
        1,
    ),
    lambda body: body.replace(b"AH=S&amp;DIS=1001", b"AH=S&amp;DIS=1002", 1),
    _duplicate_attempt_d_optional_frame,
    lambda body: body.replace(b"<td>01/07/1997</td>", b"<td>01/07/1998</td>", 1),
    lambda body: body.replace(b"<tr><td>1</td><td>", b"<tr><td>", 1),
    lambda body: body.replace(b"temp1002", b"temp1001").replace(b"DIS=1002", b"DIS=1001"),
    lambda body: _remove_attempt_d_row(body, 1010),
    _append_attempt_d_row,
    lambda body: body.replace(
        b'<input type="hidden" name="page" value="1">',
        b'<input type="hidden" name="page" value="2">',
        1,
    ),
    lambda body: body.replace(
        b'<input type="hidden" name="page" value="1">',
        b'<input type="hidden" name="page" value="1"><input type="hidden" name="page" value="1">',
        1,
    ),
    lambda body: body.replace(b'type="hidden" name="page"', b'type="text" name="page"', 1),
    lambda body: body.replace(
        b'<a aria-label="to page 2" href="javascript:pagesubmit(\'2\',this.form)">2</a>',
        b"",
    ),
    lambda body: body.replace(b"pagesubmit('2'", b"pagesubmit('164'"),
    lambda body: body.replace(b"pagesubmit('2',this.form)", b"pagesubmit(2,this.form)", 1),
    lambda body: body.replace(b"<body>", b'<body class="x" class="x">', 1),
    lambda body: body.replace(b'name="selSchct"', b'name="other"', 1),
    lambda body: body.replace(b'multiple="" multiple', b'multiple=""', 1),
    lambda body: body.replace(b'multiple="" multiple', b'multiple="x" multiple', 1),
    lambda body: body.replace(b'multiple="" multiple', b'multiple="" multiple multiple', 1),
)


@pytest.mark.parametrize("mutation", _ATTEMPT_D_RESULT_MUTATIONS)
def test_current_result_contract_rejects_attempt_d_structural_drift(
    mutation: _AttemptDMutation,
) -> None:
    original = _attempt_d_result_page()
    mutated = mutation(original)
    assert mutated != original

    with pytest.raises(ValueError, match=r"JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutated,
            year=1997,
            page=1,
            contract_version="1.0.2",
        )


def test_current_advanced_form_scopes_only_primary_get_controls_and_builds_page_one() -> None:
    """Later POST decoys cannot supply old controls or alter the exact current URL."""
    url = build_judiciary_year_result_url(
        _current_advanced_search_form(),
        entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        year=1997,
        page=1,
        contract_version="1.0.1",
    )

    assert url == (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
        "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
        "selallct=1&stem=1&txtSearch3=%2F%2F1997&year=1997"
    )


def test_current_date_submit_contract_includes_exact_operator_and_blank_day_month() -> None:
    """Current year filtering binds every date control required by the publisher form."""
    url = build_judiciary_year_result_url(
        _current_advanced_search_form(),
        entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        year=1997,
        page=1,
        contract_version="1.0.2",
    )

    assert url == (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
        "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
        "selallct=1&stem=1&txtselectopt3=5&day1=&month=&txtSearch3=%2F%2F1997&"
        "year=1997"
    )


def test_current_result_page_reads_structural_totals_and_exact_dis_rows() -> None:
    """Current separated total labels and exact result rows form one year partition."""
    page = parse_judiciary_year_result_page(
        _current_result_page(),
        year=1997,
        page=1,
        contract_version="1.0.1",
    )

    assert page.reported_results == 2
    assert page.reported_pages == 1
    assert page.dis_ids == (1, 2)
    assert page.decision_dates == (date(1997, 6, 30), date(1997, 7, 1))
    assert page.artifact_urls == (
        (
            "https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?"
            "AH=S&DIS=1&QS=%28%2F%2F1997%29&TP=JU"
        ),
        (
            "https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?"
            "AH=S&DIS=2&QS=%28%2F%2F1997%29&TP=JU"
        ),
    )

    partition = reconcile_judiciary_year_partition((page,))
    assert partition.in_scope_dis_ids == (2,)
    assert partition.artifact_urls == (page.artifact_urls[1],)


_CurrentFormMutation = Callable[[bytes], bytes]
_CURRENT_RESULT_MUTATIONS: list[_CurrentFormMutation] = [
    lambda body: body.replace(b'id="searchresult-total"', b'id="other"', 1),
    lambda body: body.replace(
        b'<span id="searchresult-total">', b'<div id="searchresult-total">', 1
    ),
    lambda body: body.replace(
        b'<span id="searchresult-total">',
        b'<span id="searchresult-total" id="searchresult-total">',
        1,
    ),
    lambda body: body.replace(b">2</span><div>found", b">1,,0</span><div>found", 1),
    lambda body: body.replace(b">2</span><div>found", b"><b>2</b></span><div>found", 1),
    lambda body: body.replace(b'<table id="table">', b"<table>", 1),
    lambda body: body.replace(b"</table>", b"<table></table>", 1),
    lambda body: body.replace(
        b'<span id="searchresult-total">2</span>',
        b'<span id="searchresult-total">2</span><span id="searchresult-total">2</span>',
        1,
    ),
    lambda body: body.replace(b">2</span><div>found", b">2x</span><div>found", 1),
    lambda body: body.replace(b"/lrs//common/ju/ju_frame.jsp", b"/lrs/common/ju/ju_frame.jsp", 1),
    lambda body: body.replace(b"AH=S&amp;DIS=1", b"AH=X&amp;DIS=1", 1),
    lambda body: body.replace(b"%2F%2F1997", b"%2F%2F1998", 1),
    lambda body: body.replace(b"&amp;TP=JU", b"", 1),
    lambda body: body.replace(b"&amp;TP=JU", b"&amp;TP=JU&amp;extra=1", 1),
    lambda body: body.replace(
        b"AH=S&amp;DIS=1&amp;QS=%28%2F%2F1997%29&amp;TP=JU",
        b"DIS=1&amp;AH=S&amp;QS=%28%2F%2F1997%29&amp;TP=JU",
        1,
    ),
    lambda body: body.replace(b"%28%2F%2F1997%29", b"%28%2f%2f1997%29", 1),
    lambda body: body.replace(
        b'<table id="table">',
        b'<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
        b'AH=S&amp;DIS=3&amp;QS=%28%2F%2F1997%29&amp;TP=JU">outside</a>'
        b'<table id="table">',
        1,
    ),
    lambda body: body.replace(
        b">one</a></td></tr>",
        b'>one</a><a href="https://legalref.judiciary.hk/lrs//common/ju/'
        b'ju_frame.jsp?AH=S&amp;DIS=3&amp;QS=%28%2F%2F1997%29&amp;TP=JU">'
        b"extra</a></td></tr>",
        1,
    ),
    lambda body: body.replace(b"<td>Date</td><td>: 30/06/1997</td><td>", b"<td>Date</td><td>", 1),
    lambda body: body.replace(b": 30/06/1997", b": 30/06/1998", 1),
]


@pytest.mark.parametrize(
    "mutation",
    _CURRENT_RESULT_MUTATIONS,
)
def test_current_result_page_rejects_total_locator_or_year_drift(
    mutation: _CurrentFormMutation,
) -> None:
    with pytest.raises(ValueError, match=r"JUDICIARY_"):
        parse_judiciary_year_result_page(
            mutation(_current_result_page()),
            year=1997,
            page=1,
            contract_version="1.0.1",
        )


def test_current_zero_result_page_still_requires_the_observed_result_table() -> None:
    body = b'<span id="searchresult-total">0</span><span id="searchresult-totalpages">1</span>'
    with pytest.raises(ValueError, match="JUDICIARY_RESULT_PAGE_MARKUP_INVALID"):
        parse_judiciary_year_result_page(
            body,
            year=1997,
            page=1,
            contract_version="1.0.1",
        )


_CURRENT_FORM_MUTATIONS: tuple[_CurrentFormMutation, ...] = (
    lambda body: body.replace(b' action=""', b"", 1),
    lambda body: body.replace(b'action=""', b'action="search_result_form.jsp"', 1),
    lambda body: body.replace(b' method="get"', b"", 1),
    lambda body: body.replace(b' id="frm_search"', b"", 1),
    lambda body: body.replace(
        b'onsubmit="javascript:return FORM_SUBMIT(this);"',
        b'onsubmit="return true;"',
        1,
    ),
    lambda body: body.replace(
        b'type="hidden" name="txtSearch3"',
        b'type="text" name="txtSearch3"',
        1,
    ),
    lambda body: body.replace(
        b'<select name="selDatabase2" multiple="" multiple>',
        b'<select name="selDatabase2" multiple="" multiple disabled>',
        1,
    ),
    lambda body: body.replace(b'name="txtSearch3"', b'name="txtSearch3" name="other"', 1),
    lambda body: body.replace(
        b'name="isadvsearch" value="1"',
        b'name="isadvsearch" value="1" disabled',
        1,
    ),
    lambda body: body.replace(b'name="stem" value="1" checked', b'name="stem" value="1"', 1),
    lambda body: body.replace(
        b'<option value="JU" selected>', b'<option value="JU" selected disabled>', 1
    ),
    lambda body: body.replace(
        b'<select name="year"><option value="" selected></option>'
        b'<option value="0"></option></select>',
        b'<input name="year" value=""><input name="year" value="0">',
        1,
    ),
    lambda body: body.replace(b'multiple="" multiple>', b'multiple="">', 1),
    lambda body: body.replace(b"</select>", b"<option>Unexpected</option></select>", 1),
    lambda body: body.replace(b'<input type="hidden" name="txtselectopt3" value="5">', b"", 1),
    lambda body: body.replace(
        b'name="txtselectopt3" value="5"', b'name="txtselectopt3" value="4"', 1
    ),
    lambda body: body.replace(b'<option value="" selected>', b'<option value="">', 1),
    lambda body: body.replace(
        b'<option value="31"></option></select>',
        b'<option value="31"></option><option value="32"></option></select>',
        1,
    ),
    lambda body: body.replace(b'<option value="JU" selected>', b'<option value="JU">', 1),
)


@pytest.mark.parametrize(
    "mutation",
    _CURRENT_FORM_MUTATIONS,
)
def test_current_advanced_form_rejects_action_method_role_or_enabled_drift(
    mutation: _CurrentFormMutation,
) -> None:
    """Observed form semantics cannot be normalized from a different source shape."""
    body = mutation(_current_advanced_search_form())
    with pytest.raises(
        ValueError,
        match=r"JUDICIARY_SEARCH_FORM_(?:METHOD|ACTION|SCOPE|INVALID)",
    ):
        build_judiciary_year_result_url(
            body,
            entry_url=(
                "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
                "?isadvsearch=1&stem=1&selall2=1&selallct=1"
            ),
            year=1997,
            page=1,
        )


def test_current_advanced_form_rejects_unobserved_page_two_grammar() -> None:
    """The page-one form cannot be promoted into an invented pagination contract."""
    with pytest.raises(ValueError, match="JUDICIARY_RESULT_PAGE_UNSUPPORTED"):
        build_judiciary_year_result_url(
            _current_advanced_search_form(),
            entry_url=(
                "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
                "?isadvsearch=1&stem=1&selall2=1&selallct=1"
            ),
            year=1997,
            page=2,
        )


def test_legacy_advanced_form_contract_remains_available_for_exact_historical_replay() -> None:
    """Only the preserved 1.0.0 grammar admits its old page-two locator."""
    body = b"""<form method="get" action="search_result_form.jsp">
      <input type="hidden" name="isadvsearch" value="1">
      <input type="hidden" name="stem" value="1">
      <input type="hidden" name="selall2" value="1">
      <input type="hidden" name="selallct" value="1">
      <select name="database"><option value="JU">Judgment</option></select>
      <select name="court" multiple>
        <option value="FA">FA</option><option value="CA">CA</option>
        <option value="HC">HC</option><option value="CT">CT</option>
        <option value="DC">DC</option><option value="FC">FC</option>
        <option value="LD">LD</option><option value="OT">OT</option>
      </select>
      <input name="txtSearch3"><input name="year"><input type="hidden" name="page" value="1">
    </form>"""

    url = build_judiciary_year_result_url(
        body,
        entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        year=1997,
        page=2,
        contract_version="1.0.0",
    )

    assert url == (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "court=FA&court=CA&court=HC&court=CT&court=DC&court=FC&court=LD&court=OT&"
        "database=JU&isadvsearch=1&page=2&selall2=1&selallct=1&stem=1&"
        "txtSearch3=%2F%2F1997&year=1997"
    )


def test_reconciled_year_partition_requires_every_page_and_every_reported_dis() -> None:
    """Reported totals, page coverage, and exact DIS identities reconcile together."""
    first = parse_judiciary_year_result_page(
        _page(
            page=1,
            links=(
                '<tr><td>01/01/1998</td><td><a href="search_result_detail_frame.jsp?'
                'DIS=24946&QS=%2B&TP=JU">A</a></td></tr>'
                '<tr><td>02/01/1998</td><td><a href="search_result_detail_frame.jsp?'
                'DIS=24947&QS=%2B&TP=JU">B</a></td></tr>'
            ),
        ),
        year=1998,
        page=1,
    )
    second = parse_judiciary_year_result_page(
        _page(
            page=2,
            links=(
                '<tr><td>03/01/1998</td><td><a href="search_result_detail_frame.jsp?'
                'DIS=24948&QS=%2B&TP=JU">C</a></td></tr>'
            ),
        ),
        year=1998,
        page=2,
    )

    partition = reconcile_judiciary_year_partition((first, second))

    assert partition.complete
    assert partition.dis_ids == (24946, 24947, 24948)
    assert partition.artifact_urls[0] == (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_body.jsp?ID=&DIS=24946&QS=%2B&TP=JU"
    )


def test_1997_partition_filters_pre_v1_decisions_only_after_complete_accounting() -> None:
    """The publisher total is reconciled before the inclusive 1997-07-01 scope filter."""
    first = parse_judiciary_year_result_page(
        b"""<p>2 results / 1 pages</p><table>
        <tr><td>30/06/1997</td><td><a href="?DIS=1">old</a></td></tr>
        <tr><td>01/07/1997</td><td><a href="?DIS=2">in scope</a></td></tr>
        </table>""",
        year=1997,
        page=1,
    )

    partition = reconcile_judiciary_year_partition((first,))

    assert partition.complete
    assert partition.dis_ids == (1, 2)
    assert partition.in_scope_dis_ids == (2,)
    assert partition.artifact_urls == (
        (
            "https://legalref.judiciary.hk/lrs/common/search/"
            "search_result_detail_body.jsp?ID=&DIS=2&QS=%2B&TP=JU"
        ),
    )


def test_later_year_partition_rejects_missing_date_before_false_complete() -> None:
    """An undated later-year row cannot be silently omitted from V1 admission."""
    undated = _result_page(
        page=1,
        reported_results=1,
        reported_pages=1,
        dis_ids=(1,),
        year=1998,
        decision_dates=(None,),
    )

    with pytest.raises(ValueError, match="JUDICIARY_DECISION_DATE_REQUIRED"):
        reconcile_judiciary_year_partition((undated,))


def test_year_partition_rejects_missing_page_duplicate_dis_and_total_mismatch() -> None:
    """Truncation and overlap cannot be repaired into a plausible complete inventory."""
    first = parse_judiciary_year_result_page(
        _page(
            page=1,
            links=(
                '<tr><td>01/01/1998</td><td><a href="search_result_detail_frame.jsp?'
                'DIS=1&QS=%2B&TP=JU">A</a></td></tr>'
                '<tr><td>02/01/1998</td><td><a href="search_result_detail_frame.jsp?'
                'DIS=2&QS=%2B&TP=JU">B</a></td></tr>'
            ),
        ),
        year=1998,
        page=1,
    )
    with pytest.raises(ValueError, match="JUDICIARY_YEAR_PARTITION_TRUNCATED"):
        reconcile_judiciary_year_partition((first,))

    duplicate = parse_judiciary_year_result_page(
        _page(
            page=2,
            links=(
                '<tr><td>02/01/1998</td><td><a href="search_result_detail_frame.jsp?'
                'DIS=2&QS=%2B&TP=JU">B</a></td></tr>'
            ),
        ),
        year=1998,
        page=2,
    )
    with pytest.raises(ValueError, match="JUDICIARY_DIS_DUPLICATE"):
        reconcile_judiciary_year_partition((first, duplicate))


def _result_page(
    *,
    page: int,
    reported_results: int,
    reported_pages: int,
    dis_ids: tuple[int, ...],
    year: int = 1998,
    decision_dates: tuple[date | None, ...] | None = None,
    artifact_urls: tuple[str, ...] | None = None,
) -> judiciary_authentic.JudiciaryYearResultPage:
    """Build literal aggregate fixtures without weakening the per-page parser."""
    return judiciary_authentic.JudiciaryYearResultPage(
        year,
        page,
        reported_results,
        reported_pages,
        dis_ids,
        decision_dates or tuple(date(1998, 1, value) for value in dis_ids),
        artifact_urls
        or tuple(
            "https://legalref.judiciary.hk/lrs/common/search/"
            f"search_result_detail_frame.jsp?DIS={dis_id}&QS=%2B&TP=JU"
            for dis_id in dis_ids
        ),
        page + 1 if page < reported_pages else None,
    )


@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_IDENTITY_CONTRACTS)
def test_result_108_reconciles_exact_rs_locator_and_rejects_it_under_result_107(
    result_contract_version: str,
) -> None:
    """The new public boundary accepts one exact RS locator only under its version."""
    rs_url = (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=1&QS=%2B&TP=RS"
    )
    page = _result_page(
        page=1,
        reported_results=1,
        reported_pages=1,
        dis_ids=(1,),
        artifact_urls=(rs_url,),
    )

    partition = reconcile_judiciary_year_partition(
        (page,), contract_version=result_contract_version
    )

    assert partition.artifact_urls == (rs_url,)
    with pytest.raises(ValueError, match="JUDICIARY_DIS_LOCATOR_INVALID"):
        reconcile_judiciary_year_partition((page,), contract_version="1.0.7")


def test_result_1010_reconciles_exact_rv_locator_and_rejects_it_under_old_versions() -> None:
    """The public aggregate boundary preserves RV only under its exact contract."""
    rv_url = (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=1&QS=%2B&TP=RV"
    )
    page = _result_page(
        page=1,
        reported_results=1,
        reported_pages=1,
        dis_ids=(1,),
        artifact_urls=(rv_url,),
    )

    partition = reconcile_judiciary_year_partition((page,), contract_version="1.0.10")

    assert partition.artifact_urls == (rv_url,)
    for old_version in ("1.0.8", "1.0.9"):
        with pytest.raises(ValueError, match="JUDICIARY_DIS_LOCATOR_INVALID"):
            reconcile_judiciary_year_partition((page,), contract_version=old_version)


@pytest.mark.parametrize("decision", [date(1997, 7, 1), date(1997, 6, 30)])
@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_IDENTITY_CONTRACTS)
def test_result_108_rejects_same_identity_jurs_locator_change_at_any_scope(
    decision: date,
    result_contract_version: str,
) -> None:
    """Identity deduplication cannot repair a source-type change, even before cutoff."""
    ju_url = (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=1&QS=%2B&TP=JU"
    )
    rs_url = ju_url.removesuffix("JU") + "RS"
    first = _result_page(
        year=1997,
        page=1,
        reported_results=2,
        reported_pages=2,
        dis_ids=(1,),
        decision_dates=(decision,),
        artifact_urls=(ju_url,),
    )
    second = _result_page(
        year=1997,
        page=2,
        reported_results=2,
        reported_pages=2,
        dis_ids=(1,),
        decision_dates=(decision,),
        artifact_urls=(rs_url,),
    )

    with pytest.raises(ValueError, match="JUDICIARY_DIS_DUPLICATE"):
        reconcile_judiciary_year_partition(
            (first, second), contract_version=result_contract_version
        )


def test_result_105_retains_exact_result_104_page_grammar() -> None:
    """The aggregate-only revision must not loosen any retained page grammar."""
    for body, page in ((_attempt_f_page_one(), 1), (_attempt_e_page_two(), 2)):
        assert parse_judiciary_year_result_page(
            body, year=1997, page=page, contract_version="1.0.5"
        ) == parse_judiciary_year_result_page(body, year=1997, page=page, contract_version="1.0.4")


def test_result_105_admits_only_exact_adjacent_boundary_identity_overlap() -> None:
    """Count listing slots first, then retain each exact artifact identity once."""
    first = _result_page(
        page=1,
        reported_results=4,
        reported_pages=2,
        dis_ids=(1, 2),
    )
    second = _result_page(
        page=2,
        reported_results=4,
        reported_pages=2,
        dis_ids=(2, 3),
        decision_dates=(date(1998, 1, 2), date(1998, 1, 3)),
    )

    partition = reconcile_judiciary_year_partition((first, second), contract_version="1.0.5")

    assert partition.complete
    assert partition.listing_count == 4
    assert partition.reported_results == 4
    assert partition.dis_ids == (1, 2, 3)
    assert partition.in_scope_dis_ids == (1, 2, 3)
    assert len(partition.artifact_urls) == 3
    with pytest.raises(ValueError, match="JUDICIARY_DIS_DUPLICATE"):
        reconcile_judiciary_year_partition((first, second), contract_version="1.0.4")


def test_result_105_rejects_every_broader_identity_overlap_shape() -> None:
    """No same-page, interior, separated, mismatched, or triplicate overlap is repaired."""
    exact_url_2 = (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=2&QS=%2B&TP=JU"
    )
    hostile: tuple[tuple[judiciary_authentic.JudiciaryYearResultPage, ...], ...] = (
        (
            _result_page(page=1, reported_results=4, reported_pages=2, dis_ids=(1, 1)),
            _result_page(page=2, reported_results=4, reported_pages=2, dis_ids=(2, 3)),
        ),
        (
            _result_page(page=1, reported_results=4, reported_pages=2, dis_ids=(1, 2)),
            _result_page(page=2, reported_results=4, reported_pages=2, dis_ids=(3, 2)),
        ),
        (
            _result_page(page=1, reported_results=5, reported_pages=3, dis_ids=(1, 2)),
            _result_page(page=2, reported_results=5, reported_pages=3, dis_ids=(3,)),
            _result_page(
                page=3,
                reported_results=5,
                reported_pages=3,
                dis_ids=(2, 4),
                decision_dates=(date(1998, 1, 2), date(1998, 1, 4)),
            ),
        ),
        (
            _result_page(page=1, reported_results=4, reported_pages=2, dis_ids=(1, 2)),
            _result_page(
                page=2,
                reported_results=4,
                reported_pages=2,
                dis_ids=(2, 3),
                decision_dates=(date(1998, 1, 2), date(1998, 1, 3)),
                artifact_urls=(exact_url_2 + "&changed=1", exact_url_2.replace("DIS=2", "DIS=3")),
            ),
        ),
        (
            _result_page(page=1, reported_results=4, reported_pages=2, dis_ids=(1, 2)),
            _result_page(
                page=2,
                reported_results=4,
                reported_pages=2,
                dis_ids=(2, 3),
                decision_dates=(date(1998, 2, 2), date(1998, 1, 3)),
            ),
        ),
        (
            _result_page(page=1, reported_results=5, reported_pages=2, dis_ids=(1, 2)),
            _result_page(
                page=2,
                reported_results=5,
                reported_pages=2,
                dis_ids=(2, 3, 2),
                decision_dates=(date(1998, 1, 2), date(1998, 1, 3), date(1998, 1, 2)),
            ),
        ),
    )
    for pages in hostile:
        with pytest.raises(ValueError, match="JUDICIARY_DIS_DUPLICATE"):
            reconcile_judiciary_year_partition(pages, contract_version="1.0.5")


def test_result_105_checks_raw_listing_count_before_identity_deduplication() -> None:
    """A plausible unique inventory cannot hide a publisher listing-count mismatch."""
    pages = (
        _result_page(page=1, reported_results=5, reported_pages=2, dis_ids=(1, 2)),
        _result_page(
            page=2,
            reported_results=5,
            reported_pages=2,
            dis_ids=(2, 3),
            decision_dates=(date(1998, 1, 2), date(1998, 1, 3)),
        ),
    )
    with pytest.raises(ValueError, match="JUDICIARY_REPORTED_RESULT_TOTAL_MISMATCH"):
        reconcile_judiciary_year_partition(pages, contract_version="1.0.5")


def test_result_106_admits_only_the_observed_cutoff_excluded_shifted_overlap() -> None:
    """A single exact last-row/row-two displacement is safe only outside V1 scope."""
    first = _result_page(
        year=1997,
        page=1,
        reported_results=5,
        reported_pages=2,
        dis_ids=(1, 2),
        decision_dates=(date(1997, 6, 1), date(1997, 6, 2)),
    )
    second = _result_page(
        year=1997,
        page=2,
        reported_results=5,
        reported_pages=2,
        dis_ids=(3, 2, 4),
        decision_dates=(date(1997, 6, 3), date(1997, 6, 2), date(1997, 7, 1)),
    )

    partition = reconcile_judiciary_year_partition((first, second), contract_version="1.0.6")

    assert partition.complete
    assert partition.listing_count == 5
    assert partition.dis_ids == (1, 2, 3, 4)
    assert partition.in_scope_dis_ids == (4,)
    with pytest.raises(ValueError, match="JUDICIARY_DIS_DUPLICATE"):
        reconcile_judiciary_year_partition((first, second), contract_version="1.0.5")


def test_result_106_rejects_shifted_overlap_hostile_matrix() -> None:
    """Every wider position, scope, multiplicity, or intervening-row shape stays closed."""
    base_first = _result_page(
        year=1997,
        page=1,
        reported_results=5,
        reported_pages=2,
        dis_ids=(1, 2),
        decision_dates=(date(1997, 6, 1), date(1997, 6, 2)),
    )
    exact_url_2 = base_first.artifact_urls[1]
    hostile_second_pages = (
        _result_page(
            year=1997,
            page=2,
            reported_results=5,
            reported_pages=2,
            dis_ids=(3, 4, 2),
            decision_dates=(date(1997, 6, 3), date(1997, 6, 4), date(1997, 6, 2)),
        ),
        _result_page(
            year=1997,
            page=2,
            reported_results=5,
            reported_pages=2,
            dis_ids=(3, 2, 4),
            decision_dates=(date(1997, 7, 1), date(1997, 6, 2), date(1997, 7, 2)),
        ),
        _result_page(
            year=1997,
            page=2,
            reported_results=5,
            reported_pages=2,
            dis_ids=(3, 2, 4),
            decision_dates=(date(1997, 6, 3), date(1997, 7, 1), date(1997, 7, 2)),
        ),
        _result_page(
            year=1997,
            page=2,
            reported_results=5,
            reported_pages=2,
            dis_ids=(3, 2, 4),
            decision_dates=(date(1997, 6, 3), date(1997, 6, 2), date(1997, 7, 2)),
            artifact_urls=(
                exact_url_2.replace("DIS=2", "DIS=3"),
                exact_url_2 + "&changed=1",
                exact_url_2.replace("DIS=2", "DIS=4"),
            ),
        ),
        _result_page(
            year=1997,
            page=2,
            reported_results=5,
            reported_pages=2,
            dis_ids=(3, 2, 2),
            decision_dates=(date(1997, 6, 3), date(1997, 6, 2), date(1997, 6, 2)),
        ),
    )
    for second in hostile_second_pages:
        with pytest.raises(ValueError, match="JUDICIARY_DIS_DUPLICATE"):
            reconcile_judiciary_year_partition((base_first, second), contract_version="1.0.6")

    second_shift = (
        _result_page(
            year=1997,
            page=1,
            reported_results=10,
            reported_pages=4,
            dis_ids=(1, 2),
            decision_dates=(date(1997, 6, 1), date(1997, 6, 2)),
        ),
        _result_page(
            year=1997,
            page=2,
            reported_results=10,
            reported_pages=4,
            dis_ids=(3, 2, 4),
            decision_dates=(date(1997, 6, 3), date(1997, 6, 2), date(1997, 6, 4)),
        ),
        _result_page(
            year=1997,
            page=3,
            reported_results=10,
            reported_pages=4,
            dis_ids=(5, 6),
            decision_dates=(date(1997, 6, 5), date(1997, 6, 6)),
        ),
        _result_page(
            year=1997,
            page=4,
            reported_results=10,
            reported_pages=4,
            dis_ids=(7, 6, 8),
            decision_dates=(date(1997, 6, 7), date(1997, 6, 6), date(1997, 7, 1)),
        ),
    )
    with pytest.raises(ValueError, match="JUDICIARY_DIS_DUPLICATE"):
        reconcile_judiciary_year_partition(second_shift, contract_version="1.0.6")


@pytest.mark.parametrize(
    ("pages", "expected_ids"),
    [
        (
            (_result_page(page=1, reported_results=4, reported_pages=1, dis_ids=(1, 2, 1, 3)),),
            (1, 2, 3),
        ),
        (
            (
                _result_page(page=1, reported_results=6, reported_pages=2, dis_ids=(1, 2, 3)),
                _result_page(page=2, reported_results=6, reported_pages=2, dis_ids=(4, 2, 5)),
            ),
            (1, 2, 3, 4, 5),
        ),
        (
            (
                _result_page(page=1, reported_results=7, reported_pages=3, dis_ids=(1, 2)),
                _result_page(page=2, reported_results=7, reported_pages=3, dis_ids=(3, 4)),
                _result_page(page=3, reported_results=7, reported_pages=3, dis_ids=(2, 5, 6)),
            ),
            (1, 2, 3, 4, 5, 6),
        ),
        (
            (
                _result_page(page=1, reported_results=6, reported_pages=2, dis_ids=(1, 2, 1)),
                _result_page(page=2, reported_results=6, reported_pages=2, dis_ids=(3, 1, 4)),
            ),
            (1, 2, 3, 4),
        ),
        (
            (
                _result_page(page=1, reported_results=5, reported_pages=2, dis_ids=(1, 2, 3)),
                _result_page(page=2, reported_results=5, reported_pages=2, dis_ids=(2, 4)),
            ),
            (1, 2, 3, 4),
        ),
    ],
    ids=("same-page", "interior", "non-adjacent", "triplicate", "attempt-i-shape"),
)
@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_IDENTITY_CONTRACTS)
def test_result_107_deduplicates_identical_identity_facts_independent_of_page_topology(
    pages: tuple[judiciary_authentic.JudiciaryYearResultPage, ...],
    expected_ids: tuple[int, ...],
    result_contract_version: str,
) -> None:
    """Stable identity facts, not mutable page positions, govern repeat admission."""
    partition = reconcile_judiciary_year_partition(pages, contract_version=result_contract_version)

    assert partition.complete
    assert partition.listing_count == pages[0].reported_results
    assert partition.dis_ids == expected_ids
    assert len(partition.artifact_urls) == len(expected_ids)


@pytest.mark.parametrize("mutation", ["date", "locator", "missing_date", "locator_collision"])
@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_IDENTITY_CONTRACTS)
def test_result_107_rejects_inconsistent_identity_facts_and_locator_collisions(
    mutation: str,
    result_contract_version: str,
) -> None:
    """Deduplication cannot repair a changed fact or a non-bijective locator mapping."""
    exact_url_1 = (
        "https://legalref.judiciary.hk/lrs/common/search/"
        "search_result_detail_frame.jsp?DIS=1&QS=%2B&TP=JU"
    )
    first = _result_page(
        year=1997,
        page=1,
        reported_results=4 if mutation != "locator_collision" else 2,
        reported_pages=2 if mutation != "locator_collision" else 1,
        dis_ids=(1, 2),
        decision_dates=(date(1997, 7, 1), date(1997, 7, 2)),
        artifact_urls=(
            exact_url_1,
            exact_url_1.replace("DIS=1", "DIS=2")
            if mutation != "locator_collision"
            else exact_url_1,
        ),
    )
    if mutation == "locator_collision":
        pages = (first,)
    else:
        repeated_date = {
            "date": date(1997, 7, 3),
            "locator": date(1997, 7, 1),
            "missing_date": None,
        }[mutation]
        repeated_url = exact_url_1 + ("&changed=1" if mutation == "locator" else "")
        second = _result_page(
            year=1997,
            page=2,
            reported_results=4,
            reported_pages=2,
            dis_ids=(1, 3),
            decision_dates=(repeated_date, date(1997, 7, 3)),
            artifact_urls=(repeated_url, exact_url_1.replace("DIS=1", "DIS=3")),
        )
        pages = (first, second)

    expected_code = (
        "JUDICIARY_DIS_LOCATOR_INVALID"
        if mutation in {"locator", "locator_collision"}
        else "JUDICIARY_DIS_DUPLICATE"
    )
    with pytest.raises(ValueError, match=expected_code):
        reconcile_judiciary_year_partition(pages, contract_version=result_contract_version)


@pytest.mark.parametrize("invalid_locator", ["", "https://example.invalid/not-canonical"])
@pytest.mark.parametrize("result_contract_version", _CURRENT_RESULT_IDENTITY_CONTRACTS)
def test_result_107_rejects_missing_or_noncanonical_locator_at_public_reconcile_boundary(
    invalid_locator: str,
    result_contract_version: str,
) -> None:
    """Direct exact page objects cannot bypass the canonical detail-locator contract."""
    page = _result_page(
        page=1,
        reported_results=2,
        reported_pages=1,
        dis_ids=(1, 2),
        artifact_urls=(
            invalid_locator,
            (
                "https://legalref.judiciary.hk/lrs/common/search/"
                "search_result_detail_frame.jsp?DIS=2&QS=%2B&TP=JU"
            ),
        ),
    )

    with pytest.raises(ValueError, match="JUDICIARY_DIS_LOCATOR_INVALID"):
        reconcile_judiciary_year_partition((page,), contract_version=result_contract_version)
