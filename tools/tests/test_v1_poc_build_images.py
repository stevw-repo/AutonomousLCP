"""Regression tests for measured V1 POC installed-tree evidence."""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from asklegal_processing.tokenization import o200k_base_encoding_from_exact_resource

import tools.v1_poc_build_images as image_builder
from tools.v1_poc_build_images import (
    WORKSPACE_WHEELS_PATH,
    ImageBuildError,
    build_workspace_wheels,
    installed_tree_content_digest,
    prepare_context,
    workspace_source_fingerprint,
)
from tools.v1_poc_patchright_runtime import (
    PatchrightBuildInputs,
    PatchrightRuntimeError,
    PatchrightRuntimePolicy,
    RuntimeMeasurement,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_O200K_BASE_RESOURCE = "asklegal_processing/_resources/o200k_base.tiktoken"
_O200K_BASE_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"


def test_workspace_source_fingerprint_binds_rotation_network_helper(tmp_path: Path) -> None:
    """Changing the privileged wrapper invalidates the candidate-image source proof."""
    root = tmp_path / "repository"
    helper = root / "infrastructure/poc/libexec/asklegal-vault-application-rotation-network"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"first")
    (root / "apps").mkdir()
    (root / "packages").mkdir()
    before = workspace_source_fingerprint(root)
    helper.write_bytes(b"second")

    assert workspace_source_fingerprint(root) != before


def test_installed_tree_digest_changes_when_installed_bytes_change(tmp_path: Path) -> None:
    """A stale image-policy digest cannot survive a package or resource byte mutation."""
    tree = tmp_path / "asklegal"
    package = tree / "lib/python3.14/site-packages/asklegal_processing"
    package.mkdir(parents=True)
    resource = package / "o200k_base.tiktoken"
    resource.write_bytes(b"exact-rank-bytes")

    before = installed_tree_content_digest(tree)
    resource.write_bytes(b"tampered-rank-bytes")

    assert installed_tree_content_digest(tree) != before


def test_fresh_processing_wheel_carries_exact_rank_resource_and_count() -> None:
    """The actual wheel image build consumes must preserve the rank bytes and vector count."""
    assert build_workspace_wheels(REPOSITORY_ROOT) == 19
    wheel = next((REPOSITORY_ROOT / WORKSPACE_WHEELS_PATH).glob("asklegal_processing-*.whl"))
    with ZipFile(wheel) as archive:
        resource = archive.read(_O200K_BASE_RESOURCE)

    assert hashlib.sha256(resource).hexdigest() == _O200K_BASE_SHA256
    assert (
        len(
            o200k_base_encoding_from_exact_resource(resource).encode_ordinary(
                "香港法例 Cap. 622 第 2 條 — Companies Ordinance."
            )
        )
        == 17
    )


