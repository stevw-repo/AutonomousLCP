"""Prepare exact disposable tool and database inputs for the local image proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import cast

from tools.image_admission_spike import (
    ImageAdmissionFailure,
    JsonValue,
    load_policy,
)

_TOOL_NAMES = ("buildx", "grype", "notation", "oras", "syft")
_CHUNK_SIZE = 1024 * 1024


def prepare_inputs(
    root: Path, destination: Path, source_cache: Path | None = None
) -> dict[str, str]:
    """Create one new exact tool tree from verified HTTPS assets or a verified cache."""
    if destination.exists():
        raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_DESTINATION_EXISTS")
    if source_cache is not None and not source_cache.is_dir():
        raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_CACHE_INVALID")

    policy = load_policy(root)
    tools = _mapping(policy["tools"], "tools")
    database = _mapping(policy["vulnerability_database"], "vulnerability database")
    destination.mkdir(mode=0o700, parents=True)
    downloads = destination / "downloads"
    binaries = destination / "bin"
    grype_db = destination / "grype-db"
    downloads.mkdir(mode=0o700)
    binaries.mkdir(mode=0o700)
    grype_db.mkdir(mode=0o700)

    result: dict[str, str] = {}
    for name in _TOOL_NAMES:
        selected = _mapping(tools[name], f"tools.{name}")
        url = _string(selected["asset_url"], f"tools.{name}.asset_url")
        archive_hash = _string(
            selected["release_asset_sha256"], f"tools.{name}.release_asset_sha256"
        )
        asset_name = url_filename(url)
        asset = downloads / asset_name
        _materialize_asset(url, archive_hash, asset, source_cache)
        binary_bytes = asset.read_bytes() if name == "buildx" else extract_binary(asset, name)
        expected_binary_hash = _string(selected["binary_sha256"], f"tools.{name}.binary_sha256")
        if _sha256(binary_bytes) != expected_binary_hash:
            raise ImageAdmissionFailure(f"IMAGE_BOOTSTRAP_BINARY_HASH_MISMATCH: {name}")
        binary = binaries / name
        binary.write_bytes(binary_bytes)
        binary.chmod(0o755)
        result[name] = str(binary.resolve())

    database_url = _string(database["source_archive_url"], "database source URL")
    database_archive_hash = _string(
        database["source_archive_sha256"], "database source archive hash"
    )
    database_archive = downloads / "grype-database.tar.zst"
    _materialize_asset(
        database_url,
        database_archive_hash,
        database_archive,
        source_cache,
        cache_name="grype-database.tar.zst",
    )
    _import_database(binaries / "grype", grype_db, database_archive)
    database_path = grype_db / "6" / "vulnerability.db"
    if _file_sha256(database_path) != _string(database["database_sha256"], "database hash"):
        raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_DATABASE_HASH_MISMATCH")
    status = _database_status(binaries / "grype", grype_db)
    if (
        status.get("valid") is not True
        or status.get("built") != database["built"]
        or status.get("schemaVersion") != database["schema_version"]
    ):
        raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_DATABASE_STATUS_MISMATCH")
    result["grype_db"] = str(grype_db.resolve())
    return dict(sorted(result.items()))


def _materialize_asset(
    url: str,
    expected_hash: str,
    destination: Path,
    source_cache: Path | None,
    *,
    cache_name: str | None = None,
) -> None:
    source = None if source_cache is None else source_cache / (cache_name or destination.name)
    if source is not None and source.is_file():
        if _file_sha256(source) != expected_hash:
            raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_CACHE_HASH_MISMATCH")
        shutil.copyfile(source, destination)
    else:
        _download(url, destination)
    if _file_sha256(destination) != expected_hash:
        raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_ASSET_HASH_MISMATCH")


def _download(url: str, destination: Path) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_URL_INVALID")
    request = urllib.request.Request(  # noqa: S310 -- URL scheme is validated above
        url, headers={"User-Agent": "asklegal-image-proof/1"}
    )
    partial = destination.with_suffix(f"{destination.suffix}.part")
    try:
        with (
            urllib.request.urlopen(  # noqa: S310 -- redirect is revalidated below
                request, timeout=60
            ) as response,
            partial.open("xb") as output,
        ):
            final_url = urllib.parse.urlparse(cast("str", response.geturl()))
            if final_url.scheme != "https" or not final_url.netloc:
                raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_REDIRECT_INVALID")
            while chunk := response.read(_CHUNK_SIZE):
                output.write(chunk)
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def extract_binary(archive_path: Path, expected_name: str) -> bytes:
    """Read one exact regular binary member from a safe gzip tar archive."""
    with tarfile.open(archive_path, mode="r:gz") as archive:
        candidates: list[tarfile.TarInfo] = []
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_ARCHIVE_PATH_UNSAFE")
            if path.name == expected_name:
                candidates.append(member)
        if len(candidates) != 1 or not candidates[0].isfile():
            raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_BINARY_MEMBER_INVALID")
        extracted = archive.extractfile(candidates[0])
        if extracted is None:
            raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_BINARY_MEMBER_MISSING")
        return extracted.read()


def _import_database(grype: Path, cache: Path, archive: Path) -> None:
    environment = _grype_environment(cache)
    result = subprocess.run(
        (str(grype), "db", "import", str(archive)),
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ImageAdmissionFailure(
            f"IMAGE_BOOTSTRAP_DATABASE_IMPORT_FAILED: {detail[-1] if detail else 'no detail'}"
        )


def _database_status(grype: Path, cache: Path) -> dict[str, JsonValue]:
    result = subprocess.run(
        (str(grype), "db", "status", "-o", "json"),
        capture_output=True,
        check=False,
        env=_grype_environment(cache),
        text=True,
    )
    if result.returncode != 0:
        raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_DATABASE_STATUS_FAILED")
    value = cast("object", json.loads(result.stdout))
    return _mapping(value, "database status")


def _grype_environment(cache: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "GRYPE_CHECK_FOR_APP_UPDATE": "false",
            "GRYPE_DB_AUTO_UPDATE": "false",
            "GRYPE_DB_CACHE_DIR": str(cache),
        }
    )
    return environment


def url_filename(url: str) -> str:
    """Return only the final decoded path component of an asset URL."""
    name = PurePosixPath(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
    if not name or name in {".", ".."}:
        raise ImageAdmissionFailure("IMAGE_BOOTSTRAP_URL_FILENAME_INVALID")
    return name


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: object, location: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ImageAdmissionFailure(f"IMAGE_BOOTSTRAP_MAPPING_INVALID: {location}")
    raw = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in raw):
        raise ImageAdmissionFailure(f"IMAGE_BOOTSTRAP_MAPPING_INVALID: {location}")
    return cast("dict[str, JsonValue]", value)


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ImageAdmissionFailure(f"IMAGE_BOOTSTRAP_STRING_INVALID: {location}")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--source-cache", type=Path)
    return parser


def main() -> int:
    """Prepare inputs and emit stable absolute paths for the opt-in proof."""
    arguments = _parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    result = prepare_inputs(
        root,
        arguments.destination.resolve(),
        None if arguments.source_cache is None else arguments.source_cache.resolve(),
    )
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
