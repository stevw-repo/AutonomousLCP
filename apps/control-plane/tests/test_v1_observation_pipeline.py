"""The V1 source observation workflow must never request promotion."""

from asklegal_control_plane.v1_pipeline import (
    SOURCE_OBSERVATION_ACTIVITIES,
    ControlActivities,
    observation_result,
)


def test_source_observation_stops_after_analysis() -> None:
    """Analysis output is not a release, Approval, or promotion command."""
    assert SOURCE_OBSERVATION_ACTIVITIES == ("start_acquisition", "start_analysis")
    assert observation_result(
        {"evidence_ref": "ev_1"},
        {"decision_code": "INSUFFICIENT_EVIDENCE"},
    ) == {
        "evidence": {"evidence_ref": "ev_1"},
        "decision": {"decision_code": "INSUFFICIENT_EVIDENCE"},
        "promotion_state": "NOT_REQUESTED",
    }


def test_control_activities_expose_no_promotion_entrypoint() -> None:
    """The service cannot register the retired arbitrary-decision activity."""
    assert not hasattr(ControlActivities, "start_promotion")
