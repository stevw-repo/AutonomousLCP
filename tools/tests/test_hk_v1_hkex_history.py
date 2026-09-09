"""Exact literal history for frozen HKEX attempts."""

from __future__ import annotations

import asklegal_source_connectors as source_connectors
import pytest

from tools.hk_v1_hkex_history import historical_hkex_replay_pin

_COMMON_ENDPOINT_PROJECTION = (
    ("301", "1.0.0", "https://en-rules.hkex.com.hk/rulebook/main-board-listing-rules"),
    ("302", "1.0.0", "https://en-rules.hkex.com.hk/rulebook/gem-listing-rules"),
    ("303", "1.0.0", "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules"),
    ("304", "1.0.0", "https://en-rules.hkex.com.hk/rulebook/gem-fees-rules"),
    ("305", "1.0.0", "https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms"),
    ("306", "1.0.0", "https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms"),
    ("307", "1.0.0", "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules"),
    ("308", "1.0.0", "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules"),
    (
        "309",
        "1.0.0",
        "https://www.hkex.com.hk/Listing/Rules-and-Resources/Listing-Rules?sc_lang=en",
    ),
    ("310", "1.0.0", "https://en-rules.hkex.com.hk/entiresection/1932"),
    (
        "311",
        "1.0.0",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/consol_mb.pdf",
    ),
    (
        "312",
        "1.0.0",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/consol_gem.pdf",
    ),
    ("313", "1.0.0", "https://en-rules.hkex.com.hk/entiresection/6189"),
    ("314", "1.0.0", "https://en-rules.hkex.com.hk/entiresection/6192"),
    ("315", "1.0.0", "https://en-rules.hkex.com.hk/entiresection/2"),
    ("316", "1.0.0", "https://en-rules.hkex.com.hk/entiresection/49"),
)
_OLD_UPDATE_PROJECTION = (
    (
        "317",
        "1.0.0",
        (
            "https://www.hkex.com.hk/-/media/HKEX-Market/Listing/Rules-and-Guidance/"
            "Listing-Rules/Amendments-to-Main-Board-Listing-Rules/amend_mb.pdf"
        ),
    ),
    (
        "318",
        "1.0.0",
        (
            "https://www.hkex.com.hk/-/media/HKEX-Market/Listing/Rules-and-Guidance/"
            "Listing-Rules/Amendments-to-GEM-Listing-Rules/amend_gem.pdf"
        ),
    ),
)
_CURRENT_UPDATE_PROJECTION = (
    (
        "317",
        "1.0.1",
        (
            "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/"
            "Update_154_Attachment.pdf"
        ),
    ),
    (
        "318",
        "1.0.1",
        (
            "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/"
            "Update_87_Attachment.pdf"
        ),
    ),
)


def test_historical_hkex_attempt_c_has_its_own_literal_contract() -> None:
    """A current-register projection must not be able to rewrite frozen attempt C."""
    pin = historical_hkex_replay_pin("hkex-live-baseline-20260901c")

    assert pin.observation_cutoff == "2026-09-01T15:33:35+08:00"
    assert pin.register_identity == (
        "hrr_000000000000000000000000000000000000000000000001",
        "2026-09-01.1",
        "sha256:bd153183d740b809f9ccdd611dfe44abeeb824f42d696e232f4aac819d4b23c3",
    )
    assert pin.allowed_urls_fingerprint == (
        "sha256:5419bfd4d529b4b8f1cdb41a6d456ac8cd23bae19887d475c27a0aaa5db4f2b5"
    )
    assert pin.authority_fingerprint == (
        "sha256:68c20b7eae6611e991e4a3b984749a68c58f8c178a04974e00d159510982fc77"
    )
    assert pin.execution_authorization_fingerprint == (
        "sha256:d01f762173c1c97726aa5f0b97ca4d256d1c6bee19e48f76df308255efa8a213"
    )
    assert pin.report_sha256 == ("74b8cfa325b6bfcc98c652d3ec413761a0792aebdf8d564bbe506719be294f75")
    assert pin.expected_result == "SOURCE_CONTRACT_CHANGED"
    assert len(pin.endpoints) == 18
    assert tuple(
        (item.endpoint_id[-3:], item.version, item.url) for item in pin.endpoints[-2:]
    ) == (
        (
            "317",
            "1.0.1",
            (
                "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/"
                "Update_154_Attachment.pdf"
            ),
        ),
        (
            "318",
            "1.0.1",
            (
                "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/"
                "Update_87_Attachment.pdf"
            ),
        ),
    )


