"""Continuous V1 Review composition through retained local Task 8 artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from asklegal_application_runtime import CredentialMaterial, ServiceExitCode
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_review_api import v1_service
from asklegal_review_api.v1_infrastructure import (
    ReviewCompositionError,
    V1ReviewInfrastructure,
    v1_dependencies,
)


def _infrastructure() -> V1ReviewInfrastructure:
    """Supply the one process credential consumed by the local Review bridge."""
    infrastructure = V1ReviewInfrastructure.__new__(V1ReviewInfrastructure)
    object.__setattr__(
        infrastructure,
        "review_api_credential",
        CredentialMaterial(b"review-api-focused-test-credential"),
    )
    return infrastructure


def _load_infrastructure(_environment: Mapping[str, str]) -> V1ReviewInfrastructure:
    """Supply the local infrastructure value at the service load boundary."""
    return _infrastructure()


def _readiness_gate(_infrastructure: V1ReviewInfrastructure) -> object:
    """Supply an opaque gate to the patched runner."""
    return object()


def _write_authority(path: Path) -> None:
    path.write_bytes(
        canonicalize(
            checked_json_value(
                {
                    "authority_evidence_fingerprint": "sha256:" + "2" * 64,
                    "authority_evidence_id": "evi_" + "2" * 48,
                    "reviewer_identity_fingerprint": "sha256:" + "1" * 64,
                    "reviewer_identity_id": "act_" + "1" * 48,
                    "roles": ["PipelineAdministrator"],
                    "schema_id": "asklegal.local-review-authority/v1",
                    "subject": "person-local-1",
                }
            )
        )
    )


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


def test_v1_service_composes_and_enters_runner_with_empty_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty artifact directory is a healthy cold state, not a startup failure."""
    artifact_root = tmp_path / "artifacts"
    state_root = tmp_path / "state"
    artifact_root.mkdir()
    state_root.mkdir()
    authority_path = tmp_path / "authority.json"
    _write_authority(authority_path)
    environment = {
        "ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT": str(artifact_root),
        "ASKLEGAL_LOCAL_REVIEW_STATE_ROOT": str(state_root),
        "ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH": str(authority_path),
    }
    dependencies = v1_dependencies(_infrastructure(), environment)
    assert dependencies.projections.load()[1] == ()
    assert dependencies.projections.check() is True

    called = False

    async def expected_service(*_args: object, **_kwargs: object) -> ServiceExitCode:
        nonlocal called
        called = True
        return ServiceExitCode.OK

    monkeypatch.setattr(v1_service, "load_v1_infrastructure", _load_infrastructure)
    monkeypatch.setattr(v1_service, "readiness_gate", _readiness_gate)
    monkeypatch.setattr(v1_service, "_server_material_present", lambda: True)
    monkeypatch.setattr(v1_service, "run_v1_service", expected_service)
    monkeypatch.setattr(v1_service.os, "environ", environment)
    assert v1_service.run() == int(ServiceExitCode.OK)
    assert called is True
