"""Accepted Hong Kong Legislation source-monitoring tiers and due sets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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

if frozenset(_TIER_BY_SOURCE_ID) != HK_LEGISLATION_SOURCE_IDS:
    raise AssertionError("monitoring assignments must cover the complete source universe")

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