def test_role_aware_attempts_have_exact_policy_bound_literal_contracts() -> None:
    """The two schema-2 stops retain one exact endpoint and parser-policy generation."""
    attempt_806 = historical_hkex_replay_pin("hkex-live-role-aware-20260902a")
    attempt_807 = historical_hkex_replay_pin("hkex-live-role-aware-20260902b")

    assert attempt_806.endpoints is attempt_807.endpoints
    assert len(attempt_806.endpoints) == 20
    assert tuple(item.endpoint_id[-3:] for item in attempt_806.endpoints) == tuple(
        str(value) for value in range(301, 321)
    )
    assert attempt_806.execution_policy_fingerprint == (
        "sha256:3d204e5dc8e8ac1fd500cf85cdeb28f43ddf3ceff1d2c3f285c56e615dce65c9"
    )
    assert attempt_807.execution_policy_fingerprint == attempt_806.execution_policy_fingerprint
    assert attempt_806.legacy_root_contract_changed is True
    assert attempt_807.legacy_root_contract_changed is False
    assert attempt_806.report_sha256 == (
        "38adea701dd4c7334c7b31af94519b0780248563248ff55ada87ed8bf3e6f9e4"
    )
    assert attempt_807.report_sha256 == (
        "0ba08e5868921fc7da0685187fd75d5246d062932cd2369ad0836ac7da6d2686"
    )


def test_historical_hkex_lookup_rejects_unallocated_attempt() -> None:
    """The history boundary must not infer another attempt from current state."""
    with pytest.raises(KeyError, match="historical HKEX attempt is not pinned"):
        historical_hkex_replay_pin("hkex-live-baseline-20260901d")


def test_historical_hkex_pins_hold_all_eighteen_literal_endpoint_coordinates() -> None:
    """Current register edits must not change any frozen endpoint coordinate."""
    attempt_a = historical_hkex_replay_pin("hkex-live-baseline-20260901a")
    attempt_b = historical_hkex_replay_pin("hkex-live-baseline-20260901b")
    attempt_c = historical_hkex_replay_pin("hkex-live-baseline-20260901c")

    def projection(attempt_id: str) -> tuple[tuple[str, str, str], ...]:
        return tuple(
            (endpoint.endpoint_id[-3:], endpoint.version, endpoint.url)
            for endpoint in historical_hkex_replay_pin(attempt_id).endpoints
        )

    assert projection(attempt_a.attempt_id) == _COMMON_ENDPOINT_PROJECTION + _OLD_UPDATE_PROJECTION
    assert projection(attempt_b.attempt_id) == _COMMON_ENDPOINT_PROJECTION + _OLD_UPDATE_PROJECTION
    assert projection(attempt_c.attempt_id) == (
        _COMMON_ENDPOINT_PROJECTION + _CURRENT_UPDATE_PROJECTION
    )
    assert attempt_a.endpoints is attempt_b.endpoints
    assert attempt_c.endpoints is not attempt_a.endpoints


def test_historical_hkex_lookup_never_consults_current_register(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Literal history remains available when current register loading explodes."""
    monkeypatch.setattr(
        source_connectors,
        "load_hk_regulatory_source_register",
        lambda: (_ for _ in ()).throw(AssertionError("current register consulted")),
    )

    assert historical_hkex_replay_pin("hkex-live-baseline-20260901a").endpoints[-1].version == (
        "1.0.0"
    )
    assert historical_hkex_replay_pin("hkex-live-baseline-20260901c").endpoints[-1].version == (
        "1.0.1"
    )
