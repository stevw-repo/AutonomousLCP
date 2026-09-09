"""Provider-neutral Hong Kong Judiciary inventory and observation contracts.

The source boundary exposes exact registered procedures and typed observations;
it does not perform transport or grant source, processing, or release authority.
Addressed artifacts remain separate work from listing enumeration.
"""

from __future__ import annotations

import re
import unicodedata
import weakref
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol
from urllib.parse import urlsplit

from asklegal_contracts import canonicalize
from asklegal_contracts.errors import ContractViolation
from asklegal_contracts.json_types import checked_json_value

from .hk_cases_official import HongKongCasesSourceProfile, load_hk_cases_source_register
from .model import HttpMethod, exact_text
from .official import EndpointInvocationKind, OfficialEndpointContract, SignalUse
from .official_http import OfficialTransportResponse

_EARLIEST_DECISION_DATE = "1997-07-01"
_INVENTORY_SOURCE_ID = "HK-CASE-JUDICIARY-LRS-INVENTORY"
_JUDGMENT_SOURCE_ID = "HK-CASE-JUDICIARY-JUDGMENT"
_TRANSLATION_SOURCE_ID = "HK-CASE-JUDICIARY-TRANSLATION"
_MAX_PAGE_SIZE = 500
_MAX_PAGE_COUNT = 10_000
_MAX_TOTAL_ENTRIES = 1_000_000
_MAX_TEXT_CHARACTERS = 1_024
_MAX_RELATIONSHIPS = 64
_MAX_ARTIFACTS = 16
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY = re.compile(r"^[a-z][a-z0-9-]{2,127}$")
_CANONICAL_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_ACCOUNTING_PROJECTION_SCHEMA = "asklegal.hk-judiciary-accounting-projection/v1"
_OBSERVATION_ENDPOINTS = {
    "CURRENT_LIST": (
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "sep_000000000000000000000000000000000000000000000202",
        "JUDICIARY_CURRENT_JUDGMENTS",
        "text/html",
        False,
    ),
    "RSS": (
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "sep_000000000000000000000000000000000000000000000203",
        "JUDICIARY_ALL_COURTS_RSS",
        "application/rss+xml",
        False,
    ),
    "YEAR_RECONCILIATION": (
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "sep_000000000000000000000000000000000000000000000204",
        "JUDICIARY_ADVANCED_YEAR_SEARCH",
        "text/html",
        True,
    ),
    "JUDGMENT_ARTIFACT": (
        "HK-CASE-JUDICIARY-JUDGMENT",
        "sep_000000000000000000000000000000000000000000000206",
        "JUDICIARY_DYNAMIC_JUDGMENT_DETAIL",
        "text/html",
        False,
    ),
}
_CURRENT_LIST_SESSION_TARGET_ID = "sep_000000000000000000000000000000000000000000000205"


class JudiciarySourceErrorCode(StrEnum):
    """Closed fail-visible Judiciary listing failures."""

    CONTRACT_INVALID = "JUDICIARY_CONTRACT_INVALID"
    INVENTORY_INCOMPLETE = "JUDICIARY_INVENTORY_INCOMPLETE"
    PARTITION_INVALID = "JUDICIARY_PARTITION_INVALID"
    PAGE_INVALID = "JUDICIARY_PAGE_INVALID"
    PROVENANCE_INVALID = "JUDICIARY_PROVENANCE_INVALID"


class JudiciarySourceError(ValueError):
    """One exact source-neutral enumeration rejection."""

    code: JudiciarySourceErrorCode

    def __init__(self, code: JudiciarySourceErrorCode) -> None:
        """Create one error carrying its closed reason code."""
        self.code = code
        super().__init__(code.value)


class JudiciaryCourtFamily(StrEnum):
    """The four and only four V1 issuing-court partitions."""

    CFA = "CFA"
    CA = "CA"
    CFI = "CFI"
    CT = "CT"


class JudiciaryLanguage(StrEnum):
    """Closed language roles for separately listed Judiciary artifacts."""

    ENGLISH = "ENGLISH"
    TRADITIONAL_CHINESE = "TRADITIONAL_CHINESE"


class JudiciaryArtifactRole(StrEnum):
    """Original authority and its linked optional official translation."""

    ORIGINAL = "ORIGINAL"
    TRANSLATION = "TRANSLATION"


class JudiciaryArtifactClass(StrEnum):
    """Accepted original written-decision classes under ADR 0046."""

    JUDGMENT = "JUDGMENT"
    REASONS_FOR_JUDGMENT = "REASONS_FOR_JUDGMENT"
    REASONS_FOR_VERDICT = "REASONS_FOR_VERDICT"
    REASONS_FOR_SENTENCE = "REASONS_FOR_SENTENCE"
    MISCELLANEOUS_WRITTEN_DECISION = "MISCELLANEOUS_WRITTEN_DECISION"


class JudiciaryObservationKind(StrEnum):
    """Closed registered procedures used by the Cases acquisition worker."""

    CURRENT_LIST = "CURRENT_LIST"
    RSS = "RSS"
    YEAR_RECONCILIATION = "YEAR_RECONCILIATION"
    JUDGMENT_ARTIFACT = "JUDGMENT_ARTIFACT"


@dataclass(frozen=True, slots=True)
class JudiciaryObservationContract:
    """One exact checked-in endpoint binding without direct-call authority."""

    kind: JudiciaryObservationKind
    source_id: str
    endpoint_id: str
    endpoint_version: str
    locator: str
    media_type: str
    max_bytes: int
    proves_complete: bool
    proves_no_change: bool

    def __post_init__(self) -> None:
        """Reject hand-built or drifted observation contracts."""
        if type(self.kind) is not JudiciaryObservationKind:
            raise ValueError("JUDICIARY_OBSERVATION_CONTRACT_INVALID")
        expected = _registered_observation_endpoint(self.kind)
        if (
            self.source_id,
            self.endpoint_id,
            self.endpoint_version,
            self.locator,
            self.media_type,
            self.max_bytes,
            self.proves_complete,
            self.proves_no_change,
        ) != expected:
            raise ValueError("JUDICIARY_OBSERVATION_CONTRACT_INVALID")


