"""Versioned official-source contracts for Hong Kong Legislation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import SourceOutageImpact

from .model import HttpMethod, exact_identifier, exact_string_tuple, exact_text

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_POLICY_SOURCE_ID = re.compile(r"^HK-(?:LEG|CASE)-[A-Z0-9-]+$")
_MAX_REGISTER_BYTES = 1_000_000
HK_LEGISLATION_SOURCE_IDS = frozenset(
    {
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-VERIFIED-COPIES",
        "HK-LEG-HKEL-ASSISTED-COPIES",
        "HK-LEG-HKEL-PAST-INVENTORY",
        "HK-LEG-HKEL-PAST-DATA",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-OFFICIAL-GAZETTE-ARCHIVE",
        "HK-LEG-HKEL-GAZETTE-BACKCAPTURE",
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
        "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
    }
)


class PublisherRightsState(StrEnum):
    """Source-specific publisher-rights conclusion."""

    PUBLISHED_TERMS_PERMIT = "PUBLISHED_TERMS_PERMIT"
    LEGAL_TEAM_CLEARED = "LEGAL_TEAM_CLEARED"
    NAMED_OWNER_ACCEPTANCE_REQUIRED = "NAMED_OWNER_ACCEPTANCE_REQUIRED"
    PRIOR_WRITTEN_AUTHORIZATION_REQUIRED = "PRIOR_WRITTEN_AUTHORIZATION_REQUIRED"
    UNVERIFIED = "UNVERIFIED"


class OfficialSourceState(StrEnum):
    """Whether a real source may currently be called by an acquisition worker."""

    CONFIGURED = "CONFIGURED"
    PARTIALLY_CONFIGURED = "PARTIALLY_CONFIGURED"
    BLOCKED = "BLOCKED"
    OUT_OF_SCOPE_V1 = "OUT_OF_SCOPE_V1"


class EndpointAccessMode(StrEnum):
    """Closed transport or holding class for an official endpoint."""

    DIRECT_HTTP = "DIRECT_HTTP"
    BROWSER_SESSION = "BROWSER_SESSION"
    CATALOGUE_DISCOVERY = "CATALOGUE_DISCOVERY"
    PHYSICAL_HOLDING = "PHYSICAL_HOLDING"


class SignalUse(StrEnum):
    """Limits what an endpoint observation may establish."""

    NOT_A_SIGNAL = "NOT_A_SIGNAL"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"
    COMPLETE_INVENTORY = "COMPLETE_INVENTORY"


@dataclass(frozen=True, slots=True)
class OfficialAccessAuthorization:
    """The user's bounded project authorization, separate from publisher rights."""

    authorized_on: str
    scope: str
    source_ids: tuple[str, ...]
    rss_policy: str
    forbidden_effects: tuple[str, ...]

    def __post_init__(self) -> None:
        exact_text(self.authorized_on, "authorized_on")
        exact_text(self.scope, "scope")
        exact_text(self.rss_policy, "rss_policy")
        exact_string_tuple(self.source_ids, "source_ids")
        exact_string_tuple(self.forbidden_effects, "forbidden_effects")
        if frozenset(self.source_ids) != HK_LEGISLATION_SOURCE_IDS:
            raise ValueError("authorization must name the complete 14-source universe")
        if self.rss_policy != "DISCOVERY_OR_CHANGE_SIGNAL_ONLY":
            raise ValueError("RSS must remain discovery or change signal only")


@dataclass(frozen=True, slots=True)
class LegalClearanceAttestation:
    """User-reported project legal clearance, separate from publisher notices."""

    attestation_id: str
    confirmed_on: str
    authority: str
    reported_by: str
    source_ids: tuple[str, ...]
    conclusion: str

    def __post_init__(self) -> None:
        exact_identifier(self.attestation_id, "attestation_id", "lca")
        for field in ("confirmed_on", "authority", "reported_by", "conclusion"):
            exact_text(getattr(self, field), field)
        exact_string_tuple(self.source_ids, "source_ids")
        if frozenset(self.source_ids) != HK_LEGISLATION_SOURCE_IDS:
            raise ValueError("legal clearance must name the complete 14-source universe")
        if self.authority != "ASKLEGAL_LEGAL_TEAM":
            raise ValueError("legal clearance authority must remain exact")
        if self.reported_by != "PROJECT_USER":
            raise ValueError("legal clearance reporter must remain exact")
        if self.conclusion != "ALL_SOURCE_RIGHTS_AND_PERMISSIONS_GREEN":
            raise ValueError("legal clearance conclusion must remain exact")


