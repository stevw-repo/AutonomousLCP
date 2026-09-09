"""Provider-neutral, inert contracts for one GLD e-Gazette observation window."""

from __future__ import annotations

import re
import weakref
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Protocol, TypeIs
from unicodedata import category
from urllib.parse import unquote_to_bytes, urlsplit

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .model import exact_identifier, exact_text
from .official import (
    EndpointAccessMode,
    OfficialEndpointContract,
    OfficialSourceProfile,
    SignalUse,
    load_hk_legislation_source_register,
)
from .official_binding import bind_official_endpoint_locator
from .official_http import OfficialTransportResponse

GLD_SOURCE_ID = "HK-LEG-GLD-EGAZETTE"
GLD_ADMITTED_HOST = "egazette.gld.gov.hk"
_LANGUAGES = frozenset({"ENGLISH", "TRADITIONAL_CHINESE", "BILINGUAL"})
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_IDENTITY = re.compile(r"^[a-z][a-z0-9-]{2,127}$")
_SESSION_ID = re.compile(r"^[a-z][a-z0-9-]{2,127}$")
_MAX_ARTIFACT_LOCATOR_CHARACTERS = 512
_MAX_ARTIFACT_LOCATOR_UTF8_BYTES = 1_024
_MAX_PERCENT_DECODE_DEPTH = 2
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_UNSAFE_LOCATOR_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Cn", "Co", "Cs", "Zl", "Zp"})


class GldGazetteClass(StrEnum):
    """The complete, source-neutral classes used by the V1 Gazette rules."""

    MAIN_GAZETTE_NOTICE = "MAIN_GAZETTE_NOTICE"
    LEGAL_SUPPLEMENT_1 = "LEGAL_SUPPLEMENT_1"
    LEGAL_SUPPLEMENT_2 = "LEGAL_SUPPLEMENT_2"
    LEGAL_SUPPLEMENT_3 = "LEGAL_SUPPLEMENT_3"
    OTHER_SUPPLEMENT = "OTHER_SUPPLEMENT"


class GldGazetteIssueKind(StrEnum):
    """The two closed publication-timing dimensions of a Gazette issue."""

    ORDINARY = "ORDINARY"
    EXTRAORDINARY = "EXTRAORDINARY"


@dataclass(frozen=True, slots=True)
class GldSessionRequest:
    """One bounded, language-specific GLD inventory observation request."""

    source_id: str
    endpoint_id: str
    endpoint_version: str
    source_profile_version: str
    register_version: str
    register_fingerprint: str
    start_date: str
    end_date: str
    language: Literal["ENGLISH", "TRADITIONAL_CHINESE", "BILINGUAL"]
    observation_cutoff: str

    def __post_init__(self) -> None:
        source_id = exact_text(self.source_id, "source_id")
        if source_id != GLD_SOURCE_ID:
            raise ValueError("GLD_SOURCE_ID_INVALID")
        _inventory_endpoint(
            self.endpoint_id,
            self.endpoint_version,
            self.source_profile_version,
            self.register_version,
            self.register_fingerprint,
        )
        start = _iso_date(self.start_date, "start_date")
        end = _iso_date(self.end_date, "end_date")
        if start > end:
            raise ValueError("GLD_DATE_WINDOW_INVALID")
        language = exact_text(self.language, "language")
        if language not in _LANGUAGES:
            raise ValueError("GLD_LANGUAGE_INVALID")
        cutoff = _utc_timestamp(self.observation_cutoff, "observation_cutoff")
        if cutoff.date() < end:
            raise ValueError("GLD_OBSERVATION_CUTOFF_INVALID")


@dataclass(frozen=True, slots=True)
class GldSessionGrant:
    """Sanitized local browser-session capability, never controlling evidence."""

    session_id: str
    established_at: str
    expires_at: str
    admitted_host: str
    policy_fingerprint: str
    observed_request_count: int = 0
    controlling_evidence: Literal[False] = False

    def __post_init__(self) -> None:
        if type(self.session_id) is not str or _SESSION_ID.fullmatch(self.session_id) is None:
            raise ValueError("GLD_SESSION_ID_INVALID")
        established = _utc_timestamp(self.established_at, "established_at")
        expires = _utc_timestamp(self.expires_at, "expires_at")
        if expires <= established:
            raise ValueError("GLD_SESSION_EXPIRY_INVALID")
        admitted_host = exact_text(self.admitted_host, "admitted_host")
        if admitted_host != GLD_ADMITTED_HOST:
            raise ValueError("GLD_SESSION_HOST_INVALID")
        _fingerprint(self.policy_fingerprint, "policy_fingerprint")
        if type(self.observed_request_count) is not int or self.observed_request_count < 0:
            raise ValueError("GLD_SESSION_REQUEST_COUNT_INVALID")
        if type(self.controlling_evidence) is not bool or self.controlling_evidence:
            raise ValueError("GLD_SESSION_CONTROLLING_EVIDENCE_FORBIDDEN")


