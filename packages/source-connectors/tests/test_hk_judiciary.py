"""Post-1997 Hong Kong Judiciary listing-first contract conformance."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from typing import Never, TypeIs

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_source_connectors import JudiciaryInventory as PublicJudiciaryInventory
from asklegal_source_connectors import validate_judiciary_inventory
from asklegal_source_connectors.hk_judiciary import (
    JudiciaryArtifactClass,
    JudiciaryArtifactLocator,
    JudiciaryArtifactRole,
    JudiciaryCourtFamily,
    JudiciaryLanguage,
    JudiciaryListingEntry,
    JudiciaryListingExhausted,
    JudiciaryListingPage,
    JudiciaryListingRequest,
    JudiciaryObservationKind,
    JudiciaryPageAccounting,
    JudiciarySourceError,
    JudiciarySourceErrorCode,
    enumerate_judiciary_inventory,
    registered_judiciary_observation_contract,
    serialize_judiciary_accounting_projection,
)


def test_registered_observation_contracts_bind_exact_roles_and_endpoints() -> None:
    """Changing an observation to an unregistered endpoint or authority must fail."""
    expected = {
        JudiciaryObservationKind.CURRENT_LIST: (
            "HK-CASE-JUDICIARY-LRS-INVENTORY",
            "sep_000000000000000000000000000000000000000000000202",
            "1.0.0",
            "text/html",
        ),
        JudiciaryObservationKind.RSS: (
            "HK-CASE-JUDICIARY-LRS-INVENTORY",
            "sep_000000000000000000000000000000000000000000000203",
            "1.0.0",
            "application/rss+xml",
        ),
        JudiciaryObservationKind.YEAR_RECONCILIATION: (
            "HK-CASE-JUDICIARY-LRS-INVENTORY",
            "sep_000000000000000000000000000000000000000000000204",
            "1.0.13",
            "text/html",
        ),
        JudiciaryObservationKind.JUDGMENT_ARTIFACT: (
            "HK-CASE-JUDICIARY-JUDGMENT",
            "sep_000000000000000000000000000000000000000000000206",
            "1.0.0",
            "text/html",
        ),
    }

    observed = {
        kind: (
            contract.source_id,
            contract.endpoint_id,
            contract.endpoint_version,
            contract.media_type,
        )
        for kind in expected
        if (contract := registered_judiciary_observation_contract(kind))
    }

    assert observed == expected
    assert all(
        not registered_judiciary_observation_contract(kind).proves_no_change
        for kind in (JudiciaryObservationKind.CURRENT_LIST, JudiciaryObservationKind.RSS)
    )


class _StringLookalike(str):
    """A static-string-compatible value rejected by exact-type source contracts."""

    __slots__ = ()


def _is_object_dict(value: object) -> TypeIs[dict[str, object]]:
    return type(value) is dict


def _serialize_object(value: object) -> object:
    return _invoke_serializer(serialize_judiciary_accounting_projection, value)


def _invoke_serializer(serializer: object, value: object) -> object:
    if not callable(serializer):
        raise TypeError
    return serializer(value)


class _LyingJudgmentSourceId(str):
    """An unregistered value whose equality and hash impersonate the judgment source."""

    __slots__ = ()

    def __hash__(self) -> int:
        return hash("HK-CASE-JUDICIARY-JUDGMENT")

    def __eq__(self, other: object) -> bool:
        return other == "HK-CASE-JUDICIARY-JUDGMENT" or super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class _LyingInventorySourceId(str):
    """An unregistered value whose equality and hash impersonate the inventory source."""

    __slots__ = ()

    def __hash__(self) -> int:
        return hash("HK-CASE-JUDICIARY-LRS-INVENTORY")

    def __eq__(self, other: object) -> bool:
        return other == "HK-CASE-JUDICIARY-LRS-INVENTORY" or super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class ScriptedJudiciaryExchange:
    """Scripted pages whose artifact surface records any accidental invocation."""

    def __init__(self, pages: tuple[JudiciaryListingPage, ...]) -> None:
        """Retain one deterministic sequence of previously constructed pages."""
        self.pages = pages
        self.listing_calls: list[int] = []
        self.artifact_calls = 0

    def fetch_listing_page(
        self, request: JudiciaryListingRequest, page_number: int
    ) -> JudiciaryListingPage | JudiciaryListingExhausted:
        """Return the addressed scripted listing page."""
        self.listing_calls.append(page_number)
        if page_number <= len(self.pages):
            return self.pages[page_number - 1]
        return JudiciaryListingExhausted.create(
            request=request, exhausted_after_page=page_number - 1
        )

    def fetch_judgment(
        self, entry: JudiciaryListingEntry, artifact: JudiciaryArtifactLocator
    ) -> Never:
        """Record forbidden artifact access and stop the scripted exchange."""
        del entry, artifact
        self.artifact_calls += 1
        message = "enumeration must never fetch an addressed artifact"
        raise AssertionError(message)


def test_baseline_freezes_inclusive_handover_boundary_and_canonical_cutoff() -> None:
    """A changed baseline boundary or UTC normalization must fail this contract."""
    request = JudiciaryListingRequest.baseline(
        "2026-08-25T00:00:00+00:00", JudiciaryCourtFamily.CFA
    )

    assert request.earliest_decision_date == "1997-07-01"
    assert request.observation_cutoff == "2026-08-25T00:00:00Z"


def test_enumerator_rejects_an_empty_intermediate_page_as_incomplete() -> None:
    """Removing a page's rows must never turn incomplete inventory into no change."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    exchange = ScriptedJudiciaryExchange(
        (
            _page(request, 1, 3, 3, (_entry(request, "listing-a"),)),
            _page(request, 2, 3, 3, ()),
            _page(request, 3, 3, 3, (_entry(request, "listing-b"),)),
        )
    )

    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(exchange, request)

    assert exchange.listing_calls == [1, 2]
    assert exchange.artifact_calls == 0


def test_baseline_accepts_only_the_four_v1_court_families() -> None:
    """Expanding the ordinary court universe without a scope decision must fail."""
    requests = tuple(
        JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", family)
        for family in JudiciaryCourtFamily
    )

    assert tuple(request.court_family.value for request in requests) == ("CFA", "CA", "CFI", "CT")