@dataclass(frozen=True, slots=True)
class PublisherRightsEvidence:
    """One observed official rights statement, without legal inference beyond it."""

    evidence_id: str
    publisher: str
    url: str
    observed_on: str
    conclusion: PublisherRightsState
    conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        exact_identifier(self.evidence_id, "evidence_id", "rte")
        for field in ("publisher", "observed_on"):
            exact_text(getattr(self, field), field)
        _https_url(self.url, "url")
        if type(self.conclusion) is not PublisherRightsState:
            raise TypeError("conclusion must be an exact PublisherRightsState")
        exact_string_tuple(self.conditions, "conditions")


@dataclass(frozen=True, slots=True)
class OfficialEndpointContract:
    """One exact official locator or bounded locator template."""

    endpoint_id: str
    source_id: str
    version: str
    name: str
    url: str
    access_mode: EndpointAccessMode
    methods: tuple[HttpMethod, ...]
    media_types: tuple[str, ...]
    max_bytes: int
    complete_inventory_required: bool
    signal_use: SignalUse
    proves_no_change: bool
    evidence_role: str
    enabled: bool

    def __post_init__(self) -> None:
        exact_identifier(self.endpoint_id, "endpoint_id", "sep")
        _policy_source_id(self.source_id)
        for field in ("version", "name", "evidence_role"):
            exact_text(getattr(self, field), field)
        _https_url(self.url, "url", allow_template=True)
        if type(self.access_mode) is not EndpointAccessMode:
            raise TypeError("access_mode must be an exact EndpointAccessMode")
        if (
            type(self.methods) is not tuple
            or not self.methods
            or any(type(item) is not HttpMethod for item in self.methods)
        ):
            raise TypeError("methods must be a non-empty exact tuple of HttpMethod")
        exact_string_tuple(self.media_types, "media_types")
        if type(self.max_bytes) is not int or self.max_bytes < 1:
            raise TypeError("max_bytes must be a positive exact integer")
        if type(self.complete_inventory_required) is not bool:
            raise TypeError("complete_inventory_required must be an exact boolean")
        if type(self.signal_use) is not SignalUse:
            raise TypeError("signal_use must be an exact SignalUse")
        if type(self.proves_no_change) is not bool or type(self.enabled) is not bool:
            raise TypeError("endpoint booleans must be exact")
        if self.signal_use is SignalUse.DISCOVERY_ONLY and (
            self.complete_inventory_required or self.proves_no_change
        ):
            raise ValueError("discovery signals cannot prove completeness or no-change")
        if self.proves_no_change and self.signal_use is not SignalUse.COMPLETE_INVENTORY:
            raise ValueError("only a complete inventory may prove no-change")
        if self.access_mode is EndpointAccessMode.PHYSICAL_HOLDING and self.enabled:
            raise ValueError("physical holdings cannot be enabled as HTTP endpoints")


@dataclass(frozen=True, slots=True)
class OfficialSourceProfile:
    """One stable legal-policy source bound to mutable official endpoints."""

    source_id: str
    registered_source_id: str
    version: str
    endpoint_ids: tuple[str, ...]
    rights_state: PublisherRightsState
    operational_state: OfficialSourceState
    outage_impact: SourceOutageImpact
    rights_evidence_ids: tuple[str, ...]
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        _policy_source_id(self.source_id)
        exact_identifier(self.registered_source_id, "registered_source_id", "src")
        exact_text(self.version, "version")
        exact_string_tuple(self.endpoint_ids, "endpoint_ids")
        for endpoint_id in self.endpoint_ids:
            exact_identifier(endpoint_id, "endpoint_id", "sep")
        if type(self.rights_state) is not PublisherRightsState:
            raise TypeError("rights_state must be an exact PublisherRightsState")
        if type(self.operational_state) is not OfficialSourceState:
            raise TypeError("operational_state must be an exact OfficialSourceState")
        if type(self.outage_impact) is not SourceOutageImpact:
            raise TypeError("outage_impact must be an exact SourceOutageImpact")
        exact_string_tuple(self.rights_evidence_ids, "rights_evidence_ids")
        if type(self.blockers) is not tuple or any(
            type(item) is not str or not item for item in self.blockers
        ):
            raise TypeError("blockers must be an exact tuple of non-empty strings")
        if self.operational_state in {
            OfficialSourceState.CONFIGURED,
            OfficialSourceState.PARTIALLY_CONFIGURED,
        }:
            if self.rights_state not in {
                PublisherRightsState.PUBLISHED_TERMS_PERMIT,
                PublisherRightsState.LEGAL_TEAM_CLEARED,
            }:
                raise ValueError("callable sources require admitted rights")
            if self.operational_state is OfficialSourceState.CONFIGURED and self.blockers:
                raise ValueError("configured sources cannot retain blockers")
            if (
                self.operational_state is OfficialSourceState.PARTIALLY_CONFIGURED
                and not self.blockers
            ):
                raise ValueError("partially configured sources require explicit blockers")
        elif not self.blockers:
            raise ValueError("blocked sources require explicit blockers")


