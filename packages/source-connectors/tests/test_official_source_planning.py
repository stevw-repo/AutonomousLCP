"""All-role technical build planning remains separate from legal admission."""

from asklegal_source_connectors import (
    OfficialSourceBuildReport,
    OfficialSourceState,
    assess_official_source_build,
    load_hk_legislation_source_register,
)


def _report() -> OfficialSourceBuildReport:
    return assess_official_source_build(load_hk_legislation_source_register())


def test_report_accounts_for_all_14_sources_and_78_endpoints() -> None:
    report = _report()

    assert len(report.sources) == 14
    assert report.endpoint_count == 78
    assert tuple(item.source_id for item in report.sources) == tuple(
        sorted(item.source_id for item in report.sources)
    )


def test_legal_clearance_enables_only_technically_complete_sources() -> None:
    report = _report()

    assert report.implementation_complete_source_ids == (
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-GAZETTE-BACKCAPTURE",
        "HK-LEG-HKEL-PAST-DATA",
        "HK-LEG-HKEL-PAST-INVENTORY",
    )
    assert report.operationally_callable_source_ids == (
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-PAST-DATA",
        "HK-LEG-HKEL-PAST-INVENTORY",
    )
    basic_law = next(item for item in report.sources if item.source_id == "HK-LEG-BASIC-LAW-PORTAL")
    assert basic_law.implementation_complete
    assert basic_law.operationally_callable
    assert basic_law.legally_admitted
    assert basic_law.operational_state is OfficialSourceState.CONFIGURED
    assert basic_law.operational_blockers == ()


def test_every_remaining_engineering_gap_is_explicit_and_endpoint_bound() -> None:
    report = _report()

    assert len(report.technically_blocked_source_ids) == 8
    assert report.legally_blocked_source_ids == ()
    endpoint_assessments = tuple(
        endpoint for source in report.sources for endpoint in source.endpoint_assessments
    )
    ready = tuple(item for item in endpoint_assessments if item.implementation_ready)
    blocked = tuple(item for item in endpoint_assessments if not item.implementation_ready)
    assert len(ready) == 62
    assert len(blocked) == 16
    assert all(item.technical_blockers for item in blocked)
    assert all(not item.technical_blockers for item in ready)
    assert sum(item.requires_locator_binding for item in endpoint_assessments) == 6
    assert {blocker for item in blocked for blocker in item.technical_blockers} == {
        "CATALOGUE_DISCOVERY_PROCEDURE_REQUIRED",
        "PHYSICAL_HOLDING_PROCEDURE_REQUIRED",
        "DIRECT_INERT_EVIDENCE_PROCEDURE_REQUIRED",
    }


def test_report_is_bound_to_the_exact_register_fingerprint() -> None:
    register = load_hk_legislation_source_register()
    report = assess_official_source_build(register)

    assert report.register_fingerprint == register.fingerprint