def test_handover_date_is_inclusive_but_the_previous_day_is_partition_drift() -> None:
    """Moving the V1 date boundary backward must fail before an inventory is issued."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    included = _entry(request, "listing-handover", decision_date="1997-07-01")
    inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 1, (included,)),)), request
    )
    assert inventory.entries == (included,)

    excluded = _entry(request, "listing-handover", decision_date="1997-06-30")
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PARTITION_INVALID"):
        enumerate_judiciary_inventory(
            ScriptedJudiciaryExchange((_page(request, 1, 1, 1, (excluded,)),)), request
        )


def test_enumerator_rejects_hostile_pagination_drift() -> None:
    """Wrong page numbers, moved totals, duplicates, or truncation must not look complete."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    scenarios = (
        (
            _page(request, 1, 2, 2, (_entry(request, "listing-a"),)),
            _page(request, 3, 2, 2, (_entry(request, "listing-b"),)),
        ),
        (
            _page(request, 1, 2, 2, (_entry(request, "listing-a"),)),
            _page(request, 2, 3, 2, (_entry(request, "listing-b"),)),
        ),
        (
            _page(request, 1, 2, 2, (_entry(request, "listing-a"),)),
            _page(request, 2, 2, 2, (_entry(request, "listing-a"),)),
        ),
        (
            _page(request, 1, 2, 3, (_entry(request, "listing-a"),)),
            _page(request, 2, 2, 3, (_entry(request, "listing-b"),)),
        ),
    )
    for pages in scenarios:
        exchange = ScriptedJudiciaryExchange(pages)
        with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
            enumerate_judiciary_inventory(exchange, request)
        assert exchange.listing_calls == [1, 2]
        assert exchange.artifact_calls == 0


def test_only_a_single_declared_empty_page_can_be_a_complete_empty_partition() -> None:
    """Treating a multi-page empty response as no change would hide a missing listing window."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CA)
    empty = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 0, ()),)), request
    )
    assert empty.entries == ()
    empty.assert_enumerator_issued()

    false_empty = _page(request, 1, 2, 0, ())
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(ScriptedJudiciaryExchange((false_empty,)), request)


def test_missing_declared_page_normalizes_the_exchange_failure_to_incomplete() -> None:
    """A missing second page must not leak a transport exception or appear complete."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CA)
    first = _page(request, 1, 2, 2, (_entry(request, "listing-first-only"),))

    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(ScriptedJudiciaryExchange((first,)), request)


def test_bounds_and_closed_enums_reject_oversized_or_untyped_publisher_values() -> None:
    """Removing bounded exact validation would permit hostile publisher-controlled memory growth."""
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_CONTRACT_INVALID"):
        JudiciaryListingRequest.baseline(
            "2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFI, page_size=501
        )
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFI)
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_CONTRACT_INVALID"):
        _entry(request, "listing-large", case_name="x" * 1_025)


def test_public_factories_normalize_malformed_primitive_values() -> None:
    """Malformed primitive inputs must never leak shared-validator exceptions."""
    with pytest.raises(JudiciarySourceError) as subclass:
        JudiciaryListingRequest.baseline(
            _StringLookalike("2026-08-25T00:00:00Z"), JudiciaryCourtFamily.CFA
        )
    assert subclass.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID

    with pytest.raises(JudiciarySourceError) as whitespace:
        JudiciaryListingRequest.baseline(" ", JudiciaryCourtFamily.CFA)
    assert whitespace.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID

    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    object.__setattr__(request, "observation_cutoff", 123)
    with pytest.raises(JudiciarySourceError) as exhaustion:
        JudiciaryListingExhausted.create(request=request, exhausted_after_page=1)
    assert exhaustion.value.code in {
        JudiciarySourceErrorCode.CONTRACT_INVALID,
        JudiciarySourceErrorCode.PROVENANCE_INVALID,
    }


def test_malformed_nested_fact_and_exchange_page_normalize_to_closed_errors() -> None:
    """Typed-looking but corrupted source objects must not escape as TypeError or ValueError."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    entry = _entry(request, "listing-malformed-nested")
    object.__setattr__(entry.artifacts[0], "official_locator", 123)
    with pytest.raises(JudiciarySourceError) as nested:
        _page(request, 1, 1, 1, (entry,))
    assert nested.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID

    page = _page(request, 1, 1, 1, (_entry(request, "listing-malformed-page"),))
    object.__setattr__(page, "page_identity", 123)
    with pytest.raises(JudiciarySourceError) as exchange:
        enumerate_judiciary_inventory(ScriptedJudiciaryExchange((page,)), request)
    assert exchange.value.code in {
        JudiciarySourceErrorCode.CONTRACT_INVALID,
        JudiciarySourceErrorCode.PROVENANCE_INVALID,
    }


def test_public_factory_rejects_unknown_exact_enum_values_as_contract_invalid() -> None:
    """String lookalikes are not closed Judiciary role or language values."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    artifact = _entry(request, "listing-unknown-enum").artifacts[0]
    object.__setattr__(artifact, "role", JudiciaryLanguage.ENGLISH)
    with pytest.raises(JudiciarySourceError) as raised:
        artifact.__post_init__()

    assert raised.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID


def test_page_accounting_rejects_the_global_entry_ceiling() -> None:
    """Public retained accounting cannot declare more than the inventory-wide bound."""
    with pytest.raises(JudiciarySourceError) as raised:
        JudiciaryPageAccounting(
            page_identity="page-over-ceiling",
            page_number=1,
            page_fingerprint="sha256:" + "0" * 64,
            declared_total_pages=1,
            declared_total_entries=1_000_001,
            member_listing_identities=(),
        )

    assert raised.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID


