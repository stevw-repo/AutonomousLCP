"""Literal immutable replay identities for the frozen HKEX baselines."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from asklegal_source_connectors import (
    EndpointAccessMode,
    HttpMethod,
    OfficialEndpointContract,
    SignalUse,
)

_REGISTER_ID = "hrr_000000000000000000000000000000000000000000000001"
_CUTOFF = "2026-09-01T15:33:35+08:00"
_METHODS = (HttpMethod.GET, HttpMethod.HEAD)
_UNPINNED = "historical HKEX attempt is not pinned"


def _endpoint(  # noqa: PLR0913 - compact constructor for exact literal snapshots.
    suffix: int,
    source_id: str,
    version: str,
    name: str,
    url: str,
    *,
    media_type: str,
    max_bytes: int,
    inventory: bool,
    signal_use: SignalUse,
    evidence_role: str,
) -> OfficialEndpointContract:
    """Build one endpoint only from this module's checked-in literal arguments."""
    return OfficialEndpointContract(
        endpoint_id=f"sep_{suffix:048d}",
        source_id=source_id,
        version=version,
        name=name,
        url=url,
        access_mode=EndpointAccessMode.DIRECT_HTTP,
        methods=_METHODS,
        media_types=(media_type,),
        max_bytes=max_bytes,
        complete_inventory_required=inventory,
        signal_use=signal_use,
        proves_no_change=False,
        evidence_role=evidence_role,
        enabled=True,
    )


