"""Deterministic implementation-readiness reporting for official sources."""

from __future__ import annotations

from dataclasses import dataclass

from .model import exact_string_tuple, exact_text
from .official import (
    EndpointAccessMode,
    HongKongLegislationSourceRegister,
    OfficialEndpointContract,
    OfficialSourceState,
    PublisherRightsState,
    SignalUse,
)


@dataclass(frozen=True, slots=True)
class OfficialEndpointBuildAssessment:
    """Technical build state for one endpoint, independent of legal admission."""

    endpoint_id: str
    source_id: str
    access_mode: EndpointAccessMode
    implementation_ready: bool
    requires_locator_binding: bool
    technical_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        exact_text(self.endpoint_id, "endpoint_id")
        exact_text(self.source_id, "source_id")
        if type(self.access_mode) is not EndpointAccessMode:
            raise TypeError("access_mode must be an exact EndpointAccessMode")
        if type(self.implementation_ready) is not bool:
            raise TypeError("implementation_ready must be an exact boolean")
        if type(self.requires_locator_binding) is not bool:
            raise TypeError("requires_locator_binding must be an exact boolean")
        if type(self.technical_blockers) is not tuple:
            raise TypeError("technical_blockers must be an exact tuple")
        if self.technical_blockers:
            exact_string_tuple(self.technical_blockers, "technical_blockers")
        if self.implementation_ready == bool(self.technical_blockers):
            raise ValueError("implementation readiness must match technical blockers")


@dataclass(frozen=True, slots=True)
class OfficialSourceBuildAssessment:
    """Separate technical completeness from publisher and owner admission."""

    source_id: str
    rights_state: PublisherRightsState
    operational_state: OfficialSourceState
    endpoint_assessments: tuple[OfficialEndpointBuildAssessment, ...]
    operational_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        exact_text(self.source_id, "source_id")
        if type(self.rights_state) is not PublisherRightsState:
            raise TypeError("rights_state must be an exact PublisherRightsState")
        if type(self.operational_state) is not OfficialSourceState:
            raise TypeError("operational_state must be an exact OfficialSourceState")
        if type(self.endpoint_assessments) is not tuple or not self.endpoint_assessments:
            raise TypeError("endpoint_assessments must be one non-empty exact tuple")
        if any(item.source_id != self.source_id for item in self.endpoint_assessments):
            raise ValueError("endpoint assessments must belong to their source")
        if type(self.operational_blockers) is not tuple:
            raise TypeError("operational_blockers must be an exact tuple")
        if self.operational_blockers:
            exact_string_tuple(self.operational_blockers, "operational_blockers")
        if self.operational_state is OfficialSourceState.CONFIGURED and self.operational_blockers:
            raise ValueError("configured sources cannot retain operational blockers")
        if (
            self.operational_state
            in {OfficialSourceState.BLOCKED, OfficialSourceState.PARTIALLY_CONFIGURED}
            and not self.operational_blockers
        ):
            raise ValueError("incomplete sources require explicit operational blockers")

    @property
    def implementation_complete(self) -> bool:
        """Return true when every declared endpoint has an implemented procedure."""
        return all(item.implementation_ready for item in self.endpoint_assessments)

    @property
    def legally_admitted(self) -> bool:
        """Return true for published permission or the recorded legal clearance."""
        return self.rights_state in {
            PublisherRightsState.PUBLISHED_TERMS_PERMIT,
            PublisherRightsState.LEGAL_TEAM_CLEARED,
        }

    @property
    def operationally_callable(self) -> bool:
        """Require both technical completeness and actual source admission."""
        return (
            self.implementation_complete
            and self.legally_admitted
            and self.operational_state is OfficialSourceState.CONFIGURED
        )