def test_public_replay_rejects_a_fully_resealed_two_page_empty_inventory() -> None:
    """Only one declared empty listing page can prove a complete empty partition."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CA)
    pages = (
        _page(request, 1, 2, 0, ()),
        _page(request, 2, 2, 0, ()),
    )
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        _reloaded_inventory(request, pages)


def test_public_replay_rejects_a_fully_resealed_page_larger_than_retained_page_size() -> None:
    """A digest-resealed replay cannot hide members the live request would reject."""
    request = JudiciaryListingRequest.baseline(
        "2026-08-25T00:00:00Z", JudiciaryCourtFamily.CA, page_size=2
    )
    pages = (
        _page(
            request,
            1,
            2,
            4,
            (
                _entry(request, "listing-replay-one"),
                _entry(request, "listing-replay-two"),
                _entry(request, "listing-replay-three"),
            ),
        ),
        _page(request, 2, 2, 4, (_entry(request, "listing-replay-four"),)),
    )
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        _reloaded_inventory(request, pages)


@pytest.mark.parametrize(
    ("total_entries", "first_entries"),
    [
        (6, ("listing-unreachable-upper",)),
        (3, ("listing-unreachable-lower-one", "listing-unreachable-lower-two")),
    ],
)
def test_enumerator_rejects_unreachable_remaining_count_before_page_two(
    total_entries: int, first_entries: tuple[str, ...]
) -> None:
    """Remaining mandatory pages must be able to reach the declared member total."""
    request = JudiciaryListingRequest.baseline(
        "2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFI, page_size=2
    )
    exchange = ScriptedJudiciaryExchange(
        (
            _page(
                request,
                1,
                3,
                total_entries,
                tuple(_entry(request, identity) for identity in first_entries),
            ),
        )
    )

    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(exchange, request)

    assert exchange.listing_calls == [1]


def test_malformed_url_and_surrogate_text_normalize_before_public_fingerprinting() -> None:
    """URL and canonical JSON parser failures remain inside the closed source error set."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CT)
    artifact = _entry(request, "listing-invalid-url").artifacts[0]
    object.__setattr__(artifact, "official_locator", "//[::1")
    with pytest.raises(JudiciarySourceError) as url:
        artifact.__post_init__()
    assert url.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID

    with pytest.raises(JudiciarySourceError) as surrogate:
        _entry(request, "listing-surrogate", case_name="case\ud800name")
    assert surrogate.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_id": "HK-CASE-INVENTED-INVENTORY"},
        {"source_profile_version": "invented-profile-v999"},
        {"register_version": "invented-register-v999"},
        {"register_fingerprint": "sha256:" + "a" * 64},
        {
            "source_id": "HK-CASE-INVENTED-INVENTORY",
            "source_profile_version": "invented-profile-v999",
            "register_version": "invented-register-v999",
            "register_fingerprint": "sha256:" + "a" * 64,
        },
    ],
)
def test_public_replay_rejects_each_fully_resealed_invented_source_fact(
    overrides: dict[str, str],
) -> None:
    """Canonical self-declared provenance cannot substitute for the checked-in profile."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)

    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        _reloaded_inventory_with_provenance(request, overrides)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("media_type", "application/\ud800pdf"),
        ("official_locator", "/judgments/\ud800.pdf"),
    ],
)
def test_standalone_artifact_rejects_json_unsafe_text(field: str, value: str) -> None:
    """Artifact leaves must be canonical-safe before any entry wrapper hashes them."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    artifact = _entry(request, "listing-standalone-leaf").artifacts[0]
    object.__setattr__(artifact, field, value)

    with pytest.raises(JudiciarySourceError) as raised:
        artifact.__post_init__()
    assert raised.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID


@pytest.mark.parametrize("proceedings", [(" ",), (" HCAL 1",), ("HCAL 1 ",)])
def test_entry_text_tuple_leaves_reject_blank_or_noncanonical_whitespace(
    proceedings: tuple[str, ...],
) -> None:
    """Proceeding and citation tokens are exact nonblank canonical text, not display strings."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)

    with pytest.raises(JudiciarySourceError) as raised:
        _entry(request, "listing-whitespace-tuple", proceeding_numbers=proceedings)
    assert raised.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID


@pytest.mark.parametrize("field", ["neutral_citations", "reported_citations"])
def test_every_citation_tuple_member_rejects_control_text(field: str) -> None:
    """All citation tuple leaves share the canonical JSON-safe exact-text contract."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    entry = _entry(request, "listing-control-citation")
    object.__setattr__(entry, field, ("citation\x00control",))

    with pytest.raises(JudiciarySourceError) as raised:
        entry.__post_init__()
    assert raised.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID


def test_canonical_text_keeps_valid_chinese_case_name_and_relative_locator() -> None:
    """Canonical safety must not exclude valid multilingual facts or relative locators."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    artifact = _entry(request, "listing-chinese-text").artifacts[0]
    object.__setattr__(artifact, "official_locator", "/判決/中文.pdf")
    artifact.__post_init__()
    entry = _entry(request, "listing-chinese-case", case_name="陳某 訴 律政司司長")

    assert entry.case_name == "陳某 訴 律政司司長"


@pytest.mark.parametrize(
    "source_id",
    [
        [],
        _StringLookalike("HK-CASE-JUDICIARY-JUDGMENT"),
        _LyingJudgmentSourceId("HK-CASE-UNREGISTERED-EVIL"),
    ],
)
def test_artifact_source_id_is_exact_before_membership(source_id: object) -> None:
    """An artifact source ID cannot invoke hashing/equality before exact-text validation."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    artifact = _entry(request, "listing-artifact-source-id").artifacts[0]
    object.__setattr__(artifact, "source_id", source_id)

    with pytest.raises(JudiciarySourceError) as raised:
        artifact.__post_init__()
    assert raised.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID

    entry = _entry(request, "listing-artifact-source-boundary")
    object.__setattr__(entry.artifacts[0], "source_id", source_id)
    exchange = ScriptedJudiciaryExchange((_page_unchecked(request, entry),))
    with pytest.raises(JudiciarySourceError):
        enumerate_judiciary_inventory(exchange, request)
    assert exchange.artifact_calls == 0


