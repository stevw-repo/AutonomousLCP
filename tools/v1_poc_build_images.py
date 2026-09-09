"""Build the five reproducible V1 POC application images from pinned inputs.

Every input is pinned before the build starts: the base image by digest, the
third-party wheels by the locked offline wheelhouse and their recorded hashes,
and the workspace distributions by the exact uv lock. The build context contains
nothing else, and the build itself runs with networking disabled, so an input
that was not pinned cannot be fetched.

This tool builds and reports. It does not push, admit, or enable anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

if __package__:
    from tools.v1_poc_patchright_runtime import (
        PatchrightBuildInputs,
        PatchrightRuntimeError,
        verify_build_inputs,
    )
    from tools.v1_poc_wheelhouse import check_wheelhouse
else:
    from v1_poc_patchright_runtime import (
        PatchrightBuildInputs,
        PatchrightRuntimeError,
        verify_build_inputs,
    )
    from v1_poc_wheelhouse import check_wheelhouse

IMAGE_POLICY_PATH = Path("infrastructure/poc/application_image_inputs.json")
IDENTITY_POLICY_PATH = Path("infrastructure/poc/host_identity_inputs.json")
DOCKERFILE_PATH = Path("infrastructure/poc/images/Dockerfile")
WHEELHOUSE_PATH = Path("var/wheelhouse")
WORKSPACE_WHEELS_PATH = Path("var/image-build/workspace-wheels")
WORKSPACE_UV_CACHE_PATH = Path("var/image-build/uv-cache")
SYSTEM_PACKAGES_PATH = Path("var/debs")
_BUILD_ROOT = Path("var/image-build/context")
_BUILD_TIMEOUT_SECONDS = 1_800
_WHEEL_BUILD_TIMEOUT_SECONDS = 900
_SG = "/usr/bin/sg"
_UV = Path.home() / ".local/bin/uv"
_LOCKED_UV_VERSION = "0.12.5"
_SOURCE_ROOT_FILES = (
    ".python-version",
    "infrastructure/poc/images/Dockerfile",
    "infrastructure/poc/libexec/asklegal-vault-application-rotation-network",
    "pyproject.toml",
    "tools/v1_poc_build_images.py",
    "uv.lock",
)
_SOURCE_PROJECT_FILES = ("README.md", "pyproject.toml")


class ImageBuildError(RuntimeError):
    """One exact, secret-free image build failure."""


@dataclass(frozen=True, slots=True)
class BuiltImage:
    """One built image and its measured installed-tree content digest."""

    artifact_id: str
    tag: str
    image_id: str
    installed_tree_sha512: str


@dataclass(frozen=True, slots=True)
class ImageBuildParameters:
    """Inputs shared by context assembly and one Docker build invocation."""

    base_image: str
    runtime_uid: int
    tag: str
    patchright: PatchrightBuildInputs


def workspace_source_fingerprint(root: Path) -> str:
    """Bind the exact wheel-producing workspace source, including untracked files."""
    candidates: set[Path] = {root / name for name in _SOURCE_ROOT_FILES}
    for collection in (root / "apps", root / "packages"):
        for project in collection.iterdir():
            if not project.is_dir() or project.is_symlink():
                continue
            candidates.update(project / name for name in _SOURCE_PROJECT_FILES)
            source = project / "src"
            if source.is_dir() and not source.is_symlink():
                candidates.update(path for path in source.rglob("*") if path.is_file())
    selected = tuple(sorted((path for path in candidates if path.is_file()), key=str))
    if not selected or any(path.is_symlink() or not path.is_relative_to(root) for path in selected):
        message = "workspace source inventory invalid"
        raise ImageBuildError(message)
    digest = hashlib.sha256()
    for path in selected:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(hashlib.sha256(content).digest())
    return "sha256:" + digest.hexdigest()


def _read_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_bytes())
    document = _string_object(value)
    if document is None:
        message = f"image build document root: {path}"
        raise ImageBuildError(message)
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


def build_workspace_wheels(root: Path) -> int:
    """Rebuild every workspace distribution from the current source tree.

    The build context is assembled from wheels on disk. Reusing wheels left by an
    earlier session would silently ship stale code: the image builds, the tag is
    new, and the change under test is simply absent. Rebuilding here makes the
    image a function of the source tree rather than of whatever ran last.
    """
    version = subprocess.run(  # noqa: S603
        [str(_UV), "--version"], check=False, capture_output=True, text=True, timeout=60
    )
    if version.returncode != 0 or _LOCKED_UV_VERSION not in version.stdout:
        message = f"uv {_LOCKED_UV_VERSION} required: {version.stdout.strip() or 'not found'}"
        raise ImageBuildError(message)
    target = root / WORKSPACE_WHEELS_PATH
    cache = root / WORKSPACE_UV_CACHE_PATH
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    cache.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["UV_CACHE_DIR"] = str(cache)
    result = subprocess.run(  # noqa: S603
        [str(_UV), "build", "--offline", "--all-packages", "--out-dir", str(target)],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=_WHEEL_BUILD_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        message = f"workspace wheel build failed\n{result.stderr[-4000:]}"
        raise ImageBuildError(message)
    return len(list(target.glob("*.whl")))


def verify_build_wheelhouse(root: Path) -> None:
    """Require every copied third-party input to match the locked wheelhouse before builds."""
    try:
        report = check_wheelhouse(root)
    except (OSError, TypeError, ValueError) as error:
        message = "wheelhouse verification failed"
        raise ImageBuildError(message) from error
    if report.verified_on_disk != report.wheels:
        message = "wheelhouse content unavailable"
        raise ImageBuildError(message)


def _runtime_uid(identities: dict[str, object], service_id: str) -> int:
    entries = identities.get("container_identity_map")
    entry_items = _object_list(entries)
    if entry_items is None:
        message = "container identity map missing"
        raise ImageBuildError(message)
    for raw_entry in entry_items:
        entry = _string_object(raw_entry)
        if entry is not None and entry.get("service_id") == service_id:
            uid = entry.get("runtime_uid")
            if type(uid) is int:
                return uid
    message = f"no runtime identity for {service_id}"
    raise ImageBuildError(message)


def prepare_context(
    root: Path,
    image: dict[str, object],
    patchright: PatchrightBuildInputs | None = None,
) -> Path:
    """Assemble the exact, minimal build context for one application."""
    distribution = image["distribution"]
    closure = _object_list(image["workspace_distribution_closure"])
    if type(distribution) is not str or closure is None:
        message = f"workspace closure for {distribution}"
        raise ImageBuildError(message)
    context = root / _BUILD_ROOT / distribution
    if context.exists():
        shutil.rmtree(context)
    (context / "wheelhouse").mkdir(parents=True)
    (context / "workspace").mkdir(parents=True)
    shutil.copytree(root / SYSTEM_PACKAGES_PATH, context / "debs", dirs_exist_ok=True)
    shutil.copytree(
        root / WHEELHOUSE_PATH / "wheels", context / "wheelhouse/wheels", dirs_exist_ok=True
    )
    shutil.copy2(
        root / WHEELHOUSE_PATH / f"{distribution}.txt",
        context / "wheelhouse" / f"{distribution}.txt",
    )
    available = {
        path.name.split("-")[0]: path for path in (root / WORKSPACE_WHEELS_PATH).glob("*.whl")
    }
    for member in closure:
        if type(member) is not str:
            message = f"invalid workspace wheel member: {distribution}"
            raise ImageBuildError(message)
        key = member.replace("-", "_")
        wheel = available.get(key)
        if wheel is None:
            message = f"missing workspace wheel: {member}"
            raise ImageBuildError(message)
        shutil.copy2(wheel, context / "workspace" / wheel.name)
    if image.get("artifact_id") == "acquisition-worker":
        if patchright is None:
            message = "Patchright runtime build inputs missing"
            raise ImageBuildError(message)
        shutil.copytree(patchright.browser_root, context / "browser-runtime")
        shutil.copytree(patchright.system_packages_root, context / "browser-debs")
    return context


def build_image(
    root: Path,
    image: dict[str, object],
    parameters: ImageBuildParameters,
) -> str:
    """Build one image with networking disabled and return its image id."""
    context = prepare_context(root, image, parameters.patchright)
    runtime_variant = "browser" if image.get("artifact_id") == "acquisition-worker" else "plain"
    command = [
        "docker",
        "build",
        "--network",
        "none",
        "--platform",
        "linux/amd64",
        "--file",
        str(root / DOCKERFILE_PATH),
        "--build-arg",
        f"BASE_IMAGE={parameters.base_image}",
        "--build-arg",
        f"APPLICATION={image['distribution']}",
        "--build-arg",
        f"RUNTIME_UID={parameters.runtime_uid}",
        "--build-arg",
        "SOURCE_DATE_EPOCH=315532800",
        "--build-arg",
        f"RUNTIME_VARIANT={runtime_variant}",
        "--tag",
        parameters.tag,
        str(context),
    ]
    result = subprocess.run(  # noqa: S603
        [_SG, "docker", "-c", " ".join(f"'{item}'" for item in command)],
        check=False,
        capture_output=True,
        text=True,
        timeout=_BUILD_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        message = f"image build failed: {image['artifact_id']}\n{result.stderr[-4000:]}"
        raise ImageBuildError(message)
    inspect = subprocess.run(  # noqa: S603
        [
            _SG,
            "docker",
            "-c",
            f"docker image inspect --format '{{{{.Id}}}}' {parameters.tag}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if inspect.returncode != 0:
        message = f"image inspect failed: {image['artifact_id']}"
        raise ImageBuildError(message)
    return inspect.stdout.strip()


def installed_tree_content_digest(tree: Path) -> str:
    """Return one deterministic SHA-512 over an extracted installed tree's exact content."""
    if not tree.is_dir() or tree.is_symlink():
        message = "installed tree missing"
        raise ImageBuildError(message)
    digest = hashlib.sha512()
    try:
        paths = tuple(sorted(tree.rglob("*"), key=lambda path: path.relative_to(tree).as_posix()))
        for path in paths:
            relative = path.relative_to(tree).as_posix().encode("utf-8")
            if path.is_symlink():
                digest.update(b"link\0")
                digest.update(relative)
                digest.update(b"\0")
                digest.update(path.readlink().as_posix().encode("utf-8"))
            elif path.is_dir():
                digest.update(b"directory\0")
                digest.update(relative)
            elif path.is_file():
                digest.update(b"file\0")
                digest.update(relative)
                digest.update(b"\0")
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            else:
                message = f"unsupported installed-tree entry: {path}"
                raise ImageBuildError(message)
    except OSError as error:
        message = "installed tree measurement failed"
        raise ImageBuildError(message) from error
    return digest.hexdigest()


