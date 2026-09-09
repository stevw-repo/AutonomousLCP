"""Strict provider-neutral GLD Gazette procedure-contract tests.

These tests protect the source-neutral boundary from turning a renderer session
into source authority or silently widening the checked-in GLD endpoint profile.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, replace
from hashlib import sha256

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_source_connectors import (
    GLD_ADMITTED_HOST,
    GldGazetteClass,
    GldGazetteEntry,
    GldGazetteIssueKind,
    GldGazetteWindow,
    GldSessionGrant,
    GldSessionRequest,
    gld_registered_host,
    load_hk_legislation_source_register,
    project_gld_artifact_requests,
)

_SOURCE_ID = "HK-LEG-GLD-EGAZETTE"
_INVENTORY_ENDPOINT_ID = "sep_00000000000000000000000000000000000000000000003b"
_ARTIFACT_ENDPOINT_ID = "sep_00000000000000000000000000000000000000000000003d"
_SHA256 = "sha256:" + "a" * 64
_CUTOFF = "2026-08-25T00:00:00+00:00"
_ENDPOINT_VERSION = "1.0.0"
_SOURCE_PROFILE_VERSION = "1.1.0"
_REGISTER_VERSION = "2026-08-28.3"
_REGISTER_FINGERPRINT = "sha256:be2dc02b4ef087ac2357ad96dc05be5a36127e2a7f395bffe5b7a98f6408de67"


def _construct[Contract](
    constructor: Callable[..., Contract], values: dict[str, object]
) -> Contract:
    """Exercise direct runtime construction with deliberately malformed payloads."""
    return constructor(**values)


def _request(**changes: object) -> GldSessionRequest:
    values: dict[str, object] = {
        "source_id": _SOURCE_ID,
        "endpoint_id": _INVENTORY_ENDPOINT_ID,
        "endpoint_version": _ENDPOINT_VERSION,
        "source_profile_version": _SOURCE_PROFILE_VERSION,
        "register_version": _REGISTER_VERSION,
        "register_fingerprint": _REGISTER_FINGERPRINT,
        "start_date": "2026-08-24",
        "end_date": "2026-08-25",
        "language": "BILINGUAL",
        "observation_cutoff": _CUTOFF,
    }
    values.update(changes)
    return _construct(GldSessionRequest, values)


def _entry(identity: str = "gld-gazette-2026-0001", **changes: object) -> GldGazetteEntry:
    values: dict[str, object] = {
        "stable_identity": identity,
        "gazette_class": GldGazetteClass.LEGAL_SUPPLEMENT_1,
        "issue_kind": GldGazetteIssueKind.ORDINARY,
        "publication_date": "2026-08-24",
        "artifact_endpoint_id": _ARTIFACT_ENDPOINT_ID,
        "artifact_endpoint_version": _ENDPOINT_VERSION,
        "source_profile_version": _SOURCE_PROFILE_VERSION,
        "register_version": _REGISTER_VERSION,
        "register_fingerprint": _REGISTER_FINGERPRINT,
        "artifact_locator": "issued/2026/0001",
    }
    values.update(changes)
    return _construct(GldGazetteEntry, values)


def _window_fingerprint(entries: tuple[GldGazetteEntry, ...]) -> str:
    projection = {
        "source_id": _SOURCE_ID,
        "endpoint_id": _INVENTORY_ENDPOINT_ID,
        "endpoint_version": _ENDPOINT_VERSION,
        "source_profile_version": _SOURCE_PROFILE_VERSION,
        "register_version": _REGISTER_VERSION,
        "register_fingerprint": _REGISTER_FINGERPRINT,
        "start_date": "2026-08-24",
        "end_date": "2026-08-25",
        "language": "BILINGUAL",
        "observation_cutoff": _CUTOFF,
        "entries": [
            {
                "stable_identity": entry.stable_identity,
                "gazette_class": entry.gazette_class.value,
                "issue_kind": entry.issue_kind.value,
                "publication_date": entry.publication_date,
                "artifact_endpoint_id": entry.artifact_endpoint_id,
                "artifact_endpoint_version": entry.artifact_endpoint_version,
                "source_profile_version": entry.source_profile_version,
                "register_version": entry.register_version,
                "register_fingerprint": entry.register_fingerprint,
                "artifact_locator": entry.artifact_locator,
            }
            for entry in entries
        ],
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"


def _window(
    entries: tuple[GldGazetteEntry, ...] | None = None, **changes: object
) -> GldGazetteWindow:
    exact_entries = entries or (_entry(),)
    values: dict[str, object] = {
        "source_id": _SOURCE_ID,
        "endpoint_id": _INVENTORY_ENDPOINT_ID,
        "endpoint_version": _ENDPOINT_VERSION,
        "source_profile_version": _SOURCE_PROFILE_VERSION,
        "register_version": _REGISTER_VERSION,
        "register_fingerprint": _REGISTER_FINGERPRINT,
        "start_date": "2026-08-24",
        "end_date": "2026-08-25",
        "language": "BILINGUAL",
        "observation_cutoff": _CUTOFF,
        "entries": exact_entries,
        "listing_fingerprint": _window_fingerprint(exact_entries),
    }
    values.update(changes)
    return _construct(GldGazetteWindow, values)


def test_gld_request_rejects_an_unregistered_endpoint() -> None:
    """A syntactically valid but unregistered endpoint cannot reach a GLD port."""
    with pytest.raises(ValueError, match="GLD_ENDPOINT_NOT_ADMITTED"):
        _request(endpoint_id="sep_ffffffffffffffffffffffffffffffffffffffffffffffff")


def test_request_uses_only_the_registered_browser_inventory_endpoint() -> None:
    """A discovery page or direct notice page cannot masquerade as the inventory."""
    with pytest.raises(ValueError, match="GLD_ENDPOINT_ROLE_INVALID"):
        _request(endpoint_id="sep_00000000000000000000000000000000000000000000003c")

    with pytest.raises(ValueError, match="GLD_ENDPOINT_ROLE_INVALID"):
        _request(endpoint_id="sep_00000000000000000000000000000000000000000000003e")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("start_date", "2026-8-24"),
        ("start_date", "2026-08-26"),
        ("end_date", "2026-08-24T00:00:00+00:00"),
        ("language", "SIMPLIFIED_CHINESE"),
        ("observation_cutoff", "2026-08-25T00:00:00Z"),
    ],
)
def test_request_rejects_noncanonical_window_or_closed_values(field: str, value: str) -> None:
    """A malformed or inverted observation window cannot broaden enumeration."""
    with pytest.raises((TypeError, ValueError)):
        _request(**{field: value})


def test_gazette_entry_requires_declared_class_and_registered_artifact_endpoint() -> None:
    """An entry cannot invent a Gazette class or make a listing endpoint an artifact."""
    with pytest.raises(TypeError, match="gazette_class"):
        _entry(gazette_class="LEGAL_SUPPLEMENT_1")

    with pytest.raises(ValueError, match="GLD_ARTIFACT_ENDPOINT_ROLE_INVALID"):
        _entry(artifact_endpoint_id=_INVENTORY_ENDPOINT_ID)


def test_gazette_entry_requires_an_exact_closed_issue_kind() -> None:
    """Ordinary and Extraordinary issues are separate complete-inventory dimensions."""
    assert _entry(issue_kind=GldGazetteIssueKind.EXTRAORDINARY).issue_kind is (
        GldGazetteIssueKind.EXTRAORDINARY
    )
    with pytest.raises(TypeError, match="issue_kind"):
        _entry(issue_kind="ORDINARY")


@pytest.mark.parametrize(
    "locator",
    [
        "",
        "/issued/2026/0001",
        "issued/2026/0001/",
        "issued//2026",
        ".",
        "issued/./2026",
        "issued/../2026",
        "issued\\2026",
        "issued?query",
        "issued#fragment",
        "{issued}",
        "%2e%2e/secret",
        "issued/%2fsecret",
        "issued/%0dsecret",
        "issued/%3fquery",
        "issued/%23fragment",
        "issued/%7btemplate%7d",
    ],
)
def test_artifact_locator_must_be_the_exact_shared_bounded_relative_path(locator: str) -> None:
    """An entry must use the single repository locator binder, never a second joiner."""
    with pytest.raises((TypeError, ValueError)):
        _entry(artifact_locator=locator)


def test_artifact_locator_accepts_one_normal_bounded_relative_path() -> None:
    """A normal publisher path remains usable after hostile-input resource bounds."""
    assert _entry(artifact_locator="issued/法令-2026").artifact_locator == "issued/法令-2026"


def test_complete_window_projects_exact_registered_artifact_requests() -> None:
    """Discovered artifacts retain identity and use only the registered URL binder."""
    entries = (_entry(), _entry("gld-gazette-2026-0002", artifact_locator="issued/2026/0002"))

    requests = project_gld_artifact_requests(_window(entries))

    assert tuple(item.stable_identity for item in requests) == (
        "gld-gazette-2026-0001",
        "gld-gazette-2026-0002",
    )
    assert requests[0].locator == "https://egazette.gld.gov.hk/issued/2026/0001"
    assert requests[0].listing_fingerprint == _window(entries).listing_fingerprint


@pytest.mark.parametrize(
    "locator",
    [
        "a" * 513,
        "法" * 342,
        "issued/%252e%252e/secret",
        "issued/%25252e%25252e/secret",
    ],
)
def test_artifact_locator_has_bounded_input_and_fixed_percent_decode_depth(locator: str) -> None:
    """A publisher field cannot force input-sized decode work before failing closed."""
    with pytest.raises(ValueError, match="GLD_ARTIFACT_LOCATOR_INVALID"):
        _entry(artifact_locator=locator)


@pytest.mark.parametrize(
    "locator",
    [
        "issued/\u0080c1",
        "issued/%c2%80c1",
        "issued/%25c2%2580c1",
        "issued/\u200bzero-width",
        "issued/%e2%80%8bzero-width",
        "issued/%25e2%2580%258bzero-width",
        "issued/\u202ebidi",
        "issued/%e2%80%aebidi",
        "issued/%25e2%2580%25aebidi",
        "issued/\u2028line-separator",
        "issued/%e2%80%a8line-separator",
        "issued/%25e2%2580%25a8line-separator",
        "issued/\u2029paragraph-separator",
        "issued/%e2%80%a9paragraph-separator",
        "issued/%25e2%2580%25a9paragraph-separator",
        "issued/\uffffnoncharacter",
        "issued/%ef%bf%bfnoncharacter",
        "issued/%25ef%25bf%25bfnoncharacter",
        "issued/\ue000private-use",
        "issued/\ud800surrogate",
        "issued/%ffmalformed-utf8",
        "issued/%c2truncated-utf8",
        "issued/%c0%afoverlong-utf8",
        "issued/%malformed-percent",
        "issued/%0truncated-percent",
        "issued/%gginvalid-percent",
    ],
)
def test_artifact_locator_rejects_unsafe_unicode_and_malformed_percent_layers(locator: str) -> None:
    """Raw and every permitted decoded layer must remain strict UTF-8 publisher paths."""
    with pytest.raises(ValueError, match="GLD_ARTIFACT_LOCATOR_INVALID"):
        _entry(artifact_locator=locator)


@pytest.mark.parametrize(
    ("factory", "field"),
    [
        (_request, "endpoint_version"),
        (_request, "source_profile_version"),
        (_request, "register_version"),
        (_request, "register_fingerprint"),
        (_entry, "artifact_endpoint_version"),
        (_entry, "source_profile_version"),
        (_entry, "register_version"),
        (_entry, "register_fingerprint"),
    ],
)
def test_profile_binding_rejects_any_current_register_drift(
    factory: Callable[..., object], field: str
) -> None:
    """An ID alone cannot survive a register, source, or endpoint contract revision."""
    with pytest.raises((TypeError, ValueError)):
        factory(**{field: "sha256:" + "f" * 64 if field == "register_fingerprint" else "9.9.9"})


def test_window_fingerprint_changes_for_the_issue_kind_and_every_profile_binding() -> None:
    """The immutable listing digest names both Gazette dimensions and every profile revision."""
    ordinary = _entry()
    extraordinary = _entry(issue_kind=GldGazetteIssueKind.EXTRAORDINARY)
    assert _window_fingerprint((ordinary,)) != _window_fingerprint((extraordinary,))


class _StringSubclass(str):
    """Direct construction must not preserve an object with custom string behavior."""

    __slots__ = ()


@pytest.mark.parametrize(
    ("factory", "field", "value"),
    [
        (_request, "source_id", _StringSubclass(_SOURCE_ID)),
        (_request, "language", _StringSubclass("BILINGUAL")),
        (_window, "source_id", _StringSubclass(_SOURCE_ID)),
        (_window, "language", _StringSubclass("BILINGUAL")),
    ],
)
def test_request_and_window_reject_string_subclasses(
    factory: Callable[..., object], field: str, value: str
) -> None:
    """Closed request/window strings cannot cross the contract as subclasses."""
    with pytest.raises((TypeError, ValueError)):
        factory(**{field: value})


@pytest.mark.parametrize(
    ("factory", "field", "value"),
    [
        (_request, "endpoint_id", _StringSubclass(_INVENTORY_ENDPOINT_ID)),
        (_request, "endpoint_version", _StringSubclass(_ENDPOINT_VERSION)),
        (_request, "source_profile_version", _StringSubclass(_SOURCE_PROFILE_VERSION)),
        (_request, "register_version", _StringSubclass(_REGISTER_VERSION)),
        (_request, "register_fingerprint", _StringSubclass(_REGISTER_FINGERPRINT)),
        (_request, "start_date", _StringSubclass("2026-08-24")),
        (_request, "end_date", _StringSubclass("2026-08-25")),
        (_request, "observation_cutoff", _StringSubclass(_CUTOFF)),
        (_window, "endpoint_id", _StringSubclass(_INVENTORY_ENDPOINT_ID)),
        (_window, "endpoint_version", _StringSubclass(_ENDPOINT_VERSION)),
        (_window, "source_profile_version", _StringSubclass(_SOURCE_PROFILE_VERSION)),
        (_window, "register_version", _StringSubclass(_REGISTER_VERSION)),
        (_window, "register_fingerprint", _StringSubclass(_REGISTER_FINGERPRINT)),
        (_window, "start_date", _StringSubclass("2026-08-24")),
        (_window, "end_date", _StringSubclass("2026-08-25")),
        (_window, "observation_cutoff", _StringSubclass(_CUTOFF)),
    ],
)
def test_every_other_closed_request_and_window_string_rejects_subclasses(
    factory: Callable[..., object], field: str, value: str
) -> None:
    """Exact-string validation applies to every remaining immutable profile field."""
    with pytest.raises((TypeError, ValueError)):
        factory(**{field: value})


def test_window_requires_sorted_unique_stable_identities_and_exact_fingerprint() -> None:
    """Traversal order and listing digest are evidence, never data we repair."""
    first = _entry("gld-gazette-2026-0001")
    second = _entry("gld-gazette-2026-0002")

    with pytest.raises(ValueError, match="GLD_ENTRIES_NOT_SORTED"):
        _window((second, first))
    with pytest.raises(ValueError, match="GLD_ENTRY_IDENTITY_DUPLICATE"):
        _window((first, replace(first, artifact_locator="issued/2026/other")))
    with pytest.raises(ValueError, match="GLD_LISTING_FINGERPRINT_MISMATCH"):
        _window((first, second), listing_fingerprint=_SHA256)


def test_window_binds_entries_to_the_request_window_and_cutoff() -> None:
    """A post-cutoff or out-of-window Gazette cannot become part of that listing."""
    with pytest.raises(ValueError, match="GLD_ENTRY_OUTSIDE_WINDOW"):
        _window(entries=(_entry(publication_date="2026-08-23"),))


def test_session_grant_has_no_controlling_evidence_authority() -> None:
    """A browser-session grant is a sanitized transport capability only."""
    field_by_name = {field.name: field for field in fields(GldSessionGrant)}
    assert field_by_name["controlling_evidence"].default is False
    assert {field.name for field in fields(GldSessionGrant)} == {
        "session_id",
        "established_at",
        "expires_at",
        "admitted_host",
        "policy_fingerprint",
        "observed_request_count",
        "controlling_evidence",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("established_at", "2026-08-25T00:00:00Z"),
        ("expires_at", "2026-08-25T00:00:00+00:00"),
        ("admitted_host", "www.gld.gov.hk"),
        ("admitted_host", _StringSubclass(GLD_ADMITTED_HOST)),
        ("policy_fingerprint", "sha256:not-a-digest"),
        ("controlling_evidence", True),
    ],
)
def test_session_grant_rejects_expiry_host_policy_and_authority_drift(
    field: str, value: object
) -> None:
    """Grant construction refuses secrets-by-proxy and invalid lifecycle facts."""
    values: dict[str, object] = {
        "session_id": "local-gld-session-01",
        "established_at": "2026-08-25T00:00:00+00:00",
        "expires_at": "2026-08-25T00:01:00+00:00",
        "admitted_host": GLD_ADMITTED_HOST,
        "policy_fingerprint": _SHA256,
    }
    values.update({field: value})
    with pytest.raises((TypeError, ValueError)):
        _construct(GldSessionGrant, values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_id", _StringSubclass("local-gld-session-01")),
        ("established_at", _StringSubclass("2026-08-25T00:00:00+00:00")),
        ("expires_at", _StringSubclass("2026-08-25T00:01:00+00:00")),
        ("policy_fingerprint", _StringSubclass(_SHA256)),
    ],
)
def test_every_other_closed_grant_string_rejects_subclasses(field: str, value: str) -> None:
    """Session lifecycle metadata is as exact as the sanitized host field."""
    values: dict[str, object] = {
        "session_id": "local-gld-session-01",
        "established_at": "2026-08-25T00:00:00+00:00",
        "expires_at": "2026-08-25T00:01:00+00:00",
        "admitted_host": GLD_ADMITTED_HOST,
        "policy_fingerprint": _SHA256,
    }
    values[field] = value
    with pytest.raises((TypeError, ValueError)):
        _construct(GldSessionGrant, values)


def test_request_validation_does_not_enable_or_resolve_the_registered_source() -> None:
    """Local contract construction must leave the checked-in source profile inert."""
    before = load_hk_legislation_source_register()

    _request()

    after = load_hk_legislation_source_register()
    endpoints = {
        endpoint.endpoint_id: endpoint.enabled
        for endpoint in after.endpoints
        if endpoint.source_id == _SOURCE_ID
    }
    assert before.operationally_admitted is False
    assert after.operationally_admitted is False
    assert endpoints == {
        _INVENTORY_ENDPOINT_ID: False,
        "sep_00000000000000000000000000000000000000000000003c": False,
        _ARTIFACT_ENDPOINT_ID: False,
        "sep_00000000000000000000000000000000000000000000003e": True,
    }


def test_registered_host_is_derived_from_the_exact_bound_inventory_profile() -> None:
    """Task 2 must not replace the register's GLD host with a hand-written authority."""
    assert gld_registered_host(_request()) == "egazette.gld.gov.hk"