@dataclass(frozen=True, slots=True)
class GldGazetteEntry:
    """One immutable GLD listing row and its registered inert-artifact binding."""

    stable_identity: str
    gazette_class: GldGazetteClass
    issue_kind: GldGazetteIssueKind
    publication_date: str
    artifact_endpoint_id: str
    artifact_endpoint_version: str
    source_profile_version: str
    register_version: str
    register_fingerprint: str
    artifact_locator: str

    def __post_init__(self) -> None:
        if (
            type(self.stable_identity) is not str
            or _STABLE_IDENTITY.fullmatch(self.stable_identity) is None
        ):
            raise ValueError("GLD_STABLE_IDENTITY_INVALID")
        if type(self.gazette_class) is not GldGazetteClass:
            raise TypeError("gazette_class must be an exact GldGazetteClass")
        if type(self.issue_kind) is not GldGazetteIssueKind:
            raise TypeError("issue_kind must be an exact GldGazetteIssueKind")
        _iso_date(self.publication_date, "publication_date")
        endpoint = _artifact_endpoint(
            self.artifact_endpoint_id,
            self.artifact_endpoint_version,
            self.source_profile_version,
            self.register_version,
            self.register_fingerprint,
        )
        _artifact_locator(endpoint, self.artifact_locator)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class GldGazetteWindow:
    """One canonicalized complete GLD listing observation with immutable entries."""

    source_id: str
    endpoint_id: str
    endpoint_version: str
    source_profile_version: str
    register_version: str
    register_fingerprint: str
    start_date: str
    end_date: str
    language: Literal["ENGLISH", "TRADITIONAL_CHINESE", "BILINGUAL"]
    observation_cutoff: str
    entries: tuple[GldGazetteEntry, ...]
    listing_fingerprint: str

    def __post_init__(self) -> None:
        request = GldSessionRequest(
            self.source_id,
            self.endpoint_id,
            self.endpoint_version,
            self.source_profile_version,
            self.register_version,
            self.register_fingerprint,
            self.start_date,
            self.end_date,
            self.language,
            self.observation_cutoff,
        )
        if type(self.entries) is not tuple or any(
            type(entry) is not GldGazetteEntry for entry in self.entries
        ):
            raise TypeError("entries must be an exact tuple of GldGazetteEntry")
        identities = tuple(entry.stable_identity for entry in self.entries)
        if len(identities) != len(set(identities)):
            raise ValueError("GLD_ENTRY_IDENTITY_DUPLICATE")
        if identities != tuple(sorted(identities)):
            raise ValueError("GLD_ENTRIES_NOT_SORTED")
        start = _iso_date(request.start_date, "start_date")
        end = _iso_date(request.end_date, "end_date")
        cutoff = _utc_timestamp(request.observation_cutoff, "observation_cutoff")
        for entry in self.entries:
            if (
                entry.source_profile_version != request.source_profile_version
                or entry.register_version != request.register_version
                or entry.register_fingerprint != request.register_fingerprint
            ):
                raise ValueError("GLD_ENTRY_PROFILE_BINDING_MISMATCH")
            published = _iso_date(entry.publication_date, "publication_date")
            if not start <= published <= end:
                raise ValueError("GLD_ENTRY_OUTSIDE_WINDOW")
            if published > cutoff.date():
                raise ValueError("GLD_ENTRY_AFTER_CUTOFF")
        _fingerprint(self.listing_fingerprint, "listing_fingerprint")
        if self.listing_fingerprint != _listing_fingerprint(request, self.entries):
            raise ValueError("GLD_LISTING_FINGERPRINT_MISMATCH")


@dataclass(frozen=True, slots=True)
class GldArtifactRequest:
    """One admitted discovery projected to an exact registered artifact URL."""

    stable_identity: str
    gazette_class: GldGazetteClass
    issue_kind: GldGazetteIssueKind
    publication_date: str
    endpoint_id: str
    endpoint_version: str
    locator: str
    listing_fingerprint: str