@dataclass(frozen=True, slots=True)
class HongKongLegislationSourceRegister:
    """Complete external-access register for the 14 accepted source roles."""

    schema_id: str
    schema_version: str
    register_id: str
    register_version: str
    effective_date: str
    status: str
    fingerprint: str
    authorization: OfficialAccessAuthorization
    legal_clearance: LegalClearanceAttestation
    rights_evidence: tuple[PublisherRightsEvidence, ...]
    sources: tuple[OfficialSourceProfile, ...]
    endpoints: tuple[OfficialEndpointContract, ...]

    def __post_init__(self) -> None:
        for field in (
            "schema_id",
            "schema_version",
            "register_version",
            "effective_date",
            "status",
            "fingerprint",
        ):
            exact_text(getattr(self, field), field)
        exact_identifier(self.register_id, "register_id", "hsr")
        if type(self.authorization) is not OfficialAccessAuthorization:
            raise TypeError("authorization must be exact")
        if type(self.legal_clearance) is not LegalClearanceAttestation:
            raise TypeError("legal_clearance must be exact")
        if type(self.rights_evidence) is not tuple or type(self.sources) is not tuple:
            raise TypeError("register collections must be exact tuples")
        if type(self.endpoints) is not tuple:
            raise TypeError("endpoints must be an exact tuple")
        source_map = {item.source_id: item for item in self.sources}
        endpoint_map = {item.endpoint_id: item for item in self.endpoints}
        rights_ids = {item.evidence_id for item in self.rights_evidence}
        if len(source_map) != len(self.sources) or len(endpoint_map) != len(self.endpoints):
            raise ValueError("source and endpoint identities must be unique")
        if len(rights_ids) != len(self.rights_evidence):
            raise ValueError("rights evidence identities must be unique")
        if frozenset(source_map) != HK_LEGISLATION_SOURCE_IDS:
            raise ValueError("register must contain the complete 14-source universe")
        if frozenset(self.legal_clearance.source_ids) != frozenset(source_map):
            raise ValueError("legal clearance must cover every registered source")
        for source in self.sources:
            if not set(source.rights_evidence_ids).issubset(rights_ids):
                raise ValueError("source rights evidence must resolve")
            for endpoint_id in source.endpoint_ids:
                endpoint = endpoint_map.get(endpoint_id)
                if endpoint is None or endpoint.source_id != source.source_id:
                    raise ValueError("every endpoint must resolve to its owning source")
                if (
                    source.operational_state is OfficialSourceState.CONFIGURED
                    and not endpoint.enabled
                ):
                    raise ValueError("configured sources require every endpoint enabled")
                if source.operational_state is OfficialSourceState.BLOCKED and endpoint.enabled:
                    raise ValueError("blocked sources cannot enable an endpoint")
            if source.operational_state is OfficialSourceState.PARTIALLY_CONFIGURED:
                enabled = tuple(endpoint_map[item].enabled for item in source.endpoint_ids)
                if not any(enabled) or all(enabled):
                    raise ValueError("partial source requires both enabled and disabled endpoints")
        referenced = {item for source in self.sources for item in source.endpoint_ids}
        if referenced != set(endpoint_map):
            raise ValueError("unowned endpoint contracts are forbidden")
        if self.status != "PARTIALLY_CONFIGURED_FAIL_CLOSED":
            raise ValueError("real-source register must remain explicitly fail-closed")

    @property
    def configured_source_ids(self) -> tuple[str, ...]:
        """Return sources whose user and publisher authorization are complete."""
        return tuple(
            sorted(
                item.source_id
                for item in self.sources
                if item.operational_state is OfficialSourceState.CONFIGURED
            )
        )

    @property
    def blocked_source_ids(self) -> tuple[str, ...]:
        """Return sources that remain unusable for live acquisition."""
        return tuple(
            sorted(
                item.source_id
                for item in self.sources
                if item.operational_state is OfficialSourceState.BLOCKED
            )
        )

    @property
    def partially_configured_source_ids(self) -> tuple[str, ...]:
        """Return sources with at least one callable and one blocked endpoint."""
        return tuple(
            sorted(
                item.source_id
                for item in self.sources
                if item.operational_state is OfficialSourceState.PARTIALLY_CONFIGURED
            )
        )

    @property
    def operationally_admitted(self) -> bool:
        """Remain false until every source role is configured without blockers."""
        return not self.blocked_source_ids and not self.partially_configured_source_ids

    def resolve_endpoint(
        self,
        endpoint_id: str,
        endpoint_version: str,
    ) -> tuple[OfficialSourceProfile, OfficialEndpointContract]:
        """Resolve one exact enabled endpoint or fail before transport."""
        exact_identifier(endpoint_id, "endpoint_id", "sep")
        exact_text(endpoint_version, "endpoint_version")
        endpoint = next(
            (item for item in self.endpoints if item.endpoint_id == endpoint_id),
            None,
        )
        if endpoint is None or endpoint.version != endpoint_version:
            raise LookupError("official endpoint or exact version is unavailable")
        source = next(item for item in self.sources if item.source_id == endpoint.source_id)
        if source.operational_state is OfficialSourceState.BLOCKED or not endpoint.enabled:
            raise PermissionError("official source is not operationally configured")
        return source, endpoint


