"""Prepare and verify the exact offline Patchright Chromium runtime input.

The browser bytes are runtime build inputs, not Git content. This tool copies
only the three Patchright-owned directories named by the checked-in policy,
measures every regular file, and atomically publishes an exact local tree.
It never downloads a browser or system package and never invokes Docker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

RUNTIME_POLICY_PATH = Path("infrastructure/poc/patchright_runtime_inputs.json")
SYSTEM_PACKAGE_POLICY_PATH = Path("infrastructure/poc/patchright_runtime_system_packages.json")
_MAX_POLICY_BYTES = 100_000
_SHA256_PREFIX = "sha256:"
_RUNTIME_KEYS = frozenset(
    {
        "browser_registry_sha256",
        "browser_version",
        "deb_dependencies_sha256",
        "directories",
        "file_count",
        "image_path",
        "network_during_build_forbidden",
        "patchright_version",
        "patchright_wheel_sha256",
        "schema_version",
        "size_bytes",
        "staging_path",
        "status",
        "system_package_manifest",
        "target_distribution",
        "target_platform",
        "tracked_in_git",
        "tree_sha256",
    }
)
_DIRECTORY_KEYS = frozenset({"executable", "name", "revision"})
_SYSTEM_KEYS = frozenset(
    {
        "dependency_declaration_sha256",
        "headed_isolated_display_required",
        "network_during_build_forbidden",
        "packages",
        "required_capabilities",
        "schema_version",
        "staging_path",
        "status",
        "target_distribution",
        "target_platform",
    }
)
_PACKAGE_KEYS = frozenset({"filename", "sha256", "size_bytes"})
_EXPECTED_DIRECTORIES = (
    ("chromium-1234", "1234", "chrome-linux64/chrome"),
    (
        "chromium_headless_shell-1234",
        "1234",
        "chrome-headless-shell-linux64/chrome-headless-shell",
    ),
    ("ffmpeg-1011", "1011", "ffmpeg-linux"),
)
_EXPECTED_CAPABILITIES = (
    "PATCHRIGHT_CHROMIUM_HEADLESS",
    "PATCHRIGHT_CHROMIUM_HEADED_XVFB",
    "PATCHRIGHT_FFMPEG",
)


class PatchrightRuntimeError(RuntimeError):
    """One exact, secret-free offline runtime input failure."""


@dataclass(frozen=True, slots=True)
class RuntimeMeasurement:
    """Content identity for the selected browser directories."""

    file_count: int
    size_bytes: int
    tree_sha256: str


@dataclass(frozen=True, slots=True)
class PatchrightRuntimePolicy:
    """Closed checked-in browser input and unresolved system-package policy."""

    staging_path: Path
    image_path: str
    directories: tuple[str, ...]
    executables: tuple[str, ...]
    expected: RuntimeMeasurement
    system_package_manifest: Path


@dataclass(frozen=True, slots=True)
class PatchrightBuildInputs:
    """Verified local browser and Debian-package directories for one image build."""

    policy: PatchrightRuntimePolicy
    browser_root: Path
    system_packages_root: Path


def _object(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PatchrightRuntimeError(code)
    candidate = cast("dict[object, object]", value)
    if not all(type(key) is str for key in candidate):
        raise PatchrightRuntimeError(code)
    return cast("dict[str, object]", candidate)


def _objects(value: object, code: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise PatchrightRuntimeError(code)
    return tuple(_object(item, code) for item in cast("list[object]", value))


def _read_document(path: Path, code: str) -> dict[str, object]:
    try:
        if not path.is_file() or path.is_symlink():
            raise PatchrightRuntimeError(code)
        raw = path.read_bytes()
        if len(raw) > _MAX_POLICY_BYTES:
            raise PatchrightRuntimeError(code)
        value: object = json.loads(raw)
    except (OSError, TypeError, ValueError) as error:
        raise PatchrightRuntimeError(code) from error
    return _object(value, code)


def _sha256_value(value: object, code: str) -> str:
    if (
        type(value) is not str
        or not value.startswith(_SHA256_PREFIX)
        or len(value) != len(_SHA256_PREFIX) + 64
    ):
        raise PatchrightRuntimeError(code)
    try:
        int(value.removeprefix(_SHA256_PREFIX), 16)
    except ValueError as error:
        raise PatchrightRuntimeError(code) from error
    return value


def _relative_path(value: object, code: str) -> Path:
    if type(value) is not str or not value or value != value.strip():
        raise PatchrightRuntimeError(code)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise PatchrightRuntimeError(code)
    return path


def load_runtime_policy(root: Path) -> PatchrightRuntimePolicy:
    """Load the exact checked-in browser and system-package input contracts."""
    code = "PATCHRIGHT_RUNTIME_POLICY_INVALID"
    document = _read_document(root / RUNTIME_POLICY_PATH, code)
    if (
        frozenset(document) != _RUNTIME_KEYS
        or document.get("schema_version") != 1
        or document.get("status") != "PINNED_OFFLINE_BROWSER_BYTES_SYSTEM_PACKAGES_REQUIRED"
        or document.get("target_platform") != "linux/amd64"
        or document.get("target_distribution") != "Debian GNU/Linux 13 (trixie)"
        or document.get("patchright_version") != "1.62.1"
        or document.get("browser_version") != "151.0.7922.34"
        or document.get("network_during_build_forbidden") is not True
        or document.get("tracked_in_git") is not False
    ):
        raise PatchrightRuntimeError(code)
    for key in (
        "patchright_wheel_sha256",
        "browser_registry_sha256",
        "deb_dependencies_sha256",
        "tree_sha256",
    ):
        _sha256_value(document.get(key), code)
    directories = _objects(document.get("directories"), code)
    rows: list[tuple[str, str, str]] = []
    for item in directories:
        if frozenset(item) != _DIRECTORY_KEYS:
            raise PatchrightRuntimeError(code)
        name = _relative_path(item.get("name"), code).as_posix()
        executable = _relative_path(item.get("executable"), code).as_posix()
        revision = item.get("revision")
        if type(revision) is not str:
            raise PatchrightRuntimeError(code)
        rows.append((name, revision, executable))
    if tuple(rows) != _EXPECTED_DIRECTORIES:
        raise PatchrightRuntimeError(code)
    file_count = document.get("file_count")
    size_bytes = document.get("size_bytes")
    if (
        type(file_count) is not int
        or file_count < 1
        or type(size_bytes) is not int
        or size_bytes < 1
    ):
        raise PatchrightRuntimeError(code)
    staging_path = _relative_path(document.get("staging_path"), code)
    manifest_path = _relative_path(document.get("system_package_manifest"), code)
    image_path = document.get("image_path")
    if image_path != "/opt/asklegal/ms-playwright":
        raise PatchrightRuntimeError(code)
    _validate_system_package_policy(root / manifest_path)
    return PatchrightRuntimePolicy(
        staging_path,
        cast("str", image_path),
        tuple(row[0] for row in rows),
        tuple(f"{row[0]}/{row[2]}" for row in rows),
        RuntimeMeasurement(file_count, size_bytes, str(document["tree_sha256"])),
        manifest_path,
    )


def _validate_system_package_policy(path: Path) -> None:
    code = "PATCHRIGHT_SYSTEM_PACKAGE_POLICY_INVALID"
    document = _read_document(path, code)
    capabilities = document.get("required_capabilities")
    if (
        frozenset(document) != _SYSTEM_KEYS
        or document.get("schema_version") != 1
        or document.get("status") not in {"INPUT_REQUIRED", "LOCKED"}
        or document.get("target_platform") != "linux/amd64"
        or document.get("target_distribution") != "Debian GNU/Linux 13 (trixie)"
        or document.get("network_during_build_forbidden") is not True
        or document.get("headed_isolated_display_required") is not True
        or capabilities != list(_EXPECTED_CAPABILITIES)
    ):
        raise PatchrightRuntimeError(code)
    _relative_path(document.get("staging_path"), code)
    _sha256_value(document.get("dependency_declaration_sha256"), code)
    packages = _objects(document.get("packages"), code)
    if document["status"] == "INPUT_REQUIRED" and packages:
        raise PatchrightRuntimeError(code)
    if document["status"] == "LOCKED" and not packages:
        raise PatchrightRuntimeError(code)
    for package in packages:
        if (
            frozenset(package) != _PACKAGE_KEYS
            or type(package.get("filename")) is not str
            or Path(str(package["filename"])).name != package["filename"]
            or type(size_bytes := package.get("size_bytes")) is not int
            or size_bytes < 1
        ):
            raise PatchrightRuntimeError(code)
        _sha256_value(package.get("sha256"), code)


def system_package_closure_ready(root: Path) -> bool:
    """Return whether the checked-in browser system-package manifest is locked."""
    policy = load_runtime_policy(root)
    document = _read_document(
        root / policy.system_package_manifest, "PATCHRIGHT_SYSTEM_PACKAGE_POLICY_INVALID"
    )
    return document["status"] == "LOCKED"


def verify_system_package_closure(root: Path, policy: PatchrightRuntimePolicy) -> Path:
    """Verify every locked Debian package and reject missing or extra build inputs."""
    code = "PATCHRIGHT_DEBIAN_SYSTEM_PACKAGE_CLOSURE_REQUIRED"
    document = _read_document(root / policy.system_package_manifest, code)
    if document.get("status") != "LOCKED":
        raise PatchrightRuntimeError(code)
    packages = _objects(document.get("packages"), code)
    staging = root / _relative_path(document.get("staging_path"), code)
    if not staging.is_dir() or staging.is_symlink():
        raise PatchrightRuntimeError(code)
    expected: set[str] = set()
    for package in packages:
        filename = package.get("filename")
        size_bytes = package.get("size_bytes")
        digest = package.get("sha256")
        if type(filename) is not str or type(size_bytes) is not int or type(digest) is not str:
            raise PatchrightRuntimeError(code)
        expected.add(filename)
        candidate = staging / filename
        try:
            raw = candidate.read_bytes()
        except OSError as error:
            raise PatchrightRuntimeError(code) from error
        if (
            not candidate.is_file()
            or candidate.is_symlink()
            or len(raw) != size_bytes
            or f"sha256:{hashlib.sha256(raw).hexdigest()}" != digest
        ):
            raise PatchrightRuntimeError(code)
    try:
        entries = tuple(staging.iterdir())
    except OSError as error:
        raise PatchrightRuntimeError(code) from error
    if any(item.is_symlink() or not item.is_file() for item in entries):
        raise PatchrightRuntimeError(code)
    actual = {item.name for item in entries}
    if actual != expected:
        raise PatchrightRuntimeError(code)
    return staging


def verify_build_inputs(root: Path) -> PatchrightBuildInputs:
    """Resolve and verify all offline inputs needed by the acquisition image stage."""
    policy = load_runtime_policy(root)
    browser_root = root / policy.staging_path
    validate_runtime_tree(browser_root, policy)
    system_packages_root = verify_system_package_closure(root, policy)
    return PatchrightBuildInputs(policy, browser_root, system_packages_root)


def measure_runtime_tree(path: Path, directories: tuple[str, ...]) -> RuntimeMeasurement:
    """Measure exact relative paths, modes, sizes, and bytes without following links."""
    code = "PATCHRIGHT_RUNTIME_INPUT_INVALID"
    if not path.is_dir() or path.is_symlink():
        raise PatchrightRuntimeError(code)
    rows: list[dict[str, object]] = []
    for directory in directories:
        base = path / directory
        if not base.is_dir() or base.is_symlink():
            raise PatchrightRuntimeError(code)
        for item in sorted(base.rglob("*"), key=lambda value: value.relative_to(path).as_posix()):
            if item.is_symlink():
                raise PatchrightRuntimeError(code)
            if item.is_dir():
                continue
            if not item.is_file():
                raise PatchrightRuntimeError(code)
            try:
                raw = item.read_bytes()
                mode = stat.S_IMODE(item.stat(follow_symlinks=False).st_mode)
            except OSError as error:
                raise PatchrightRuntimeError(code) from error
            rows.append(
                {
                    "mode": mode,
                    "path": item.relative_to(path).as_posix(),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
            )
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return RuntimeMeasurement(
        len(rows),
        sum(cast("int", row["size_bytes"]) for row in rows),
        f"sha256:{hashlib.sha256(canonical).hexdigest()}",
    )


def validate_runtime_tree(path: Path, policy: PatchrightRuntimePolicy) -> RuntimeMeasurement:
    """Require the exact pinned browser tree and executable entry points."""
    measured = measure_runtime_tree(path, policy.directories)
    if measured != policy.expected:
        message = "PATCHRIGHT_RUNTIME_INPUT_DRIFT"
        raise PatchrightRuntimeError(message)
    for relative in policy.executables:
        executable = path / relative
        if not executable.is_file() or executable.is_symlink():
            message = "PATCHRIGHT_RUNTIME_INPUT_INVALID"
            raise PatchrightRuntimeError(message)
        if stat.S_IMODE(executable.stat(follow_symlinks=False).st_mode) & 0o111 == 0:
            message = "PATCHRIGHT_RUNTIME_INPUT_INVALID"
            raise PatchrightRuntimeError(message)
    return measured


def prepare_runtime_tree(source: Path, destination: Path, policy: PatchrightRuntimePolicy) -> None:
    """Copy one exact cache tree to an atomic, create-or-match local build input."""
    validate_runtime_tree(source, policy)
    if destination.exists():
        validate_runtime_tree(destination, policy)
        return
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.prepare-", dir=destination.parent)
    )
    try:
        for directory in policy.directories:
            shutil.copytree(source / directory, temporary / directory, symlinks=False)
        validate_runtime_tree(temporary, policy)
        temporary.replace(destination)
        descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    validate_runtime_tree(destination, policy)


def main() -> None:
    """Prepare or verify the exact local browser tree without external effects."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    policy = load_runtime_policy(root)
    destination = arguments.output or root / policy.staging_path
    if not destination.is_absolute():
        destination = root / destination
    if arguments.check:
        measurement = validate_runtime_tree(destination, policy)
    else:
        if not isinstance(arguments.source, Path):
            parser.error("--source is required unless --check is used")
        source = arguments.source.resolve(strict=True)
        prepare_runtime_tree(source, destination, policy)
        measurement = validate_runtime_tree(destination, policy)
    blocker = (
        "NONE"
        if system_package_closure_ready(root)
        else "PATCHRIGHT_DEBIAN_SYSTEM_PACKAGE_CLOSURE_REQUIRED"
    )
    print(  # noqa: T201
        f"PATCHRIGHT_RUNTIME_READY files={measurement.file_count} "
        f"bytes={measurement.size_bytes} tree={measurement.tree_sha256} blocker={blocker}"
    )


if __name__ == "__main__":
    main()