_COMMON_ENDPOINTS = (
    _endpoint(
        301,
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "1.0.0",
        "HKEX_MAIN_BOARD_RULEBOOK",
        "https://en-rules.hkex.com.hk/rulebook/main-board-listing-rules",
        media_type="text/html",
        max_bytes=16_777_216,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="MAIN_BOARD_RULEBOOK_ROOT",
    ),
    _endpoint(
        302,
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "1.0.0",
        "HKEX_GEM_RULEBOOK",
        "https://en-rules.hkex.com.hk/rulebook/gem-listing-rules",
        media_type="text/html",
        max_bytes=16_777_216,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="GEM_RULEBOOK_ROOT",
    ),
    _endpoint(
        303,
        "HK-REG-HKEX-FEES-RULES",
        "1.0.0",
        "HKEX_MAIN_BOARD_FEES_RULES",
        "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
        media_type="text/html",
        max_bytes=8_388_608,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="MAIN_BOARD_FEES_RULES_ROOT",
    ),
    _endpoint(
        304,
        "HK-REG-HKEX-FEES-RULES",
        "1.0.0",
        "HKEX_GEM_FEES_RULES",
        "https://en-rules.hkex.com.hk/rulebook/gem-fees-rules",
        media_type="text/html",
        max_bytes=8_388_608,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="GEM_FEES_RULES_ROOT",
    ),
    _endpoint(
        305,
        "HK-REG-HKEX-REGULATORY-FORMS",
        "1.0.0",
        "HKEX_MAIN_BOARD_REGULATORY_FORMS",
        "https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
        media_type="text/html",
        max_bytes=8_388_608,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="MAIN_BOARD_REGULATORY_FORMS_ROOT",
    ),
    _endpoint(
        306,
        "HK-REG-HKEX-REGULATORY-FORMS",
        "1.0.0",
        "HKEX_GEM_REGULATORY_FORMS",
        "https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms",
        media_type="text/html",
        max_bytes=8_388_608,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="GEM_REGULATORY_FORMS_ROOT",
    ),
    _endpoint(
        307,
        "HK-REG-HKEX-RULE-UPDATES",
        "1.0.0",
        "HKEX_MAIN_BOARD_RULE_UPDATES",
        "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules",
        media_type="text/html",
        max_bytes=8_388_608,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="MAIN_BOARD_FINAL_RULE_UPDATES_ROOT",
    ),
    _endpoint(
        308,
        "HK-REG-HKEX-RULE-UPDATES",
        "1.0.0",
        "HKEX_GEM_RULE_UPDATES",
        "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules",
        media_type="text/html",
        max_bytes=8_388_608,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="GEM_FINAL_RULE_UPDATES_ROOT",
    ),
    _endpoint(
        309,
        "HK-REG-HKEX-RULEBOOK-CATALOGUE",
        "1.0.0",
        "HKEX_LISTING_RULES_CATALOGUE",
        "https://www.hkex.com.hk/Listing/Rules-and-Resources/Listing-Rules?sc_lang=en",
        media_type="text/html",
        max_bytes=8_388_608,
        inventory=False,
        signal_use=SignalUse.DISCOVERY_ONLY,
        evidence_role="BOARD_AND_PRODUCT_FAMILY_CATALOGUE",
    ),
    _endpoint(
        310,
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "1.0.0",
        "HKEX_MAIN_BOARD_ENTIRE_RULEBOOK",
        "https://en-rules.hkex.com.hk/entiresection/1932",
        media_type="text/html",
        max_bytes=33_554_432,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="MAIN_BOARD_COMPLETE_SECTION",
    ),
    _endpoint(
        311,
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "1.0.0",
        "HKEX_MAIN_BOARD_PREVAILING_PDF",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/consol_mb.pdf",
        media_type="application/pdf",
        max_bytes=67_108_864,
        inventory=False,
        signal_use=SignalUse.NOT_A_SIGNAL,
        evidence_role="MAIN_BOARD_PREVAILING_PDF",
    ),
    _endpoint(
        312,
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "1.0.0",
        "HKEX_GEM_PREVAILING_PDF",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/consol_gem.pdf",
        media_type="application/pdf",
        max_bytes=67_108_864,
        inventory=False,
        signal_use=SignalUse.NOT_A_SIGNAL,
        evidence_role="GEM_PREVAILING_PDF",
    ),
    _endpoint(
        313,
        "HK-REG-HKEX-REGULATORY-FORMS",
        "1.0.0",
        "HKEX_REGULATORY_FORMS_ENTIRE_SECTION",
        "https://en-rules.hkex.com.hk/entiresection/6189",
        media_type="text/html",
        max_bytes=33_554_432,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="REGULATORY_FORMS_COMPLETE_SECTION",
    ),
    _endpoint(
        314,
        "HK-REG-HKEX-FEES-RULES",
        "1.0.0",
        "HKEX_FEES_RULES_ENTIRE_SECTION",
        "https://en-rules.hkex.com.hk/entiresection/6192",
        media_type="text/html",
        max_bytes=33_554_432,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="FEES_RULES_COMPLETE_SECTION",
    ),
    _endpoint(
        315,
        "HK-REG-HKEX-RULE-UPDATES",
        "1.0.0",
        "HKEX_MAIN_RULE_UPDATES_ENTIRE_SECTION",
        "https://en-rules.hkex.com.hk/entiresection/2",
        media_type="text/html",
        max_bytes=33_554_432,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="MAIN_RULE_UPDATES_COMPLETE_SECTION",
    ),
    _endpoint(
        316,
        "HK-REG-HKEX-RULE-UPDATES",
        "1.0.0",
        "HKEX_GEM_RULE_UPDATES_ENTIRE_SECTION",
        "https://en-rules.hkex.com.hk/entiresection/49",
        media_type="text/html",
        max_bytes=33_554_432,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="GEM_RULE_UPDATES_COMPLETE_SECTION",
    ),
)