def test_build_all_rejects_tampered_requirements_before_workspace_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route must verify copied requirements before it creates any build input."""
    root = tmp_path / "repository"
    for relative in (
        "infrastructure/poc/application_image_inputs.json",
        "infrastructure/poc/application_wheelhouse.json",
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative, destination)
    wheelhouse = root / "var/wheelhouse"
    wheelhouse.mkdir(parents=True)
    source_wheelhouse = REPOSITORY_ROOT / "var/wheelhouse"
    for requirements in source_wheelhouse.glob("asklegal-*.txt"):
        shutil.copy2(requirements, wheelhouse / requirements.name)
    (wheelhouse / "wheels").symlink_to(source_wheelhouse / "wheels", target_is_directory=True)
    target = wheelhouse / "asklegal-legal-processing-worker.txt"
    target.write_bytes(target.read_bytes() + b"# tampered\n")

    workspace_build_calls: list[Path] = []

    def workspace_build_must_not_run(candidate: Path) -> int:
        workspace_build_calls.append(candidate)
        return 19

    monkeypatch.setattr(image_builder, "build_workspace_wheels", workspace_build_must_not_run)

    with pytest.raises(ImageBuildError, match="wheelhouse"):
        image_builder.build_all(root, "tampered-requirements")
    assert workspace_build_calls == []


def test_build_tool_cli_imports_before_docker_is_called() -> None:
    """The user-facing repository build route must load its verifier as a script."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(REPOSITORY_ROOT / "tools/v1_poc_build_images.py"), "--help"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_build_all_stops_before_workspace_build_when_runtime_closure_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid Debian closure must stop before wheel or Docker work."""
    workspace_build_calls: list[Path] = []

    def invalid_runtime(_root: Path) -> PatchrightBuildInputs:
        message = "PATCHRIGHT_DEBIAN_SYSTEM_PACKAGE_CLOSURE_REQUIRED"
        raise PatchrightRuntimeError(message)

    def workspace_build_must_not_run(candidate: Path) -> int:
        workspace_build_calls.append(candidate)
        return 19

    def verified_wheelhouse(_root: Path) -> None:
        return

    monkeypatch.setattr(image_builder, "verify_build_wheelhouse", verified_wheelhouse)
    monkeypatch.setattr(image_builder, "verify_build_inputs", invalid_runtime)
    monkeypatch.setattr(image_builder, "build_workspace_wheels", workspace_build_must_not_run)

    with pytest.raises(
        ImageBuildError,
        match="PATCHRIGHT_DEBIAN_SYSTEM_PACKAGE_CLOSURE_REQUIRED",
    ):
        image_builder.build_all(REPOSITORY_ROOT, "invalid-runtime")
    assert workspace_build_calls == []


def test_acquisition_context_requires_verified_browser_inputs(tmp_path: Path) -> None:
    """Never build the acquisition stage without its exact offline browser closure."""
    image: dict[str, object] = {
        "artifact_id": "acquisition-worker",
        "distribution": "asklegal-acquisition-worker",
        "workspace_distribution_closure": [],
    }
    (tmp_path / "var/debs").mkdir(parents=True)
    (tmp_path / "var/wheelhouse/wheels").mkdir(parents=True)
    requirements = tmp_path / "var/wheelhouse/asklegal-acquisition-worker.txt"
    requirements.write_text("", encoding="utf-8")
    (tmp_path / WORKSPACE_WHEELS_PATH).mkdir(parents=True)

    with pytest.raises(ImageBuildError, match="Patchright runtime build inputs missing"):
        prepare_context(tmp_path, image)


def test_acquisition_context_copies_only_verified_browser_inputs(tmp_path: Path) -> None:
    """Put browser bytes and their Debian archives only in the acquisition context."""
    image: dict[str, object] = {
        "artifact_id": "acquisition-worker",
        "distribution": "asklegal-acquisition-worker",
        "workspace_distribution_closure": [],
    }
    (tmp_path / "var/debs").mkdir(parents=True)
    (tmp_path / "var/wheelhouse/wheels").mkdir(parents=True)
    (tmp_path / "var/wheelhouse/asklegal-acquisition-worker.txt").write_text("", encoding="utf-8")
    (tmp_path / WORKSPACE_WHEELS_PATH).mkdir(parents=True)
    browser = tmp_path / "browser"
    browser.mkdir()
    (browser / "marker").write_bytes(b"browser")
    debs = tmp_path / "browser-debs"
    debs.mkdir()
    (debs / "xvfb.deb").write_bytes(b"deb")
    runtime = PatchrightBuildInputs(
        PatchrightRuntimePolicy(
            Path("browser"),
            "/opt/asklegal/ms-playwright",
            (),
            (),
            RuntimeMeasurement(0, 0, "sha256:" + "0" * 64),
            Path("system.json"),
        ),
        browser,
        debs,
    )

    context = prepare_context(tmp_path, image, runtime)

    assert (context / "browser-runtime/marker").read_bytes() == b"browser"
    assert (context / "browser-debs/xvfb.deb").read_bytes() == b"deb"
