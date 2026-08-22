"""Tests for exact image-admission input preparation."""

import io
import tarfile
from pathlib import Path

import pytest

from tools.image_admission_bootstrap import extract_binary, url_filename
from tools.image_admission_spike import ImageAdmissionFailure


def _archive(path: Path, members: dict[str, bytes]) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def test_exact_regular_binary_is_extracted_without_other_archive_members(tmp_path: Path) -> None:
    """Extract the exact named binary and ignore unrelated regular files."""
    archive = tmp_path / "tool.tar.gz"
    _archive(archive, {"LICENSE": b"licence", "nested/grype": b"exact-binary"})

    assert extract_binary(archive, "grype") == b"exact-binary"


def test_duplicate_and_unsafe_binary_members_fail_closed(tmp_path: Path) -> None:
    """Reject ambiguous names and traversal even when the target name matches."""
    duplicate = tmp_path / "duplicate.tar.gz"
    _archive(duplicate, {"grype": b"one", "nested/grype": b"two"})
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_BOOTSTRAP_BINARY_MEMBER_INVALID"):
        extract_binary(duplicate, "grype")

    unsafe = tmp_path / "unsafe.tar.gz"
    _archive(unsafe, {"../grype": b"unsafe"})
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_BOOTSTRAP_ARCHIVE_PATH_UNSAFE"):
        extract_binary(unsafe, "grype")


def test_https_asset_filename_is_derived_only_from_the_url_path() -> None:
    """Ignore query data when deriving the local source-cache filename."""
    assert url_filename("https://example.test/releases/tool.tar.gz?digest=one") == "tool.tar.gz"