@pytest.mark.parametrize(
    "source_id",
    [
        [],
        _StringLookalike("HK-CASE-JUDICIARY-LRS-INVENTORY"),
        _LyingInventorySourceId("HK-CASE-UNREGISTERED-EVIL"),
    ],
)
def test_listing_source_id_is_exact_before_equality_and_no_inventory_issues(
    source_id: object,
) -> None:
    """A forged listing source cannot pass entry, page, or enumerator provenance checks."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    entry = _entry(request, "listing-entry-source-id")
    object.__setattr__(entry, "listing_source_id", source_id)

    with pytest.raises(JudiciarySourceError) as standalone:
        entry.__post_init__()
    assert standalone.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID

    with pytest.raises(JudiciarySourceError) as nested:
        _page(request, 1, 1, 1, (entry,))
    assert nested.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID

    exchange = ScriptedJudiciaryExchange((_page_unchecked(request, entry),))
    with pytest.raises(JudiciarySourceError) as enumerated:
        enumerate_judiciary_inventory(exchange, request)
    assert enumerated.value.code in {
        JudiciarySourceErrorCode.CONTRACT_INVALID,
        JudiciarySourceErrorCode.PROVENANCE_INVALID,
    }
    assert exchange.artifact_calls == 0


def test_inventory_fingerprint_is_stable_across_page_member_order_but_changes_with_facts() -> None:
    """Using response order or ignoring changed listing facts would lose reproducible evidence."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CT)
    first = _entry(request, "listing-a")
    second = _entry(request, "listing-b")
    reversed_inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 2, (second, first)),)), request
    )
    ordered_inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 2, (first, second)),)), request
    )
    changed = _entry(request, "listing-a", case_name="Changed Example v Secretary")
    changed_inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 2, (changed, second)),)), request
    )

    assert tuple(entry.listing_identity for entry in reversed_inventory.entries) == (
        "listing-a",
        "listing-b",
    )
    assert reversed_inventory.inventory_fingerprint == ordered_inventory.inventory_fingerprint
    assert changed_inventory.inventory_fingerprint != ordered_inventory.inventory_fingerprint


def test_issued_inventory_serializes_one_detached_accounting_projection() -> None:
    """The source boundary must bind the real full inventory digest to exact listing facts."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange(
            (_page(request, 1, 1, 1, (_entry(request, "listing-projected"),)),)
        ),
        request,
    )

    projection = serialize_judiciary_accounting_projection(inventory)
    document: object = json.loads(projection)

    assert type(projection) is bytes
    assert _is_object_dict(document)
    assert document["schema_id"] == "asklegal.hk-judiciary-accounting-projection/v1"
    assert document["source_inventory_fingerprint"] == inventory.inventory_fingerprint
    assert document["entries"] == [
        {
            "court_family": "CFA",
            "decision_date": "2020-01-02",
            "listing_fact_fingerprint": inventory.entries[0].listing_fact_fingerprint,
            "listing_identity": "listing-projected",
        }
    ]
    assert str(document["projection_fingerprint"]).startswith("sha256:")


def test_accounting_projection_rejects_hidden_issued_and_exposed_fabricated_facts() -> None:
    """A structural wrapper cannot separate live issuance from its exposed row universe."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    hidden = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 0, ()),)), request
    )
    exposed = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange(
            (_page(request, 1, 1, 1, (_entry(request, "listing-fabricated"),)),)
        ),
        request,
    )

    class _DetachedWrapper:
        def __init__(self) -> None:
            self.entries = exposed.entries
            self.inventory_fingerprint = exposed.inventory_fingerprint
            self.replay_calls = 0

        def __post_init__(self) -> None:
            self.replay_calls += 1
            hidden.__post_init__()

        def assert_enumerator_issued(self) -> None:
            self.replay_calls += 1
            hidden.assert_enumerator_issued()

    wrapper = _DetachedWrapper()
    with pytest.raises(JudiciarySourceError) as rejected:
        _serialize_object(wrapper)

    assert rejected.value.code is JudiciarySourceErrorCode.CONTRACT_INVALID
    assert wrapper.replay_calls == 0


def test_accounting_projection_rejects_permanent_live_inventory_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issuance replay cannot permanently drop a row after the full pre-capture."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 1, (_entry(request, "listing-drift"),)),)),
        request,
    )
    original_assert = PublicJudiciaryInventory.assert_enumerator_issued

    def drop_after_replay(value: PublicJudiciaryInventory) -> None:
        original_assert(value)
        object.__setattr__(value, "entries", ())

    monkeypatch.setattr(PublicJudiciaryInventory, "assert_enumerator_issued", drop_after_replay)
    with pytest.raises(JudiciarySourceError) as rejected:
        serialize_judiciary_accounting_projection(inventory)

    assert rejected.value.code is JudiciarySourceErrorCode.PROVENANCE_INVALID


def test_accounting_projection_transient_a_b_a_cannot_influence_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the complete pre-captured A projection is returned after exact restoration."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 1, (_entry(request, "listing-stable"),)),)),
        request,
    )
    expected = serialize_judiciary_accounting_projection(inventory)
    original_entries = inventory.entries
    original_assert = PublicJudiciaryInventory.assert_enumerator_issued

    def change_and_restore(value: PublicJudiciaryInventory) -> None:
        original_assert(value)
        object.__setattr__(value, "entries", ())
        object.__setattr__(value, "entries", original_entries)

    monkeypatch.setattr(PublicJudiciaryInventory, "assert_enumerator_issued", change_and_restore)

    assert serialize_judiciary_accounting_projection(inventory) == expected


