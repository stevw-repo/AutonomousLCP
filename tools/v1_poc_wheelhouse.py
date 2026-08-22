"""Fail-closed validation for the locked offline V1 POC application wheelhouse.

The wheels themselves are runtime data and stay in the ignored `var/` tree. This
contract is the part that belongs in Git: the exact platform, base image, hash
policy, per-application requirement digests, and every wheel's name, size, and
SHA-256. When the wheelhouse is present the checker verifies the bytes on disk
against that inventory; when it is absent the contract is still validated, so a
clean checkout fails on drift rather than on a missing directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

WHEELHOUSE_PATH = Path("infrastructure/poc/application_wheelhouse.json")
APPLICATION_IMAGE_POLICY_PATH = Path("infrastructure/poc/application_image_inputs.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_DOCUMENT_TOO_LARGE = "wheelhouse document too large"
_DOCUMENT_ROOT = "wheelhouse document root"
_DOCUMENT_KEYS = frozenset(
    {
        "applications",
        "base_image_ref",
        "excluded_platform_only_distributions",
        "network_during_install_forbidden",
        "python_tag",
        "require_hashes",
        "schema_version",
        "status",
        "target_platform",
        "tracked_in_git",
        "wheel_count",
        "wheelhouse_path",
        "wheels",
    }
)
_WHEEL_KEYS = frozenset({"filename", "sha256", "size_bytes"})
_APPLICATION_KEYS = frozenset({"pinned_distributions", "requirements_sha256"})
_EXPECTED_APPLICATIONS = frozenset(
    {
        "asklegal-acquisition-worker",
        "asklegal-control-plane",
        "asklegal-legal-processing-worker",
        "asklegal-promotion-worker",
        "asklegal-review-api",
    }
)
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
_WHEEL_NAME = re.compile(r"\A[A-Za-z0-9._+!-]+\.whl\Z")
_FOREIGN_PLATFORM = re.compile(r"(?:win32|win_amd64|macosx|musllinux|_i686|_aarch64|_arm64)")


class WheelhouseCode(StrEnum):
    """Closed wheelhouse validation findings."""

    APPLICATION = "APPLICATION"
    CONTENT = "CONTENT"
    INVENTORY = "INVENTORY"
    PLATFORM = "PLATFORM"
    POLICY = "POLICY"


@dataclass(frozen=True, slots=True)
class WheelhouseFinding:
    """One stable fail-closed wheelhouse finding."""

    code: WheelhouseCode
    detail: str


@dataclass(frozen=True, slots=True)
class WheelhouseReport:
    """One validated wheelhouse contract summary."""

    wheels: int
    applications: int
    verified_on_disk: int


def _read_object(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise ValueError(_DOCUMENT_TOO_LARGE)
    value: object = json.loads(raw)
    document = _string_object(value)
    if document is None:
        raise TypeError(_DOCUMENT_ROOT)
    return document


def _string_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    candidate = cast("dict[object, object]", value)
    if not all(type(key) is str for key in candidate):
        return None
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast("list[object]", value)


def _validate_header(
    policy: dict[str, object], base_image_ref: object
) -> tuple[WheelhouseFinding, ...]:
    """Require the exact platform, base image, and offline hash policy."""
    findings: list[WheelhouseFinding] = []
    if (
        frozenset(policy) != _DOCUMENT_KEYS
        or policy.get("schema_version") != 1
        or policy.get("status") != "LOCKED_OFFLINE_WHEELHOUSE"
        or policy.get("wheelhouse_path") != "var/wheelhouse/wheels"
    ):
        findings.append(WheelhouseFinding(WheelhouseCode.INVENTORY, "document"))
    if policy.get("target_platform") != "linux/amd64" or policy.get("python_tag") != "cp314":
        findings.append(WheelhouseFinding(WheelhouseCode.PLATFORM, "target"))
    if policy.get("base_image_ref") != base_image_ref:
        findings.append(WheelhouseFinding(WheelhouseCode.PLATFORM, "base image"))
    if (
        policy.get("require_hashes") is not True
        or policy.get("network_during_install_forbidden") is not True
        or policy.get("tracked_in_git") is not False
    ):
        findings.append(WheelhouseFinding(WheelhouseCode.POLICY, "install policy"))
    return tuple(findings)


def _validate_applications(value: object) -> tuple[WheelhouseFinding, ...]:
    """Require one hashed requirement export for each of the five applications."""
    applications = _string_object(value)
    if applications is None or frozenset(applications) != _EXPECTED_APPLICATIONS:
        return (WheelhouseFinding(WheelhouseCode.APPLICATION, "coverage"),)
    findings: list[WheelhouseFinding] = []
    for name in sorted(applications):
        entry = _string_object(applications[name])
        if entry is None:
            findings.append(WheelhouseFinding(WheelhouseCode.APPLICATION, name))
            continue
        requirements_digest = entry.get("requirements_sha256")
        pinned_distributions = entry.get("pinned_distributions")
        if (
            frozenset(entry) != _APPLICATION_KEYS
            or type(requirements_digest) is not str
            or _SHA256.fullmatch(requirements_digest) is None
            or type(pinned_distributions) is not int
            or pinned_distributions <= 0
        ):
            findings.append(WheelhouseFinding(WheelhouseCode.APPLICATION, name))
    return tuple(findings)


def _validate_wheels(policy: dict[str, object]) -> tuple[WheelhouseFinding, ...]:
    """Require a complete, deduplicated, correctly targeted wheel inventory."""
    wheels = _object_list(policy.get("wheels"))
    if wheels is None or not wheels:
        return (WheelhouseFinding(WheelhouseCode.INVENTORY, "wheels"),)
    if policy.get("wheel_count") != len(wheels):
        return (WheelhouseFinding(WheelhouseCode.INVENTORY, "wheel count"),)
    findings: list[WheelhouseFinding] = []
    names: set[str] = set()
    for raw_wheel in wheels:
        wheel = _string_object(raw_wheel)
        if wheel is None or frozenset(wheel) != _WHEEL_KEYS:
            findings.append(WheelhouseFinding(WheelhouseCode.INVENTORY, "wheel entry"))
            continue
        filename = wheel.get("filename")
        digest = wheel.get("sha256")
        size = wheel.get("size_bytes")
        label = filename if isinstance(filename, str) else "unknown"
        if (
            not isinstance(filename, str)
            or _WHEEL_NAME.fullmatch(filename) is None
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or type(size) is not int
            or size <= 0
        ):
            findings.append(WheelhouseFinding(WheelhouseCode.INVENTORY, label))
            continue
        if filename in names:
            findings.append(WheelhouseFinding(WheelhouseCode.INVENTORY, f"duplicate {label}"))
        names.add(filename)
        if _FOREIGN_PLATFORM.search(filename) is not None:
            findings.append(WheelhouseFinding(WheelhouseCode.PLATFORM, label))
    return tuple(findings)


def validate_wheelhouse(
    policy: dict[str, object], base_image_ref: object
) -> tuple[WheelhouseFinding, ...]:
    """Return every drift; empty proves only one locked offline wheelhouse contract."""
    return (
        *_validate_header(policy, base_image_ref),
        *_validate_applications(policy.get("applications")),
        *_validate_wheels(policy),
    )


def verify_wheelhouse_contents(root: Path, policy: dict[str, object]) -> int:
    """Verify present wheel bytes; an absent wheelhouse verifies nothing and hides nothing."""
    directory = root / "var/wheelhouse/wheels"
    if not directory.is_dir():
        return 0
    wheels = _object_list(policy.get("wheels"))
    if wheels is None:
        raise TypeError(_DOCUMENT_ROOT)
    expected: dict[str, dict[str, object]] = {}
    for raw_wheel in wheels:
        wheel = _string_object(raw_wheel)
        if wheel is None:
            raise TypeError(_DOCUMENT_ROOT)
        filename = wheel.get("filename")
        if type(filename) is not str:
            raise TypeError(_DOCUMENT_ROOT)
        expected[filename] = wheel
    present = {path.name for path in directory.glob("*.whl")}
    expected_names = set(expected)
    if present != expected_names:
        message = f"wheelhouse content drift: {sorted(present ^ expected_names)}"
        raise ValueError(message)
    for filename, wheel in sorted(expected.items()):
        raw = (directory / filename).read_bytes()
        if len(raw) != wheel.get("size_bytes") or hashlib.sha256(raw).hexdigest() != wheel.get(
            "sha256"
        ):
            message = f"wheelhouse digest drift: {filename}"
            raise ValueError(message)
    return len(expected)


def check_wheelhouse(root: Path) -> WheelhouseReport:
    """Validate the locked wheelhouse contract and any wheels actually present."""
    policy = _read_object(root / WHEELHOUSE_PATH)
    images = _read_object(root / APPLICATION_IMAGE_POLICY_PATH)
    base_image = _string_object(images.get("base_image"))
    base_image_ref = base_image.get("artifact_ref") if base_image is not None else None
    findings = validate_wheelhouse(policy, base_image_ref)
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    applications = _string_object(policy["applications"])
    wheels = _object_list(policy["wheels"])
    if applications is None or wheels is None:
        raise TypeError(_DOCUMENT_ROOT)
    return WheelhouseReport(
        wheels=len(wheels),
        applications=len(applications),
        verified_on_disk=verify_wheelhouse_contents(root, policy),
    )


def main() -> None:
    """Run the locked offline wheelhouse contract gate."""
    root = Path(__file__).resolve().parents[1]
    argparse.ArgumentParser(description=__doc__).parse_args()
    report = check_wheelhouse(root)
    print(  # noqa: T201
        "PASS V1 POC application wheelhouse: "
        f"{report.wheels} wheels, {report.applications} applications, "
        f"{report.verified_on_disk} verified on disk"
    )


if __name__ == "__main__":
    main()
