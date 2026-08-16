"""Fail-closed tests for the local package-spike proof."""

import base64
import csv
import hashlib
import io
import os
import zipfile
from pathlib import Path

import pytest

from tools.package_spike import (
    MANIFEST_PATH,
    PackageSpikeFailure,
    compare_wheel_directories,
    create_container_input_bundle,
    load_manifest,
    run_spike,
    validate_repository,
    verify_wheel,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _record_digest(value: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b"=")
    return f"sha256={digest.decode('ascii')}"


def _write_test_wheel(path: Path, *, module_body: bytes = b"VALUE = 1\n") -> None:
    entries = {
        "example/__init__.py": module_body,
        "example-1.0.dist-info/METADATA": b"Name: example\nVersion: 1.0\n",
        "example-1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nTag: py3-none-any\n",
    }
    rows = [
        (name, _record_digest(value), str(len(value))) for name, value in sorted(entries.items())
    ]
    record_name = "example-1.0.dist-info/RECORD"
    rows.append((record_name, "", ""))
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    entries[record_name] = output.getvalue().encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in sorted(entries.items()):
            archive.writestr(name, value)


def test_manifest_covers_and_validates_every_current_workspace_member() -> None:
    """Keep future members from silently escaping the package proof."""
    manifest = load_manifest(REPOSITORY_ROOT / MANIFEST_PATH)
    validate_repository(REPOSITORY_ROOT, manifest)
    assert {member.path for member in manifest.members} == {
        "apps/acquisition-worker",
        "apps/control-plane",
        "apps/legal-processing-worker",
        "apps/promotion-worker",
        "apps/review-api",
        "packages/application-runtime",
        "packages/contracts",
        "packages/corpus",
        "packages/domain",
        "packages/durable-task-adapter",
        "packages/evidence-vault",
        "packages/legal-desks",
        "packages/management-register",
        "packages/management-register-adapter",
        "packages/observability",
        "packages/processing",
        "packages/promotion",
        "packages/reporting",
        "packages/source-connectors",
    }


def test_wheel_verifier_checks_complete_record(tmp_path: Path) -> None:
    """Accept a complete wheel, then reject a body changed after RECORD creation."""
    wheel = tmp_path / "example-1.0-py3-none-any.whl"
    _write_test_wheel(wheel)
    verify_wheel(wheel)

    corrupt_wheel = tmp_path / "example-corrupt-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["example/__init__.py"] = b"VALUE = 2\n"
    with zipfile.ZipFile(corrupt_wheel, "w") as archive:
        for name, value in sorted(entries.items()):
            archive.writestr(name, value)
    with pytest.raises(PackageSpikeFailure, match="PACKAGE_WHEEL_RECORD_HASH_MISMATCH"):
        verify_wheel(corrupt_wheel)


def test_two_build_directories_must_be_byte_identical(tmp_path: Path) -> None:
    """Reject path-distinct builds whose wheel bytes differ."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    wheel_name = "example-1.0-py3-none-any.whl"
    _write_test_wheel(first / wheel_name)
    _write_test_wheel(second / wheel_name, module_body=b"VALUE = 2\n")
    with pytest.raises(PackageSpikeFailure, match="PACKAGE_WHEEL_BYTES_MISMATCH"):
        compare_wheel_directories(first, second)


def test_container_inputs_are_deterministic_and_lock_bound(tmp_path: Path) -> None:
    """Make ordering irrelevant while binding the bundle to the exact lock bytes."""
    manifest = load_manifest(REPOSITORY_ROOT / MANIFEST_PATH)
    first_root = tmp_path / "a"
    second_root = tmp_path / "b"
    first_wheels = first_root / "wheels"
    second_wheels = second_root / "wheels"
    for root in (first_root, second_root):
        for relative_path in manifest.container_metadata_inputs:
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((REPOSITORY_ROOT / relative_path).read_bytes())
    _write_test_wheel(first_wheels / "example-1.0-py3-none-any.whl")
    _write_test_wheel(second_wheels / "example-1.0-py3-none-any.whl")

    first = create_container_input_bundle(first_root, first_wheels, manifest)
    second = create_container_input_bundle(second_root, second_wheels, manifest)
    assert first == second

    with (second_root / "uv.lock").open("ab") as lock_file:
        lock_file.write(b"\n# changed\n")
    changed = create_container_input_bundle(second_root, second_wheels, manifest)
    assert changed != first


@pytest.mark.package_spike
@pytest.mark.skipif(
    os.environ.get("ASKLEGAL_PACKAGE_SPIKE") != "1",
    reason="set ASKLEGAL_PACKAGE_SPIKE=1 with ASKLEGAL_UV to run the offline proof",
)
def test_complete_network_disabled_package_spike(tmp_path: Path) -> None:
    """Exercise both builds and every clean member-specific installation."""
    uv_value = os.environ.get("ASKLEGAL_UV")
    if uv_value is None:
        pytest.fail("ASKLEGAL_UV must name the exact checked-in uv version")
    report = run_spike(REPOSITORY_ROOT, Path(uv_value), tmp_path)
    assert len(report.wheel_artifacts) == 19
    assert len(report.import_proofs) == 19
    assert all(proof.importable_workspace_modules for proof in report.import_proofs)