def installed_tree_digest_for_image(tag: str) -> str:
    """Extract `/opt/asklegal` from one locally built image and measure its content."""
    create = subprocess.run(  # noqa: S603
        [_SG, "docker", "-c", shlex.join(("docker", "create", tag))],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    container_id = create.stdout.strip()
    if create.returncode != 0 or not container_id:
        message = f"image container create failed: {tag}"
        raise ImageBuildError(message)
    try:
        with tempfile.TemporaryDirectory(prefix="asklegal-installed-tree-") as temporary:
            destination = Path(temporary)
            copy = subprocess.run(  # noqa: S603
                [
                    _SG,
                    "docker",
                    "-c",
                    shlex.join(("docker", "cp", f"{container_id}:/opt/asklegal", str(destination))),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if copy.returncode != 0:
                message = f"installed-tree extraction failed: {tag}"
                raise ImageBuildError(message)
            return installed_tree_content_digest(destination / "asklegal")
    finally:
        subprocess.run(  # noqa: S603
            [_SG, "docker", "-c", shlex.join(("docker", "rm", "--force", container_id))],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )


def build_all(root: Path, tag_suffix: str) -> tuple[BuiltImage, ...]:
    """Build every declared application image once from freshly built wheels."""
    verify_build_wheelhouse(root)
    try:
        patchright = verify_build_inputs(root)
    except PatchrightRuntimeError as error:
        message = str(error)
        raise ImageBuildError(message) from error
    build_workspace_wheels(root)
    policy = _read_object(root / IMAGE_POLICY_PATH)
    identities = _read_object(root / IDENTITY_POLICY_PATH)
    base = _string_object(policy["base_image"])
    if base is None:
        message = "base image block"
        raise ImageBuildError(message)
    base_image = base["artifact_ref"]
    images = _object_list(policy["images"])
    if type(base_image) is not str or images is None:
        message = "image inventory"
        raise ImageBuildError(message)
    built: list[BuiltImage] = []
    for raw_image in images:
        image = _string_object(raw_image)
        if image is None or type(image.get("artifact_id")) is not str:
            message = "invalid image inventory entry"
            raise ImageBuildError(message)
        artifact_id = cast("str", image["artifact_id"])
        tag = f"asklegal/{artifact_id}:{tag_suffix}"
        uid = _runtime_uid(identities, artifact_id)
        image_id = build_image(
            root,
            image,
            ImageBuildParameters(base_image, uid, tag, patchright),
        )
        built.append(
            BuiltImage(
                artifact_id,
                tag,
                image_id,
                installed_tree_digest_for_image(tag),
            )
        )
    return tuple(built)


def main() -> None:
    """Build every application image and print its exact identity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag-suffix", default="v1-poc")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        built = build_all(root, arguments.tag_suffix)
    except ImageBuildError as error:
        print(f"NOT_READY {error}", file=sys.stderr)  # noqa: T201
        raise SystemExit(2) from None
    for item in built:
        print(  # noqa: T201
            f"{item.artifact_id} {item.tag} {item.image_id} {item.installed_tree_sha512}"
        )


if __name__ == "__main__":
    main()