_AB_ENDPOINTS = (
    *_COMMON_ENDPOINTS,
    _endpoint(
        317,
        "HK-REG-HKEX-RULE-UPDATES",
        "1.0.0",
        "HKEX_MAIN_RULE_UPDATES_PDF",
        "https://www.hkex.com.hk/-/media/HKEX-Market/Listing/Rules-and-Guidance/"
        "Listing-Rules/Amendments-to-Main-Board-Listing-Rules/amend_mb.pdf",
        media_type="application/pdf",
        max_bytes=67_108_864,
        inventory=False,
        signal_use=SignalUse.NOT_A_SIGNAL,
        evidence_role="MAIN_RULE_UPDATES_PDF",
    ),
    _endpoint(
        318,
        "HK-REG-HKEX-RULE-UPDATES",
        "1.0.0",
        "HKEX_GEM_RULE_UPDATES_PDF",
        "https://www.hkex.com.hk/-/media/HKEX-Market/Listing/Rules-and-Guidance/"
        "Listing-Rules/Amendments-to-GEM-Listing-Rules/amend_gem.pdf",
        media_type="application/pdf",
        max_bytes=67_108_864,
        inventory=False,
        signal_use=SignalUse.NOT_A_SIGNAL,
        evidence_role="GEM_RULE_UPDATES_PDF",
    ),
)

_C_ENDPOINTS = (
    *_COMMON_ENDPOINTS,
    _endpoint(
        317,
        "HK-REG-HKEX-RULE-UPDATES",
        "1.0.1",
        "HKEX_MAIN_RULE_UPDATES_PDF",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_154_Attachment.pdf",
        media_type="application/pdf",
        max_bytes=67_108_864,
        inventory=False,
        signal_use=SignalUse.NOT_A_SIGNAL,
        evidence_role="MAIN_RULE_UPDATES_PDF",
    ),
    _endpoint(
        318,
        "HK-REG-HKEX-RULE-UPDATES",
        "1.0.1",
        "HKEX_GEM_RULE_UPDATES_PDF",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_87_Attachment.pdf",
        media_type="application/pdf",
        max_bytes=67_108_864,
        inventory=False,
        signal_use=SignalUse.NOT_A_SIGNAL,
        evidence_role="GEM_RULE_UPDATES_PDF",
    ),
)

_ROLE_AWARE_ENDPOINTS = (
    *_COMMON_ENDPOINTS[:2],
    *(replace(endpoint, version="2.0.0") for endpoint in _COMMON_ENDPOINTS[2:8]),
    *_COMMON_ENDPOINTS[8:12],
    _endpoint(
        313,
        "HK-REG-HKEX-REGULATORY-FORMS",
        "2.0.0",
        "HKEX_MAIN_REGULATORY_FORMS_ENTIRE_SECTION",
        "https://en-rules.hkex.com.hk/entiresection/6190",
        media_type="text/html",
        max_bytes=33_554_432,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="MAIN_REGULATORY_FORMS_COMPLETE_SECTION",
    ),
    _endpoint(
        314,
        "HK-REG-HKEX-FEES-RULES",
        "2.0.0",
        "HKEX_MAIN_FEES_RULES_ENTIRE_SECTION",
        "https://en-rules.hkex.com.hk/entiresection/3783",
        media_type="text/html",
        max_bytes=33_554_432,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="MAIN_FEES_RULES_COMPLETE_SECTION",
    ),
    replace(_COMMON_ENDPOINTS[14], version="2.0.0"),
    replace(_COMMON_ENDPOINTS[15], version="2.0.0"),
    *_C_ENDPOINTS[-2:],
    _endpoint(
        319,
        "HK-REG-HKEX-REGULATORY-FORMS",
        "1.0.0",
        "HKEX_GEM_REGULATORY_FORMS_ENTIRE_SECTION",
        "https://en-rules.hkex.com.hk/entiresection/6191",
        media_type="text/html",
        max_bytes=33_554_432,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="GEM_REGULATORY_FORMS_COMPLETE_SECTION",
    ),
    _endpoint(
        320,
        "HK-REG-HKEX-FEES-RULES",
        "1.0.0",
        "HKEX_GEM_FEES_RULES_ENTIRE_SECTION",
        "https://en-rules.hkex.com.hk/entiresection/1836",
        media_type="text/html",
        max_bytes=33_554_432,
        inventory=True,
        signal_use=SignalUse.COMPLETE_INVENTORY,
        evidence_role="GEM_FEES_RULES_COMPLETE_SECTION",
    ),
)


