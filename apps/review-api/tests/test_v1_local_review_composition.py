"""Continuous V1 Review composition through retained local Task 8 artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from asklegal_application_runtime import ServiceExitCode
from asklegal_review_api import v1_service
from asklegal_review_api.v1_infrastructure import (
    ReviewCompositionError,
    V1ReviewInfrastructure,
    v1_dependencies,
)


def _infrastructure() -> V1ReviewInfrastructure:
    """Supply a value that must remain unused by the local Review bridge."""
    return V1ReviewInfrastructure.__new__(V1ReviewInfrastructure)


def _load_infrastructure(_environment: Mapping[str, str]) -> V1ReviewInfrastructure:
    """Supply the unused infrastructure value at the service load boundary."""
    return _infrastructure()


def test_v1_review_requires_explicit_existing_artifact_and_state_roots(
    tmp_path: Path,
) -> None:
    """Missing or non-directory local authority paths fail before API service."""
    with pytest.raises(ReviewCompositionError, match="LOCAL_REVIEW_CONFIGURATION_NOT_READY"):
        v1_dependencies(_infrastructure(), {})

    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    missing_state = tmp_path / "missing-state"
    with pytest.raises(ReviewCompositionError, match="LOCAL_REVIEW_CONFIGURATION_NOT_READY"):
        v1_dependencies(
            _infrastructure(),
            {
                "ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT": str(artifact_root),
                "ASKLEGAL_LOCAL_REVIEW_STATE_ROOT": str(missing_state),
            },
        )

    state_root = tmp_path / "state"
    state_root.mkdir()
    with pytest.raises(ReviewCompositionError, match="LOCAL_REVIEW_CONFIGURATION_NOT_READY"):
        v1_dependencies(
            _infrastructure(),
            {
                "ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT": str(artifact_root),
                "ASKLEGAL_LOCAL_REVIEW_STATE_ROOT": str(state_root),
            },
        )


def test_v1_service_returns_not_ready_before_serving_when_local_review_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The process cannot start its listener with absent retained Review inputs."""
    monkeypatch.setattr(
        v1_service,
        "load_v1_infrastructure",
        _load_infrastructure,
    )
    monkeypatch.setattr(v1_service, "_server_material_present", lambda: True)

    async def unexpected_service(*_args: object, **_kwargs: object) -> ServiceExitCode:
        message = "service started without retained local Review inputs"
        raise AssertionError(message)

    monkeypatch.setattr(v1_service, "run_v1_service", unexpected_service)
    environment: dict[str, str] = {}
    monkeypatch.setattr(v1_service.os, "environ", environment)
    assert v1_service.run() == int(ServiceExitCode.NOT_READY)
