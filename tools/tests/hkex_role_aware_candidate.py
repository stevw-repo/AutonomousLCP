"""Immutable test-only 20-endpoint HKEX role-aware candidate projection."""

from __future__ import annotations

from dataclasses import replace

from asklegal_source_connectors import OfficialEndpointContract, load_hk_regulatory_source_register

_ID = "sep_000000000000000000000000000000000000000000000"


def candidate_hkex_endpoints() -> tuple[OfficialEndpointContract, ...]:
    """Project the reviewed candidate without activating the checked-in register."""
    current = {
        endpoint.endpoint_id: endpoint
        for endpoint in load_hk_regulatory_source_register().endpoints
    }
    projected = dict(current)
    for suffix in range(303, 309):
        endpoint_id = f"{_ID}{suffix}"
        projected[endpoint_id] = replace(projected[endpoint_id], version="2.0.0")
    projected[f"{_ID}313"] = replace(
        projected[f"{_ID}313"],
        version="2.0.0",
        name="HKEX_MAIN_REGULATORY_FORMS_ENTIRE_SECTION",
        url="https://en-rules.hkex.com.hk/entiresection/6190",
        evidence_role="MAIN_REGULATORY_FORMS_COMPLETE_SECTION",
    )
    projected[f"{_ID}314"] = replace(
        projected[f"{_ID}314"],
        version="2.0.0",
        name="HKEX_MAIN_FEES_RULES_ENTIRE_SECTION",
        url="https://en-rules.hkex.com.hk/entiresection/3783",
        evidence_role="MAIN_FEES_RULES_COMPLETE_SECTION",
    )
    for suffix in (315, 316):
        endpoint_id = f"{_ID}{suffix}"
        projected[endpoint_id] = replace(projected[endpoint_id], version="2.0.0")
    projected[f"{_ID}319"] = replace(
        projected[f"{_ID}313"],
        endpoint_id=f"{_ID}319",
        version="1.0.0",
        name="HKEX_GEM_REGULATORY_FORMS_ENTIRE_SECTION",
        url="https://en-rules.hkex.com.hk/entiresection/6191",
        evidence_role="GEM_REGULATORY_FORMS_COMPLETE_SECTION",
    )
    projected[f"{_ID}320"] = replace(
        projected[f"{_ID}314"],
        endpoint_id=f"{_ID}320",
        version="1.0.0",
        name="HKEX_GEM_FEES_RULES_ENTIRE_SECTION",
        url="https://en-rules.hkex.com.hk/entiresection/1836",
        evidence_role="GEM_FEES_RULES_COMPLETE_SECTION",
    )
    return tuple(projected[key] for key in sorted(projected))