def load_hk_legislation_source_register(
    path: Path | None = None,
) -> HongKongLegislationSourceRegister:
    """Load and strictly validate the checked-in official-source register."""
    register_path = path or Path(__file__).with_name("hk_legislation_source_register.json")
    raw = register_path.read_bytes()
    document = _object(parse_json_bytes(raw, max_bytes=_MAX_REGISTER_BYTES), "source register")
    expected_fingerprint = _register_fingerprint(document)
    fingerprint = _string(document.get("fingerprint"), "fingerprint")
    if fingerprint != expected_fingerprint:
        raise ValueError("source register fingerprint does not match its canonical content")
    _exact_keys(
        document,
        frozenset(
            {
                "schema_id",
                "schema_version",
                "register_id",
                "register_version",
                "effective_date",
                "status",
                "fingerprint",
                "authorization",
                "legal_clearance",
                "rights_evidence",
                "sources",
                "endpoints",
            }
        ),
        "source register",
    )
    authorization = _parse_authorization(_object(document["authorization"], "authorization"))
    legal_clearance = _parse_legal_clearance(
        _object(document["legal_clearance"], "legal_clearance")
    )
    rights = tuple(
        _parse_rights(_object(item, "rights evidence"))
        for item in _array(document["rights_evidence"], "rights_evidence")
    )
    sources = tuple(
        _parse_source(_object(item, "source")) for item in _array(document["sources"], "sources")
    )
    endpoints = tuple(
        _parse_endpoint(_object(item, "endpoint"))
        for item in _array(document["endpoints"], "endpoints")
    )
    return HongKongLegislationSourceRegister(
        _string(document["schema_id"], "schema_id"),
        _string(document["schema_version"], "schema_version"),
        _string(document["register_id"], "register_id"),
        _string(document["register_version"], "register_version"),
        _string(document["effective_date"], "effective_date"),
        _string(document["status"], "status"),
        fingerprint,
        authorization,
        legal_clearance,
        rights,
        sources,
        endpoints,
    )


def _parse_authorization(document: dict[str, JsonValue]) -> OfficialAccessAuthorization:
    _exact_keys(
        document,
        frozenset({"authorized_on", "scope", "source_ids", "rss_policy", "forbidden_effects"}),
        "authorization",
    )
    return OfficialAccessAuthorization(
        _string(document["authorized_on"], "authorized_on"),
        _string(document["scope"], "scope"),
        _strings(document["source_ids"], "source_ids"),
        _string(document["rss_policy"], "rss_policy"),
        _strings(document["forbidden_effects"], "forbidden_effects"),
    )


def _parse_legal_clearance(document: dict[str, JsonValue]) -> LegalClearanceAttestation:
    _exact_keys(
        document,
        frozenset(
            {
                "attestation_id",
                "confirmed_on",
                "authority",
                "reported_by",
                "source_ids",
                "conclusion",
            }
        ),
        "legal clearance",
    )
    return LegalClearanceAttestation(
        _string(document["attestation_id"], "attestation_id"),
        _string(document["confirmed_on"], "confirmed_on"),
        _string(document["authority"], "authority"),
        _string(document["reported_by"], "reported_by"),
        _strings(document["source_ids"], "source_ids"),
        _string(document["conclusion"], "conclusion"),
    )


