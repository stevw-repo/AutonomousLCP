"""Fail-closed tests for V1 POC application-image input contracts."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

import tools.v1_poc_application_image_oci_proof as local_oci
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
    value: object = json.loads(path.read_bytes())
    return _object_map(value)


def _object_map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _item_by_id(value: object, field: str, expected: str) -> dict[str, object]:
    for raw_item in _object_list(value):
        item = _object_map(raw_item)
        if item.get(field) == expected:
            return item
    raise AssertionError(expected)


def _policy() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / APPLICATION_IMAGE_POLICY_PATH)


def _image(policy: dict[str, object], artifact_id: str) -> dict[str, object]:
    return _item_by_id(policy["images"], "artifact_id", artifact_id)


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


def test_repository_application_image_inputs_are_complete_but_disabled(tmp_path: Path) -> None:
    """Bind all five apps without claiming a runnable or admitted image."""
    assert check_application_image_policy(
        REPOSITORY_ROOT, oci_proof_path=tmp_path / "missing-local-proof.json"
    ) == ApplicationImageReport(
        images=5,
        workspace_distributions=19,
        blockers=("UBUNTU_24_04_X86_64_OCI_PROOF",),
        admitted=0,
    )


def test_valid_local_oci_proof_discharges_only_the_oci_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A current retained proof removes the build/runtime blocker, not admission."""
    proof_path = tmp_path / "local-oci-proof.json"
    proof_path.write_bytes(b"measured-proof-placeholder")
    checked: list[tuple[Path, Path]] = []

    def valid_proof(root: Path, path: Path) -> None:
        checked.append((root, path))

    monkeypatch.setattr(local_oci, "check_local_oci_proof", valid_proof)

    assert check_application_image_policy(
        REPOSITORY_ROOT, oci_proof_path=proof_path
    ) == ApplicationImageReport(
        images=5,
        workspace_distributions=19,
        blockers=(),
        admitted=0,
    )
    assert checked == [(REPOSITORY_ROOT, proof_path)]


def test_acquisition_image_binds_verified_browser_and_debian_runtime_inputs() -> None:
    """Pin the real browser bytes and exact Debian/Xvfb closure without admitting OCI."""
    policy = _policy()
    blockers = _object_list(policy["required_blockers"])
    dockerfile = (REPOSITORY_ROOT / "infrastructure/poc/images/Dockerfile").read_text()
    acquisition = _image(policy, "acquisition-worker")

    assert "ACQUISITION_PATCHRIGHT_DEBIAN_SYSTEM_PACKAGE_CLOSURE_REQUIRED" not in blockers
    assert acquisition["third_party_wheelhouse_state"] == "LOCKED"
    locks = _object_map(policy["input_locks"])
    assert "infrastructure/poc/patchright_runtime_inputs.json" in locks
    assert "infrastructure/poc/patchright_runtime_system_packages.json" in locks
    assert "PLAYWRIGHT_BROWSERS_PATH" in dockerfile
    assert "browser-runtime" in dockerfile


def test_root_pyproject_lock_tracks_current_wheel_build_metadata() -> None:
    """The image policy binds lint and Pyright metadata consumed by workspace builds."""
    locks = _object_map(_policy()["input_locks"])
    expected = (
        f"sha256:{hashlib.sha256((REPOSITORY_ROOT / 'pyproject.toml').read_bytes()).hexdigest()}"
    )

    assert locks["pyproject.toml"] == expected


def test_rotation_network_helper_is_an_exact_application_image_input() -> None:
    """Helper drift fails the image contract before an OCI proof can be reused."""
    relative = "infrastructure/poc/libexec/asklegal-vault-application-rotation-network"
    locks = _object_map(_policy()["input_locks"])
    expected = f"sha256:{hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()}"

    assert locks[relative] == expected


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
        authority = _object_map(policy["authority"])
        authority["image_build_authorized"] = True
    elif mutation == "base":
        base = _object_map(policy["base_image"])
        base["selection_state"] = "SELECTED"
    elif mutation == "input":
        locks = _object_map(policy["input_locks"])
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
    control_artifact = _item_by_id(artifacts["artifacts"], "artifact_id", "control-plane")
    control_artifact["selection_state"] = "DIGEST_PINNED_REPROOF_REQUIRED"
    assert ApplicationImageCode.COVERAGE in _codes(_policy(), artifacts=artifacts)

    topology = _object(REPOSITORY_ROOT / TOPOLOGY_PATH)
    review = _item_by_id(topology["services"], "service_id", "review-api")
    review["identity"] = "shared-identity-forbidden"
    assert ApplicationImageCode.TOPOLOGY in _codes(_policy(), topology=topology)


@pytest.mark.parametrize(
    "mutation", ["mutable_tag", "wrong_state", "missing_digest", "unrecorded_distribution"]
)
def test_base_image_pin_cannot_be_loosened(mutation: str) -> None:
    """A base image without an immutable digest cannot be reproducibly rebuilt."""
    policy = deepcopy(_policy())
    base = _object_map(policy["base_image"])
    if mutation == "mutable_tag":
        base["artifact_ref"] = "docker.io/library/python:3.14.7-slim-trixie"
    elif mutation == "wrong_state":
        base["selection_state"] = "DIGEST_REQUIRED"
    elif mutation == "missing_digest":
        base["artifact_ref"] = None
    else:
        base["distribution"] = "Ubuntu 24.04"
    assert ApplicationImageCode.BLOCKER in _codes(policy)


@pytest.mark.parametrize(
    "mutation",
    ["network_enabled", "false_image_id_claim", "weaker_measure", "missing_tool"],
)
def test_build_definition_cannot_overclaim(mutation: str) -> None:
    """The build must stay offline and must not claim reproducibility it lacks."""
    policy = deepcopy(_policy())
    definition = _object_map(policy["build_definition"])
    if mutation == "network_enabled":
        definition["network_during_build"] = "ENABLED"
    elif mutation == "false_image_id_claim":
        definition["image_id_stability"] = "BYTE_IDENTICAL"
    elif mutation == "weaker_measure":
        definition["reproducibility_measure"] = "BEST_EFFORT"
    else:
        del definition["build_tool"]
    assert ApplicationImageCode.BLOCKER in _codes(policy)


@pytest.mark.parametrize("mutation", ["root_uid", "missing_digest", "short_digest"])
def test_built_image_identity_and_content_must_be_recorded(mutation: str) -> None:
    """A recorded image needs its exact runtime identity and installed-tree digest."""
    policy = deepcopy(_policy())
    images = _object_list(policy["images"])
    first = _object_map(images[0])
    if mutation == "root_uid":
        first["runtime_uid"] = None
    elif mutation == "missing_digest":
        first["installed_tree_sha256"] = None
    else:
        first["installed_tree_sha256"] = "abc"
    assert ApplicationImageCode.RUNTIME in _codes(policy)
