"""Dependency-neutral, exact HKEX role-aware traversal policy."""

from __future__ import annotations

import hashlib
import json
from typing import Final, cast

_POLICY_NAME: Final = "HKEX_ROLE_AWARE_2.0.0"
_INVALID: Final = "HKEX_EXECUTION_POLICY_INVALID"
_PROFILE: Final[dict[str, object]] = {
    "fees_pdfs_per_board": 32,
    "followed_redirect_hop_starts": 512,
    "form_nodes_per_board": 256,
    "form_pdfs_per_board": 256,
    "logical_request_starts": 3_168,
    "minimum_physical_start_interval_seconds": 0.25,
    "name": _POLICY_NAME,
    "one_html_response_bytes": 16_777_216,
    "one_pdf_response_bytes": 67_108_864,
    "physical_request_starts": 3_680,
    "raw_location_admission_octets": 8_192,
    "raw_location_discarded_lookahead_octets": 1,
    "raw_location_retained_prefix_octets": 8_193,
    "redirect_events_globally": 1_024,
    "redirect_events_per_forms_attempt": 2,
    "retained_response_bytes": 68_719_476_736,
    "static_registered_requests": 32,
    "total_elapsed_observation_seconds": 3_600,
    "unique_dynamic_html_requests": 512,
    "unique_dynamic_pdf_requests": 2_624,
    "update_containers_per_board": 64,
    "update_pages_per_board": 1_024,
    "update_pdfs_per_board": 1_024,
}


def canonical(value: object) -> bytes:
    """Encode one policy fact in the repository's canonical JSON form."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def execution_policy() -> dict[str, object]:
    """Return a fresh exact role-aware HKEX execution policy."""
    value: object = json.loads(canonical(_PROFILE))
    if type(value) is not dict:
        raise ValueError(_INVALID)
    return cast("dict[str, object]", value)


def execution_policy_fingerprint() -> str:
    """Return the canonical fingerprint for the current HKEX policy."""
    return "sha256:" + hashlib.sha256(canonical(execution_policy())).hexdigest()


def recognized_execution_policy(policy: object, fingerprint: object) -> str | None:
    """Resolve only the exact current policy and fingerprint pair."""
    if type(fingerprint) is not str:
        return None
    try:
        candidate = canonical(policy)
    except TypeError, ValueError:
        return None
    if candidate != canonical(execution_policy()):
        return None
    if fingerprint != execution_policy_fingerprint():
        return None
    return _POLICY_NAME


def raw_location_consumption_ceiling(policy: object) -> int:
    """Derive the closed prefix-plus-lookahead transport consumption ceiling."""
    if canonical(policy) != canonical(execution_policy()):
        raise ValueError(_INVALID)
    candidate = cast("dict[str, object]", policy)
    prefix = candidate.get("raw_location_retained_prefix_octets")
    lookahead = candidate.get("raw_location_discarded_lookahead_octets")
    if type(prefix) is not int or type(lookahead) is not int:
        raise ValueError(_INVALID)
    return prefix + lookahead