def registered_judiciary_observation_contract(
    kind: JudiciaryObservationKind,
) -> JudiciaryObservationContract:
    """Resolve one exact current procedure through the checked-in Cases register."""
    if type(kind) is not JudiciaryObservationKind:
        raise ValueError("JUDICIARY_OBSERVATION_CONTRACT_INVALID")
    values = _registered_observation_endpoint(kind)
    return JudiciaryObservationContract(kind, *values)


def registered_judiciary_current_list_route() -> tuple[str, str]:
    """Return the sole registered entry and redirect-target chain for current listings."""
    entry = registered_judiciary_observation_contract(JudiciaryObservationKind.CURRENT_LIST)
    target = load_hk_cases_source_register().resolve_redirect_target(
        entry_endpoint_id=entry.endpoint_id,
        method=HttpMethod.GET,
        target_endpoint_id=_CURRENT_LIST_SESSION_TARGET_ID,
    )
    return entry.locator, target.url


def _registered_observation_endpoint(
    kind: JudiciaryObservationKind,
) -> tuple[str, str, str, str, str, int, bool, bool]:
    expected_source, endpoint_id, expected_name, media_type, proves_complete = (
        _OBSERVATION_ENDPOINTS[kind.value]
    )
    endpoint = load_hk_cases_source_register().resolve_registered_endpoint(endpoint_id)
    expected_signal = (
        SignalUse.COMPLETE_INVENTORY
        if proves_complete
        else SignalUse.NOT_A_SIGNAL
        if kind is JudiciaryObservationKind.JUDGMENT_ARTIFACT
        else SignalUse.DISCOVERY_ONLY
    )
    if (
        type(endpoint) is not OfficialEndpointContract
        or endpoint.source_id != expected_source
        or endpoint.name != expected_name
        or endpoint.invocation_kind is not EndpointInvocationKind.DIRECT_REQUEST
        or endpoint.signal_use is not expected_signal
        or endpoint.complete_inventory_required is not proves_complete
        or endpoint.proves_no_change
        or media_type not in endpoint.media_types
        or not endpoint.enabled
    ):
        raise ValueError("JUDICIARY_OBSERVATION_CONTRACT_INVALID")
    return (
        expected_source,
        endpoint.endpoint_id,
        endpoint.version,
        endpoint.url,
        media_type,
        endpoint.max_bytes,
        proves_complete,
        False,
    )


@dataclass(frozen=True, slots=True)
class JudiciaryListingRequest:
    """One bounded court/date partition, bound to the checked-in source register."""

    source_id: str
    source_profile_version: str
    register_version: str
    register_fingerprint: str
    observation_cutoff: str
    court_family: JudiciaryCourtFamily
    page_size: int = 100
    maximum_pages: int = _MAX_PAGE_COUNT
    earliest_decision_date: str = dataclass_field(init=False, default=_EARLIEST_DECISION_DATE)
    request_fingerprint: str = dataclass_field(init=False, default="")

    def __post_init__(self) -> None:
        _validate_request_fields(self)
        object.__setattr__(self, "request_fingerprint", _request_fingerprint(self))

    @classmethod
    def baseline(
        cls,
        observation_cutoff: str,
        court_family: JudiciaryCourtFamily,
        *,
        page_size: int = 100,
        maximum_pages: int = _MAX_PAGE_COUNT,
    ) -> JudiciaryListingRequest:
        """Build the fixed V1 baseline request without a caller-controlled start date."""
        profile = _checked_in_inventory_profile()
        return cls(
            source_id=profile.source_id,
            source_profile_version=profile.version,
            register_version=_checked_in_register_version(),
            register_fingerprint=_checked_in_register_fingerprint(),
            observation_cutoff=_canonicalize_utc(observation_cutoff),
            court_family=court_family,
            page_size=page_size,
            maximum_pages=maximum_pages,
        )


@dataclass(frozen=True, slots=True)
class JudiciaryArtifactLocator:
    """One identity-only official original or optional translation locator."""

    artifact_identity: str
    listing_identity: str
    source_id: str
    role: JudiciaryArtifactRole
    language: JudiciaryLanguage
    opinion_or_reasons_identity: str
    media_type: str
    official_locator: str
    correction_identity: str | None
    reissue_identity: str | None
    replaces_artifact_identity: str | None

    def __post_init__(self) -> None:
        _identity(self.artifact_identity, "artifact_identity")
        _identity(self.listing_identity, "listing_identity")
        source_id = _exact_text(self.source_id, "source_id")
        if source_id not in {_JUDGMENT_SOURCE_ID, _TRANSLATION_SOURCE_ID}:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if (
            type(self.role) is not JudiciaryArtifactRole
            or type(self.language) is not JudiciaryLanguage
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if self.role is JudiciaryArtifactRole.ORIGINAL and source_id != _JUDGMENT_SOURCE_ID:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if self.role is JudiciaryArtifactRole.TRANSLATION and source_id != _TRANSLATION_SOURCE_ID:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        _bounded_text(self.media_type, "media_type")
        _identity(self.opinion_or_reasons_identity, "opinion_or_reasons_identity")
        _official_locator(self.official_locator)
        _optional_identity(self.correction_identity, "correction_identity")
        _optional_identity(self.reissue_identity, "reissue_identity")
        _optional_identity(self.replaces_artifact_identity, "replaces_artifact_identity")
        if self.replaces_artifact_identity == self.artifact_identity:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)


