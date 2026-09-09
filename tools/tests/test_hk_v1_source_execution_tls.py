"""Narrow no-network proof for the HKEX urllib TLS-chain composition."""

from __future__ import annotations

import hashlib
import os
import ssl
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

import tools.hk_v1_source_execution as execution

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_HKEX_INTERMEDIATE = _REPOSITORY_ROOT / "tools/hkex-sectigo-r36.pem"
_HKEX_URL = "https://en-rules.hkex.com.hk/rulebook/main-board-listing-rules"
_RESOURCE_FAILURE = "HKEX_TLS_INTERMEDIATE_INVALID"
_UNRELATED_RESOURCE_ACCESS = "unrelated transport accessed HKEX trust resource"
_UNREADABLE_RESOURCE = "test-only denied resource"
_LATER_OPENER_FAILURE = "LATER_OPENER_FAILURE"


def _empty_cadata() -> list[str]:
    """Return one typed recorder list for a fake SSL context."""
    return []


@dataclass
class _RecordingSslContext:
    """Record the one trust addition while exposing secure context policy."""

    check_hostname: bool = True
    verify_mode: ssl.VerifyMode = ssl.CERT_REQUIRED
    cadata: list[str] = field(default_factory=_empty_cadata)

    def load_verify_locations(self, *, cadata: str) -> None:
        """Record the pinned repository certificate passed to OpenSSL."""
        self.cadata.append(cadata)


def _empty_opener(*_handlers: object) -> urllib.request.OpenerDirector:
    """Return a director without installing handlers or reaching a network."""
    return urllib.request.OpenerDirector()


def test_registered_hkex_transport_builds_explicit_verified_https_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing HKEX's explicit default-root context must break composition."""
    contexts: list[_RecordingSslContext] = []
    handlers: list[object] = []

    def create_default_context() -> ssl.SSLContext:
        context = _RecordingSslContext()
        contexts.append(context)
        return cast("ssl.SSLContext", context)

    def build_opener(*items: object) -> urllib.request.OpenerDirector:
        handlers.extend(items)
        return urllib.request.OpenerDirector()

    monkeypatch.setattr(ssl, "create_default_context", create_default_context)
    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

    execution.UrllibReadOnlyTransport(allowed_redirect_urls=frozenset({_HKEX_URL}))

    assert len(contexts) == 1
    context = contexts[0]
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.cadata == [_HKEX_INTERMEDIATE.read_text(encoding="ascii")]
    assert any(
        isinstance(handler, urllib.request.HTTPSHandler)
        and getattr(handler, "_context", None) is context
        for handler in handlers
    )


def test_repository_hkex_intermediate_is_the_exact_verified_resource() -> None:
    """Any resource-byte drift must break the independently pinned fixture contract."""
    data = _HKEX_INTERMEDIATE.read_bytes()

    assert len(data) == 2244
    assert (
        hashlib.sha256(data).hexdigest()
        == "505ca50c3930cedca888c4e1ebb0747cb485498547b60ea6bcd23cf78766aeeb"
    )
    assert data.decode("ascii", errors="strict").startswith("-----BEGIN CERTIFICATE-----\n")