@dataclass(frozen=True, slots=True)
class _IssuedGldWindow:
    reference: weakref.ReferenceType[object]
    snapshot: str


_WINDOW_ISSUANCE: dict[int, _IssuedGldWindow] = {}


def _window_snapshot(window: GldGazetteWindow) -> str:
    body = {
        "source_id": window.source_id,
        "endpoint_id": window.endpoint_id,
        "endpoint_version": window.endpoint_version,
        "source_profile_version": window.source_profile_version,
        "register_version": window.register_version,
        "register_fingerprint": window.register_fingerprint,
        "start_date": window.start_date,
        "end_date": window.end_date,
        "language": window.language,
        "observation_cutoff": window.observation_cutoff,
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
            for entry in window.entries
        ],
        "listing_fingerprint": window.listing_fingerprint,
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"


def assert_gld_gazette_window_issued(window: object) -> GldGazetteWindow:
    """Require the exact live window returned by the admitted exchange call."""
    if type(window) is not GldGazetteWindow:
        raise ValueError("GLD_WINDOW_NOT_ISSUED")
    issued = _WINDOW_ISSUANCE.get(id(window))
    if (
        issued is None
        or issued.reference() is not window
        or issued.snapshot != _window_snapshot(window)
    ):
        raise ValueError("GLD_WINDOW_NOT_ISSUED")
    window.__post_init__()
    return window


def enumerate_gld_gazette_window(
    exchange: object,
    grant: GldSessionGrant,
    request: GldSessionRequest,
) -> GldGazetteWindow:
    """Call the admitted exchange and issue its exact live complete-window result."""
    if (
        type(grant) is not GldSessionGrant
        or type(request) is not GldSessionRequest
        or not _gld_exchange(exchange)
    ):
        raise ValueError("GLD_WINDOW_NOT_ISSUED")
    grant.__post_init__()
    request.__post_init__()
    if grant.admitted_host != gld_registered_host(request):
        raise ValueError("GLD_WINDOW_NOT_ISSUED")
    window = exchange.enumerate_window(grant, request)
    if type(window) is not GldGazetteWindow:
        raise ValueError("GLD_WINDOW_NOT_ISSUED")
    window.__post_init__()
    if (
        window.source_id,
        window.endpoint_id,
        window.endpoint_version,
        window.source_profile_version,
        window.register_version,
        window.register_fingerprint,
        window.start_date,
        window.end_date,
        window.language,
        window.observation_cutoff,
    ) != (
        request.source_id,
        request.endpoint_id,
        request.endpoint_version,
        request.source_profile_version,
        request.register_version,
        request.register_fingerprint,
        request.start_date,
        request.end_date,
        request.language,
        request.observation_cutoff,
    ):
        raise ValueError("GLD_WINDOW_NOT_ISSUED")
    identity = id(window)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        issued = _WINDOW_ISSUANCE.get(identity)
        if issued is not None and issued.reference is reference:
            del _WINDOW_ISSUANCE[identity]

    _WINDOW_ISSUANCE[identity] = _IssuedGldWindow(
        weakref.ref(window, cleanup), _window_snapshot(window)
    )
    return window


def _gld_exchange(value: object) -> TypeIs[GldGazetteExchange]:
    return callable(getattr(value, "enumerate_window", None)) and callable(
        getattr(value, "fetch_artifact", None)
    )


def project_gld_artifact_requests(window: object) -> tuple[GldArtifactRequest, ...]:
    """Project only validated complete-window entries into inert artifact requests."""
    if type(window) is not GldGazetteWindow:
        raise TypeError("window must be an exact GldGazetteWindow")
    window.__post_init__()
    projected: list[GldArtifactRequest] = []
    for entry in window.entries:
        endpoint = _artifact_endpoint(
            entry.artifact_endpoint_id,
            entry.artifact_endpoint_version,
            entry.source_profile_version,
            entry.register_version,
            entry.register_fingerprint,
        )
        bound = bind_official_endpoint_locator(
            endpoint,
            placeholder="issued_artifact_locator",
            locator=entry.artifact_locator,
        )
        projected.append(
            GldArtifactRequest(
                entry.stable_identity,
                entry.gazette_class,
                entry.issue_kind,
                entry.publication_date,
                bound.endpoint_id,
                bound.endpoint_version,
                bound.url,
                window.listing_fingerprint,
            )
        )
    return tuple(projected)


class GldSessionPort(Protocol):
    """Acquisition-owned browser session lifecycle boundary."""

    def establish(self, request: GldSessionRequest) -> GldSessionGrant:
        """Establish one sanitized local GLD browser-session grant."""
        ...

    def invalidate(self, session_id: str) -> None:
        """Discard one protected local session by its opaque grant identity."""
        ...