@dataclass(frozen=True, slots=True)
class JudiciaryListingEntry:
    """One preserved official listing row; it is neither a decision nor an artifact."""

    listing_identity: str
    case_name: str
    proceeding_numbers: tuple[str, ...]
    neutral_citations: tuple[str, ...]
    reported_citations: tuple[str, ...]
    court_family: JudiciaryCourtFamily
    decision_date: str
    language: JudiciaryLanguage
    artifact_class: JudiciaryArtifactClass
    artifact_role: JudiciaryArtifactRole
    opinion_or_reasons_identities: tuple[str, ...]
    artifacts: tuple[JudiciaryArtifactLocator, ...]
    correction_identities: tuple[str, ...]
    reissue_identities: tuple[str, ...]
    replacement_identities: tuple[str, ...]
    translation_listing_identities: tuple[str, ...]
    listing_source_id: str
    listing_source_profile_version: str
    listing_register_version: str
    listing_register_fingerprint: str
    listing_observed_at: str
    listing_fact_fingerprint: str = dataclass_field(init=False, default="")

    @property
    def relationship_work_identities(self) -> tuple[str, ...]:
        """Expose every source-declared relationship for durable worker graph retention."""
        return tuple(
            sorted(
                {
                    *(artifact.artifact_identity for artifact in self.artifacts),
                    *self.correction_identities,
                    *self.reissue_identities,
                    *self.replacement_identities,
                    *self.translation_listing_identities,
                    *self.opinion_or_reasons_identities,
                    *(f"proceeding:{value}" for value in self.proceeding_numbers),
                }
            )
        )

    def __post_init__(self) -> None:
        _identity(self.listing_identity, "listing_identity")
        _bounded_text(self.case_name, "case_name")
        _exact_text_tuple(self.proceeding_numbers, "proceeding_numbers", minimum=1)
        _exact_text_tuple(self.neutral_citations, "neutral_citations")
        _exact_text_tuple(self.reported_citations, "reported_citations")
        if type(self.court_family) is not JudiciaryCourtFamily:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        _iso_date(self.decision_date, "decision_date")
        if type(self.language) is not JudiciaryLanguage:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if type(self.artifact_class) is not JudiciaryArtifactClass:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if type(self.artifact_role) is not JudiciaryArtifactRole:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        _identity_tuple(
            self.opinion_or_reasons_identities,
            "opinion_or_reasons_identities",
            minimum=1,
        )
        if (
            type(self.artifacts) is not tuple
            or not self.artifacts
            or len(self.artifacts) > _MAX_ARTIFACTS
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if any(type(item) is not JudiciaryArtifactLocator for item in self.artifacts):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        artifacts = self.artifacts
        for artifact in artifacts:
            artifact.__post_init__()
        if any(item.listing_identity != self.listing_identity for item in artifacts):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if len({item.artifact_identity for item in artifacts}) != len(artifacts):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if tuple(item.artifact_identity for item in artifacts) != tuple(
            sorted(item.artifact_identity for item in artifacts)
        ) or len({item.official_locator for item in artifacts}) != len(artifacts):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if not any(
            item.role is self.artifact_role and item.language is self.language for item in artifacts
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if {item.opinion_or_reasons_identity for item in artifacts} != set(
            self.opinion_or_reasons_identities
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        _identity_tuple(self.correction_identities, "correction_identities")
        _identity_tuple(self.reissue_identities, "reissue_identities")
        _identity_tuple(self.replacement_identities, "replacement_identities")
        _identity_tuple(self.translation_listing_identities, "translation_listing_identities")
        if self.listing_identity in (
            self.correction_identities
            + self.reissue_identities
            + self.replacement_identities
            + self.translation_listing_identities
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        listing_source_id = _exact_text(self.listing_source_id, "listing_source_id")
        if listing_source_id != _INVENTORY_SOURCE_ID:
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
        _bounded_text(self.listing_source_profile_version, "listing_source_profile_version")
        _bounded_text(self.listing_register_version, "listing_register_version")
        _fingerprint(self.listing_register_fingerprint, "listing_register_fingerprint")
        _canonical_utc(self.listing_observed_at, "listing_observed_at")
        fingerprint = _entry_fingerprint(self)
        if self.listing_fact_fingerprint and self.listing_fact_fingerprint != fingerprint:
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
        object.__setattr__(self, "listing_fact_fingerprint", fingerprint)


@dataclass(frozen=True, slots=True)
class JudiciaryListingPage:
    """A publisher page with frozen complete-inventory totals and member identities."""

    request_fingerprint: str
    page_identity: str
    page_number: int
    declared_total_pages: int
    declared_total_entries: int
    entries: tuple[JudiciaryListingEntry, ...]
    page_fingerprint: str = dataclass_field(init=False, default="")

    def __post_init__(self) -> None:
        _fingerprint(self.request_fingerprint, "request_fingerprint")
        _identity(self.page_identity, "page_identity")
        _positive_bounded(self.page_number, "page_number", _MAX_PAGE_COUNT)
        _positive_bounded(self.declared_total_pages, "declared_total_pages", _MAX_PAGE_COUNT)
        if (
            type(self.declared_total_entries) is not int
            or not 0 <= self.declared_total_entries <= _MAX_TOTAL_ENTRIES
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if type(self.entries) is not tuple or len(self.entries) > _MAX_PAGE_SIZE:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        if any(type(entry) is not JudiciaryListingEntry for entry in self.entries):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        for entry in self.entries:
            entry.__post_init__()
        identities = tuple(entry.listing_identity for entry in self.entries)
        if len(identities) != len(set(identities)):
            raise JudiciarySourceError(JudiciarySourceErrorCode.PAGE_INVALID)
        fingerprint = _page_fingerprint(self)
        if self.page_fingerprint and self.page_fingerprint != fingerprint:
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
        object.__setattr__(self, "page_fingerprint", fingerprint)


@dataclass(frozen=True, slots=True)
class JudiciaryListingExhausted:
    """An explicit bounded publisher exhaustion signal after one declared final page."""

    request_fingerprint: str
    exhausted_after_page: int
    exhaustion_fingerprint: str

    def __post_init__(self) -> None:
        _fingerprint(self.request_fingerprint, "request_fingerprint")
        _positive_bounded(self.exhausted_after_page, "exhausted_after_page", _MAX_PAGE_COUNT)
        _fingerprint(self.exhaustion_fingerprint, "exhaustion_fingerprint")
        if self.exhaustion_fingerprint != _exhaustion_fingerprint(self):
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)

    @classmethod
    def create(
        cls, *, request: JudiciaryListingRequest, exhausted_after_page: int
    ) -> JudiciaryListingExhausted:
        """Build one exact terminal signal bound to the request and final page number."""
        if type(request) is not JudiciaryListingRequest:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        _validate_request_fields(request)
        if request.request_fingerprint != _request_fingerprint(request):
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
        return cls(
            request_fingerprint=request.request_fingerprint,
            exhausted_after_page=exhausted_after_page,
            exhaustion_fingerprint=_sha256(
                {
                    "exhausted_after_page": exhausted_after_page,
                    "request_fingerprint": request.request_fingerprint,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class JudiciaryPageAccounting:
    """Canonical page-level proof retained by an issued complete inventory."""

    page_identity: str
    page_number: int
    page_fingerprint: str
    declared_total_pages: int
    declared_total_entries: int
    member_listing_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        _identity(self.page_identity, "page_identity")
        _positive_bounded(self.page_number, "page_number", _MAX_PAGE_COUNT)
        _fingerprint(self.page_fingerprint, "page_fingerprint")
        _positive_bounded(self.declared_total_pages, "declared_total_pages", _MAX_PAGE_COUNT)
        if (
            type(self.declared_total_entries) is not int
            or not 0 <= self.declared_total_entries <= _MAX_TOTAL_ENTRIES
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
        _page_member_identity_tuple(self.member_listing_identities)


class JudiciaryExchange(Protocol):
    """Listing and separately addressed-artifact contract for a future acquisition worker."""

    def fetch_listing_page(
        self, request: JudiciaryListingRequest, page_number: int
    ) -> JudiciaryListingPage | JudiciaryListingExhausted:
        """Return exactly one page of one bound official listing observation."""
        ...

    def fetch_judgment(
        self, entry: JudiciaryListingEntry, artifact: JudiciaryArtifactLocator
    ) -> OfficialTransportResponse:
        """Fetch one already addressed artifact outside enumeration."""
        ...


@dataclass(frozen=True, slots=True, weakref_slot=True)
class JudiciaryInventory:
    """Complete sorted listing inventory, issued only by the enumerator."""

    request_fingerprint: str
    source_id: str
    source_profile_version: str
    register_version: str
    register_fingerprint: str
    court_family: JudiciaryCourtFamily
    earliest_decision_date: str
    observation_cutoff: str
    page_size: int
    maximum_pages: int
    page_accounting: tuple[JudiciaryPageAccounting, ...]
    terminal_exhaustion: JudiciaryListingExhausted
    entries: tuple[JudiciaryListingEntry, ...]
    inventory_fingerprint: str

    def __post_init__(self) -> None:
        _validate_inventory_replay(self)

    @property
    def page_identities(self) -> tuple[str, ...]:
        """Return page identities for callers that need a compact traversal projection."""
        return tuple(page.page_identity for page in self.page_accounting)

    def assert_enumerator_issued(self) -> None:
        """Reject caller-built or mutated aggregates that lack live enumerator provenance."""
        _require_inventory_replay(self)
        issued = _INVENTORY_ISSUANCE.get(id(self))
        if (
            issued is None
            or issued.reference() is not self
            or issued.snapshot != self.inventory_fingerprint
            or self.inventory_fingerprint != issued.snapshot
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)


@dataclass(frozen=True, slots=True)
class _IssuedInventory:
    reference: weakref.ReferenceType[JudiciaryInventory]
    snapshot: str


_INVENTORY_ISSUANCE: dict[int, _IssuedInventory] = {}


def _require_inventory_replay(inventory: JudiciaryInventory) -> None:
    """Normalize one recursive replay proof for durable and live public boundaries."""
    try:
        _validate_inventory_replay(inventory)
    except JudiciarySourceError as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID) from error
    except (
        ContractViolation,
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID) from error


def _validate_inventory_replay(inventory: JudiciaryInventory) -> None:
    """Reconstruct every retained completeness fact without live issuance state."""
    _validate_inventory_request_facts(inventory)
    entries_by_identity, declared_entries = _validate_inventory_member_partition(inventory)
    _reconcile_accounted_pages(inventory, entries_by_identity, declared_entries)
    if type(inventory.terminal_exhaustion) is not JudiciaryListingExhausted:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    inventory.terminal_exhaustion.__post_init__()
    if (
        inventory.terminal_exhaustion.request_fingerprint != inventory.request_fingerprint
        or inventory.terminal_exhaustion.exhausted_after_page != len(inventory.page_accounting)
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
    _fingerprint(inventory.inventory_fingerprint, "inventory_fingerprint")
    if inventory.inventory_fingerprint != _inventory_fingerprint(inventory):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)


def _validate_inventory_request_facts(inventory: JudiciaryInventory) -> None:
    """Validate and fingerprint the full retained request projection."""
    _fingerprint(inventory.request_fingerprint, "request_fingerprint")
    _validate_source_binding(inventory)
    if type(inventory.court_family) is not JudiciaryCourtFamily:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    if inventory.earliest_decision_date != _EARLIEST_DECISION_DATE:
        raise JudiciarySourceError(JudiciarySourceErrorCode.PARTITION_INVALID)
    _iso_date(inventory.earliest_decision_date, "earliest_decision_date")
    _canonical_utc(inventory.observation_cutoff, "observation_cutoff")
    if type(inventory.page_size) is not int or not 1 <= inventory.page_size <= _MAX_PAGE_SIZE:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    _positive_bounded(inventory.maximum_pages, "maximum_pages", _MAX_PAGE_COUNT)
    if inventory.request_fingerprint != _request_fingerprint_from_facts(inventory):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)


def _validate_inventory_member_partition(
    inventory: JudiciaryInventory,
) -> tuple[dict[str, JudiciaryListingEntry], int]:
    """Reconcile declared totals, exact entries, and member identity partition."""
    if type(inventory.page_accounting) is not tuple or not inventory.page_accounting:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    if any(type(item) is not JudiciaryPageAccounting for item in inventory.page_accounting):
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    for page in inventory.page_accounting:
        page.__post_init__()
    page_numbers = tuple(page.page_number for page in inventory.page_accounting)
    page_identities = tuple(page.page_identity for page in inventory.page_accounting)
    if (
        page_numbers != tuple(range(1, len(page_numbers) + 1))
        or len(page_identities) != len(set(page_identities))
        or len(inventory.page_accounting) > inventory.maximum_pages
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
    if type(inventory.entries) is not tuple or any(
        type(item) is not JudiciaryListingEntry for item in inventory.entries
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    identities = tuple(entry.listing_identity for entry in inventory.entries)
    if (
        len(inventory.entries) > _MAX_TOTAL_ENTRIES
        or identities != tuple(sorted(identities))
        or len(identities) != len(set(identities))
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
    for entry in inventory.entries:
        entry.__post_init__()
        _validate_entry_against_inventory(entry, inventory)
    entries_by_identity = {entry.listing_identity: entry for entry in inventory.entries}
    declared_pages = inventory.page_accounting[0].declared_total_pages
    declared_entries = inventory.page_accounting[0].declared_total_entries
    accounted_members = tuple(
        member for page in inventory.page_accounting for member in page.member_listing_identities
    )
    if (
        declared_pages != len(inventory.page_accounting)
        or declared_pages > inventory.maximum_pages
        or declared_entries != len(inventory.entries)
        or declared_entries > _MAX_TOTAL_ENTRIES
        or (declared_entries and declared_entries < declared_pages)
        or declared_entries > inventory.page_size * declared_pages
        or any(
            page.declared_total_pages != declared_pages
            or page.declared_total_entries != declared_entries
            for page in inventory.page_accounting
        )
        or tuple(sorted(accounted_members)) != identities
        or len(accounted_members) != len(set(accounted_members))
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
    _validate_listing_progress(
        declared_total_pages=declared_pages,
        declared_total_entries=declared_entries,
        page_size=inventory.page_size,
        member_counts=tuple(
            len(page.member_listing_identities) for page in inventory.page_accounting
        ),
        error_code=JudiciarySourceErrorCode.PROVENANCE_INVALID,
    )
    return entries_by_identity, declared_entries


def _reconcile_accounted_pages(
    inventory: JudiciaryInventory,
    entries_by_identity: dict[str, JudiciaryListingEntry],
    declared_entries: int,
) -> None:
    """Rebuild every retained page fingerprint from its exact member entries."""
    for accounting in inventory.page_accounting:
        try:
            members = tuple(
                entries_by_identity[identity] for identity in accounting.member_listing_identities
            )
        except KeyError as error:
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID) from error
        if declared_entries and not members:
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
        reconstructed_page = JudiciaryListingPage(
            request_fingerprint=inventory.request_fingerprint,
            page_identity=accounting.page_identity,
            page_number=accounting.page_number,
            declared_total_pages=accounting.declared_total_pages,
            declared_total_entries=accounting.declared_total_entries,
            entries=members,
        )
        if accounting.page_fingerprint != reconstructed_page.page_fingerprint:
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)


def _validate_entry_against_inventory(
    entry: JudiciaryListingEntry, inventory: JudiciaryInventory
) -> None:
    """Bind one retained entry to the exact retained inventory partition."""
    if (
        entry.listing_source_id != inventory.source_id
        or entry.listing_source_profile_version != inventory.source_profile_version
        or entry.listing_register_version != inventory.register_version
        or entry.listing_register_fingerprint != inventory.register_fingerprint
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
    decision_date = _iso_date(entry.decision_date, "decision_date")
    earliest = _iso_date(inventory.earliest_decision_date, "earliest_decision_date")
    cutoff = _canonical_utc(inventory.observation_cutoff, "observation_cutoff")
    if (
        entry.court_family is not inventory.court_family
        or decision_date < earliest
        or decision_date > cutoff.date()
        or _canonical_utc(entry.listing_observed_at, "listing_observed_at") > cutoff
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PARTITION_INVALID)


def _validate_listing_progress(
    *,
    declared_total_pages: int,
    declared_total_entries: int,
    page_size: int,
    member_counts: tuple[int, ...],
    error_code: JudiciarySourceErrorCode,
) -> None:
    """Apply the one listing reachability invariant used by live and retained evidence."""
    if (
        not 1 <= declared_total_pages <= _MAX_PAGE_COUNT
        or not 0 <= declared_total_entries <= _MAX_TOTAL_ENTRIES
        or not 1 <= page_size <= _MAX_PAGE_SIZE
        or not member_counts
        or len(member_counts) > declared_total_pages
    ):
        raise JudiciarySourceError(error_code)
    if declared_total_entries == 0:
        if declared_total_pages != 1 or member_counts != (0,):
            raise JudiciarySourceError(error_code)
        return
    if (
        declared_total_entries < declared_total_pages
        or declared_total_entries > declared_total_pages * page_size
    ):
        raise JudiciarySourceError(error_code)
    running_members = 0
    for accepted_pages, member_count in enumerate(member_counts, start=1):
        if not 1 <= member_count <= page_size:
            raise JudiciarySourceError(error_code)
        running_members += member_count
        remaining_pages = declared_total_pages - accepted_pages
        minimum_reachable = running_members + remaining_pages
        maximum_reachable = running_members + remaining_pages * page_size
        if not minimum_reachable <= declared_total_entries <= maximum_reachable:
            raise JudiciarySourceError(error_code)


def enumerate_judiciary_inventory(
    exchange: JudiciaryExchange, request: JudiciaryListingRequest
) -> JudiciaryInventory:
    """Fetch a complete frozen listing set without fetching any judgment artifact."""
    if type(request) is not JudiciaryListingRequest:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    _validate_request_fields(request)
    if request.request_fingerprint != _request_fingerprint(request):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
    request_snapshot = request.request_fingerprint
    first = _fetch_page(exchange, request, 1)
    _assert_request_fresh(request, request_snapshot)
    _validate_page_against_request(first, request, 1)
    accepted_pages = [(first, _page_fingerprint(first))]
    total_pages = first.declared_total_pages
    total_entries = first.declared_total_entries
    if total_pages > request.maximum_pages:
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
    _validate_listing_progress(
        declared_total_pages=total_pages,
        declared_total_entries=total_entries,
        page_size=request.page_size,
        member_counts=(len(first.entries),),
        error_code=JudiciarySourceErrorCode.INVENTORY_INCOMPLETE,
    )
    if total_entries == 0:
        terminal = _require_exhaustion(exchange, request, 1)
        _assert_request_and_pages_fresh(request, request_snapshot, accepted_pages)
        return _issue_inventory(request, tuple(page for page, _ in accepted_pages), terminal)
    if not first.entries:
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
    pages = [first]
    seen_page_identities = {first.page_identity}
    seen_listing_identities = {entry.listing_identity for entry in first.entries}
    for number in range(2, total_pages + 1):
        page = _fetch_page(exchange, request, number)
        _assert_request_and_pages_fresh(request, request_snapshot, accepted_pages)
        _validate_page_against_request(page, request, number)
        if (
            page.declared_total_pages != total_pages
            or page.declared_total_entries != total_entries
            or not page.entries
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
        page_listing_identities = tuple(entry.listing_identity for entry in page.entries)
        if page.page_identity in seen_page_identities or any(
            identity in seen_listing_identities for identity in page_listing_identities
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
        pages.append(page)
        _validate_listing_progress(
            declared_total_pages=total_pages,
            declared_total_entries=total_entries,
            page_size=request.page_size,
            member_counts=tuple(len(accepted.entries) for accepted in pages),
            error_code=JudiciarySourceErrorCode.INVENTORY_INCOMPLETE,
        )
        accepted_pages.append((page, _page_fingerprint(page)))
        seen_page_identities.add(page.page_identity)
        seen_listing_identities.update(page_listing_identities)
    entries = tuple(entry for page in pages for entry in page.entries)
    if len(entries) != total_entries:
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
    terminal = _require_exhaustion(exchange, request, total_pages)
    _assert_request_and_pages_fresh(request, request_snapshot, accepted_pages)
    return _issue_inventory(request, tuple(pages), terminal)


def validate_judiciary_inventory(inventory: JudiciaryInventory) -> JudiciaryInventory:
    """Require self-reproducing inventory proof at every public consumer boundary."""
    if type(inventory) is not JudiciaryInventory:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    _require_inventory_replay(inventory)
    return inventory


def serialize_judiciary_accounting_projection(inventory: JudiciaryInventory) -> bytes:
    """Serialize one live-issued inventory into detached source-neutral accounting bytes."""
    if type(inventory) is not JudiciaryInventory:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    try:
        before_full = _inventory_serialization_snapshot(inventory)
        before_projection = _accounting_projection_bytes(inventory)
        inventory.__post_init__()
        inventory.assert_enumerator_issued()
        after_full = _inventory_serialization_snapshot(inventory)
        after_projection = _accounting_projection_bytes(inventory)
        _require_unchanged_inventory_projection(
            before_full, before_projection, after_full, after_projection
        )
    except JudiciarySourceError:
        raise
    except Exception as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID) from error
    return before_projection


def _require_unchanged_inventory_projection(
    before_full: bytes,
    before_projection: bytes,
    after_full: bytes,
    after_projection: bytes,
) -> None:
    if after_full != before_full or after_projection != before_projection:
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)


def _fetch_page(
    exchange: JudiciaryExchange, request: JudiciaryListingRequest, page_number: int
) -> JudiciaryListingPage:
    try:
        response = exchange.fetch_listing_page(request, page_number)
    except JudiciarySourceError:
        raise
    except Exception as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE) from error
    if type(response) is JudiciaryListingExhausted:
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
    page = response
    if type(page) is not JudiciaryListingPage:
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
    return page


def _require_exhaustion(
    exchange: JudiciaryExchange, request: JudiciaryListingRequest, final_page_number: int
) -> JudiciaryListingExhausted:
    """Perform one bounded N+1 probe and require its exact typed exhaustion signal."""
    try:
        response = exchange.fetch_listing_page(request, final_page_number + 1)
    except JudiciarySourceError:
        raise
    except Exception as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE) from error
    if type(response) is not JudiciaryListingExhausted:
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
    try:
        response.__post_init__()
    except JudiciarySourceError as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID) from error
    if (
        response.request_fingerprint != request.request_fingerprint
        or response.exhausted_after_page != final_page_number
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
    return response


def _assert_request_fresh(request: JudiciaryListingRequest, snapshot: str) -> None:
    """Reject a request object whose primitive facts changed across an exchange call."""
    try:
        _validate_request_fields(request)
    except JudiciarySourceError as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID) from error
    if request.request_fingerprint != snapshot or _request_fingerprint(request) != snapshot:
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)


def _assert_request_and_pages_fresh(
    request: JudiciaryListingRequest,
    request_snapshot: str,
    accepted_pages: list[tuple[JudiciaryListingPage, str]],
) -> None:
    """Revalidate every accepted primitive snapshot at each exchange boundary and before issue."""
    _assert_request_fresh(request, request_snapshot)
    for page, snapshot in accepted_pages:
        try:
            page.__post_init__()
        except JudiciarySourceError as error:
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID) from error
        if _page_fingerprint(page) != snapshot:
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)


def _validate_page_against_request(
    page: JudiciaryListingPage, request: JudiciaryListingRequest, expected_number: int
) -> None:
    try:
        page.__post_init__()
    except JudiciarySourceError as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID) from error
    if (
        page.request_fingerprint != request.request_fingerprint
        or page.page_number != expected_number
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
    if len(page.entries) > request.page_size:
        raise JudiciarySourceError(JudiciarySourceErrorCode.INVENTORY_INCOMPLETE)
    for entry in page.entries:
        if (
            entry.listing_source_id != request.source_id
            or entry.listing_source_profile_version != request.source_profile_version
            or entry.listing_register_version != request.register_version
            or entry.listing_register_fingerprint != request.register_fingerprint
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)
        decision_date = _iso_date(entry.decision_date, "decision_date")
        if (
            entry.court_family is not request.court_family
            or decision_date < _iso_date(request.earliest_decision_date, "earliest_decision_date")
            or decision_date
            > _canonical_utc(request.observation_cutoff, "observation_cutoff").date()
            or _canonical_utc(entry.listing_observed_at, "listing_observed_at")
            > _canonical_utc(request.observation_cutoff, "observation_cutoff")
        ):
            raise JudiciarySourceError(JudiciarySourceErrorCode.PARTITION_INVALID)


def _issue_inventory(
    request: JudiciaryListingRequest,
    pages: tuple[JudiciaryListingPage, ...],
    terminal: JudiciaryListingExhausted,
) -> JudiciaryInventory:
    entries = tuple(
        sorted(
            (entry for page in pages for entry in page.entries),
            key=lambda item: item.listing_identity,
        )
    )
    inventory = JudiciaryInventory(
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
        page_accounting=tuple(_page_accounting(page) for page in pages),
        terminal_exhaustion=terminal,
        entries=entries,
        inventory_fingerprint=_inventory_fingerprint_components(request, pages, entries, terminal),
    )
    snapshot = _inventory_fingerprint(inventory)

    inventory_id = id(inventory)

    def cleanup(reference: weakref.ReferenceType[JudiciaryInventory]) -> None:
        current = _INVENTORY_ISSUANCE.get(inventory_id)
        if current is not None and current.reference is reference:
            _INVENTORY_ISSUANCE.pop(inventory_id, None)

    reference = weakref.ref(inventory, cleanup)
    _INVENTORY_ISSUANCE[inventory_id] = _IssuedInventory(reference, snapshot)
    inventory.assert_enumerator_issued()
    return inventory


def _validate_request_fields(request: JudiciaryListingRequest) -> None:
    _validate_source_binding(request)
    if type(request.court_family) is not JudiciaryCourtFamily:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    _canonical_utc(request.observation_cutoff, "observation_cutoff")
    if request.earliest_decision_date != _EARLIEST_DECISION_DATE:
        raise JudiciarySourceError(JudiciarySourceErrorCode.PARTITION_INVALID)
    _iso_date(request.earliest_decision_date, "earliest_decision_date")
    if type(request.page_size) is not int or not 1 <= request.page_size <= _MAX_PAGE_SIZE:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    _positive_bounded(request.maximum_pages, "maximum_pages", _MAX_PAGE_COUNT)


def _validate_source_binding(request: JudiciaryListingRequest | JudiciaryInventory) -> None:
    """Bind live and retained request facts to the exact checked-in Cases profile."""
    _bounded_text(request.source_id, "source_id")
    _bounded_text(request.source_profile_version, "source_profile_version")
    _bounded_text(request.register_version, "register_version")
    _fingerprint(request.register_fingerprint, "register_fingerprint")
    profile = _checked_in_inventory_profile()
    if (
        request.source_id != profile.source_id
        or request.source_profile_version != profile.version
        or request.register_version != _checked_in_register_version()
        or request.register_fingerprint != _checked_in_register_fingerprint()
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.PROVENANCE_INVALID)


def _checked_in_inventory_profile() -> HongKongCasesSourceProfile:
    register = load_hk_cases_source_register()
    return next(source for source in register.sources if source.source_id == _INVENTORY_SOURCE_ID)


def _checked_in_register_version() -> str:
    return load_hk_cases_source_register().register_version


def _checked_in_register_fingerprint() -> str:
    return load_hk_cases_source_register().fingerprint


def _request_fingerprint(request: JudiciaryListingRequest) -> str:
    return _request_fingerprint_from_facts(request)


def _request_fingerprint_from_facts(
    request: JudiciaryListingRequest | JudiciaryInventory,
) -> str:
    """Fingerprint the retained primitive request projection used by inventories."""
    return _sha256(
        {
            "court_family": request.court_family.value,
            "earliest_decision_date": request.earliest_decision_date,
            "maximum_pages": request.maximum_pages,
            "observation_cutoff": request.observation_cutoff,
            "page_size": request.page_size,
            "register_fingerprint": request.register_fingerprint,
            "register_version": request.register_version,
            "source_id": request.source_id,
            "source_profile_version": request.source_profile_version,
        }
    )


def _page_fingerprint(page: JudiciaryListingPage) -> str:
    return _sha256(
        {
            "declared_total_entries": page.declared_total_entries,
            "declared_total_pages": page.declared_total_pages,
            "entries": [
                _entry_projection(entry)
                for entry in sorted(page.entries, key=lambda item: item.listing_identity)
            ],
            "page_identity": page.page_identity,
            "page_number": page.page_number,
            "request_fingerprint": page.request_fingerprint,
        }
    )


def _inventory_fingerprint(inventory: JudiciaryInventory) -> str:
    return _sha256(_inventory_projection(inventory))


def _inventory_projection(inventory: JudiciaryInventory) -> dict[str, object]:
    return {
        "entries": [_entry_projection(entry) for entry in inventory.entries],
        "page_accounting": [
            _page_accounting_projection(page) for page in inventory.page_accounting
        ],
        "court_family": inventory.court_family.value,
        "earliest_decision_date": inventory.earliest_decision_date,
        "observation_cutoff": inventory.observation_cutoff,
        "page_size": inventory.page_size,
        "maximum_pages": inventory.maximum_pages,
        "register_fingerprint": inventory.register_fingerprint,
        "register_version": inventory.register_version,
        "request_fingerprint": inventory.request_fingerprint,
        "source_id": inventory.source_id,
        "source_profile_version": inventory.source_profile_version,
        "terminal_exhaustion": {
            "exhausted_after_page": inventory.terminal_exhaustion.exhausted_after_page,
            "exhaustion_fingerprint": inventory.terminal_exhaustion.exhaustion_fingerprint,
            "request_fingerprint": inventory.terminal_exhaustion.request_fingerprint,
        },
    }


def _inventory_serialization_snapshot(inventory: JudiciaryInventory) -> bytes:
    return _canonical_bytes(
        {
            "inventory_fingerprint": inventory.inventory_fingerprint,
            "listing_fact_fingerprints": [
                entry.listing_fact_fingerprint for entry in inventory.entries
            ],
            "retained_inventory": _inventory_projection(inventory),
        }
    )


def _accounting_projection_bytes(inventory: JudiciaryInventory) -> bytes:
    _fingerprint(inventory.inventory_fingerprint, "inventory_fingerprint")
    if type(inventory.court_family) is not JudiciaryCourtFamily:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    _iso_date(inventory.earliest_decision_date, "earliest_decision_date")
    _canonical_utc(inventory.observation_cutoff, "observation_cutoff")
    if type(inventory.entries) is not tuple or any(
        type(entry) is not JudiciaryListingEntry for entry in inventory.entries
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    entries = tuple(_accounting_entry_projection(entry) for entry in inventory.entries)
    identities = tuple(
        _identity(entry["listing_identity"], "listing_identity") for entry in entries
    )
    if identities != tuple(sorted(identities)) or len(identities) != len(set(identities)):
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    projection: dict[str, object] = {
        "schema_id": _ACCOUNTING_PROJECTION_SCHEMA,
        "source_inventory_fingerprint": inventory.inventory_fingerprint,
        "court_family": inventory.court_family.value,
        "earliest_decision_date": inventory.earliest_decision_date,
        "observation_cutoff": inventory.observation_cutoff,
        "entries": list(entries),
    }
    projection["projection_fingerprint"] = _sha256(projection)
    return _canonical_bytes(projection)


def _accounting_entry_projection(entry: JudiciaryListingEntry) -> dict[str, object]:
    _identity(entry.listing_identity, "listing_identity")
    if type(entry.court_family) is not JudiciaryCourtFamily:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    _iso_date(entry.decision_date, "decision_date")
    _fingerprint(entry.listing_fact_fingerprint, "listing_fact_fingerprint")
    return {
        "listing_identity": entry.listing_identity,
        "court_family": entry.court_family.value,
        "decision_date": entry.decision_date,
        "listing_fact_fingerprint": entry.listing_fact_fingerprint,
    }


def _inventory_fingerprint_components(
    request: JudiciaryListingRequest,
    pages: tuple[JudiciaryListingPage, ...],
    entries: tuple[JudiciaryListingEntry, ...],
    terminal: JudiciaryListingExhausted,
) -> str:
    return _sha256(
        {
            "entries": [_entry_projection(entry) for entry in entries],
            "page_accounting": [
                _page_accounting_projection(_page_accounting(page)) for page in pages
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
    )


def _entry_projection(entry: JudiciaryListingEntry) -> dict[str, object]:
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


def _entry_fingerprint(entry: JudiciaryListingEntry) -> str:
    """Recompute one listing-fact digest without trusting its displayed value."""
    return _sha256(_entry_projection(entry))


def _exhaustion_fingerprint(exhaustion: JudiciaryListingExhausted) -> str:
    return _sha256(
        {
            "exhausted_after_page": exhaustion.exhausted_after_page,
            "request_fingerprint": exhaustion.request_fingerprint,
        }
    )


def _page_accounting(page: JudiciaryListingPage) -> JudiciaryPageAccounting:
    return JudiciaryPageAccounting(
        page_identity=page.page_identity,
        page_number=page.page_number,
        page_fingerprint=page.page_fingerprint,
        declared_total_pages=page.declared_total_pages,
        declared_total_entries=page.declared_total_entries,
        member_listing_identities=tuple(sorted(entry.listing_identity for entry in page.entries)),
    )


def _page_accounting_projection(page: JudiciaryPageAccounting) -> dict[str, object]:
    return {
        "declared_total_entries": page.declared_total_entries,
        "declared_total_pages": page.declared_total_pages,
        "member_listing_identities": list(page.member_listing_identities),
        "page_fingerprint": page.page_fingerprint,
        "page_identity": page.page_identity,
        "page_number": page.page_number,
    }


def _sha256(value: object) -> str:
    return f"sha256:{sha256(_canonical_bytes(value)).hexdigest()}"


def _canonical_bytes(value: object) -> bytes:
    try:
        return canonicalize(checked_json_value(value))
    except (ContractViolation, TypeError, ValueError, UnicodeError) as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID) from error


def _canonicalize_utc(value: object) -> str:
    text = _exact_text(value, "observation_cutoff")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID) from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed) or parsed.microsecond:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_utc(value: object, field: str) -> datetime:
    text = _exact_text(value, field)
    if _CANONICAL_UTC.fullmatch(text) is None:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID) from error
    if parsed.tzinfo is not UTC:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    return parsed


def _iso_date(value: object, field: str) -> date:
    text = _exact_text(value, field)
    if _DATE.fullmatch(text) is None:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID) from error


def _identity(value: object, field: str) -> str:
    text = _exact_text(value, field)
    if _IDENTITY.fullmatch(text) is None:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    return text


def _optional_identity(value: object, field: str) -> None:
    if value is not None:
        _identity(value, field)


def _bounded_text(value: object, field: str) -> str:
    text = _exact_text(value, field)
    if len(text) > _MAX_TEXT_CHARACTERS:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    return text


def _exact_text_tuple(value: tuple[str, ...], _field: str, *, minimum: int = 0) -> None:
    if type(value) is not tuple:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    if not minimum <= len(value) <= _MAX_RELATIONSHIPS:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    for item in value:
        if len(_exact_text(item, _field)) > _MAX_TEXT_CHARACTERS:
            raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    if len(set(value)) != len(value) or value != tuple(sorted(value)):
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)


