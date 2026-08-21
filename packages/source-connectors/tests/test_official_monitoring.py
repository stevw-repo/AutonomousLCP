"""Accepted Hong Kong source-monitoring tier and due-set tests."""

from asklegal_source_connectors import (
    HK_LEGISLATION_MONITORING_ASSIGNMENTS,
    HK_LEGISLATION_SOURCE_IDS,
    OfficialCoverageCycle,
    OfficialMonitoringTier,
    due_official_source_profiles,
    load_hk_legislation_source_register,
)


def _due(cycle: OfficialCoverageCycle) -> tuple[str, ...]:
    register = load_hk_legislation_source_register()
    return tuple(source.source_id for source in due_official_source_profiles(register, cycle))


def test_monitoring_assignments_cover_every_stable_source_exactly_once() -> None:
    assert tuple(item.source_id for item in HK_LEGISLATION_MONITORING_ASSIGNMENTS) == tuple(
        sorted(HK_LEGISLATION_SOURCE_IDS)
    )
    assert {item.tier for item in HK_LEGISLATION_MONITORING_ASSIGNMENTS} == set(
        OfficialMonitoringTier
    )


def test_periodic_due_sets_are_derived_and_exclude_out_of_scope_v1_roles() -> None:
    assert _due(OfficialCoverageCycle.DAILY_CURRENT_LAW) == (
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
    )
    assert _due(OfficialCoverageCycle.WEEKLY_RELEASE) == (
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
    )
    assert _due(OfficialCoverageCycle.MONTHLY_CROSSCHECK) == ("HK-LEG-BASIC-LAW-PORTAL",)
    assert _due(OfficialCoverageCycle.FULL_PERIODIC) == (
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
    )


def test_on_demand_sources_are_never_silently_added_to_periodic_cycles() -> None:
    periodic = set(_due(OfficialCoverageCycle.FULL_PERIODIC))

    assert "HK-LEG-HKEL-CURRENT-DATA" not in periodic
    assert "HK-LEG-HKEL-VERIFIED-COPIES" not in periodic
    assert "HK-LEG-HKEL-GAZETTE-BACKCAPTURE" not in periodic
