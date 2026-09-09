"""Fail-closed official-source register for Hong Kong Cases."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import SourceOutageImpact

from .model import HttpMethod, exact_identifier, exact_text
from .official import (
    EndpointAccessMode,
    EndpointInvocationKind,
    OfficialEndpointContract,
    OfficialSourceState,
    PublisherRightsState,
    SignalUse,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_MAX_REGISTER_BYTES = 250_000
HK_CASE_SOURCE_IDS = frozenset(
    {
        "HK-CASE-COURT-REGISTRY",
        "HK-CASE-HKLII-DISCOVERY",
        "HK-CASE-JUDICIARY-JUDGMENT",
        "HK-CASE-JUDICIARY-LIBRARY",
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "HK-CASE-JUDICIARY-TRANSLATION",
        "HK-CASE-PRIVY-COUNCIL",
    }
)
HK_CASE_SOURCE_ACCESS_FORBIDDEN_EFFECTS = (
    "CORPUS_PUBLICATION",
    "DEPLOYMENT",
    "MODEL_OR_EMBEDDING_CALL",
    "PINECONE_MUTATION",
    "PRODUCTION_ROUTING",
)

_EXPECTED_SOURCE_FACTS = {
    "HK-CASE-COURT-REGISTRY": (
        "KNOWN_ITEM_AUTHENTICITY_VERSION_OR_AVAILABILITY_FALLBACK",
        "CANNOT_PROVE_COMPLETE_ONLINE_INVENTORY",
        SourceOutageImpact.AFFECTED_WORK_BLOCKING,
    ),
    "HK-CASE-HKLII-DISCOVERY": (
        "DISCOVERY_ALIAS_CITATION_AND_TREATMENT_LEADS_ONLY",
        "NEVER_PROVES_OFFICIAL_COMPLETENESS_OR_NO_CHANGE",
        SourceOutageImpact.NONBLOCKING,
    ),
    "HK-CASE-JUDICIARY-JUDGMENT": (
        "ORIGINAL_WORDING_VERSION_LANGUAGE_AND_OPINION_EVIDENCE",
        "EVERY_ACQUIRED_IN_SCOPE_DECISION_REQUIRES_ACCEPTED_ORIGINAL",
        SourceOutageImpact.AFFECTED_WORK_BLOCKING,
    ),
    "HK-CASE-JUDICIARY-LIBRARY": (
        "HISTORICAL_SUPERIOR_COURT_INVENTORY_AND_ORIGINATING_EVIDENCE",
        "EVERY_PROMISED_HISTORICAL_SCOPE_REQUIRES_COMPLETE_ENUMERATION",
        SourceOutageImpact.AFFECTED_WORK_BLOCKING,
    ),
    "HK-CASE-JUDICIARY-LRS-INVENTORY": (
        "CURRENT_OFFICIAL_LISTING_INVENTORY",
        "EVERY_DUE_COURT_YEAR_PARTITION_MUST_COMPLETE",
        SourceOutageImpact.RELEASE_BLOCKING,
    ),
    "HK-CASE-JUDICIARY-TRANSLATION": (
        "LINKED_TRANSLATION_EVIDENCE_NOT_A_SECOND_AUTHORITY",
        "TRANSLATION_ABSENCE_NEVER_CREATES_A_COVERAGE_GAP",
        SourceOutageImpact.NONBLOCKING,
    ),
    "HK-CASE-PRIVY-COUNCIL": (
        "HONG_KONG_PRIVY_COUNCIL_INVENTORY_AND_ORIGINATING_EVIDENCE",
        "EVERY_PROMISED_HKPC_SCOPE_REQUIRES_COMPLETE_ENUMERATION",
        SourceOutageImpact.AFFECTED_WORK_BLOCKING,
    ),
}


@dataclass(frozen=True, slots=True)
class HongKongCasesAccessBoundary:
    """Current implementation authority, expressly excluding source access."""

    state: str
    forbidden_effects: tuple[str, ...]

    def __post_init__(self) -> None:
        exact_text(self.state, "state")
        if self.state != "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING":
            raise ValueError("Hong Kong Cases access authority provenance drift")
        if self.forbidden_effects != HK_CASE_SOURCE_ACCESS_FORBIDDEN_EFFECTS:
            raise ValueError("Hong Kong Cases forbidden effects must remain exact")


@dataclass(frozen=True, slots=True)
class HongKongCasesSourceProfile:
    """One accepted Cases source role before an endpoint is admitted."""

    source_id: str
    registered_source_id: str
    version: str
    endpoint_ids: tuple[str, ...]
    rights_state: PublisherRightsState
    operational_state: OfficialSourceState
    outage_impact: SourceOutageImpact
    fact_authority: str
    completeness_authority: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.source_id not in HK_CASE_SOURCE_IDS:
            raise ValueError("unknown Hong Kong Cases source role")
        exact_identifier(self.registered_source_id, "registered_source_id", "src")
        exact_text(self.version, "version")
        if type(self.endpoint_ids) is not tuple:
            raise TypeError("endpoint_ids must be an exact tuple")
        for endpoint_id in self.endpoint_ids:
            exact_identifier(endpoint_id, "endpoint_id", "sep")
        if len(self.endpoint_ids) != len(set(self.endpoint_ids)):
            raise ValueError("endpoint_ids must be unique")
        if self.endpoint_ids != tuple(sorted(self.endpoint_ids)):
            raise ValueError("endpoint_ids must be sorted")
        if type(self.rights_state) is not PublisherRightsState:
            raise TypeError("rights_state must be an exact PublisherRightsState")
        if type(self.operational_state) is not OfficialSourceState:
            raise TypeError("operational_state must be an exact OfficialSourceState")
        if type(self.outage_impact) is not SourceOutageImpact:
            raise TypeError("outage_impact must be an exact SourceOutageImpact")
        exact_text(self.fact_authority, "fact_authority")
        exact_text(self.completeness_authority, "completeness_authority")
        if (
            type(self.blockers) is not tuple
            or not self.blockers
            or any(type(item) is not str or not item for item in self.blockers)
        ):
            raise TypeError("blockers must be a non-empty exact string tuple")
        if self.blockers != tuple(sorted(set(self.blockers))):
            raise ValueError("blockers must be sorted and unique")
        admitted = bool(self.endpoint_ids)
        if admitted != (
            self.rights_state is PublisherRightsState.USER_ATTESTED_PERMISSION_DOCUMENT_PENDING
            and self.operational_state is OfficialSourceState.PARTIALLY_CONFIGURED
        ):
            if admitted:
                raise ValueError("Cases endpoint authority must remain exact")
            if (
                self.rights_state is not PublisherRightsState.UNVERIFIED
                or self.operational_state is not OfficialSourceState.BLOCKED
            ):
                raise ValueError("unconfigured Cases sources must remain blocked and unverified")


@dataclass(frozen=True, slots=True)
class HongKongCasesSourceRegister:
    """Complete fail-closed access register for the seven accepted source roles."""

    schema_id: str
    schema_version: str
    register_id: str
    register_version: str
    effective_date: str
    status: str
    fingerprint: str
    access_boundary: HongKongCasesAccessBoundary
    sources: tuple[HongKongCasesSourceProfile, ...]
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
        exact_identifier(self.register_id, "register_id", "hcr")
        if self.status != "AUTHORIZED_PARTIAL_FAIL_VISIBLE":
            raise ValueError("Hong Kong Cases register authority status drift")
        if type(self.access_boundary) is not HongKongCasesAccessBoundary:
            raise TypeError("access_boundary must be exact")
        if type(self.sources) is not tuple or type(self.endpoints) is not tuple:
            raise TypeError("register collections must be exact tuples")
        if tuple(item.source_id for item in self.sources) != tuple(sorted(HK_CASE_SOURCE_IDS)):
            raise ValueError("register must contain the sorted seven-source universe")
        if len({item.registered_source_id for item in self.sources}) != len(self.sources):
            raise ValueError("registered source identities must be unique")
        endpoint_map = {item.endpoint_id: item for item in self.endpoints}
        if len(endpoint_map) != len(self.endpoints):
            raise ValueError("endpoint identities must be unique")
        referenced = {item for source in self.sources for item in source.endpoint_ids}
        if referenced != set(endpoint_map):
            raise ValueError("every endpoint must have exactly one owning source")
        for source in self.sources:
            expected = _EXPECTED_SOURCE_FACTS[source.source_id]
            if (
                source.fact_authority,
                source.completeness_authority,
                source.outage_impact,
            ) != expected:
                raise ValueError("Cases source authority drift is forbidden")
            for endpoint_id in source.endpoint_ids:
                endpoint = endpoint_map[endpoint_id]
                if endpoint.source_id != source.source_id:
                    raise ValueError("endpoint must resolve to its owning source")
                if not endpoint.enabled:
                    raise ValueError("referenced Cases endpoints must be enabled")
        redirect_target = endpoint_map.get("sep_000000000000000000000000000000000000000000000205")
        if (
            redirect_target is None
            or redirect_target.source_id != "HK-CASE-JUDICIARY-LRS-INVENTORY"
            or redirect_target.invocation_kind is not EndpointInvocationKind.REDIRECT_TARGET_ONLY
            or not redirect_target.enabled
        ):
            raise ValueError("Cases session redirect target contract drift is forbidden")
        if any(
            endpoint is not redirect_target
            and endpoint.invocation_kind is not EndpointInvocationKind.DIRECT_REQUEST
            for endpoint in self.endpoints
        ):
            raise ValueError("Cases endpoint invocation contract drift is forbidden")

    @property
    def operationally_admitted(self) -> bool:
        """Remain false while any source or endpoint lacks admission."""
        return False

    def resolve_endpoint(
        self,
        endpoint_id: str,
        endpoint_version: str,
    ) -> tuple[HongKongCasesSourceProfile, OfficialEndpointContract]:
        """Fail before transport unless a future exact register admits an endpoint."""
        exact_identifier(endpoint_id, "endpoint_id", "sep")
        exact_text(endpoint_version, "endpoint_version")
        endpoint = next(
            (
                item
                for item in self.endpoints
                if item.endpoint_id == endpoint_id and item.version == endpoint_version
            ),
            None,
        )
        if endpoint is None:
            raise LookupError("Cases endpoint or exact version is unavailable")
        source = next(item for item in self.sources if item.source_id == endpoint.source_id)
        if (
            source.operational_state is OfficialSourceState.BLOCKED
            or not endpoint.enabled
            or endpoint.invocation_kind is not EndpointInvocationKind.DIRECT_REQUEST
        ):
            raise PermissionError("Cases redirect targets cannot be directly invoked")
        return source, endpoint

    def resolve_registered_endpoint(self, endpoint_id: str) -> OfficialEndpointContract:
        """Resolve one checked-in Cases endpoint without granting direct-call authority."""
        exact_identifier(endpoint_id, "endpoint_id", "sep")
        endpoint = next((item for item in self.endpoints if item.endpoint_id == endpoint_id), None)
        if endpoint is None:
            raise LookupError("Cases registered endpoint is unavailable")
        return endpoint

    def resolve_redirect_target(
        self,
        *,
        entry_endpoint_id: str,
        method: HttpMethod,
        target_endpoint_id: str,
    ) -> OfficialEndpointContract:
        """Authorize only the registered Judiciary session-entry GET transition."""
        entry_source, entry = self.resolve_endpoint(entry_endpoint_id, "1.0.0")
        target = self.resolve_registered_endpoint(target_endpoint_id)
        if (
            entry_source.source_id != "HK-CASE-JUDICIARY-LRS-INVENTORY"
            or entry.endpoint_id != "sep_000000000000000000000000000000000000000000000202"
            or method is not HttpMethod.GET
            or target.endpoint_id != "sep_000000000000000000000000000000000000000000000205"
            or target.invocation_kind is not EndpointInvocationKind.REDIRECT_TARGET_ONLY
            or not target.enabled
        ):
            raise PermissionError("Cases redirect transition is unavailable")
        return target


def load_hk_cases_source_register(path: Path | None = None) -> HongKongCasesSourceRegister:
    """Load and strictly validate the checked-in Hong Kong Cases source register."""
    register_path = path or Path(__file__).with_name("hk_cases_source_register.json")
    raw = register_path.read_bytes()
    document = _object(parse_json_bytes(raw, max_bytes=_MAX_REGISTER_BYTES), "source register")
    expected_fingerprint = _register_fingerprint(document)
    fingerprint = _string(document.get("fingerprint"), "fingerprint")
    if fingerprint != expected_fingerprint:
        raise ValueError("Cases source register fingerprint does not match canonical content")
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
                "access_boundary",
                "sources",
                "endpoints",
            }
        ),
        "source register",
    )
    boundary_document = _object(document["access_boundary"], "access boundary")
    _exact_keys(
        boundary_document,
        frozenset({"state", "forbidden_effects"}),
        "access boundary",
    )
    boundary = HongKongCasesAccessBoundary(
        _string(boundary_document["state"], "state"),
        _strings(boundary_document["forbidden_effects"], "forbidden_effects"),
    )
    sources = tuple(
        _parse_source(_object(item, "source")) for item in _array(document["sources"], "sources")
    )
    endpoints = tuple(
        _parse_endpoint(_object(item, "endpoint"))
        for item in _array(document["endpoints"], "endpoints")
    )
    return HongKongCasesSourceRegister(
        _string(document["schema_id"], "schema_id"),
        _string(document["schema_version"], "schema_version"),
        _string(document["register_id"], "register_id"),
        _string(document["register_version"], "register_version"),
        _string(document["effective_date"], "effective_date"),
        _string(document["status"], "status"),
        fingerprint,
        boundary,
        sources,
        endpoints,
    )


def _parse_source(document: dict[str, JsonValue]) -> HongKongCasesSourceProfile:
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
                "fact_authority",
                "completeness_authority",
                "blockers",
            }
        ),
        "source",
    )
    return HongKongCasesSourceProfile(
        _string(document["source_id"], "source_id"),
        _string(document["registered_source_id"], "registered_source_id"),
        _string(document["version"], "version"),
        _optional_strings(document["endpoint_ids"], "endpoint_ids"),
        PublisherRightsState(_string(document["rights_state"], "rights_state")),
        OfficialSourceState(_string(document["operational_state"], "operational_state")),
        SourceOutageImpact(_string(document["outage_impact"], "outage_impact")),
        _string(document["fact_authority"], "fact_authority"),
        _string(document["completeness_authority"], "completeness_authority"),
        _strings(document["blockers"], "blockers"),
    )


def _parse_endpoint(document: dict[str, JsonValue]) -> OfficialEndpointContract:
    expected = frozenset(
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
            "invocation_kind",
        }
    )
    if frozenset(document) != expected:
        raise ValueError("endpoint has unknown or missing fields")
    return OfficialEndpointContract(
        _string(document["endpoint_id"], "endpoint_id"),
        _string(document["source_id"], "source_id"),
        _string(document["version"], "version"),
        _string(document["name"], "name"),
        _string(document["url"], "url"),
        EndpointAccessMode(_string(document["access_mode"], "access_mode")),
        tuple(
            HttpMethod(_string(item, "method")) for item in _array(document["methods"], "methods")
        ),
        _strings(document["media_types"], "media_types"),
        _integer(document["max_bytes"], "max_bytes"),
        _boolean(document["complete_inventory_required"], "complete_inventory_required"),
        SignalUse(_string(document["signal_use"], "signal_use")),
        _boolean(document["proves_no_change"], "proves_no_change"),
        _string(document["evidence_role"], "evidence_role"),
        _boolean(document["enabled"], "enabled"),
        EndpointInvocationKind(_string(document["invocation_kind"], "invocation_kind")),
    )


def _register_fingerprint(document: dict[str, JsonValue]) -> str:
    projection = dict(document)
    projection.pop("fingerprint", None)
    return f"sha256:{sha256(canonicalize(checked_json_value(projection))).hexdigest()}"


def _object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an exact object")
    return value


def _array(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be an exact array")
    return value


def _string(value: JsonValue, label: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
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