def _identity_tuple(value: tuple[str, ...], _field: str, *, minimum: int = 0) -> None:
    if type(value) is not tuple:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    if not minimum <= len(value) <= _MAX_RELATIONSHIPS:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    for item in value:
        _identity(item, _field)
    if len(set(value)) != len(value) or value != tuple(sorted(value)):
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)


def _page_member_identity_tuple(value: tuple[str, ...]) -> None:
    """Accept one canonical page-sized member identity projection."""
    if type(value) is not tuple or len(value) > _MAX_PAGE_SIZE:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    for item in value:
        _identity(item, "member_listing_identities")
    if len(set(value)) != len(value) or value != tuple(sorted(value)):
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)


def _positive_bounded(value: object, _field: str, maximum: int) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)


def _fingerprint(value: object, _field: str) -> None:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)


def _official_locator(value: object) -> None:
    locator = _bounded_text(value, "official_locator")
    try:
        parsed = urlsplit(locator)
    except ValueError as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID) from error
    if (
        not locator.startswith("/")
        or parsed.scheme
        or parsed.netloc
        or ".." in parsed.path.split("/")
        or any(ord(character) < 32 or ord(character) == 127 for character in locator)
    ):
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)


def _exact_text(value: object, field: str) -> str:
    """Return one exact, JSON-safe, control-free text leaf or a closed source error."""
    try:
        text = exact_text(value, field)
        checked_json_value(text)
    except (ContractViolation, TypeError, ValueError, UnicodeError) as error:
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID) from error
    if any(unicodedata.category(character) == "Cc" for character in text):
        raise JudiciarySourceError(JudiciarySourceErrorCode.CONTRACT_INVALID)
    return text