def _parse_rights(document: dict[str, JsonValue]) -> PublisherRightsEvidence:
    _exact_keys(
        document,
        frozenset({"evidence_id", "publisher", "url", "observed_on", "conclusion", "conditions"}),
        "rights evidence",
    )
    return PublisherRightsEvidence(
        _string(document["evidence_id"], "evidence_id"),
        _string(document["publisher"], "publisher"),
        _string(document["url"], "url"),
        _string(document["observed_on"], "observed_on"),
        PublisherRightsState(_string(document["conclusion"], "conclusion")),
        _strings(document["conditions"], "conditions"),
    )


def _parse_source(document: dict[str, JsonValue]) -> OfficialSourceProfile:
    _exact_keys(
        document,
        frozenset(
            {
                "source_id",
                "registered_source_id",
                "version",
                "endpoint_ids",
                "rights_state",
                "operational_state",
                "outage_impact",
                "rights_evidence_ids",
                "blockers",
            }
        ),
        "source",
    )
    return OfficialSourceProfile(
        _string(document["source_id"], "source_id"),
        _string(document["registered_source_id"], "registered_source_id"),
        _string(document["version"], "version"),
        _strings(document["endpoint_ids"], "endpoint_ids"),
        PublisherRightsState(_string(document["rights_state"], "rights_state")),
        OfficialSourceState(_string(document["operational_state"], "operational_state")),
        SourceOutageImpact(_string(document["outage_impact"], "outage_impact")),
        _strings(document["rights_evidence_ids"], "rights_evidence_ids"),
        _optional_strings(document["blockers"], "blockers"),
    )


def _parse_endpoint(document: dict[str, JsonValue]) -> OfficialEndpointContract:
    _exact_keys(
        document,
        frozenset(
            {
                "endpoint_id",
                "source_id",
                "version",
                "name",
                "url",
                "access_mode",
                "methods",
                "media_types",
                "max_bytes",
                "complete_inventory_required",
                "signal_use",
                "proves_no_change",
                "evidence_role",
                "enabled",
            }
        ),
        "endpoint",
    )
    return OfficialEndpointContract(
        _string(document["endpoint_id"], "endpoint_id"),
        _string(document["source_id"], "source_id"),
        _string(document["version"], "version"),
        _string(document["name"], "name"),
        _string(document["url"], "url"),
        EndpointAccessMode(_string(document["access_mode"], "access_mode")),
        tuple(HttpMethod(item) for item in _strings(document["methods"], "methods")),
        _strings(document["media_types"], "media_types"),
        _integer(document["max_bytes"], "max_bytes"),
        _boolean(document["complete_inventory_required"], "complete_inventory_required"),
        SignalUse(_string(document["signal_use"], "signal_use")),
        _boolean(document["proves_no_change"], "proves_no_change"),
        _string(document["evidence_role"], "evidence_role"),
        _boolean(document["enabled"], "enabled"),
    )


def _register_fingerprint(document: dict[str, JsonValue]) -> str:
    projection = dict(document)
    projection.pop("fingerprint", None)
    return f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"


def _policy_source_id(value: object) -> str:
    text = exact_text(value, "source_id")
    if _POLICY_SOURCE_ID.fullmatch(text) is None:
        raise ValueError("source_id must be a stable HK Legislation or Cases source identity")
    return text


def _https_url(value: object, field: str, *, allow_template: bool = False) -> str:
    text = exact_text(value, field)
    parsed = urlsplit(text)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{field} must be one credential-free HTTPS URL")
    if parsed.fragment:
        raise ValueError(f"{field} must not contain a fragment")
    if not allow_template and ("{" in text or "}" in text):
        raise ValueError(f"{field} must not be a URL template")
    if allow_template and text.count("{") != text.count("}"):
        raise ValueError(f"{field} has an invalid template")
    return text


def _object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an exact object")
    return value


def _array(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be an exact array")
    return value


def _string(value: JsonValue, label: str) -> str:
    if type(value) is not str or not value:
        raise TypeError(f"{label} must be an exact non-empty string")
    return value


def _integer(value: JsonValue, label: str) -> int:
    if type(value) is not int or value < 1:
        raise TypeError(f"{label} must be a positive exact integer")
    return value


def _boolean(value: JsonValue, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{label} must be an exact boolean")
    return value


def _strings(value: JsonValue, label: str) -> tuple[str, ...]:
    result = tuple(_string(item, label) for item in _array(value, label))
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{label} must be non-empty and unique")
    return result


def _optional_strings(value: JsonValue, label: str) -> tuple[str, ...]:
    result = tuple(_string(item, label) for item in _array(value, label))
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


def _exact_keys(document: Mapping[str, JsonValue], expected: frozenset[str], label: str) -> None:
    if frozenset(document) != expected:
        raise ValueError(f"{label} has unknown or missing fields")