@dataclass(frozen=True, slots=True)
class HistoricalHKEXReplayPin:
    """One complete frozen HKEX replay identity and endpoint snapshot."""

    attempt_id: str
    observation_cutoff: str
    register_identity: tuple[str, str, str]
    allowed_urls_fingerprint: str
    authority_fingerprint: str
    execution_authorization_fingerprint: str
    report_sha256: str
    expected_result: str
    endpoints: tuple[OfficialEndpointContract, ...]
    execution_policy_fingerprint: str | None = None
    legacy_root_contract_changed: bool = False


_PINS: Mapping[str, HistoricalHKEXReplayPin] = MappingProxyType(
    {
        "hkex-live-baseline-20260901a": HistoricalHKEXReplayPin(
            attempt_id="hkex-live-baseline-20260901a",
            observation_cutoff=_CUTOFF,
            register_identity=(
                _REGISTER_ID,
                "2026-08-27.2",
                "sha256:23afbd17a44764a8acf98fece0287100ae4204e136be706c6d65e189addd6e0d",
            ),
            allowed_urls_fingerprint=(
                "sha256:5763c1a154548c7a46babc99292473f0fe37cbd814e7efcd0f5b4a9f63b5624f"
            ),
            authority_fingerprint=(
                "sha256:42b82ac6eb6e148a435d32e6a0c90b81a92e80949ebde52392d5fe2c2f329341"
            ),
            execution_authorization_fingerprint=(
                "sha256:4a25566e2edc3ef54f51e9c4b817c3571f90e6ea3f9ccaac5c7eed531e6ded61"
            ),
            report_sha256="d04259b54ce71e5d7fec2f26de667006cfcb55a93e2d2b78617637a7604e966c",
            expected_result="SOURCE_OUTAGE",
            endpoints=_AB_ENDPOINTS,
        ),
        "hkex-live-baseline-20260901b": HistoricalHKEXReplayPin(
            attempt_id="hkex-live-baseline-20260901b",
            observation_cutoff=_CUTOFF,
            register_identity=(
                _REGISTER_ID,
                "2026-08-27.2",
                "sha256:23afbd17a44764a8acf98fece0287100ae4204e136be706c6d65e189addd6e0d",
            ),
            allowed_urls_fingerprint=(
                "sha256:5763c1a154548c7a46babc99292473f0fe37cbd814e7efcd0f5b4a9f63b5624f"
            ),
            authority_fingerprint=(
                "sha256:5c59de5a7e9acb6ea8ef727af59aeab86ed41b9cee821852901a777b56f9e8a7"
            ),
            execution_authorization_fingerprint=(
                "sha256:db0232aa00c940b82b02b450ecce816184340b2d62bf6c727732e17f5f0b046e"
            ),
            report_sha256="0e24ae06367796bfc8a8581f4538c3d8c16f9fdc7b169dd6c45e4544194b186e",
            expected_result="SOURCE_OUTAGE",
            endpoints=_AB_ENDPOINTS,
        ),
        "hkex-live-baseline-20260901c": HistoricalHKEXReplayPin(
            attempt_id="hkex-live-baseline-20260901c",
            observation_cutoff=_CUTOFF,
            register_identity=(
                _REGISTER_ID,
                "2026-09-01.1",
                "sha256:bd153183d740b809f9ccdd611dfe44abeeb824f42d696e232f4aac819d4b23c3",
            ),
            allowed_urls_fingerprint=(
                "sha256:5419bfd4d529b4b8f1cdb41a6d456ac8cd23bae19887d475c27a0aaa5db4f2b5"
            ),
            authority_fingerprint=(
                "sha256:68c20b7eae6611e991e4a3b984749a68c58f8c178a04974e00d159510982fc77"
            ),
            execution_authorization_fingerprint=(
                "sha256:d01f762173c1c97726aa5f0b97ca4d256d1c6bee19e48f76df308255efa8a213"
            ),
            report_sha256="74b8cfa325b6bfcc98c652d3ec413761a0792aebdf8d564bbe506719be294f75",
            expected_result="SOURCE_CONTRACT_CHANGED",
            endpoints=_C_ENDPOINTS,
        ),
        "hkex-live-role-aware-20260902a": HistoricalHKEXReplayPin(
            attempt_id="hkex-live-role-aware-20260902a",
            observation_cutoff="2026-09-02T09:51:30+08:00",
            register_identity=(
                _REGISTER_ID,
                "2026-09-01.2",
                "sha256:9af7fb460f3556d82b93620ba171cf7391480ad288268afce24ac03e8b7bbbb6",
            ),
            allowed_urls_fingerprint=(
                "sha256:1a81de290ca1f103f35b331a18b0bb8a2d85e264f9edfc335f90db305ee74da6"
            ),
            authority_fingerprint=(
                "sha256:4de2b260808138806b087df0d97fa438b659cb5fa7daa9b98147cd0f9da63d1a"
            ),
            execution_authorization_fingerprint=(
                "sha256:09a821e8e56e17d14dfedc65a559866266d964ff4d8f0b2de8b03a5beb2e9a6f"
            ),
            report_sha256="38adea701dd4c7334c7b31af94519b0780248563248ff55ada87ed8bf3e6f9e4",
            expected_result="SOURCE_CONTRACT_CHANGED",
            endpoints=_ROLE_AWARE_ENDPOINTS,
            execution_policy_fingerprint=(
                "sha256:3d204e5dc8e8ac1fd500cf85cdeb28f43ddf3ceff1d2c3f285c56e615dce65c9"
            ),
            legacy_root_contract_changed=True,
        ),
        "hkex-live-role-aware-20260902b": HistoricalHKEXReplayPin(
            attempt_id="hkex-live-role-aware-20260902b",
            observation_cutoff="2026-09-02T10:03:57+08:00",
            register_identity=(
                _REGISTER_ID,
                "2026-09-01.2",
                "sha256:9af7fb460f3556d82b93620ba171cf7391480ad288268afce24ac03e8b7bbbb6",
            ),
            allowed_urls_fingerprint=(
                "sha256:1a81de290ca1f103f35b331a18b0bb8a2d85e264f9edfc335f90db305ee74da6"
            ),
            authority_fingerprint=(
                "sha256:054f2b679e5c133dc4950f57b6d1cadd01c0d3df76cbdbc2b3fb9d52e1dcc4f3"
            ),
            execution_authorization_fingerprint=(
                "sha256:a3870eabfbb3dd791c8d2ee27a0e2cd15a37ce8d6aa6fc9e5ba2d9e862380133"
            ),
            report_sha256="0ba08e5868921fc7da0685187fd75d5246d062932cd2369ad0836ac7da6d2686",
            expected_result="SOURCE_CONTRACT_CHANGED",
            endpoints=_ROLE_AWARE_ENDPOINTS,
            execution_policy_fingerprint=(
                "sha256:3d204e5dc8e8ac1fd500cf85cdeb28f43ddf3ceff1d2c3f285c56e615dce65c9"
            ),
        ),
    }
)


def historical_hkex_replay_pin(attempt_id: str) -> HistoricalHKEXReplayPin:
    """Return only one exact checked-in replay pin; never consult current state."""
    try:
        return _PINS[attempt_id]
    except KeyError as error:
        raise KeyError(_UNPINNED) from error


def historical_hkex_attempt_ids() -> frozenset[str]:
    """Return the closed set of pinned historical attempt identities."""
    return frozenset(_PINS)