@pytest.mark.parametrize(
    "allowed_urls",
    [
        frozenset[str](),
        frozenset({"https://legalref.judiciary.hk/lrs/common/index.jsp"}),
        frozenset({"https://www.elegislation.gov.hk/terms"}),
        frozenset({"https://www.gld.gov.hk/egazette/"}),
        frozenset({"https://www.hkex.com.hk/Listing/Rules-and-Resources/Listing-Rules"}),
        frozenset({"http://en-rules.hkex.com.hk/rulebook/main-board-listing-rules"}),
        frozenset({"https://en-rules.hkex.com.hk:444/rulebook/main-board-listing-rules"}),
        frozenset({"https://en-rules.hkex.com.hk:0/rulebook/main-board-listing-rules"}),
        frozenset({"https://en-rules.hkex.com.hk:/rulebook/main-board-listing-rules"}),
        frozenset({"https://EN-RULES.HKEX.COM.HK/rulebook/main-board-listing-rules"}),
        frozenset({"https://user@en-rules.hkex.com.hk/rulebook/main-board-listing-rules"}),
        frozenset({"https://en-rules.hkex.com.hk:not-a-port/rulebook"}),
        frozenset({"ht\ttps://en-rules.hkex.com.hk/rulebook"}),
        frozenset({"https\n://en-rules.hkex.com.hk/rulebook"}),
        frozenset({" https://en-rules.hkex.com.hk/rulebook"}),
        frozenset({"https://\ten-rules.hkex.com.hk/rulebook"}),
        frozenset({"https://en-rules.hkex.com.\thk/rulebook"}),
        frozenset({"https://en-rules.hkex.com.\rhk/rulebook"}),
        frozenset({"https://en-rules.hkex.com.\nhk/rulebook"}),
        frozenset({"https://en-rules.hkex.com.hk\t/rulebook"}),
        frozenset({"https://en-rules.hkex.com.hk/rule book"}),
        frozenset({"https://en-rules.hkex.com.hk/rulebook\x00"}),
        frozenset({"https://en-rules.hkex.com.hk/rulebook\x7f"}),
        frozenset({"https://en-rules.hkex.com.hk/rulebook\u00a0"}),
    ],
)
def test_non_hkex_443_allowed_sets_never_access_the_pinned_resource(
    allowed_urls: frozenset[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unrelated, malformed, empty, wrong-scheme, and wrong-port sets keep default urllib TLS."""

    def forbidden_resource_access(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(_UNRELATED_RESOURCE_ACCESS)

    monkeypatch.setattr(Path, "read_bytes", forbidden_resource_access)
    monkeypatch.setattr(os, "open", forbidden_resource_access)
    monkeypatch.setattr(ssl, "create_default_context", forbidden_resource_access)
    monkeypatch.setattr(urllib.request, "build_opener", _empty_opener)

    execution.UrllibReadOnlyTransport(allowed_redirect_urls=allowed_urls)


@pytest.mark.parametrize(
    "allowed_url",
    [
        _HKEX_URL,
        "https://en-rules.hkex.com.hk:443/rulebook/main-board-listing-rules",
    ],
)
def test_exact_hkex_443_forms_load_the_pinned_resource(
    allowed_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both implicit and explicit standard HTTPS ports select the exact HKEX trust addition."""
    context = _RecordingSslContext()
    monkeypatch.setattr(
        ssl,
        "create_default_context",
        lambda: cast("ssl.SSLContext", context),
    )
    monkeypatch.setattr(urllib.request, "build_opener", _empty_opener)

    execution.UrllibReadOnlyTransport(allowed_redirect_urls=frozenset({allowed_url}))

    assert context.cadata == [_HKEX_INTERMEDIATE.read_text(encoding="ascii")]


def _write_mutated_resource(*, target: Path, mutation: str, canonical: bytes) -> None:
    """Build one controlled resource state without changing repository bytes."""
    if mutation == "symlink":
        target.symlink_to(_HKEX_INTERMEDIATE)
        return
    if mutation == "non_regular":
        target.mkdir()
        return
    if mutation == "missing":
        return
    data = bytearray(canonical)
    if mutation == "non_ascii":
        data[0] = 0xFF
    elif mutation == "length":
        data.append(ord("x"))
    elif mutation == "hash":
        offset = data.index(b"MIIG")
        data[offset] = ord("N")
    target.write_bytes(data)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "symlink", "non_regular", "unreadable", "non_ascii", "length", "hash"],
)
def test_hkex_resource_mutation_fails_closed_before_opener(
    mutation: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every untrusted resource state returns one stable code before opener construction."""
    target = tmp_path / "hkex-intermediate.pem"
    canonical = _HKEX_INTERMEDIATE.read_bytes()
    _write_mutated_resource(target=target, mutation=mutation, canonical=canonical)

    if mutation == "unreadable":
        real_open = os.open

        def denied_open(path: str | os.PathLike[str], flags: int) -> int:
            if Path(path) == target:
                raise PermissionError(_UNREADABLE_RESOURCE)
            return real_open(path, flags)

        monkeypatch.setattr(os, "open", denied_open)

    opener_calls: list[tuple[object, ...]] = []

    def build_opener(*handlers: object) -> urllib.request.OpenerDirector:
        opener_calls.append(handlers)
        return urllib.request.OpenerDirector()

    monkeypatch.setattr(execution, "_HKEX_TLS_INTERMEDIATE_PATH", target)
    monkeypatch.setattr(urllib.request, "build_opener", build_opener)

    with pytest.raises(ValueError, match=f"^{_RESOURCE_FAILURE}$"):
        execution.UrllibReadOnlyTransport(allowed_redirect_urls=frozenset({_HKEX_URL}))

    assert opener_calls == []


def test_post_resource_opener_error_is_not_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An error after verified resource loading remains the original execution error."""
    context = _RecordingSslContext()

    def later_failure(*_handlers: object) -> urllib.request.OpenerDirector:
        raise RuntimeError(_LATER_OPENER_FAILURE)

    monkeypatch.setattr(
        ssl,
        "create_default_context",
        lambda: cast("ssl.SSLContext", context),
    )
    monkeypatch.setattr(urllib.request, "build_opener", later_failure)

    with pytest.raises(RuntimeError, match=r"^LATER_OPENER_FAILURE$"):
        execution.UrllibReadOnlyTransport(allowed_redirect_urls=frozenset({_HKEX_URL}))

    assert context.cadata == [_HKEX_INTERMEDIATE.read_text(encoding="ascii")]
