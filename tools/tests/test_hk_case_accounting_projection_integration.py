"""Boundary-allowed integration proof for Judiciary accounting projection bytes."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Never, TypeIs

from asklegal_legal_desks.hk_case_authority_graph import build_hk_case_authority_graph
from asklegal_legal_desks.hk_case_records import (
    HKCaseListingWork,
    HKCaseRecordAccountingRequest,
    HKCaseRecordBlockerCode,
    HKCaseReleaseRunKind,
    account_hk_case_records,
)
from asklegal_source_connectors.hk_judiciary import (
    JudiciaryArtifactLocator,
    JudiciaryCourtFamily,
    JudiciaryListingEntry,
    JudiciaryListingExhausted,
    JudiciaryListingPage,
    JudiciaryListingRequest,
    enumerate_judiciary_inventory,
    serialize_judiciary_accounting_projection,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_HELPERS: object = runpy.run_path(
    str(_REPOSITORY_ROOT / "packages/source-connectors/tests/test_hk_judiciary.py")
)


def _helper(name: str) -> object:
    if not _is_object_dict(_SOURCE_HELPERS):
        raise TypeError
    return _SOURCE_HELPERS[name]


def _is_object_dict(value: object) -> TypeIs[dict[str, object]]:
    return type(value) is dict


class _OnePageExchange:
    def __init__(self, page: JudiciaryListingPage) -> None:
        self.page = page

    def fetch_listing_page(
        self, request: JudiciaryListingRequest, page_number: int
    ) -> JudiciaryListingPage | JudiciaryListingExhausted:
        if page_number == 1:
            return self.page
        return JudiciaryListingExhausted.create(request=request, exhausted_after_page=1)

    def fetch_judgment(
        self, entry: JudiciaryListingEntry, artifact: JudiciaryArtifactLocator
    ) -> Never:
        del entry, artifact
        raise AssertionError


def test_actual_issued_inventory_projection_accounts_exactly_one_listing() -> None:
    """The real enumerator-to-Desk byte boundary preserves exact one-row accounting."""
    entry_factory = _helper("_entry")
    page_factory = _helper("_page")
    if not callable(entry_factory) or not callable(page_factory):
        raise TypeError
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    entry = entry_factory(request, "listing-integrated")
    if type(entry) is not JudiciaryListingEntry:
        raise TypeError
    page = page_factory(request, 1, 1, 1, (entry,))
    if type(page) is not JudiciaryListingPage:
        raise TypeError
    inventory = enumerate_judiciary_inventory(_OnePageExchange(page), request)

    result = account_hk_case_records(
        HKCaseRecordAccountingRequest(
            "hk_cases_cfa_2020",
            "CFA",
            2020,
            "2026-08-25T00:00:00Z",
            HKCaseReleaseRunKind.INITIAL,
            None,
        ),
        serialize_judiciary_accounting_projection(inventory),
        (HKCaseListingWork("listing-integrated", None, None, ("gap:artifact",)),),
        build_hk_case_authority_graph((), (), (), "2026-08-25"),
    )

    assert result.inventory_fingerprint == inventory.inventory_fingerprint
    assert result.listing_count == result.disposition_count == 1
    assert tuple(row.listing_id for row in result.listing_accounting) == ("listing-integrated",)
    assert result.blockers == tuple(sorted(HKCaseRecordBlockerCode, key=lambda item: item.value))
