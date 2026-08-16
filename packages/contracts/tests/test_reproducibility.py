"""Independent-oracle and fresh-process reproducibility checks."""

import os
import subprocess
import sys
from hashlib import sha256

from asklegal_contracts import fingerprint, parse_json_bytes

from .conftest import CONTRACTS_ROOT, REPOSITORY_ROOT

EXPECTED_PACKAGE_FINGERPRINT = (
    "sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e"
)


def _snapshot(seed: str) -> str:
    code = (
        "from pathlib import Path; "
        "from asklegal_contracts import fingerprint, parse_json_bytes; "
        "p=Path('contracts/package-manifest.json'); b=p.read_bytes(); "
        "print(fingerprint(parse_json_bytes(b,max_bytes=len(b))))"
    )
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = seed
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_package_manifest_matches_the_independent_node_oracle() -> None:
    """Python JCS/SHA reproduces the exact existing Node package root."""
    path = CONTRACTS_ROOT / "package-manifest.json"
    raw = path.read_bytes()
    value = parse_json_bytes(raw, max_bytes=len(raw))
    assert fingerprint(value) == EXPECTED_PACKAGE_FINGERPRINT


def test_python_reproduces_every_manifested_artifact_hash_and_size() -> None:
    """Every exact contract artifact agrees with the normative manifest."""
    manifest_path = CONTRACTS_ROOT / "package-manifest.json"
    raw_manifest = manifest_path.read_bytes()
    manifest = parse_json_bytes(raw_manifest, max_bytes=len(raw_manifest))
    assert isinstance(manifest, dict)
    entries = manifest.get("files")
    assert isinstance(entries, list)

    declared_paths: set[str] = set()
    for entry_value in entries:
        assert isinstance(entry_value, dict)
        relative_path = entry_value.get("path")
        byte_size = entry_value.get("byte_size")
        expected_fingerprint = entry_value.get("fingerprint")
        assert isinstance(relative_path, str)
        assert isinstance(byte_size, int)
        assert isinstance(expected_fingerprint, str)
        artifact = CONTRACTS_ROOT / relative_path
        artifact_bytes = artifact.read_bytes()
        assert len(artifact_bytes) == byte_size
        assert f"sha256:{sha256(artifact_bytes).hexdigest()}" == expected_fingerprint
        declared_paths.add(relative_path)

    actual_paths = {
        path.relative_to(CONTRACTS_ROOT).as_posix()
        for path in CONTRACTS_ROOT.rglob("*")
        if path.is_file() and path != manifest_path
    }
    assert declared_paths == actual_paths


def test_two_fresh_processes_are_byte_identical() -> None:
    """Hash randomization cannot change canonical bytes or fingerprints."""
    assert _snapshot("11") == _snapshot("97") == EXPECTED_PACKAGE_FINGERPRINT


def test_existing_node_validator_still_passes() -> None:
    """The independent implementation-neutral oracle remains green."""
    node_executable = os.environ.get("ASKLEGAL_NODE_EXECUTABLE", "node")
    completed = subprocess.run(
        [node_executable, "tools/validate-contracts.mjs"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert f"PACKAGE_MANIFEST_FINGERPRINT {EXPECTED_PACKAGE_FINGERPRINT}" in completed.stdout
