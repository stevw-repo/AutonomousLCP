"""Local-only HKEX source-observation inventory contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_source_connectors import (
    HKEX_REGULATORY_SOURCE_IDS as ROOT_SOURCE_IDS,
)
from asklegal_source_connectors import (
    load_hk_regulatory_source_register as root_load_hk_regulatory_source_register,
)
from asklegal_source_connectors.hk_regulatory_official import (
    HKEX_REGULATORY_SOURCE_IDS,
    HKEXObservedSourceEntry,
    HKEXPublisherBoard,
    HKEXSourceInventory,
    HKEXSourceObjectKind,
    HKEXSourceProfile,
    HKEXSourceTerminal,
    HKEXTerminalCode,
    OfficialSourceState,
    PublisherRightsState,
    build_hkex_source_inventory,
    load_hk_regulatory_source_register,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REGISTER_PATH = (
    REPOSITORY_ROOT
    / "packages/source-connectors/src/asklegal_source_connectors/hk_regulatory_source_register.json"
)
LEGAL_DESK_SOURCE_IDS = (
    "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
    "HK-REG-HKEX-FEES-RULES",
    "HK-REG-HKEX-REGULATORY-FORMS",
    "HK-REG-HKEX-RULE-UPDATES",
    "HK-REG-HKEX-RULEBOOK-CATALOGUE",
)


def _complete_zero_inventory() -> HKEXSourceInventory:
    """Build one exact terminal observation with an explicitly empty declared universe."""
    terminals = tuple(
        HKEXSourceTerminal.complete(
            source_id=source_id,
            board=board,
            observed_at="2026-08-26T00:00:00Z",
            declared_member_count=0,
        )
        for source_id in HKEX_REGULATORY_SOURCE_IDS
        for board in HKEXPublisherBoard
    )
    return build_hkex_source_inventory(
        observation_cutoff="2026-08-26T00:00:00Z", terminals=terminals, entries=()
    )


def _entry_with_locator(locator: str) -> HKEXObservedSourceEntry:
    """Construct one source observation to exercise the public locator boundary."""
    return HKEXObservedSourceEntry.create(
        "observation-locator",
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        HKEXPublisherBoard.MAIN,
        "product-locator",
        HKEXSourceObjectKind.RULE,
        locator,
        "sha256:" + "a" * 64,
        1,
        None,
        0,
    )


def test_hkex_source_contract_module_is_public() -> None:
    """The five-role source boundary has a dedicated public connector module."""
    assert HKEX_REGULATORY_SOURCE_IDS == (
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "HK-REG-HKEX-FEES-RULES",
        "HK-REG-HKEX-REGULATORY-FORMS",
        "HK-REG-HKEX-RULE-UPDATES",
        "HK-REG-HKEX-RULEBOOK-CATALOGUE",
    )


def test_register_is_exactly_five_role_and_partial_fail_visible() -> None:
    """The checked-in source boundary preserves exact, incomplete live access."""
    register = load_hk_regulatory_source_register()

    assert tuple(source.source_id for source in register.sources) == HKEX_REGULATORY_SOURCE_IDS
    assert register.register_version == "2026-09-01.2"
    assert len(register.endpoints) == 20
    assert not register.operationally_admitted
    assert all(
        source.endpoint_ids
        and source.rights_state is PublisherRightsState.USER_ATTESTED_PERMISSION_DOCUMENT_PENDING
        and source.operational_state is OfficialSourceState.PARTIALLY_CONFIGURED
        and source.source_policy_owner == "HK_REGULATORY_MATERIALS_LEGAL_DESK"
        for source in register.sources
    )
    with pytest.raises(ValueError, match="profile provenance"):
        replace(register.sources[0], source_policy_owner="UNTRUSTED_OWNER")


def test_user_attested_authority_binds_exact_hkex_role_endpoints() -> None:
    """Task 7 binds each required role to the publisher routes observed live."""
    register = load_hk_regulatory_source_register()

    assert all(
        source.rights_state is PublisherRightsState.USER_ATTESTED_PERMISSION_DOCUMENT_PENDING
        and source.operational_state is OfficialSourceState.PARTIALLY_CONFIGURED
        and source.endpoint_ids
        for source in register.sources
    )
    endpoints = {endpoint.name: endpoint for endpoint in register.endpoints}
    assert endpoints["HKEX_LISTING_RULES_CATALOGUE"].url == (
        "https://www.hkex.com.hk/Listing/Rules-and-Resources/Listing-Rules?sc_lang=en"
    )
    assert endpoints["HKEX_MAIN_BOARD_RULEBOOK"].url == (
        "https://en-rules.hkex.com.hk/rulebook/main-board-listing-rules"
    )
    assert endpoints["HKEX_GEM_RULE_UPDATES"].url == (
        "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules"
    )
    assert endpoints["HKEX_MAIN_REGULATORY_FORMS_ENTIRE_SECTION"].url == (
        "https://en-rules.hkex.com.hk/entiresection/6190"
    )
    assert endpoints["HKEX_GEM_REGULATORY_FORMS_ENTIRE_SECTION"].url == (
        "https://en-rules.hkex.com.hk/entiresection/6191"
    )
    assert endpoints["HKEX_MAIN_FEES_RULES_ENTIRE_SECTION"].url == (
        "https://en-rules.hkex.com.hk/entiresection/3783"
    )
    assert endpoints["HKEX_GEM_FEES_RULES_ENTIRE_SECTION"].url == (
        "https://en-rules.hkex.com.hk/entiresection/1836"
    )
    profiles = {source.source_id: source for source in register.sources}
    assert profiles["HK-REG-HKEX-FEES-RULES"].version == "2.0.0"
    assert profiles["HK-REG-HKEX-REGULATORY-FORMS"].version == "2.0.0"
    assert profiles["HK-REG-HKEX-RULE-UPDATES"].version == "2.0.0"
    assert endpoints["HKEX_MAIN_BOARD_ENTIRE_RULEBOOK"].url == (
        "https://en-rules.hkex.com.hk/entiresection/1932"
    )
    assert endpoints["HKEX_MAIN_BOARD_PREVAILING_PDF"].url.endswith("/consol_mb.pdf")
    assert endpoints["HKEX_GEM_PREVAILING_PDF"].url.endswith("/consol_gem.pdf")
    assert endpoints["HKEX_MAIN_RULE_UPDATES_ENTIRE_SECTION"].url == (
        "https://en-rules.hkex.com.hk/entiresection/2"
    )
    assert endpoints["HKEX_GEM_RULE_UPDATES_ENTIRE_SECTION"].url == (
        "https://en-rules.hkex.com.hk/entiresection/49"
    )
    assert endpoints["HKEX_MAIN_RULE_UPDATES_PDF"].url == (
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_154_Attachment.pdf"
    )
    assert endpoints["HKEX_GEM_RULE_UPDATES_PDF"].url == (
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_87_Attachment.pdf"
    )
    assert len(register.endpoints) == 20


def test_public_source_profile_rejects_unpinned_role_policy_without_a_register() -> None:
    """A standalone exported profile cannot carry a changed role-policy fact."""

    class SourceIdText(str):
        __slots__ = ()

    profile = load_hk_regulatory_source_register().sources[0]
    assert type(profile) is HKEXSourceProfile
    with pytest.raises(TypeError, match="source_id"):
        replace(profile, source_id=SourceIdText(profile.source_id))

    for field_name, replacement, message in (
        ("source_id", "HK-REG-HKEX-FEES-RULES", "profile provenance"),
        (
            "registered_source_id",
            "src_000000000000000000000000000000000000000000000999",
            "profile provenance",
        ),
        ("version", "9.9.9", "profile provenance"),
        ("source_policy_owner", "FOREIGN_OWNER", "profile provenance"),
        (
            "endpoint_ids",
            ("sep_000000000000000000000000000000000000000000000999",),
            "endpoint binding",
        ),
        ("outage_consequence", "FOREIGN_OUTAGE", "authority drift"),
        ("fact_authority", "FOREIGN_FACT", "authority drift"),
        ("completeness_authority", "FOREIGN_COMPLETENESS", "authority drift"),
        ("blockers", ("FOREIGN_BLOCKER",), "profile provenance"),
        (
            "rights_state",
            PublisherRightsState.PUBLISHED_TERMS_PERMIT,
            "authority provenance",
        ),
        ("operational_state", OfficialSourceState.CONFIGURED, "visibly partial"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(profile, **{field_name: replacement})


def test_register_fingerprint_rejects_resealed_unknown_or_enabled_endpoint(tmp_path: Path) -> None:
    """A matching digest cannot turn an unadmitted product into a callable route."""
    document = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    document["unknown"] = True
    projection = dict(document)
    projection.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(projection))).hexdigest()
    )
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown or missing"):
        load_hk_regulatory_source_register(unknown)

    document.pop("unknown")
    document["endpoints"] = [
        {
            "endpoint_id": "sep_000000000000000000000000000000000000000000000301",
            "source_id": "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
            "version": "1.0.0",
            "name": "TEST_ONLY_ENDPOINT",
            "url": "https://example.invalid/hkex",
            "access_mode": "DIRECT_HTTP",
            "methods": ["GET"],
            "media_types": ["text/html"],
            "max_bytes": 1024,
            "complete_inventory_required": True,
            "signal_use": "COMPLETE_INVENTORY",
            "proves_no_change": False,
            "evidence_role": "TEST_ONLY",
            "enabled": True,
        }
    ]
    document["sources"][0]["endpoint_ids"] = [
        "sep_000000000000000000000000000000000000000000000301"
    ]
    projection = dict(document)
    projection.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(projection))).hexdigest()
    )
    endpoint = tmp_path / "endpoint.json"
    endpoint.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match=r"endpoint|binding"):
        load_hk_regulatory_source_register(endpoint)


def test_complete_inventory_requires_all_five_roles_and_both_publisher_boards() -> None:
    """A catalogue or one-board listing cannot stand in for the reconciled universe."""
    terminals = tuple(
        HKEXSourceTerminal.complete(
            source_id=source_id,
            board=board,
            observed_at="2026-08-26T00:00:00Z",
            declared_member_count=0,
        )
        for source_id in HKEX_REGULATORY_SOURCE_IDS
        for board in HKEXPublisherBoard
    )
    complete = build_hkex_source_inventory(
        observation_cutoff="2026-08-26T00:00:00Z", terminals=terminals, entries=()
    )
    assert complete.complete
    assert len(complete.role_board_accounting) == 10

    missing_gem = tuple(item for item in terminals if item.board is not HKEXPublisherBoard.GEM)
    with pytest.raises(ValueError, match="HKEX_SOURCE_INVENTORY_INCOMPLETE"):
        build_hkex_source_inventory(
            observation_cutoff="2026-08-26T00:00:00Z", terminals=missing_gem, entries=()
        )

    not_complete = HKEXSourceTerminal.create(
        terminals[0].source_id,
        terminals[0].source_profile_version,
        terminals[0].board,
        terminals[0].observed_at,
        HKEXTerminalCode.OUTAGE,
        terminals[0].declared_member_count,
    )
    incomplete = build_hkex_source_inventory(
        observation_cutoff="2026-08-26T00:00:00Z",
        terminals=(not_complete, *terminals[1:]),
        entries=(),
    )
    assert not incomplete.complete


def test_complete_replays_every_mutable_aggregate_fact_before_reporting_success() -> None:
    """An object mutation must not leave a stale complete inventory reporting true."""
    inventory = _complete_zero_inventory()
    object.__setattr__(inventory.terminals[0], "declared_member_count", 123)

    with pytest.raises(ValueError, match="terminal fingerprint drift"):
        _ = inventory.complete


def test_complete_rejects_equality_lying_outer_values_and_foreign_accounting() -> None:
    """Hostile equality cannot replace exact validated provenance or accounting."""

    class PlainText(str):
        __slots__ = ()

    class LyingText(str):
        __slots__ = ()

        def __eq__(self, other: object) -> bool:
            return True

        def __hash__(self) -> int:
            raise TypeError

    class ForeignAccounting:
        __slots__ = ()

        def __eq__(self, other: object) -> bool:
            return True

        def __hash__(self) -> int:
            raise TypeError

    for text_type in (PlainText, LyingText):
        for field_name in (
            "observation_cutoff",
            "register_version",
            "register_fingerprint",
            "inventory_fingerprint",
        ):
            inventory = _complete_zero_inventory()
            object.__setattr__(
                inventory,
                field_name,
                text_type(str(getattr(inventory, field_name))),
            )
            with pytest.raises(TypeError, match="exact"):
                _ = inventory.complete

    inventory = _complete_zero_inventory()
    object.__setattr__(inventory, "role_board_accounting", (ForeignAccounting(),) * 10)
    with pytest.raises(TypeError, match="accounting"):
        _ = inventory.complete


def test_terminal_and_entry_reject_equality_lying_displayed_fingerprints() -> None:
    """Displayed leaf fingerprints must be exact text before their digest is compared."""

    class LyingFingerprint(str):
        __slots__ = ()

        def __eq__(self, other: object) -> bool:
            return True

        def __hash__(self) -> int:
            raise TypeError

    terminal = HKEXSourceTerminal.complete(
        source_id="HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        board=HKEXPublisherBoard.MAIN,
        observed_at="2026-08-26T00:00:00Z",
        declared_member_count=0,
    )
    with pytest.raises(TypeError, match="terminal_fingerprint"):
        HKEXSourceTerminal(
            terminal.source_id,
            terminal.source_profile_version,
            terminal.board,
            terminal.observed_at,
            terminal.terminal_code,
            terminal.declared_member_count,
            LyingFingerprint(str(terminal.terminal_fingerprint)),
        )

    entry = HKEXObservedSourceEntry.create(
        "observation-fingerprint",
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        HKEXPublisherBoard.MAIN,
        "product-fingerprint",
        HKEXSourceObjectKind.RULE,
        "https://example.invalid/fingerprint",
        "sha256:" + "a" * 64,
        1,
        None,
        0,
    )
    with pytest.raises(TypeError, match="entry_fingerprint"):
        HKEXObservedSourceEntry(
            entry.observation_id,
            entry.source_id,
            entry.board,
            entry.product_identity,
            entry.source_object_kind,
            entry.official_locator,
            entry.artifact_fingerprint,
            entry.source_order,
            entry.parent_observation_id,
            entry.declared_child_count,
            LyingFingerprint(str(entry.entry_fingerprint)),
        )


def test_register_copy_is_rejected_even_when_its_old_fingerprint_is_retained() -> None:
    """A public copy cannot retain stale register provenance after a field mutation."""
    register = load_hk_regulatory_source_register()
    with pytest.raises(ValueError, match=r"register .*provenance drift"):
        replace(register, register_version="2099-01-01.1")


def test_terminal_time_after_inventory_cutoff_is_rejected() -> None:
    """A future source observation cannot support an earlier claimed inventory cutoff."""
    future_terminals = tuple(
        HKEXSourceTerminal.complete(
            source_id=source_id,
            board=board,
            observed_at="2026-08-27T00:00:00Z",
            declared_member_count=0,
        )
        for source_id in HKEX_REGULATORY_SOURCE_IDS
        for board in HKEXPublisherBoard
    )
    with pytest.raises(ValueError, match="after inventory cutoff"):
        build_hkex_source_inventory(
            observation_cutoff="2026-08-26T00:00:00Z", terminals=future_terminals, entries=()
        )


def test_entry_rejects_credential_bearing_locator() -> None:
    """A publisher locator cannot carry a username or password into evidence state."""
    with pytest.raises(ValueError, match="official_locator"):
        HKEXObservedSourceEntry.create(
            "observation-credential",
            "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
            HKEXPublisherBoard.MAIN,
            "product-credential",
            HKEXSourceObjectKind.RULE,
            "https://user:password@example.invalid/path",
            "sha256:" + "e" * 64,
            1,
            None,
            0,
        )
    for locator in (
        "https://example.invalid/a b",
        "https://[bad/x",
        "https://example.invalid/control\npath",
        "https://user%3Apassword@example.invalid/path",
    ):
        with pytest.raises(ValueError, match="official_locator"):
            HKEXObservedSourceEntry.create(
                "observation-malformed",
                "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
                HKEXPublisherBoard.MAIN,
                "product-malformed",
                HKEXSourceObjectKind.RULE,
                locator,
                "sha256:" + "e" * 64,
                1,
                None,
                0,
            )


def test_entry_rejects_noncanonical_official_locator_corpus() -> None:
    """Malformed authority and control forms cannot become stored source evidence."""
    for locator in (
        "HTTPS://example.invalid/path",
        "https://example.invalid\x7f/a",
        "https://example.invalid\u0080/a",
        "https://example.invalid\u009f/a",
        "https://example.invalid\u200e/a",
        "https://example.invalid\ue000/a",
        "https://bad_name.example/a",
        "https://-bad.example/a",
        "https://bad-.example/a",
        "https://example..com/a",
        "https://./a",
        "https://example.invalid\\a",
        "https://user%40example.invalid/a",
        "https://256.1.1.1/a",
        "https://[1:2:3:4:5:6:7:8:9]/a",
        "https://example.invalid/%2Fpath",
        "https://example.invalid/%3A443",
        "https://example.invalid/%5Cpath",
        "https://example.invalid/%00path",
        "https://example.invalid/%C2%80path",
        "https://example.invalid/%E2%80%8Epath",
        "https://example.invalid/%ZZpath",
        "https://example.invalid:00080/path",
        "https://example.invalid:443/path",
        "https://example.invalid:0/path",
        "https://example.invalid:65536/path",
        "https://example.invalid/#fragment",
        "https://example.invalid/path#",
        "https://xn--abc/path",
        "https://xn--a/path",
        "https://xn--0/path",
        "https://xn--00b.example/path",
        "https://xn--00g.example/path",
        "https://xn--01c.example/path",
        "https://xn--009a.example/path",
        "https://xn--zca.example/path",
        "https://0x7f000001/path",
        "https://0x7f.1/path",
        "https://127.0x0.0.1/path",
        "https://127.0.0x1/path",
        "https://0177.0.0.1/path",
        "https://017700000001/path",
        "https://2130706433/path",
        "https://127.1/path",
        "https://127.0.0.01/path",
        "https://example.123/path",
    ):
        with pytest.raises(ValueError, match="official_locator"):
            _entry_with_locator(locator)


def test_entry_retains_canonical_hkex_like_official_locators() -> None:
    """The strict locator grammar retains ordinary HTTPS paths and bounded queries."""
    for locator in (
        "https://www.hkex.com.hk/Listing/Rules-and-Resources/Listing-Rules?sc_lang=en",
        "https://www.hkex.com.hk/%E4%B8%80?sc_lang=zh-HK",
        "https://en-rules.hkex.com.hk/rulebook/fees-rules?board=gem&lang=en",
        "https://en-rules.hkex.com.hk:8443/rulebook/regulatory-forms",
        "https://127.0.0.1/path",
        "https://[2001:db8::1]/path",
    ):
        assert _entry_with_locator(locator).official_locator == locator


def test_invalid_a_label_mutation_cannot_support_a_complete_inventory() -> None:
    """A blocked internationalized host cannot survive complete-inventory replay."""
    source_id = "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS"
    entry = _entry_with_locator("https://www.hkex.com.hk/Listing/Rules")
    terminals = tuple(
        HKEXSourceTerminal.complete(
            source_id=role,
            board=board,
            observed_at="2026-08-26T00:00:00Z",
            declared_member_count=int((role, board) == (source_id, HKEXPublisherBoard.MAIN)),
        )
        for role in HKEX_REGULATORY_SOURCE_IDS
        for board in HKEXPublisherBoard
    )
    inventory = build_hkex_source_inventory(
        observation_cutoff="2026-08-26T00:00:00Z", terminals=terminals, entries=(entry,)
    )
    assert inventory.complete

    object.__setattr__(entry, "official_locator", "https://xn--00b.example/path")
    with pytest.raises(ValueError, match="official_locator"):
        _ = inventory.complete


def test_factory_hostile_enums_fail_closed_before_fingerprint_projection() -> None:
    """Untrusted primitive enums cannot leak raw attribute failures from factories."""
    with pytest.raises(TypeError):
        HKEXSourceTerminal.create(
            "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
            "1.0.0",
            "MAIN",
            "2026-08-26T00:00:00Z",
            HKEXTerminalCode.COMPLETE,
            0,
        )

    with pytest.raises(ValueError, match="unknown source"):
        HKEXSourceTerminal.complete(
            source_id="UNKNOWN_SOURCE",
            board=HKEXPublisherBoard.MAIN,
            observed_at="2026-08-26T00:00:00Z",
            declared_member_count=0,
        )


def test_terminal_and_entry_rehydrate_from_displayed_fingerprints_after_restart() -> None:
    """Exact persisted primitives remain verifiable without process-local issuance state."""
    terminal = HKEXSourceTerminal.complete(
        source_id="HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        board=HKEXPublisherBoard.MAIN,
        observed_at="2026-08-26T00:00:00Z",
        declared_member_count=0,
    )
    assert (
        HKEXSourceTerminal(
            terminal.source_id,
            terminal.source_profile_version,
            terminal.board,
            terminal.observed_at,
            terminal.terminal_code,
            terminal.declared_member_count,
            terminal.terminal_fingerprint,
        )
        == terminal
    )
    entry = HKEXObservedSourceEntry.create(
        "observation-rehydrate",
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        HKEXPublisherBoard.MAIN,
        "product-rehydrate",
        HKEXSourceObjectKind.RULE,
        "https://example.invalid/rehydrate",
        "sha256:" + "a" * 64,
        1,
        None,
        0,
    )
    assert (
        HKEXObservedSourceEntry(
            entry.observation_id,
            entry.source_id,
            entry.board,
            entry.product_identity,
            entry.source_object_kind,
            entry.official_locator,
            entry.artifact_fingerprint,
            entry.source_order,
            entry.parent_observation_id,
            entry.declared_child_count,
            entry.entry_fingerprint,
        )
        == entry
    )
    with pytest.raises(TypeError):
        HKEXObservedSourceEntry.create(
            "observation-kind",
            "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
            HKEXPublisherBoard.MAIN,
            "product-kind",
            "RULE",
            "https://example.invalid/kind",
            "sha256:" + "f" * 64,
            1,
            None,
            0,
        )

    inventory = _complete_zero_inventory()
    object.__setattr__(inventory, "register_fingerprint", "sha256:" + "f" * 64)
    with pytest.raises(ValueError, match="register provenance drift"):
        _ = inventory.complete


def test_register_policy_facts_match_the_separate_legal_desk_contract() -> None:
    """Duplicated policy facts surface drift without a forbidden runtime import."""
    assert ROOT_SOURCE_IDS == LEGAL_DESK_SOURCE_IDS
    assert tuple(
        source.source_id for source in root_load_hk_regulatory_source_register().sources
    ) == (LEGAL_DESK_SOURCE_IDS)


def test_entries_preserve_both_boards_without_creating_a_component_or_cross_board_merge() -> None:
    """One shared artifact is two board-owned observations, not one legal identity."""
    source_id = "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS"
    shared_artifact = "sha256:" + "a" * 64
    entries = tuple(
        sorted(
            (
                HKEXObservedSourceEntry.create(
                    observation_id="observation-gem",
                    source_id=source_id,
                    board=HKEXPublisherBoard.GEM,
                    product_identity="product-shared",
                    source_object_kind=HKEXSourceObjectKind.RULE,
                    official_locator="https://example.invalid/shared",
                    artifact_fingerprint=shared_artifact,
                    source_order=1,
                    parent_observation_id=None,
                    declared_child_count=0,
                ),
                HKEXObservedSourceEntry.create(
                    observation_id="observation-main",
                    source_id=source_id,
                    board=HKEXPublisherBoard.MAIN,
                    product_identity="product-shared",
                    source_object_kind=HKEXSourceObjectKind.RULE,
                    official_locator="https://example.invalid/shared",
                    artifact_fingerprint=shared_artifact,
                    source_order=1,
                    parent_observation_id=None,
                    declared_child_count=0,
                ),
            ),
            key=lambda item: (
                item.source_id,
                item.board.value,
                item.source_order,
                item.observation_id,
            ),
        )
    )
    terminals = tuple(
        HKEXSourceTerminal.complete(
            source_id=role,
            board=board,
            observed_at="2026-08-26T00:00:00Z",
            declared_member_count=int(
                (role, board)
                in {(source_id, HKEXPublisherBoard.GEM), (source_id, HKEXPublisherBoard.MAIN)}
            ),
        )
        for role in HKEX_REGULATORY_SOURCE_IDS
        for board in HKEXPublisherBoard
    )

    inventory = build_hkex_source_inventory(
        observation_cutoff="2026-08-26T00:00:00Z", terminals=terminals, entries=entries
    )

    assert inventory.complete
    assert tuple(entry.observation_id for entry in inventory.entries) == (
        "observation-gem",
        "observation-main",
    )
    assert not hasattr(inventory.entries[0], "component_id")
    with pytest.raises(ValueError, match="entry fingerprint drift"):
        replace(inventory.entries[0], official_locator="https://example.invalid/moved")
    with pytest.raises(ValueError, match="inventory fingerprint drift"):
        replace(inventory, observation_cutoff="2026-08-26T00:00:01Z")
    with pytest.raises(ValueError, match="terminal fingerprint drift"):
        replace(
            inventory,
            terminals=(
                replace(inventory.terminals[0], terminal_code=HKEXTerminalCode.OUTAGE),
                *inventory.terminals[1:],
            ),
        )


def test_inventory_rejects_cross_board_parent_cycles_and_accounting_mutation() -> None:
    """Malformed publisher structure cannot become an apparently complete inventory."""
    source_id = "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS"
    terminals = tuple(
        HKEXSourceTerminal.complete(
            source_id=role,
            board=board,
            observed_at="2026-08-26T00:00:00Z",
            declared_member_count=0,
        )
        for role in HKEX_REGULATORY_SOURCE_IDS
        for board in HKEXPublisherBoard
    )
    main_parent = HKEXObservedSourceEntry.create(
        "parent-main",
        source_id,
        HKEXPublisherBoard.MAIN,
        "product-main",
        HKEXSourceObjectKind.CHAPTER,
        "https://example.invalid/main",
        "sha256:" + "b" * 64,
        1,
        None,
        0,
    )
    gem_child = HKEXObservedSourceEntry.create(
        "child-gem",
        source_id,
        HKEXPublisherBoard.GEM,
        "product-gem",
        HKEXSourceObjectKind.RULE,
        "https://example.invalid/gem",
        "sha256:" + "c" * 64,
        1,
        main_parent.observation_id,
        0,
    )
    wrong_terminal = tuple(
        HKEXSourceTerminal.create(
            item.source_id,
            item.source_profile_version,
            item.board,
            item.observed_at,
            item.terminal_code,
            1,
        )
        if (item.source_id, item.board)
        in {
            (source_id, HKEXPublisherBoard.GEM),
            (source_id, HKEXPublisherBoard.MAIN),
        }
        else item
        for item in terminals
    )

    with pytest.raises(ValueError, match="parent provenance"):
        build_hkex_source_inventory(
            observation_cutoff="2026-08-26T00:00:00Z",
            terminals=wrong_terminal,
            entries=(gem_child, main_parent),
        )


def test_inventory_rejects_duplicate_source_order_inside_one_role_board() -> None:
    """Publisher order is evidence and cannot be made ambiguous by a duplicate rank."""
    source_id = "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS"
    terminals = tuple(
        HKEXSourceTerminal.complete(
            source_id=role,
            board=board,
            observed_at="2026-08-26T00:00:00Z",
            declared_member_count=2 if (role, board) == (source_id, HKEXPublisherBoard.MAIN) else 0,
        )
        for role in HKEX_REGULATORY_SOURCE_IDS
        for board in HKEXPublisherBoard
    )
    entries = tuple(
        HKEXObservedSourceEntry.create(
            observation_id=observation_id,
            source_id=source_id,
            board=HKEXPublisherBoard.MAIN,
            product_identity=f"product-{index}",
            source_object_kind=HKEXSourceObjectKind.RULE,
            official_locator=f"https://example.invalid/{index}",
            artifact_fingerprint="sha256:" + character * 64,
            source_order=1,
            parent_observation_id=None,
            declared_child_count=0,
        )
        for index, observation_id, character in (
            (1, "observation-one", "d"),
            (2, "observation-two", "e"),
        )
    )

    with pytest.raises(ValueError, match="canonical unique"):
        build_hkex_source_inventory(
            observation_cutoff="2026-08-26T00:00:00Z", terminals=terminals, entries=entries
        )