def test_entry_preserves_distinct_artifacts_and_relationships_without_collapsing_them() -> None:
    """Collapsing related Judiciary identities would lose ADR 0048 facts."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    entry = _entry(request, "listing-rich")
    translation = JudiciaryArtifactLocator(
        artifact_identity="artifact-translation",
        listing_identity=entry.listing_identity,
        source_id="HK-CASE-JUDICIARY-TRANSLATION",
        role=JudiciaryArtifactRole.TRANSLATION,
        language=JudiciaryLanguage.TRADITIONAL_CHINESE,
        opinion_or_reasons_identity="opinion-translation",
        media_type="text/html",
        official_locator="/translations/listing-rich.html",
        correction_identity="correction-translation",
        reissue_identity=None,
        replaces_artifact_identity="artifact-prior-translation",
    )
    rich = _entry(
        request,
        entry.listing_identity,
        proceeding_numbers=("CACV 1", "HCAL 2"),
        artifacts=(entry.artifacts[0], translation),
        correction_identities=("correction-current",),
        reissue_identities=("reissue-current",),
        replacement_identities=("replacement-current",),
        translation_listing_identities=("listing-translation",),
    )
    inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 1, (rich,)),)), request
    )

    assert inventory.entries[0].proceeding_numbers == ("CACV 1", "HCAL 2")
    assert tuple(artifact.artifact_identity for artifact in inventory.entries[0].artifacts) == (
        "artifact-listing-rich",
        "artifact-translation",
    )
    assert inventory.entries[0].translation_listing_identities == ("listing-translation",)
    assert inventory.entries[0].correction_identities == ("correction-current",)


def test_page_and_inventory_fingerprints_reject_stale_or_caller_issued_aggregates() -> None:
    """Trusting caller-displayed aggregate fingerprints would allow false completeness claims."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    page = _page(request, 1, 1, 1, (_entry(request, "listing-forged"),))
    object.__setattr__(page, "page_fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        enumerate_judiciary_inventory(ScriptedJudiciaryExchange((page,)), request)

    page = _page(request, 1, 1, 1, (_entry(request, "listing-forged"),))
    inventory = enumerate_judiciary_inventory(ScriptedJudiciaryExchange((page,)), request)
    caller_aggregate = replace(inventory)
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        caller_aggregate.assert_enumerator_issued()

    assert validate_judiciary_inventory(caller_aggregate) is caller_aggregate


def test_inventory_reconstructs_from_retained_fields_without_process_local_issuance() -> None:
    """A durable reload can prove complete request/page/member facts without an object registry."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    issued = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 1, (_entry(request, "listing-reload"),)),)),
        request,
    )
    reloaded = PublicJudiciaryInventory(
        request_fingerprint=issued.request_fingerprint,
        source_id=issued.source_id,
        source_profile_version=issued.source_profile_version,
        register_version=issued.register_version,
        register_fingerprint=issued.register_fingerprint,
        court_family=issued.court_family,
        earliest_decision_date=issued.earliest_decision_date,
        observation_cutoff=issued.observation_cutoff,
        page_size=issued.page_size,
        maximum_pages=issued.maximum_pages,
        page_accounting=issued.page_accounting,
        terminal_exhaustion=issued.terminal_exhaustion,
        entries=issued.entries,
        inventory_fingerprint=issued.inventory_fingerprint,
    )

    assert validate_judiciary_inventory(reloaded) is reloaded
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        reloaded.assert_enumerator_issued()


def test_inventory_rejects_copied_inconsistent_retained_request_and_page_proof() -> None:
    """Copying an aggregate cannot hide a mismatched request or page digest."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 1, (_entry(request, "listing-reseal"),)),)),
        request,
    )
    object.__setattr__(inventory, "court_family", JudiciaryCourtFamily.CA)
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        validate_judiciary_inventory(inventory)

    inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange(
            (_page(request, 1, 1, 1, (_entry(request, "listing-page-reseal"),)),)
        ),
        request,
    )
    object.__setattr__(inventory.page_accounting[0], "page_fingerprint", "sha256:" + "f" * 64)
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        validate_judiciary_inventory(inventory)


def test_enumerator_stops_before_an_avoidable_extra_call_on_count_or_identity_failure() -> None:
    """Contradictory totals and repeated identities are rejected at the first possible fetch."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    contradictory = ScriptedJudiciaryExchange(
        (_page(request, 1, 2, 1, (_entry(request, "listing-contradictory"),)),)
    )
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(contradictory, request)
    assert contradictory.listing_calls == [1]

    first = _page(request, 1, 3, 3, (_entry(request, "listing-one"),))
    duplicate_listing = _page(request, 2, 3, 3, (_entry(request, "listing-one"),))
    duplicate_listing_exchange = ScriptedJudiciaryExchange((first, duplicate_listing))
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(duplicate_listing_exchange, request)
    assert duplicate_listing_exchange.listing_calls == [1, 2]

    duplicate_page = JudiciaryListingPage(
        request_fingerprint=request.request_fingerprint,
        page_identity=first.page_identity,
        page_number=2,
        declared_total_pages=3,
        declared_total_entries=3,
        entries=(_entry(request, "listing-two"),),
    )
    duplicate_page_exchange = ScriptedJudiciaryExchange((first, duplicate_page))
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(duplicate_page_exchange, request)
    assert duplicate_page_exchange.listing_calls == [1, 2]

    overrun = ScriptedJudiciaryExchange(
        (
            _page(
                request,
                1,
                3,
                3,
                (_entry(request, "listing-overrun-one"), _entry(request, "listing-overrun-two")),
            ),
            _page(
                request,
                2,
                3,
                3,
                (_entry(request, "listing-overrun-three"), _entry(request, "listing-overrun-four")),
            ),
        )
    )
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(overrun, request)
    assert overrun.listing_calls == [1]


def test_enumeration_never_calls_the_addressed_artifact_method() -> None:
    """Fetching artifacts during listing enumeration would violate the listing-first boundary."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    exchange = ScriptedJudiciaryExchange(
        (_page(request, 1, 1, 1, (_entry(request, "listing-no-fetch"),)),)
    )

    enumerate_judiciary_inventory(exchange, request)

    assert exchange.listing_calls == [1, 2]
    assert exchange.artifact_calls == 0