class GldGazetteExchange(Protocol):
    """Provider-neutral inventory and inert artifact-fetch contract."""

    def enumerate_window(
        self, grant: GldSessionGrant, request: GldSessionRequest
    ) -> GldGazetteWindow:
        """Return one canonical, complete GLD listing window."""
        ...

    def fetch_artifact(
        self, grant: GldSessionGrant, entry: GldGazetteEntry
    ) -> OfficialTransportResponse:
        """Capture one entry through its already registered artifact endpoint."""
        ...


def gld_registered_host(request: GldSessionRequest) -> str:
    """Derive the exact GLD browser host from the request's bound inventory profile."""
    if type(request) is not GldSessionRequest:
        raise TypeError("request must be an exact GldSessionRequest")
    endpoint = _inventory_endpoint(
        request.endpoint_id,
        request.endpoint_version,
        request.source_profile_version,
        request.register_version,
        request.register_fingerprint,
    )
    hostname = urlsplit(endpoint.url).hostname
    if hostname is None:
        raise ValueError("GLD_REGISTERED_HOST_INVALID")
    return hostname


def _inventory_endpoint(
    endpoint_id: object,
    endpoint_version: object,
    source_profile_version: object,
    register_version: object,
    register_fingerprint: object,
) -> OfficialEndpointContract:
    """Bind a request to the existing disabled GLD browser inventory endpoint."""
    source, endpoint = _registered_gld_endpoint(
        endpoint_id,
        endpoint_version,
        source_profile_version,
        register_version,
        register_fingerprint,
    )
    if (
        source.source_id != GLD_SOURCE_ID
        or endpoint.access_mode is not EndpointAccessMode.BROWSER_SESSION
        or not endpoint.complete_inventory_required
        or endpoint.signal_use is not SignalUse.COMPLETE_INVENTORY
        or endpoint.evidence_role != "MODERN_GAZETTE_INVENTORY"
    ):
        raise ValueError("GLD_ENDPOINT_ROLE_INVALID")
    return endpoint


def _artifact_endpoint(
    endpoint_id: object,
    endpoint_version: object,
    source_profile_version: object,
    register_version: object,
    register_fingerprint: object,
) -> OfficialEndpointContract:
    """Bind each entry to the existing disabled GLD artifact endpoint."""
    source, endpoint = _registered_gld_endpoint(
        endpoint_id,
        endpoint_version,
        source_profile_version,
        register_version,
        register_fingerprint,
    )
    if (
        source.source_id != GLD_SOURCE_ID
        or endpoint.access_mode is not EndpointAccessMode.BROWSER_SESSION
        or endpoint.complete_inventory_required
        or endpoint.signal_use is not SignalUse.NOT_A_SIGNAL
        or endpoint.evidence_role != "ISSUED_GAZETTE_ARTIFACT"
    ):
        raise ValueError("GLD_ARTIFACT_ENDPOINT_ROLE_INVALID")
    return endpoint


def _registered_gld_endpoint(
    endpoint_id: object,
    endpoint_version: object,
    source_profile_version: object,
    register_version: object,
    register_fingerprint: object,
) -> tuple[OfficialSourceProfile, OfficialEndpointContract]:
    """Resolve identity only; this never enables or calls the source endpoint."""
    registered_endpoint_id = exact_identifier(endpoint_id, "endpoint_id", "sep")
    exact_endpoint_version = exact_text(endpoint_version, "endpoint_version")
    exact_source_profile_version = exact_text(source_profile_version, "source_profile_version")
    exact_register_version = exact_text(register_version, "register_version")
    _fingerprint(register_fingerprint, "register_fingerprint")
    register = load_hk_legislation_source_register()
    if (
        register.register_version != exact_register_version
        or register.fingerprint != register_fingerprint
    ):
        raise ValueError("GLD_REGISTER_PROFILE_DRIFT")
    try:
        source, endpoint = register.resolve_registered_endpoint(registered_endpoint_id)
    except LookupError as error:
        raise ValueError("GLD_ENDPOINT_NOT_ADMITTED") from error
    if source.source_id != GLD_SOURCE_ID:
        raise ValueError("GLD_ENDPOINT_NOT_ADMITTED")
    if endpoint.version != exact_endpoint_version or source.version != exact_source_profile_version:
        raise ValueError("GLD_ENDPOINT_PROFILE_DRIFT")
    return source, endpoint


