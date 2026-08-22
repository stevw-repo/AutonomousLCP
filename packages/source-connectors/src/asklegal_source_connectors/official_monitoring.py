"""Accepted Hong Kong Legislation source-monitoring tiers and due sets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from asklegal_domain import SourceOutageImpact

from .model import exact_text
from .official import (
    HK_LEGISLATION_SOURCE_IDS,
    HongKongLegislationSourceRegister,
    OfficialSourceProfile,
    OfficialSourceState,
)


class OfficialMonitoringTier(StrEnum):
    """Closed ADR 0031 monitoring tiers for one registered source role."""

    DAILY_CURRENT_LAW = "DAILY_CURRENT_LAW"
    WEEKLY_SUPPORTING = "WEEKLY_SUPPORTING"
    MONTHLY_CROSSCHECK = "MONTHLY_CROSSCHECK"
    ON_DEMAND = "ON_DEMAND"


class OfficialCoverageCycle(StrEnum):
    """Closed periodic cycles whose due set cannot be weakened by a caller."""

    DAILY_CURRENT_LAW = "DAILY_CURRENT_LAW"
    WEEKLY_RELEASE = "WEEKLY_RELEASE"
    MONTHLY_CROSSCHECK = "MONTHLY_CROSSCHECK"
    FULL_PERIODIC = "FULL_PERIODIC"


@dataclass(frozen=True, slots=True)
class OfficialMonitoringAssignment:
    """One stable source role's accepted normal monitoring tier."""

    source_id: str
    tier: OfficialMonitoringTier

    def __post_init__(self) -> None:
        exact_text(self.source_id, "source_id")
        if type(self.tier) is not OfficialMonitoringTier:
            raise TypeError("tier must be an exact OfficialMonitoringTier")


@dataclass(frozen=True, slots=True)
class OfficialObservationProfile:
    """One source-specific bounded and polite observation policy."""

    source_id: str
    timeout_seconds: int
    attempt_ceiling: int
    backoff_seconds: tuple[int, ...]
    minimum_interval_seconds: int
    concurrency_ceiling: int
    retryable_http_statuses: tuple[int, ...]
    outage_impact: SourceOutageImpact

    def __post_init__(self) -> None:
        exact_text(self.source_id, "source_id")
        for field in (
            "timeout_seconds",
            "attempt_ceiling",
            "minimum_interval_seconds",
            "concurrency_ceiling",
        ):
            value = getattr(self, field)
            if type(value) is not int or value < 1:
                raise TypeError(f"{field} must be a positive exact integer")
        if self.timeout_seconds > 120:
            raise ValueError("timeout_seconds must not exceed the transport ceiling")
        if self.concurrency_ceiling != 1:
            raise ValueError("official V1 observations must remain serial per source")
        if (
            type(self.backoff_seconds) is not tuple
            or len(self.backoff_seconds) != self.attempt_ceiling - 1
            or any(type(value) is not int or value < 1 for value in self.backoff_seconds)
        ):
            raise TypeError("backoff_seconds must cover every bounded retry exactly")
        if (
            type(self.retryable_http_statuses) is not tuple
            or not self.retryable_http_statuses
            or self.retryable_http_statuses != tuple(sorted(set(self.retryable_http_statuses)))
            or any(
                type(value) is not int or not 400 <= value <= 599
                for value in self.retryable_http_statuses
            )
        ):
            raise TypeError("retryable_http_statuses must be one sorted exact status tuple")
        if type(self.outage_impact) is not SourceOutageImpact:
            raise TypeError("outage_impact must be an exact SourceOutageImpact")


@dataclass(frozen=True, slots=True)
class _ObservationTransportPolicy:
    timeout_seconds: int
    attempt_ceiling: int
    backoff_seconds: tuple[int, ...]
    minimum_interval_seconds: int
    retryable_http_statuses: tuple[int, ...]