def test_enumerator_rejects_same_object_page_and_nested_artifact_mutation() -> None:
    """Trusting a stale displayed page digest would allow changed artifact facts into inventory."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    page = _page(request, 1, 1, 1, (_entry(request, "listing-mutated-page"),))
    object.__setattr__(page.entries[0].artifacts[0], "official_locator", "/judgments/changed.pdf")

    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        enumerate_judiciary_inventory(ScriptedJudiciaryExchange((page,)), request)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_id", "HK-CASE-JUDICIARY-TRANSLATION"),
        ("official_locator", "https://example.invalid/judgment.pdf"),
        ("language", JudiciaryLanguage.TRADITIONAL_CHINESE),
    ],
)
def test_page_rejects_mutated_artifact_role_locator_or_language_linkage(
    field: str, value: object
) -> None:
    """Relabelling a translation or invalid locator as an original must fail closed."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    entry = _entry(request, "listing-artifact-linkage")
    object.__setattr__(entry.artifacts[0], field, value)

    with pytest.raises(JudiciarySourceError):
        _page(request, 1, 1, 1, (entry,))


def test_enumerator_rejects_same_object_request_mutation_with_stale_digest() -> None:
    """A changed request partition must not retain its prior CFA request fingerprint."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    object.__setattr__(request, "court_family", JudiciaryCourtFamily.CA)
    page = _page(request, 1, 1, 1, (_entry(request, "listing-mutated-request"),))

    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        enumerate_judiciary_inventory(ScriptedJudiciaryExchange((page,)), request)


def test_exhaustion_probe_rejects_an_undeclared_extra_page_and_bad_terminal_signal() -> None:
    """A publisher page after declared exhaustion must never be ignored as an extra tuple member."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    first = _page(request, 1, 1, 1, (_entry(request, "listing-first"),))
    extra = _page(request, 2, 1, 1, (_entry(request, "listing-extra"),))
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(ScriptedJudiciaryExchange((first, extra)), request)

    bad_terminal = _BadTerminalExchange(first)
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(bad_terminal, request)


