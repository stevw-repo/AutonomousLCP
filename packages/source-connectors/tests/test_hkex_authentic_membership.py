"""Authentic HKEX catalogue and role-membership traversal contracts."""

from __future__ import annotations

import pytest
from asklegal_source_connectors.hkex_authentic import (
    parse_hkex_catalogue,
    parse_hkex_role_membership,
    reconcile_hkex_role_capture,
    require_hkex_pdf,
)


def test_catalogue_and_forms_membership_bind_every_listed_member_after_entire_section() -> None:
    """Exact role roots bound by the catalogue lead to a complete member traversal plan."""
    catalogue = parse_hkex_catalogue(
        b'<a href="https://en-rules.hkex.com.hk/rulebook/main-board-listing-rules">MB</a>'
        b'<a href="https://en-rules.hkex.com.hk/rulebook/gem-listing-rules">GEM</a>'
        b'<a href="https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms">MF</a>'
        b'<a href="https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms">GF</a>'
        b'<a href="https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules">MFee</a>'
        b'<a href="https://en-rules.hkex.com.hk/rulebook/gem-fees-rules">GFee</a>'
        b'<a href="https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules">MU</a>'
        b'<a href="https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules">GU</a>'
    )
    assert len(catalogue.role_roots) == 8

    membership = parse_hkex_role_membership(
        b'<a href="/entiresection/6189">Entire Section</a>'
        b'<a href="/rulebook/form-a1">Form A1</a>'
        b'<a href="/rulebook/form-a2">Form A2</a>'
        b'<a href="/rulebook/main-board-listing-rules">navigation</a>',
        root_url="https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
        entire_section_url="https://en-rules.hkex.com.hk/entiresection/6189",
    )
    assert membership.member_urls == (
        "https://en-rules.hkex.com.hk/rulebook/form-a1",
        "https://en-rules.hkex.com.hk/rulebook/form-a2",
    )
    complete = reconcile_hkex_role_capture(
        membership, (membership.entire_section_url, *membership.member_urls)
    )
    assert complete.complete
    assert complete.declared_member_count == 2


def test_role_membership_rejects_missing_entire_section_and_truncated_capture() -> None:
    """A role root or traversal without its complete-section/member proof cannot complete."""
    with pytest.raises(ValueError, match="HKEX_ENTIRE_SECTION_MISSING"):
        parse_hkex_role_membership(
            b'<a href="/rulebook/form-a1">Form A1</a>',
            root_url="https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
            entire_section_url="https://en-rules.hkex.com.hk/entiresection/6189",
        )
    membership = parse_hkex_role_membership(
        b'<a href="/entiresection/6189">Entire Section</a><a href="/rulebook/form-a1">Form A1</a>',
        root_url="https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
        entire_section_url="https://en-rules.hkex.com.hk/entiresection/6189",
    )
    with pytest.raises(ValueError, match="HKEX_ROLE_CAPTURE_TRUNCATED"):
        reconcile_hkex_role_capture(membership, (membership.entire_section_url,))


def test_role_capture_rejects_non_pdf_when_prevailing_pdf_is_required() -> None:
    """HTML disguised at the prevailing PDF locator cannot complete the rulebook role."""
    assert require_hkex_pdf(b"%PDF-1.7\nfixture") == 16
    with pytest.raises(ValueError, match="HKEX_PDF_BYTES_INVALID"):
        require_hkex_pdf(b"<html>gateway error</html>")