_TIER_BY_SOURCE_ID = {
    "HK-LEG-HKEL-CURRENT-INVENTORY": OfficialMonitoringTier.DAILY_CURRENT_LAW,
    "HK-LEG-HKEL-CURRENT-DATA": OfficialMonitoringTier.ON_DEMAND,
    "HK-LEG-HKEL-VERIFIED-COPIES": OfficialMonitoringTier.ON_DEMAND,
    "HK-LEG-HKEL-ASSISTED-COPIES": OfficialMonitoringTier.ON_DEMAND,
    "HK-LEG-HKEL-PAST-INVENTORY": OfficialMonitoringTier.ON_DEMAND,
    "HK-LEG-HKEL-PAST-DATA": OfficialMonitoringTier.ON_DEMAND,
    "HK-LEG-HKEL-EDITORIAL-RECORDS": OfficialMonitoringTier.WEEKLY_SUPPORTING,
    "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS": OfficialMonitoringTier.WEEKLY_SUPPORTING,
    "HK-LEG-GLD-EGAZETTE": OfficialMonitoringTier.DAILY_CURRENT_LAW,
    "HK-LEG-OFFICIAL-GAZETTE-ARCHIVE": OfficialMonitoringTier.ON_DEMAND,
    "HK-LEG-HKEL-GAZETTE-BACKCAPTURE": OfficialMonitoringTier.ON_DEMAND,
    "HK-LEG-BASIC-LAW-PORTAL": OfficialMonitoringTier.MONTHLY_CROSSCHECK,
    "HK-LEG-NPC-NATIONAL-LAWS-DATABASE": OfficialMonitoringTier.MONTHLY_CROSSCHECK,
    "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS": OfficialMonitoringTier.MONTHLY_CROSSCHECK,
}

_HKEL_POLICY = _ObservationTransportPolicy(
    45,
    3,
    (20, 40),
    1,
    (408, 425, 429, 500, 502, 503, 504),
)
_GLD_POLICY = _ObservationTransportPolicy(60, 2, (60,), 5, (408, 425, 429, 500, 502, 503, 504))
_BASIC_LAW_POLICY = _ObservationTransportPolicy(
    45,
    2,
    (30,),
    2,
    (408, 425, 429, 500, 502, 503, 504),
)
_NPC_POLICY = _ObservationTransportPolicy(60, 2, (60,), 5, (408, 425, 429, 500, 502, 503, 504))
_ARCHIVE_POLICY = _ObservationTransportPolicy(120, 1, (), 10, (408, 425, 429, 500, 502, 503, 504))

_OBSERVATION_POLICY_BY_SOURCE_ID = {
    "HK-LEG-HKEL-CURRENT-INVENTORY": _HKEL_POLICY,
    "HK-LEG-HKEL-CURRENT-DATA": _HKEL_POLICY,
    "HK-LEG-HKEL-VERIFIED-COPIES": _HKEL_POLICY,
    "HK-LEG-HKEL-ASSISTED-COPIES": _HKEL_POLICY,
    "HK-LEG-HKEL-PAST-INVENTORY": _HKEL_POLICY,
    "HK-LEG-HKEL-PAST-DATA": _HKEL_POLICY,
    "HK-LEG-HKEL-EDITORIAL-RECORDS": _HKEL_POLICY,
    "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS": _HKEL_POLICY,
    "HK-LEG-GLD-EGAZETTE": _GLD_POLICY,
    "HK-LEG-OFFICIAL-GAZETTE-ARCHIVE": _ARCHIVE_POLICY,
    "HK-LEG-HKEL-GAZETTE-BACKCAPTURE": _HKEL_POLICY,
    "HK-LEG-BASIC-LAW-PORTAL": _BASIC_LAW_POLICY,
    "HK-LEG-NPC-NATIONAL-LAWS-DATABASE": _NPC_POLICY,
    "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS": _NPC_POLICY,
}