def _iso_date(value: object, field: str) -> date:
    """Require a calendar date in its one canonical ISO representation."""
    text = exact_text(value, field)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(f"{field} must be an exact ISO date")
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field} must be an exact ISO date") from error


def _utc_timestamp(value: object, field: str) -> datetime:
    """Require a canonical whole-second UTC timestamp with an explicit offset."""
    text = exact_text(value, field)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", text) is None:
        raise ValueError(f"{field} must be an exact UTC ISO timestamp")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field} must be an exact UTC ISO timestamp") from error
    if parsed.tzinfo is not UTC:
        raise ValueError(f"{field} must be an exact UTC ISO timestamp")
    return parsed


def _fingerprint(value: object, field: str) -> None:
    """Require the canonical lower-case SHA-256 fingerprint representation."""
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        raise ValueError(f"{field} must be an exact SHA-256 fingerprint")


def _artifact_locator(endpoint: OfficialEndpointContract, value: object) -> None:
    """Validate one publisher locator through the shared bounded-template resolver."""
    text = exact_text(value, "artifact_locator")
    if _locator_exceeds_input_limit(text) or _encoded_locator_is_unsafe(text):
        raise ValueError("GLD_ARTIFACT_LOCATOR_INVALID")
    try:
        bind_official_endpoint_locator(
            endpoint,
            placeholder="issued_artifact_locator",
            locator=text,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("GLD_ARTIFACT_LOCATOR_INVALID") from error


def _encoded_locator_is_unsafe(value: str) -> bool:
    """Reject unsafe characters through each bounded, strict decode layer."""
    decoded = value
    for _ in range(_MAX_PERCENT_DECODE_DEPTH):
        if _unicode_locator_is_unsafe(decoded):
            return True
        next_value = _strict_percent_decode(decoded)
        if next_value is None:
            return True
        if next_value == decoded:
            return False
        decoded = next_value
    if _unicode_locator_is_unsafe(decoded):
        return True
    next_value = _strict_percent_decode(decoded)
    return next_value is None or next_value != decoded


def _strict_percent_decode(value: str) -> str | None:
    """Decode one percent-escape layer only when it is valid strict UTF-8."""
    if not _percent_escapes_are_valid(value):
        return None
    try:
        return unquote_to_bytes(value).decode("utf-8", "strict")
    except UnicodeDecodeError, UnicodeEncodeError:
        return None


def _percent_escapes_are_valid(value: str) -> bool:
    """Reject every incomplete or non-hex escape before interpreting bytes."""
    percent_index = value.find("%")
    while percent_index != -1:
        if (
            percent_index + 2 >= len(value)
            or value[percent_index + 1] not in _HEX_DIGITS
            or value[percent_index + 2] not in _HEX_DIGITS
        ):
            return False
        percent_index = value.find("%", percent_index + 3)
    return True


def _unicode_locator_is_unsafe(value: str) -> bool:
    """Reject ambiguous path syntax and unsafe Unicode publisher-locator text."""
    return (
        any(character in value for character in ("\\", "?", "#", "{", "}"))
        or any(category(character) in _UNSAFE_LOCATOR_UNICODE_CATEGORIES for character in value)
        or any(segment in {"", ".", ".."} for segment in value.split("/"))
    )


def _locator_exceeds_input_limit(value: str) -> bool:
    """Bound one publisher-relative path before decoding or URL-template work.

    A GLD artifact locator is one path inserted into a registered URL template,
    not a document title or body.  512 Unicode characters and 1,024 UTF-8 bytes
    comfortably exceed the short publisher identifiers expected for that path,
    while limiting hostile listing input before any decode pass.
    """
    if len(value) > _MAX_ARTIFACT_LOCATOR_CHARACTERS:
        return True
    try:
        return len(value.encode("utf-8")) > _MAX_ARTIFACT_LOCATOR_UTF8_BYTES
    except UnicodeEncodeError:
        return True


def _listing_fingerprint(request: GldSessionRequest, entries: tuple[GldGazetteEntry, ...]) -> str:
    """Fingerprint exactly the immutable inventory facts, preserving their order."""
    projection = {
        "source_id": request.source_id,
        "endpoint_id": request.endpoint_id,
        "endpoint_version": request.endpoint_version,
        "source_profile_version": request.source_profile_version,
        "register_version": request.register_version,
        "register_fingerprint": request.register_fingerprint,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "language": request.language,
        "observation_cutoff": request.observation_cutoff,
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
