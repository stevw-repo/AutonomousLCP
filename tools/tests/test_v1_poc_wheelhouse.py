"""Fail-closed tests for the locked offline V1 POC application wheelhouse."""

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from tools.v1_poc_wheelhouse import (
    APPLICATION_IMAGE_POLICY_PATH,
    WHEELHOUSE_PATH,
    WheelhouseCode,
    check_wheelhouse,
    validate_wheelhouse,
    verify_wheelhouse_contents,
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


def _policy() -> dict[str, object]:
    return _object(REPOSITORY_ROOT / WHEELHOUSE_PATH)


def _base_image_ref() -> object:
    images = _object(REPOSITORY_ROOT / APPLICATION_IMAGE_POLICY_PATH)
    base = _object_map(images["base_image"])
    return base["artifact_ref"]


def _codes(policy: dict[str, object], base_image_ref: object = None) -> set[WheelhouseCode]:
    reference = _base_image_ref() if base_image_ref is None else base_image_ref
    return {finding.code for finding in validate_wheelhouse(policy, reference)}


def test_repository_wheelhouse_contract_is_complete() -> None:
    """One locked inventory covers all five applications and every wheel."""
    report = check_wheelhouse(REPOSITORY_ROOT)
    assert report.wheels == 59
    assert report.applications == 5
    assert validate_wheelhouse(_policy(), _base_image_ref()) == ()


def test_wheelhouse_is_not_tracked_in_git() -> None:
    """Wheels are runtime data; only the contract belongs in the repository."""
    policy = _policy()
    assert policy["tracked_in_git"] is False
    assert not (REPOSITORY_ROOT / "var/wheelhouse/wheels").is_relative_to(
        REPOSITORY_ROOT / "infrastructure"
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("status", WheelhouseCode.INVENTORY),
        ("platform", WheelhouseCode.PLATFORM),
        ("python_tag", WheelhouseCode.PLATFORM),
        ("require_hashes", WheelhouseCode.POLICY),
        ("network_allowed", WheelhouseCode.POLICY),
        ("tracked_in_git", WheelhouseCode.POLICY),
        ("extra_field", WheelhouseCode.INVENTORY),
    ],
)
def test_header_drift_fails_closed(mutation: str, expected: WheelhouseCode) -> None:
    """An offline, hash-checked, single-platform install policy cannot be relaxed."""
    policy = deepcopy(_policy())
    if mutation == "status":
        policy["status"] = "BEST_EFFORT"
    elif mutation == "platform":
        policy["target_platform"] = "linux/arm64"
    elif mutation == "python_tag":
        policy["python_tag"] = "cp312"
    elif mutation == "require_hashes":
        policy["require_hashes"] = False
    elif mutation == "network_allowed":
        policy["network_during_install_forbidden"] = False
    elif mutation == "tracked_in_git":
        policy["tracked_in_git"] = True
    else:
        policy["unexpected"] = "field"
    assert expected in _codes(policy)


def test_base_image_drift_invalidates_the_wheelhouse() -> None:
    """Wheels built for one interpreter must not silently follow a new base image."""
    assert WheelhouseCode.PLATFORM in _codes(_policy(), "docker.io/library/python@sha256:0" * 1)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("missing_application", WheelhouseCode.APPLICATION),
        ("extra_application", WheelhouseCode.APPLICATION),
        ("bad_digest", WheelhouseCode.APPLICATION),
        ("zero_distributions", WheelhouseCode.APPLICATION),
    ],
)
def test_application_coverage_fails_closed(mutation: str, expected: WheelhouseCode) -> None:
    """Every application needs its own hashed, non-empty requirement export."""
    policy = deepcopy(_policy())
    applications = _object_map(policy["applications"])
    if mutation == "missing_application":
        del applications["asklegal-review-api"]
    elif mutation == "extra_application":
        applications["asklegal-unknown"] = applications["asklegal-review-api"]
    elif mutation == "bad_digest":
        entry = _object_map(applications["asklegal-review-api"])
        entry["requirements_sha256"] = "not-a-digest"
    else:
        entry = _object_map(applications["asklegal-review-api"])
        entry["pinned_distributions"] = 0
    assert expected in _codes(policy)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("count_drift", WheelhouseCode.INVENTORY),
        ("duplicate", WheelhouseCode.INVENTORY),
        ("bad_digest", WheelhouseCode.INVENTORY),
        ("negative_size", WheelhouseCode.INVENTORY),
        ("windows_wheel", WheelhouseCode.PLATFORM),
        ("macos_wheel", WheelhouseCode.PLATFORM),
        ("arm_wheel", WheelhouseCode.PLATFORM),
    ],
)
def test_wheel_inventory_fails_closed(mutation: str, expected: WheelhouseCode) -> None:
    """A miscounted, duplicated, unhashed, or foreign-platform wheel is not admissible."""
    policy = deepcopy(_policy())
    wheels = _object_list(policy["wheels"])
    first = _object_map(wheels[0])
    if mutation == "count_drift":
        policy["wheel_count"] = len(wheels) + 1
    elif mutation == "duplicate":
        wheels.append(deepcopy(first))
        policy["wheel_count"] = len(wheels)
    elif mutation == "bad_digest":
        first["sha256"] = "0" * 63
    elif mutation == "negative_size":
        first["size_bytes"] = -1
    elif mutation == "windows_wheel":
        first["filename"] = "example-1.0-cp314-cp314-win_amd64.whl"
    elif mutation == "macos_wheel":
        first["filename"] = "example-1.0-cp314-cp314-macosx_11_0_x86_64.whl"
    else:
        first["filename"] = "example-1.0-cp314-cp314-manylinux_2_28_aarch64.whl"
    assert expected in _codes(policy)


def test_missing_wheelhouse_directory_verifies_nothing(tmp_path: Path) -> None:
    """A clean checkout has no wheels; that must not be reported as verified."""
    assert verify_wheelhouse_contents(tmp_path, _policy()) == 0


def test_wheel_byte_drift_is_rejected(tmp_path: Path) -> None:
    """A wheel whose bytes changed since locking cannot pass content verification."""
    directory = tmp_path / "var/wheelhouse/wheels"
    directory.mkdir(parents=True)
    policy = deepcopy(_policy())
    wheels = _object_list(policy["wheels"])
    policy["wheels"] = wheels[:1]
    first = _object_map(wheels[0])
    (directory / str(first["filename"])).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="wheelhouse"):
        verify_wheelhouse_contents(tmp_path, policy)