if frozenset(_TIER_BY_SOURCE_ID) != HK_LEGISLATION_SOURCE_IDS:
    raise AssertionError("monitoring assignments must cover the complete source universe")
if frozenset(_OBSERVATION_POLICY_BY_SOURCE_ID) != HK_LEGISLATION_SOURCE_IDS:
    raise AssertionError("observation profiles must cover the complete source universe")

HK_LEGISLATION_MONITORING_ASSIGNMENTS = tuple(
    OfficialMonitoringAssignment(source_id, tier)
    for source_id, tier in sorted(_TIER_BY_SOURCE_ID.items())
)

_DUE_TIERS = {
    OfficialCoverageCycle.DAILY_CURRENT_LAW: frozenset({OfficialMonitoringTier.DAILY_CURRENT_LAW}),
    OfficialCoverageCycle.WEEKLY_RELEASE: frozenset(
        {
            OfficialMonitoringTier.DAILY_CURRENT_LAW,
            OfficialMonitoringTier.WEEKLY_SUPPORTING,
        }
    ),
    OfficialCoverageCycle.MONTHLY_CROSSCHECK: frozenset(
        {OfficialMonitoringTier.MONTHLY_CROSSCHECK}
    ),
    OfficialCoverageCycle.FULL_PERIODIC: frozenset(
        {
            OfficialMonitoringTier.DAILY_CURRENT_LAW,
            OfficialMonitoringTier.WEEKLY_SUPPORTING,
            OfficialMonitoringTier.MONTHLY_CROSSCHECK,
        }
    ),
}


def due_official_source_profiles(
    register: HongKongLegislationSourceRegister,
    cycle: OfficialCoverageCycle,
) -> tuple[OfficialSourceProfile, ...]:
    """Return every in-scope source due for one exact accepted periodic cycle."""
    if type(register) is not HongKongLegislationSourceRegister:
        raise TypeError("register must be an exact HongKongLegislationSourceRegister")
    if type(cycle) is not OfficialCoverageCycle:
        raise TypeError("cycle must be an exact OfficialCoverageCycle")
    due_tiers = _DUE_TIERS[cycle]
    profiles = tuple(
        sorted(
            (
                source
                for source in register.sources
                if source.operational_state is not OfficialSourceState.OUT_OF_SCOPE_V1
                and _TIER_BY_SOURCE_ID[source.source_id] in due_tiers
            ),
            key=lambda source: source.source_id,
        )
    )
    if not profiles:
        raise ValueError("periodic source cycle must contain at least one in-scope source")
    return profiles


def due_official_source_ids(cycle: OfficialCoverageCycle) -> tuple[str, ...]:
    """Return the replay-safe static source IDs for one cycle, before admission filtering."""
    if type(cycle) is not OfficialCoverageCycle:
        raise TypeError("cycle must be an exact OfficialCoverageCycle")
    due_tiers = _DUE_TIERS[cycle]
    return tuple(
        source_id for source_id, tier in sorted(_TIER_BY_SOURCE_ID.items()) if tier in due_tiers
    )


def official_observation_profile(
    register: HongKongLegislationSourceRegister,
    source_id: str,
) -> OfficialObservationProfile:
    """Bind one exact transport policy to the active source's outage consequence."""
    if type(register) is not HongKongLegislationSourceRegister:
        raise TypeError("register must be an exact HongKongLegislationSourceRegister")
    exact_text(source_id, "source_id")
    source = next((item for item in register.sources if item.source_id == source_id), None)
    policy = _OBSERVATION_POLICY_BY_SOURCE_ID.get(source_id)
    if source is None or policy is None:
        raise LookupError("official observation profile is unavailable")
    return OfficialObservationProfile(
        source_id,
        policy.timeout_seconds,
        policy.attempt_ceiling,
        policy.backoff_seconds,
        policy.minimum_interval_seconds,
        1,
        policy.retryable_http_statuses,
        source.outage_impact,
    )
