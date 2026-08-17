"""Fail-closed tests for V1 POC application-image input contracts."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.v1_poc_application_images import (
    APPLICATION_IMAGE_POLICY_PATH,
    ARTIFACT_POLICY_PATH,
    PACKAGE_POLICY_PATH,
    TOPOLOGY_PATH,
    ApplicationImageCode,
    ApplicationImageReport,
    check_application_image_policy,
    validate_application_image_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _policy() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / APPLICATION_IMAGE_POLICY_PATH)


def _image(policy: dict[str, object], artifact_id: str) -> dict[str, object]:
    images = policy["images"]
    assert isinstance(images, list)
    return next(
        image
        for image in images
        if isinstance(image, dict) and image.get("artifact_id") == artifact_id
    )


def _codes(
    policy: dict[str, object],
    *,
    artifacts: dict[str, object] | None = None,
    topology: dict[str, object] | None = None,
) -> set[ApplicationImageCode]:
    return {
        finding.code
        for finding in validate_application_image_policy(
            policy,
            _object(REPOSITORY_ROOT / PACKAGE_POLICY_PATH),
            artifacts or _object(REPOSITORY_ROOT / ARTIFACT_POLICY_PATH),
            topology or _object(REPOSITORY_ROOT / TOPOLOGY_PATH),
            REPOSITORY_ROOT,
        )
    }


def test_repository_application_image_inputs_are_complete_but_disabled() -> None:
    """Bind all five apps without claiming a runnable or admitted image."""
    assert check_application_image_policy(REPOSITORY_ROOT) == ApplicationImageReport(
        images=5,
        workspace_distributions=19,
        blockers=(
            "BASE_IMAGE_DIGEST",
            "THIRD_PARTY_WHEELHOUSE",
            "OCI_BUILD_DEFINITION",
            "RUNTIME_CONFIGURATION_ADAPTER",
            "UBUNTU_24_04_X86_64_OCI_PROOF",
        ),
        admitted=0,
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("authority", ApplicationImageCode.AUTHORITY),
        ("base", ApplicationImageCode.BLOCKER),
        ("input", ApplicationImageCode.INPUT),
        ("admit", ApplicationImageCode.ADMISSION),
        ("runtime", ApplicationImageCode.RUNTIME),
        ("closure", ApplicationImageCode.PACKAGE),
        ("secret", ApplicationImageCode.SECRET),
        ("schema", ApplicationImageCode.INVENTORY),
    ],
)
def test_application_image_policy_drift_fails_closed(
    mutation: str, expected_code: ApplicationImageCode
) -> None:
    """Reject false readiness, authority expansion, secret data, and input drift."""
    policy = deepcopy(_policy())
    if mutation == "authority":
        authority = policy["authority"]
        assert isinstance(authority, dict)
        authority["image_build_authorized"] = True
    elif mutation == "base":
        base = policy["base_image"]
        assert isinstance(base, dict)
        base["selection_state"] = "SELECTED"
    elif mutation == "input":
        locks = policy["input_locks"]
        assert isinstance(locks, dict)
        locks["uv.lock"] = "sha256:" + ("0" * 64)
    elif mutation == "admit":
        _image(policy, "control-plane")["admitted"] = True
    elif mutation == "runtime":
        _image(policy, "review-api")["runtime_entrypoint_state"] = "READY"
    elif mutation == "closure":
        _image(policy, "acquisition-worker")["workspace_distribution_closure"] = []
    elif mutation == "secret":
        policy["api_key"] = "must-not-exist"
    else:
        _image(policy, "promotion-worker")["unexpected"] = "field"
    assert expected_code in _codes(policy)


def test_artifact_registry_and_topology_drift_fail_closed() -> None:
    """Keep build inputs bound to the exact disabled artifact and service inventories."""
    artifacts = _object(REPOSITORY_ROOT / ARTIFACT_POLICY_PATH)
    artifact_entries = artifacts["artifacts"]
    assert isinstance(artifact_entries, list)
    control_artifact = next(
        item
        for item in artifact_entries
        if isinstance(item, dict) and item.get("artifact_id") == "control-plane"
    )
    control_artifact["selection_state"] = "DIGEST_PINNED_REPROOF_REQUIRED"
    assert ApplicationImageCode.COVERAGE in _codes(_policy(), artifacts=artifacts)

    topology = _object(REPOSITORY_ROOT / TOPOLOGY_PATH)
    services = topology["services"]
    assert isinstance(services, list)
    review = next(
        item
        for item in services
        if isinstance(item, dict) and item.get("service_id") == "review-api"
    )
    review["identity"] = "shared-identity-forbidden"
    assert ApplicationImageCode.TOPOLOGY in _codes(_policy(), topology=topology)