def test_inventory_preserves_canonical_full_page_accounting() -> None:
    """Dropping canonical page proof would make completeness unauditable."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    page = _page(request, 1, 1, 1, (_entry(request, "listing-accounted"),))
    inventory = enumerate_judiciary_inventory(ScriptedJudiciaryExchange((page,)), request)

    assert inventory.page_accounting[0].page_number == 1
    assert inventory.page_accounting[0].page_fingerprint == page.page_fingerprint
    assert inventory.page_accounting[0].member_listing_identities == ("listing-accounted",)


def test_public_inventory_consumer_rejects_a_same_object_forged_inventory_digest() -> None:
    """A changed displayed inventory digest must not pass an issued completeness consumer."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange((_page(request, 1, 1, 1, (_entry(request, "listing-digest"),)),)),
        request,
    )
    object.__setattr__(inventory, "inventory_fingerprint", "sha256:" + "0" * 64)

    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        validate_judiciary_inventory(inventory)


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("source_id", _StringLookalike("HK-CASE-JUDICIARY-JUDGMENT")),
        ("artifact_role", "ORIGINAL"),
    ],
)
def test_issued_inventory_assertion_recursively_rejects_nested_nonexact_facts(
    mutation: str, value: object
) -> None:
    """The optional live issuance assertion must not fingerprint malformed nested state."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    inventory = enumerate_judiciary_inventory(
        ScriptedJudiciaryExchange(
            (_page(request, 1, 1, 1, (_entry(request, "listing-issued-nested"),)),)
        ),
        request,
    )
    target = inventory.entries[0].artifacts[0] if mutation == "source_id" else inventory.entries[0]
    object.__setattr__(target, mutation, value)

    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        inventory.assert_enumerator_issued()


def test_enumerator_detects_request_or_accepted_page_mutation_during_exchange() -> None:
    """A transport that mutates already-validated facts must not win a time-of-check race."""
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    first = _page(request, 1, 1, 1, (_entry(request, "listing-race-request"),))
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        enumerate_judiciary_inventory(_MutatingRequestExchange(first), request)

    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00Z", JudiciaryCourtFamily.CFA)
    first = _page(request, 1, 1, 1, (_entry(request, "listing-race-page"),))
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_PROVENANCE_INVALID"):
        enumerate_judiciary_inventory(_MutatingPageExchange(first), request)


class _BadTerminalExchange:
    """Returns a terminal marker for the wrong page after an otherwise valid first page."""

    def __init__(self, first: JudiciaryListingPage) -> None:
        """Retain the only declared page."""
        self.first = first

    def fetch_listing_page(
        self, request: JudiciaryListingRequest, page_number: int
    ) -> JudiciaryListingPage | JudiciaryListingExhausted:
        """Return page one then an explicitly contradictory terminal signal."""
        if page_number == 1:
            return self.first
        return JudiciaryListingExhausted.create(request=request, exhausted_after_page=2)

    def fetch_judgment(
        self, entry: JudiciaryListingEntry, artifact: JudiciaryArtifactLocator
    ) -> Never:
        """Prevent forbidden artifact fetching during enumeration."""
        del entry, artifact
        message = "enumeration must never fetch an addressed artifact"
        raise AssertionError(message)


class _MutatingRequestExchange(_BadTerminalExchange):
    """Mutates the caller request during the first page fetch."""

    def fetch_listing_page(
        self, request: JudiciaryListingRequest, page_number: int
    ) -> JudiciaryListingPage | JudiciaryListingExhausted:
        """Alter the request after the enumerator has captured its first snapshot."""
        if page_number == 1:
            object.__setattr__(request, "court_family", JudiciaryCourtFamily.CA)
            return self.first
        return JudiciaryListingExhausted.create(request=request, exhausted_after_page=1)


class _MutatingPageExchange(_BadTerminalExchange):
    """Mutates page one during the bounded exhaustion probe."""

    def fetch_listing_page(
        self, request: JudiciaryListingRequest, page_number: int
    ) -> JudiciaryListingPage | JudiciaryListingExhausted:
        """Return page one then alter it before supplying the terminal signal."""
        if page_number == 1:
            return self.first
        object.__setattr__(self.first.entries[0], "case_name", "Changed during terminal probe")
        return JudiciaryListingExhausted.create(request=request, exhausted_after_page=1)


def test_task_four_inventory_type_is_exported_from_the_source_connector_boundary() -> None:
    """Removing the package export would make the public source-neutral contract unavailable."""
    assert PublicJudiciaryInventory.__name__ == "JudiciaryInventory"


def _entry(
    request: JudiciaryListingRequest,
    listing_identity: str,
    *,
    case_name: str = "Example v Secretary",
    decision_date: str = "2020-01-02",
    proceeding_numbers: tuple[str, ...] | None = None,
    artifacts: tuple[JudiciaryArtifactLocator, ...] | None = None,
    correction_identities: tuple[str, ...] = (),
    reissue_identities: tuple[str, ...] = (),
    replacement_identities: tuple[str, ...] = (),
    translation_listing_identities: tuple[str, ...] = (),
) -> JudiciaryListingEntry:
    artifact = JudiciaryArtifactLocator(
        artifact_identity=f"artifact-{listing_identity}",
        listing_identity=listing_identity,
        source_id="HK-CASE-JUDICIARY-JUDGMENT",
        role=JudiciaryArtifactRole.ORIGINAL,
        language=JudiciaryLanguage.ENGLISH,
        opinion_or_reasons_identity=f"opinion-{listing_identity}",
        media_type="application/pdf",
        official_locator=f"/judgments/{listing_identity}.pdf",
        correction_identity=None,
        reissue_identity=None,
        replaces_artifact_identity=None,
    )
    final_artifacts = artifacts or (artifact,)
    return JudiciaryListingEntry(
        listing_identity=listing_identity,
        case_name=case_name,
        proceeding_numbers=proceeding_numbers or (f"HCAL {listing_identity}",),
        neutral_citations=(f"[2020] HKCFA {listing_identity[-1].upper()}",),
        reported_citations=(),
        court_family=request.court_family,
        decision_date=decision_date,
        language=JudiciaryLanguage.ENGLISH,
        artifact_class=JudiciaryArtifactClass.JUDGMENT,
        artifact_role=JudiciaryArtifactRole.ORIGINAL,
        opinion_or_reasons_identities=tuple(
            sorted({item.opinion_or_reasons_identity for item in final_artifacts})
        ),
        artifacts=final_artifacts,
        correction_identities=correction_identities,
        reissue_identities=reissue_identities,
        replacement_identities=replacement_identities,
        translation_listing_identities=translation_listing_identities,
        listing_source_id=request.source_id,
        listing_source_profile_version=request.source_profile_version,
        listing_register_version=request.register_version,
        listing_register_fingerprint=request.register_fingerprint,
        listing_observed_at=request.observation_cutoff,
    )


def test_listing_entry_preserves_every_relationship_as_typed_durable_work_identity() -> None:
    """Dropping a source relationship would make a discovered correction or alias invisible."""
    request = JudiciaryListingRequest.baseline("2026-09-06T00:00:00Z", JudiciaryCourtFamily.CFA)
    entry = _entry(
        request,
        "listing-current",
        correction_identities=("correction-current",),
        reissue_identities=("reissue-current",),
        replacement_identities=("replacement-current",),
        translation_listing_identities=("translation-current",),
    )

    assert entry.relationship_work_identities == (
        "artifact-listing-current",
        "correction-current",
        "opinion-listing-current",
        "proceeding:HCAL listing-current",
        "reissue-current",
        "replacement-current",
        "translation-current",
    )


def _page(
    request: JudiciaryListingRequest,
    page_number: int,
    total_pages: int,
    total_entries: int,
    entries: tuple[JudiciaryListingEntry, ...],
) -> JudiciaryListingPage:
    return JudiciaryListingPage(
        request_fingerprint=request.request_fingerprint,
        page_identity=f"page-{page_number}",
        page_number=page_number,
        declared_total_pages=total_pages,
        declared_total_entries=total_entries,
        entries=entries,
    )


def _page_unchecked(
    request: JudiciaryListingRequest, entry: JudiciaryListingEntry
) -> JudiciaryListingPage:
    """Return a source-shaped page whose post-init must perform the public rejection."""
    page = _page(request, 1, 1, 1, (_entry(request, "listing-page-unchecked"),))
    object.__setattr__(page, "entries", (entry,))
    object.__setattr__(page, "page_fingerprint", "")
    return page


def _reloaded_inventory(
    request: JudiciaryListingRequest, pages: tuple[JudiciaryListingPage, ...]
) -> PublicJudiciaryInventory:
    """Construct a serialization-shaped aggregate with every displayed digest resealed."""
    entries = tuple(
        sorted(
            (entry for page in pages for entry in page.entries),
            key=lambda entry: entry.listing_identity,
        )
    )
    accounting = tuple(
        JudiciaryPageAccounting(
            page_identity=page.page_identity,
            page_number=page.page_number,
            page_fingerprint=page.page_fingerprint,
            declared_total_pages=page.declared_total_pages,
            declared_total_entries=page.declared_total_entries,
            member_listing_identities=tuple(
                sorted(entry.listing_identity for entry in page.entries)
            ),
        )
        for page in pages
    )
    terminal = JudiciaryListingExhausted.create(request=request, exhausted_after_page=len(pages))
    payload = {
        "entries": [_entry_payload(entry) for entry in entries],
        "page_accounting": [
            {
                "declared_total_entries": page.declared_total_entries,
                "declared_total_pages": page.declared_total_pages,
                "member_listing_identities": list(page.member_listing_identities),
                "page_fingerprint": page.page_fingerprint,
                "page_identity": page.page_identity,
                "page_number": page.page_number,
            }
            for page in accounting
        ],
        "court_family": request.court_family.value,
        "earliest_decision_date": request.earliest_decision_date,
        "observation_cutoff": request.observation_cutoff,
        "page_size": request.page_size,
        "maximum_pages": request.maximum_pages,
        "register_fingerprint": request.register_fingerprint,
        "register_version": request.register_version,
        "request_fingerprint": request.request_fingerprint,
        "source_id": request.source_id,
        "source_profile_version": request.source_profile_version,
        "terminal_exhaustion": {
            "exhausted_after_page": terminal.exhausted_after_page,
            "exhaustion_fingerprint": terminal.exhaustion_fingerprint,
            "request_fingerprint": terminal.request_fingerprint,
        },
    }
    return PublicJudiciaryInventory(
        request_fingerprint=request.request_fingerprint,
        source_id=request.source_id,
        source_profile_version=request.source_profile_version,
        register_version=request.register_version,
        register_fingerprint=request.register_fingerprint,
        court_family=request.court_family,
        earliest_decision_date=request.earliest_decision_date,
        observation_cutoff=request.observation_cutoff,
        page_size=request.page_size,
        maximum_pages=request.maximum_pages,
        page_accounting=accounting,
        terminal_exhaustion=terminal,
        entries=entries,
        inventory_fingerprint=_fingerprint(payload),
    )


def _reloaded_inventory_with_provenance(
    request: JudiciaryListingRequest, overrides: dict[str, str]
) -> PublicJudiciaryInventory:
    """Reseal a one-page durable aggregate after replacing all retained source facts."""
    source_id = overrides.get("source_id", request.source_id)
    source_profile_version = overrides.get("source_profile_version", request.source_profile_version)
    register_version = overrides.get("register_version", request.register_version)
    register_fingerprint = overrides.get("register_fingerprint", request.register_fingerprint)
    request_fingerprint = _fingerprint(
        {
            "court_family": request.court_family.value,
            "earliest_decision_date": request.earliest_decision_date,
            "maximum_pages": request.maximum_pages,
            "observation_cutoff": request.observation_cutoff,
            "page_size": request.page_size,
            "register_fingerprint": register_fingerprint,
            "register_version": register_version,
            "source_id": source_id,
            "source_profile_version": source_profile_version,
        }
    )
    original = _entry(request, "listing-invented-provenance")
    entry = replace(
        original,
        listing_source_profile_version=source_profile_version,
        listing_register_version=register_version,
        listing_register_fingerprint=register_fingerprint,
    )
    page = JudiciaryListingPage(
        request_fingerprint=request_fingerprint,
        page_identity="page-invented-provenance",
        page_number=1,
        declared_total_pages=1,
        declared_total_entries=1,
        entries=(entry,),
    )
    accounting = (
        JudiciaryPageAccounting(
            page_identity=page.page_identity,
            page_number=page.page_number,
            page_fingerprint=page.page_fingerprint,
            declared_total_pages=page.declared_total_pages,
            declared_total_entries=page.declared_total_entries,
            member_listing_identities=(entry.listing_identity,),
        ),
    )
    terminal = JudiciaryListingExhausted(
        request_fingerprint=request_fingerprint,
        exhausted_after_page=1,
        exhaustion_fingerprint=_fingerprint(
            {"exhausted_after_page": 1, "request_fingerprint": request_fingerprint}
        ),
    )
    payload = {
        "entries": [_entry_payload(entry)],
        "page_accounting": [
            {
                "declared_total_entries": 1,
                "declared_total_pages": 1,
                "member_listing_identities": [entry.listing_identity],
                "page_fingerprint": page.page_fingerprint,
                "page_identity": page.page_identity,
                "page_number": 1,
            }
        ],
        "court_family": request.court_family.value,
        "earliest_decision_date": request.earliest_decision_date,
        "observation_cutoff": request.observation_cutoff,
        "page_size": request.page_size,
        "maximum_pages": request.maximum_pages,
        "register_fingerprint": register_fingerprint,
        "register_version": register_version,
        "request_fingerprint": request_fingerprint,
        "source_id": source_id,
        "source_profile_version": source_profile_version,
        "terminal_exhaustion": {
            "exhausted_after_page": 1,
            "exhaustion_fingerprint": terminal.exhaustion_fingerprint,
            "request_fingerprint": request_fingerprint,
        },
    }
    return PublicJudiciaryInventory(
        request_fingerprint=request_fingerprint,
        source_id=source_id,
        source_profile_version=source_profile_version,
        register_version=register_version,
        register_fingerprint=register_fingerprint,
        court_family=request.court_family,
        earliest_decision_date=request.earliest_decision_date,
        observation_cutoff=request.observation_cutoff,
        page_size=request.page_size,
        maximum_pages=request.maximum_pages,
        page_accounting=accounting,
        terminal_exhaustion=terminal,
        entries=(entry,),
        inventory_fingerprint=_fingerprint(payload),
    )


def _entry_payload(entry: JudiciaryListingEntry) -> dict[str, object]:
    """Mirror the documented primitive persistence shape, never its displayed digest."""
    return {
        "artifact_class": entry.artifact_class.value,
        "artifact_role": entry.artifact_role.value,
        "artifacts": [
            {
                "artifact_identity": artifact.artifact_identity,
                "correction_identity": artifact.correction_identity,
                "language": artifact.language.value,
                "listing_identity": artifact.listing_identity,
                "media_type": artifact.media_type,
                "opinion_or_reasons_identity": artifact.opinion_or_reasons_identity,
                "official_locator": artifact.official_locator,
                "replaces_artifact_identity": artifact.replaces_artifact_identity,
                "reissue_identity": artifact.reissue_identity,
                "role": artifact.role.value,
                "source_id": artifact.source_id,
            }
            for artifact in entry.artifacts
        ],
        "case_name": entry.case_name,
        "correction_identities": list(entry.correction_identities),
        "court_family": entry.court_family.value,
        "decision_date": entry.decision_date,
        "language": entry.language.value,
        "listing_identity": entry.listing_identity,
        "listing_observed_at": entry.listing_observed_at,
        "listing_register_fingerprint": entry.listing_register_fingerprint,
        "listing_register_version": entry.listing_register_version,
        "listing_source_id": entry.listing_source_id,
        "listing_source_profile_version": entry.listing_source_profile_version,
        "neutral_citations": list(entry.neutral_citations),
        "opinion_or_reasons_identities": list(entry.opinion_or_reasons_identities),
        "proceeding_numbers": list(entry.proceeding_numbers),
        "reissue_identities": list(entry.reissue_identities),
        "replacement_identities": list(entry.replacement_identities),
        "reported_citations": list(entry.reported_citations),
        "translation_listing_identities": list(entry.translation_listing_identities),
    }


def _fingerprint(value: object) -> str:
    """Calculate the persisted digest with the repository canonical codec."""
    return f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"
