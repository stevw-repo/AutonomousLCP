"""Tests for the exact offline Patchright browser build input."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.v1_poc_patchright_runtime import (
    PatchrightRuntimeError,
    PatchrightRuntimePolicy,
    RuntimeMeasurement,
    load_runtime_policy,
    measure_runtime_tree,
    prepare_runtime_tree,
    system_package_closure_ready,
    validate_runtime_tree,
    verify_build_inputs,
    verify_system_package_closure,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _fixture_policy(path: Path) -> PatchrightRuntimePolicy:
    directories = ("chromium-1234", "chromium_headless_shell-1234", "ffmpeg-1011")
    measured = measure_runtime_tree(path, directories)
    return PatchrightRuntimePolicy(
        Path("var/application-inputs/ms-playwright"),
        "/opt/asklegal/ms-playwright",
        directories,
        (
            "chromium-1234/chrome-linux64/chrome",
            "chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell",
            "ffmpeg-1011/ffmpeg-linux",
        ),
        measured,
        Path("infrastructure/poc/patchright_runtime_system_packages.json"),
    )


def _runtime_tree(path: Path) -> None:
    files = {
        "chromium-1234/chrome-linux64/chrome": b"headed-browser",
        (
            "chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell"
        ): b"headless-browser",
        "ffmpeg-1011/ffmpeg-linux": b"ffmpeg",
    }
    for relative, content in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o755)


def test_repository_policy_pins_observed_browser_and_debian_runtime_bytes() -> None:
    """Bind the observed browser tree and downloaded Debian closure exactly."""
    policy = load_runtime_policy(REPOSITORY_ROOT)

    assert policy.expected == RuntimeMeasurement(
        598,
        685_353_456,
        "sha256:fa4d31234885e3dd42df99d947c27d5c0a3d62e24d5818fa17aa16ac7f99aabf",
    )
    assert system_package_closure_ready(REPOSITORY_ROOT) is True


def test_prepare_is_atomic_exact_and_replayable(tmp_path: Path) -> None:
    """Publish one exact tree and adopt the same bytes on replay."""
    source = tmp_path / "source"
    destination = tmp_path / "published"
    _runtime_tree(source)
    policy = _fixture_policy(source)

    prepare_runtime_tree(source, destination, policy)
    prepare_runtime_tree(source, destination, policy)

    assert validate_runtime_tree(destination, policy) == policy.expected
    assert not tuple(tmp_path.glob(".published.prepare-*"))


def test_prepare_rejects_byte_drift_without_overwriting_destination(tmp_path: Path) -> None:
    """Reject changed source bytes without replacing a valid retained tree."""
    source = tmp_path / "source"
    destination = tmp_path / "published"
    _runtime_tree(source)
    policy = _fixture_policy(source)
    prepare_runtime_tree(source, destination, policy)
    before = hashlib.sha256(
        (destination / "chromium-1234/chrome-linux64/chrome").read_bytes()
    ).hexdigest()
    (source / "chromium-1234/chrome-linux64/chrome").write_bytes(b"drift")

    with pytest.raises(PatchrightRuntimeError, match="PATCHRIGHT_RUNTIME_INPUT_DRIFT"):
        prepare_runtime_tree(source, destination, policy)

    assert (
        hashlib.sha256(
            (destination / "chromium-1234/chrome-linux64/chrome").read_bytes()
        ).hexdigest()
        == before
    )


def test_measurement_rejects_symlinked_runtime_member(tmp_path: Path) -> None:
    """Never follow a browser-cache member outside the selected runtime root."""
    source = tmp_path / "source"
    _runtime_tree(source)
    browser = source / "chromium-1234/chrome-linux64/chrome"
    browser.unlink()
    browser.symlink_to(tmp_path / "outside")

    with pytest.raises(PatchrightRuntimeError, match="PATCHRIGHT_RUNTIME_INPUT_INVALID"):
        measure_runtime_tree(
            source,
            ("chromium-1234", "chromium_headless_shell-1234", "ffmpeg-1011"),
        )


def test_locked_system_manifest_requires_exact_package_inventory(tmp_path: Path) -> None:
    """A LOCKED claim requires at least one exact package entry."""
    root = tmp_path / "repository"
    policy = json.loads(
        (REPOSITORY_ROOT / "infrastructure/poc/patchright_runtime_inputs.json").read_bytes()
    )
    system = json.loads(
        (
            REPOSITORY_ROOT / "infrastructure/poc/patchright_runtime_system_packages.json"
        ).read_bytes()
    )
    system["status"] = "LOCKED"
    system["packages"] = []
    for relative, document in (
        ("infrastructure/poc/patchright_runtime_inputs.json", policy),
        ("infrastructure/poc/patchright_runtime_system_packages.json", system),
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(PatchrightRuntimeError, match="PATCHRIGHT_SYSTEM_PACKAGE_POLICY_INVALID"):
        load_runtime_policy(root)


def test_build_inputs_resolve_exact_locked_debian_closure() -> None:
    """The current local build input includes exact browser and Debian package bytes."""
    inputs = verify_build_inputs(REPOSITORY_ROOT)

    assert inputs.browser_root == REPOSITORY_ROOT / "var/application-inputs/ms-playwright"
    assert inputs.system_packages_root == REPOSITORY_ROOT / "var/patchright-debs"


def test_locked_system_package_files_are_exact_and_no_extra_is_accepted(
    tmp_path: Path,
) -> None:
    """Bind every Debian archive byte and reject an expanded build directory."""
    source = tmp_path / "source"
    _runtime_tree(source)
    policy = _fixture_policy(source)
    manifest = tmp_path / policy.system_package_manifest
    manifest.parent.mkdir(parents=True)
    packages = tmp_path / "var/patchright-debs"
    packages.mkdir(parents=True)
    archive = packages / "xvfb_exact_amd64.deb"
    archive.write_bytes(b"exact-deb")
    document = json.loads(
        (
            REPOSITORY_ROOT / "infrastructure/poc/patchright_runtime_system_packages.json"
        ).read_bytes()
    )
    document["status"] = "LOCKED"
    document["packages"] = [
        {
            "filename": archive.name,
            "sha256": f"sha256:{hashlib.sha256(archive.read_bytes()).hexdigest()}",
            "size_bytes": archive.stat().st_size,
        }
    ]
    manifest.write_text(json.dumps(document), encoding="utf-8")

    assert verify_system_package_closure(tmp_path, policy) == packages
    (packages / "extra.deb").write_bytes(b"extra")
    with pytest.raises(
        PatchrightRuntimeError,
        match="PATCHRIGHT_DEBIAN_SYSTEM_PACKAGE_CLOSURE_REQUIRED",
    ):
        verify_system_package_closure(tmp_path, policy)
    (packages / "extra.deb").unlink()
    (packages / "unverified-directory").mkdir()
    with pytest.raises(
        PatchrightRuntimeError,
        match="PATCHRIGHT_DEBIAN_SYSTEM_PACKAGE_CLOSURE_REQUIRED",
    ):
        verify_system_package_closure(tmp_path, policy)
