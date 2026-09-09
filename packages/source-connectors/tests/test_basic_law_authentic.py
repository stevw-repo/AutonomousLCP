"""Exact current English Basic Law category-membership and content tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_source_connectors import basic_law_authentic
from asklegal_source_connectors.basic_law_authentic import (
    parse_basic_law_membership,
    validate_basic_law_content_page,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue


@runtime_checkable
class _LocatorNormalizer(Protocol):
    def __call__(self, value: str, *, base_url: str) -> list[object]: ...


@runtime_checkable
class _ContractProvider(Protocol):
    def __call__(self) -> Mapping[str, object]: ...


_CONSTITUTION_ROOT = "https://www.basiclaw.gov.hk/en/constitution/index.html"
_BASIC_LAW_ROOT = "https://www.basiclaw.gov.hk/en/basiclaw/index.html"
_EXPECTED_MEMBERS = (
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
_FIXTURE = Path(__file__).with_name("fixtures") / "basic_law_constitution_preamble_sanitized.html"
_CONTRACT = Path(basic_law_authentic.__file__).with_name("basic_law_content_structure.json")
_PREAMBLE_TITLE = "Basic Law - Constitution - Preamble (EN)"
_EXPECTED_STRUCTURE_IDENTITIES = (
    (
        _EXPECTED_MEMBERS[0],
        _PREAMBLE_TITLE,
        "sha256:4f6d2c0a0042a69be317a6dba0cdbc3661433def7b3690e885f92ca74974017c",
    ),
    (
        _EXPECTED_MEMBERS[1],
        "Basic Law - Constitution - Chapter I (EN)",
        "sha256:e7eb4e3688841bd28af1b4ff2295903a1cf5236c73be2d492f21c76966ac1446",
    ),
    (
        _EXPECTED_MEMBERS[2],
        "Basic Law - Constitution - Chapter II (EN)",
        "sha256:7c01c3e538688e691e8ec52c637c1ae46d863fca3d045795c869e04776d5366d",
    ),
    (
        _EXPECTED_MEMBERS[3],
        "Basic Law - Constitution - Chapter III (EN)",
        "sha256:fa566be06083b530e8e112c810782ace25db3bee1a61266871899d80c21dad40",
    ),
    (
        _EXPECTED_MEMBERS[4],
        "Basic Law - Constitution - Chapter IV (EN)",
        "sha256:d70c8e3f80e05522960e37a385b570bda585cd628b673166f07617b3606240cc",
    ),
    (
        _EXPECTED_MEMBERS[5],
        "Basic Law - Basic Law - Decree of the President of the People's Republic of China (EN)",
        "sha256:2235db38138246bd0bf6e8c0911b8d9c39fd1b6a7331ef182e5c4dc42d9e737e",
    ),
    (
        _EXPECTED_MEMBERS[6],
        "Basic Law - Basic Law - Preamble (EN)",
        "sha256:4b967ffc8ebfb3f12559cf31b1194106ae25a4082bd74f49a045fce68f02a267",
    ),
    (
        _EXPECTED_MEMBERS[7],
        "Basic Law - Basic Law - Chapter I (EN)",
        "sha256:cb203cd08bd2dead617e1442da7e9397add0caf528bec8ed60dd75ff26a71864",
    ),
    (
        _EXPECTED_MEMBERS[8],
        "Basic Law - Basic Law - Chapter II (EN)",
        "sha256:b9c7cd44be8dbf9a3ffb42348da49deb7fc8afd556bf738b273bed89d3d881af",
    ),
    (
        _EXPECTED_MEMBERS[9],
        "Basic Law - Basic Law - Chapter III (EN)",
        "sha256:1331b6eafedfedff4fa49ec17793db29a04c9ca4dd785962de373407c993ca0d",
    ),
    (
        _EXPECTED_MEMBERS[10],
        "Basic Law - Basic Law - Chapter IV (EN)",
        "sha256:cc6202f14652a94ac8da2f574493053ac1302fa2a443c6f4f72975edecadd7ab",
    ),
    (
        _EXPECTED_MEMBERS[11],
        "Basic Law - Basic Law - Chapter V (EN)",
        "sha256:dc8572680514ecbe47ba398fcb6da1fb70e56a51f843590fdb6a10c2c0d6cf57",
    ),
    (
        _EXPECTED_MEMBERS[12],
        "Basic Law - Basic Law - Chapter VI (EN)",
        "sha256:fed55e44b76ad75ec9e19b3255eee83db9da7de8db9f1b75bf0611cffeb83bfb",
    ),
    (
        _EXPECTED_MEMBERS[13],
        "Basic Law - Basic Law - Chapter VII (EN)",
        "sha256:6276fe03499fceae86907d4973cea8580a8bf8f0021887e46f28a6e5b6263ff6",
    ),
    (
        _EXPECTED_MEMBERS[14],
        "Basic Law - Basic Law - Chapter VIII (EN)",
        "sha256:5e74607b051b5cfb06680848cc89be1c43e9d4b6d0405c2a868d22bd40ccb5b8",
    ),
    (
        _EXPECTED_MEMBERS[15],
        "Basic Law - Basic Law - Chapter IX (EN)",
        "sha256:c6503de1cc6563c0dbc0ccc0da3239a7b6691e7f077c4aac36361157215e1842",
    ),
    (
        _EXPECTED_MEMBERS[16],
        "Basic Law - Basic Law - Annex & Instrument - Annex I (EN)",
        "sha256:f72a2808749abb8bf26a60b02b3306689f671f54585575d57da2756029572c2e",
    ),
    (
        _EXPECTED_MEMBERS[17],
        "Basic Law - Basic Law - Annex & Instrument - Annex II (EN)",
        "sha256:433efc0781ae58bfd3d40b4cfc74434d78f4fecff7e2458f8a9f1e9a219811ca",
    ),
    (
        _EXPECTED_MEMBERS[18],
        "Basic Law - Basic Law - Annex & Instrument - Annex III (EN)",
        "sha256:6b8df405e6902ece730fc180fbe7f5b9b0a0d10775fd254c04a7d9cfb9991a07",
    ),
    (
        _EXPECTED_MEMBERS[19],
        "Basic Law - Basic Law - Annex & Instrument (EN)",
        "sha256:4bb0ac2ad531fa1a6209a0032810896336570138c52e19e141bdbfbf8a476a78",
    ),
)
_GENERIC_STATUS = (
    "Loading request service response status page information remains temporarily "
    "unavailable while system processes continue please retry using browser navigation."
)


def _authentic_shape() -> bytes:
    return _FIXTURE.read_bytes()


def _replace_once(body: bytes, old: bytes, new: bytes) -> bytes:
    assert old in body
    return body.replace(old, new, 1)


def _validate(body: bytes, *, url: str = _EXPECTED_MEMBERS[0]) -> None:
    validate_basic_law_content_page(body, url=url, media_type="text/html")


def _publisher_shell(*, title: str, content: str) -> bytes:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">'
        '<meta name="format-detection" content="telephone=no">'
        '<meta http-equiv="X-UA-Compatible" content="IE=edge">'
        f"<title>{title}</title>"
        '<script type="text/javascript"></script>'
        '<script type="text/javascript" '
        'src="../../filemanager/system/en/js/template2.js"></script>'
        '<script type="text/javascript" '
        'src="../../filemanager/system/en/js/menu.js"></script>'
        '</head><body><script type="text/javascript"></script>'
        f"{content}"
        '<script type="text/javascript"></script></body></html>'
    ).encode()


def _page(*hrefs: str) -> bytes:
    unrelated = (
        '<a href="https://www.had.gov.hk/en/public_services/public_enquiry_services/'
        'ctec.htm">Public enquiry</a>'
        '<a href="../../filemanager/content/en/files/basiclawtext/'
        'basiclaw_full_text.pdf">PDF</a>'
    )
    return (unrelated + "".join(f'<a href="{href}">member</a>' for href in hrefs)).encode()


def _parse(
    constitution_hrefs: tuple[str, ...],
    basic_law_hrefs: tuple[str, ...],
) -> tuple[str, ...]:
    return parse_basic_law_membership(
        _page(*constitution_hrefs),
        _page(*basic_law_hrefs),
        constitution_root_url=_CONSTITUTION_ROOT,
        basic_law_root_url=_BASIC_LAW_ROOT,
    ).member_urls


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _contract_document() -> dict[str, JsonValue]:
    parsed = parse_json_bytes(_CONTRACT.read_bytes(), max_bytes=65_536)
    assert isinstance(parsed, dict)
    return parsed


def _contract_members(document: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    raw_members = document["members"]
    assert isinstance(raw_members, list)
    assert all(isinstance(member, dict) for member in raw_members)
    return [member for member in raw_members if isinstance(member, dict)]


def _member_string(member: dict[str, JsonValue], key: str) -> str:
    value = member[key]
    assert isinstance(value, str)
    return value


def _locator_normalizer() -> _LocatorNormalizer:
    candidate = basic_law_authentic.__dict__.get("_normalized_locator")
    assert isinstance(candidate, _LocatorNormalizer)
    return candidate


def _cached_contract_provider() -> _ContractProvider:
    candidate = basic_law_authentic.__dict__.get("_default_structure_contract")
    assert isinstance(candidate, _ContractProvider)
    return candidate


def _set_mapping_item(mapping: object, key: str, value: object) -> None:
    if not isinstance(mapping, MutableMapping):
        raise TypeError
    mapping[key] = value


def _write_contract(path: Path, document: dict[str, JsonValue]) -> None:
    unsigned = dict(document)
    unsigned.pop("fingerprint", None)
    document["fingerprint"] = "sha256:" + hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    path.write_bytes(_canonical_json(document))


def test_exact_category_membership_returns_literal_ordered_twenty_member_inventory() -> None:
    actual = _parse(
        ("chapter4.html", "preamble.html", "chapter2.html", "chapter1.html", "chapter3.html"),
        (
            "annex-instrument.html",
            "chapter9.html",
            "annex3.html",
            "decree.html",
            "chapter1.html",
            "chapter2.html",
            "chapter3.html",
            "chapter4.html",
            "chapter5.html",
            "chapter6.html",
            "chapter7.html",
            "chapter8.html",
            "preamble.html",
            "annex1.html",
            "annex2.html",
        ),
    )
    assert actual == _EXPECTED_MEMBERS


@pytest.mark.parametrize(
    ("constitution_hrefs", "basic_law_hrefs"),
    [
        (
            ("preamble.html", "chapter1.html", "chapter2.html", "chapter3.html"),
            tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[5:]),
        ),
        (
            (*tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[:5]), "chapter5.html"),
            tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[5:]),
        ),
        (
            (*tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[:5]), "preamble.html"),
            tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[5:]),
        ),
        (
            (
                *tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[:5]),
                "../basiclaw/decree.html",
            ),
            tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[6:]),
        ),
    ],
    ids=("missing", "extra", "duplicate", "cross-category"),
)
def test_missing_extra_duplicate_and_cross_category_membership_reject(
    constitution_hrefs: tuple[str, ...],
    basic_law_hrefs: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match=r"BASIC_LAW_(?:MEMBERSHIP|MEMBER_URL)_INVALID"):
        _parse(constitution_hrefs, basic_law_hrefs)


@pytest.mark.parametrize(
    "hostile",
    [
        "chapter1.html?download=1",
        "chapter1.html#part",
        "chapter%31.html",
        "../constitution/chapter1.html",
        "https://attacker.example/en/constitution/chapter1.html",
        "https://www.basiclaw.gov.hk:443/en/constitution/chapter1.html",
        "https://www.basiclaw.gov.hk/en/basiclaw/chapter1.html",
    ],
)
def test_hostile_or_noncanonical_content_locator_rejects(hostile: str) -> None:
    constitution = tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[:5])
    basic_law = tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[5:])
    with pytest.raises(ValueError, match="BASIC_LAW_MEMBER_URL_INVALID"):
        _parse((hostile, *constitution[1:]), basic_law)


def test_encoded_family_shaped_candidate_rejects_before_navigation_filter() -> None:
    constitution = tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[:5])
    basic_law = tuple(url.rsplit("/", 1)[-1] for url in _EXPECTED_MEMBERS[5:])
    with pytest.raises(ValueError, match="BASIC_LAW_MEMBER_URL_INVALID"):
        _parse((*constitution, "/en/%63onstitution/chapter1.html"), basic_law)


def test_sanitized_authentic_shape_and_text_only_change_are_accepted() -> None:
    body = _authentic_shape()
    _validate(body)
    _validate(body.replace(b"Synthetic visible text.", b"Different autonomous text."))


def test_exact_title_and_trivial_body_rejects() -> None:
    body = (
        f"<html><head><title>{_PREAMBLE_TITLE}</title></head><body><p>Loading.</p></body></html>"
    ).encode()
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(body)


@pytest.mark.parametrize(
    ("url", "title", "content"),
    [
        (
            _EXPECTED_MEMBERS[0],
            _PREAMBLE_TITLE,
            (
                f'<div class="message" role="status"><p>{_GENERIC_STATUS}</p></div>'
                '<div class="nav-btn-wrap clearfix"><a href="index.html">Index</a>'
                '<a href="chapter1.html">Next</a></div>'
            ),
        ),
        (
            _EXPECTED_MEMBERS[19],
            "Basic Law - Basic Law - Annex & Instrument (EN)",
            (
                f'<div class="message" role="status"><p>{_GENERIC_STATUS}</p></div>'
                '<a href="index.html">Index</a><a href="annex3.html">Back</a>'
            ),
        ),
    ],
)
def test_exact_title_generic_publisher_shell_rejects(
    url: str,
    title: str,
    content: str,
) -> None:
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(_publisher_shell(title=title, content=content), url=url)


def test_exact_structure_copied_to_wrong_member_rejects() -> None:
    body = _replace_once(
        _authentic_shape(),
        _PREAMBLE_TITLE.encode(),
        b"Basic Law - Basic Law - Preamble (EN)",
    )
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(body, url=_EXPECTED_MEMBERS[6])


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            (
                b'<a href="index.html" class="btn-back-to-index">Synthetic visible text.</a>'
                b'<a href="introduction.html" class="generalBtn btn-back f_left">'
            ),
            (
                b'<a href="introduction.html" class="generalBtn btn-back f_left">'
                b'Synthetic visible text.</a><a href="index.html" class="btn-back-to-index">'
            ),
        ),
        (b"<p>Synthetic visible text.</p>", b""),
        (
            b'<div class="nav-btn-wrap clearfix">',
            b'<span></span><div class="nav-btn-wrap clearfix">',
        ),
        (b'href="chapter1.html"', b'href="chapter2.html"'),
        (b"<p>", b"<p hidden>"),
        (b"<p>", b'<p aria-hidden="true">'),
        (b"<p>", b'<p style="display:none">'),
    ],
    ids=("reordered", "removed", "extra", "link", "hidden", "aria-hidden", "style-hidden"),
)
def test_tag_link_order_and_visibility_mutations_reject(old: bytes, new: bytes) -> None:
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(_replace_once(_authentic_shape(), old, new))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            b'href="chapter1.html"',
            b'HREF="https://attacker.example/error" href="chapter1.html"',
        ),
        (
            b'src="../../filemanager/system/en/js/template2.js"',
            (
                b'SRC="https://attacker.example/code.js" '
                b'src="../../filemanager/system/en/js/template2.js"'
            ),
        ),
        (
            b'class="nav-btn-wrap clearfix"',
            b'CLASS="hidden" class="nav-btn-wrap clearfix"',
        ),
        (b"<p>", b'<p STYLE="color:red" style="color:blue">'),
        (b"<p>", b'<p hidden="false" HIDDEN="false">'),
        (b"<p>", b'<p aria-hidden="false" ARIA-HIDDEN="false">'),
        (b"<p>", b'<p id="unsafe" ID="canonical">'),
        (b"<p>", b'<p role="alert" ROLE="document">'),
        (
            b'name="viewport"',
            b'NAME="unsafe-selector" name="viewport"',
        ),
        (
            b'http-equiv="X-UA-Compatible"',
            b'HTTP-EQUIV="refresh" http-equiv="X-UA-Compatible"',
        ),
        (b'charset="utf-8"', b'CHARSET="utf-16" charset="utf-8"'),
        (
            b'<script type="text/javascript"></script>',
            b'<script TYPE="application/unsafe" type="text/javascript"></script>',
        ),
        (b'<html lang="en">', b'<html LANG="en" lang="en">'),
        (
            b'href="chapter1.html"',
            b'HREF=https://attacker.example/error&amp;code href="chapter1.html"',
        ),
    ],
    ids=(
        "href-case-insensitive",
        "src-case-insensitive",
        "class-hidden-first",
        "style-benign",
        "hidden",
        "aria-hidden-benign",
        "id",
        "role",
        "meta-name",
        "meta-http-equiv",
        "meta-charset",
        "script-type",
        "exact-benign-lang",
        "unquoted-entity-href",
    ),
)
def test_duplicate_attribute_names_reject_before_semantic_projection(
    old: bytes,
    new: bytes,
) -> None:
    """Browser-first/parser-last duplicate ambiguity must fail before interpretation."""
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(_replace_once(_authentic_shape(), old, new))


def test_wrong_title_rejects_otherwise_exact_structure() -> None:
    body = _replace_once(_authentic_shape(), _PREAMBLE_TITLE.encode(), b"Nearby Page")
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(body)


@pytest.mark.parametrize("tag", ["iframe", "object", "script", "style", "noscript", "template"])
def test_nonvisible_container_mutations_reject(tag: str) -> None:
    replacement = f"<{tag}>Synthetic visible text.</{tag}>".encode()
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(_replace_once(_authentic_shape(), b"<p>Synthetic visible text.</p>", replacement))


@pytest.mark.parametrize(
    "malformed_or_duplicate_style",
    [
        "display none",
        "visibility:hidden !",
        "display:none !important trailing",
        "display:none; display:block",
        "visibility:visible; VISIBILITY:hidden",
        "display:block; display/**/:none",
        "visibility:visible; visibility/**/:hidden",
        "color:red; display/* unterminated : none",
        r"dis\70 lay:none",
        r"vis\69 bility:hidden",
    ],
)
def test_malformed_duplicate_or_escaped_hide_declaration_rejects(
    malformed_or_duplicate_style: str,
) -> None:
    replacement = f'<p style="{malformed_or_duplicate_style}">'.encode()
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(_replace_once(_authentic_shape(), b"<p>", replacement))


@pytest.mark.parametrize(
    "comment_obscured_style",
    [
        " DiS/**/pLaY : NoNe ",
        " /**/ VISIBILITY /**/ : HIDDEN /**/ ",
        "display/* comment: with; separators */: none",
        "VisI/**/biLiTy/*gap*/ : HiDdEn ! /**/ ImPoRtAnT",
    ],
)
def test_comment_obscured_hide_declaration_rejects(comment_obscured_style: str) -> None:
    replacement = f'<p style="{comment_obscured_style}">'.encode()
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(_replace_once(_authentic_shape(), b"<p>", replacement))


def test_closed_comments_in_non_hide_style_are_projection_neutral() -> None:
    replacement = b'<p style="color/* comment: with; separators */: red; border/**/-color: blue">'
    _validate(_replace_once(_authentic_shape(), b"<p>", replacement))


@pytest.mark.parametrize(
    "body",
    [
        b"<body><title>Basic Law - Constitution - Preamble (EN)</title><html>",
        b"<html><body><title>Basic Law - Constitution - Preamble (EN)</title></body></html>",
        (
            b"<html><head><title>Basic Law - Constitution - Preamble (EN)</title>"
            b"</head><body></body></html>"
        ),
    ],
)
def test_malformed_or_empty_html_rejects(body: bytes) -> None:
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(body)


def test_contract_is_closed_self_fingerprinted_and_has_twenty_unique_members() -> None:
    parsed = _contract_document()
    members = _contract_members(parsed)
    assert len(members) == 20
    assert [_member_string(member, "url") for member in members] == list(_EXPECTED_MEMBERS)
    assert len({_member_string(member, "projection_fingerprint") for member in members}) == 20
    assert set(parsed) == {
        "schema_id",
        "schema_version",
        "projection_version",
        "fingerprint",
        "members",
    }
    assert all(set(member) == {"url", "title", "projection_fingerprint"} for member in members)
    assert basic_law_authentic.read_basic_law_structure_contract(_CONTRACT)


def test_contract_literal_member_identities_match_independent_twenty_member_lock() -> None:
    """Expected URL/title/hash literals do not come from the production loader."""
    members = _contract_members(_contract_document())
    observed = tuple(
        (
            _member_string(member, "url"),
            _member_string(member, "title"),
            _member_string(member, "projection_fingerprint"),
        )
        for member in members
    )
    assert observed == _EXPECTED_STRUCTURE_IDENTITIES


def test_cached_contract_mapping_cannot_be_mutated_in_process() -> None:
    contract = _cached_contract_provider()()
    member = contract[_EXPECTED_MEMBERS[0]]
    with pytest.raises(TypeError):
        _set_mapping_item(contract, _EXPECTED_MEMBERS[0], member)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"<p>", b'<p onclick="unsafe()">'),
        (b"<p>", b'<p data-unknown="value">'),
        (
            b'src="../../filemanager/system/en/js/template2.js"',
            b'src="https://attacker.example/template2.js"',
        ),
    ],
    ids=("event-name", "unknown-name", "script-src"),
)
def test_event_unknown_attribute_and_script_source_mutations_reject(
    old: bytes,
    new: bytes,
) -> None:
    with pytest.raises(ValueError, match="BASIC_LAW_CONTENT_PAGE_INVALID"):
        _validate(_replace_once(_authentic_shape(), old, new))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            b'href="chapter1.html"',
            b'href="https://www.basiclaw.gov.hk/en/constitution/chapter1.html"',
        ),
        (
            b'src="../../filemanager/system/en/js/template2.js"',
            b'src="https://www.basiclaw.gov.hk/filemanager/system/en/js/template2.js"',
        ),
    ],
    ids=("anchor", "script"),
)
def test_equivalent_absolute_locators_preserve_projection(old: bytes, new: bytes) -> None:
    _validate(_replace_once(_authentic_shape(), old, new))


def test_javascript_control_locator_is_closed_and_text_free() -> None:
    normalize = _locator_normalizer()
    base_url = _EXPECTED_MEMBERS[3]
    assert normalize("javascript:;", base_url=base_url) == [
        "control",
        "javascript-empty",
    ]
    assert normalize("javascript:alert(1)", base_url=base_url) == [
        "control",
        "javascript-other",
    ]
    assert normalize("javascript://attacker.example/", base_url=base_url) == [
        "control",
        "javascript-other",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-root",
        "extra-root",
        "missing-member-field",
        "extra-member-field",
        "missing-member",
        "duplicate-url",
        "unknown-url",
        "bad-projection-hash",
    ],
)
def test_contract_loader_rejects_closed_schema_mutations(tmp_path: Path, mutation: str) -> None:
    document = _contract_document()
    members = _contract_members(document)
    if mutation == "missing-root":
        del document["projection_version"]
    elif mutation == "extra-root":
        document["unknown"] = "value"
    elif mutation == "missing-member-field":
        del members[0]["title"]
    elif mutation == "extra-member-field":
        members[0]["unknown"] = "value"
    elif mutation == "missing-member":
        raw_members = document["members"]
        assert isinstance(raw_members, list)
        raw_members.pop()
    elif mutation == "duplicate-url":
        members[1]["url"] = _member_string(members[0], "url")
    elif mutation == "unknown-url":
        members[0]["url"] = "https://www.basiclaw.gov.hk/en/constitution/unknown.html"
    else:
        members[0]["projection_fingerprint"] = "sha256:bad"
    path = tmp_path / "contract.json"
    _write_contract(path, document)
    with pytest.raises(ValueError, match="BASIC_LAW_STRUCTURE_CONTRACT_INVALID"):
        basic_law_authentic.read_basic_law_structure_contract(path)


def test_contract_loader_rejects_duplicate_json_key(tmp_path: Path) -> None:
    raw = _CONTRACT.read_bytes().replace(
        b'{\n  "schema_id":',
        b'{\n  "schema_id": "duplicate",\n  "schema_id":',
        1,
    )
    path = tmp_path / "contract.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="BASIC_LAW_STRUCTURE_CONTRACT_INVALID"):
        basic_law_authentic.read_basic_law_structure_contract(path)