@dataclass(frozen=True, slots=True)
class OfficialSourceBuildReport:
    """Complete 14-role engineering and admission report."""

    register_fingerprint: str
    sources: tuple[OfficialSourceBuildAssessment, ...]

    def __post_init__(self) -> None:
        exact_text(self.register_fingerprint, "register_fingerprint")
        if type(self.sources) is not tuple or not self.sources:
            raise TypeError("sources must be one non-empty exact tuple")
        source_ids = tuple(item.source_id for item in self.sources)
        if source_ids != tuple(sorted(source_ids)) or len(set(source_ids)) != len(source_ids):
            raise ValueError("source assessments must be unique and sorted")

    @property
    def endpoint_count(self) -> int:
        """Return the total endpoint inventory accounted for by the report."""
        return sum(len(item.endpoint_assessments) for item in self.sources)

    @property
    def implementation_complete_source_ids(self) -> tuple[str, ...]:
        """Return technically complete roles even when legal admission is pending."""
        return tuple(item.source_id for item in self.sources if item.implementation_complete)

    @property
    def operationally_callable_source_ids(self) -> tuple[str, ...]:
        """Return roles that are both built and presently admitted."""
        return tuple(item.source_id for item in self.sources if item.operationally_callable)

    @property
    def technically_blocked_source_ids(self) -> tuple[str, ...]:
        """Return roles that still need one or more acquisition procedures."""
        return tuple(item.source_id for item in self.sources if not item.implementation_complete)

    @property
    def legally_blocked_source_ids(self) -> tuple[str, ...]:
        """Return roles whose source admission evidence remains incomplete."""
        return tuple(item.source_id for item in self.sources if not item.legally_admitted)


def assess_official_source_build(
    register: HongKongLegislationSourceRegister,
) -> OfficialSourceBuildReport:
    """Account for every endpoint without converting assumed rights into admission."""
    if type(register) is not HongKongLegislationSourceRegister:
        raise TypeError("register must be an exact HongKongLegislationSourceRegister")
    endpoints = {item.endpoint_id: item for item in register.endpoints}
    source_assessments: list[OfficialSourceBuildAssessment] = []
    for source in sorted(register.sources, key=lambda item: item.source_id):
        endpoint_assessments = tuple(
            _assess_endpoint(endpoints[endpoint_id]) for endpoint_id in source.endpoint_ids
        )
        source_assessments.append(
            OfficialSourceBuildAssessment(
                source.source_id,
                source.rights_state,
                source.operational_state,
                endpoint_assessments,
                source.blockers,
            )
        )
    report = OfficialSourceBuildReport(register.fingerprint, tuple(source_assessments))
    if report.endpoint_count != len(register.endpoints):
        raise ValueError("build report must account for every registered endpoint")
    return report


def _assess_endpoint(
    endpoint: OfficialEndpointContract,
) -> OfficialEndpointBuildAssessment:
    blockers: list[str] = []
    requires_locator_binding = "{" in endpoint.url or "}" in endpoint.url
    if endpoint.access_mode is EndpointAccessMode.BROWSER_SESSION:
        if endpoint.signal_use is not SignalUse.DISCOVERY_ONLY:
            blockers.append("DIRECT_INERT_EVIDENCE_PROCEDURE_REQUIRED")
    elif endpoint.access_mode is EndpointAccessMode.CATALOGUE_DISCOVERY:
        blockers.append("CATALOGUE_DISCOVERY_PROCEDURE_REQUIRED")
    elif endpoint.access_mode is EndpointAccessMode.PHYSICAL_HOLDING:
        blockers.append("PHYSICAL_HOLDING_PROCEDURE_REQUIRED")
    elif endpoint.access_mode is not EndpointAccessMode.DIRECT_HTTP:
        raise AssertionError("unhandled endpoint access mode")
    exact_blockers = tuple(sorted(set(blockers)))
    return OfficialEndpointBuildAssessment(
        endpoint.endpoint_id,
        endpoint.source_id,
        endpoint.access_mode,
        not exact_blockers,
        requires_locator_binding,
        exact_blockers,
    )
