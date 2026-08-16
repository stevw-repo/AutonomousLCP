"""Fail-closed local proof for locked, isolated, reproducible Python packages."""

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

MANIFEST_PATH = Path("tools/package_spike_manifest.json")
_BUILD_BACKEND_REQUIREMENT = "uv-build==0.12.5"
_FIXED_FILE_MODE = 0o644


class PackageSpikeFailure(RuntimeError):
    """One exact package-spike invariant failed."""


@dataclass(frozen=True, slots=True)
class PackageSpec:
    """One workspace member and its permitted workspace dependency closure."""

    distribution: str
    module: str
    path: str
    allowed_workspace_distributions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PackageSpikeManifest:
    """Closed checked-in policy for the local package proof."""

    schema_version: int
    python_version: str
    uv_version: str
    source_date_epoch: int
    container_metadata_inputs: tuple[str, ...]
    forbidden_dev_distributions: tuple[str, ...]
    members: tuple[PackageSpec, ...]


@dataclass(frozen=True, slots=True)
class FileArtifact:
    """Exact name, size, and SHA-256 for one generated artifact."""

    name: str
    size: int
    sha256: str

    def to_json(self) -> dict[str, str | int]:
        """Return the deterministic report representation."""
        return {"name": self.name, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True, slots=True)
class ImportProof:
    """Installed workspace distributions and import roots for one member."""

    distribution: str
    installed_workspace_distributions: tuple[str, ...]
    importable_workspace_modules: tuple[str, ...]

    def to_json(self) -> dict[str, str | list[str]]:
        """Return the deterministic report representation."""
        return {
            "distribution": self.distribution,
            "importable_workspace_modules": list(self.importable_workspace_modules),
            "installed_workspace_distributions": list(self.installed_workspace_distributions),
        }


@dataclass(frozen=True, slots=True)
class PackageSpikeReport:
    """Complete deterministic result of one package-spike execution."""

    lock_sha256: str
    wheel_artifacts: tuple[FileArtifact, ...]
    container_input_artifact: FileArtifact
    import_proofs: tuple[ImportProof, ...]

    def to_json(self) -> dict[str, str | dict[str, str | int] | list[object]]:
        """Return the canonical JSON-ready report."""
        return {
            "container_input_artifact": self.container_input_artifact.to_json(),
            "import_proofs": [proof.to_json() for proof in self.import_proofs],
            "lock_sha256": self.lock_sha256,
            "wheel_artifacts": [artifact.to_json() for artifact in self.wheel_artifacts],
        }


def load_manifest(path: Path) -> PackageSpikeManifest:
    """Load and strictly validate the checked-in package-spike policy."""
    raw_value = cast("object", json.loads(path.read_text(encoding="utf-8")))
    raw = _mapping(raw_value, "manifest")
    expected_keys = {
        "container_metadata_inputs",
        "forbidden_dev_distributions",
        "members",
        "python_version",
        "schema_version",
        "source_date_epoch",
        "uv_version",
    }
    _require_exact_keys(raw, expected_keys, "manifest")
    members_value = _sequence(raw["members"], "manifest.members")
    members: list[PackageSpec] = []
    for index, member_value in enumerate(members_value):
        location = f"manifest.members[{index}]"
        member = _mapping(member_value, location)
        _require_exact_keys(
            member,
            {"allowed_workspace_distributions", "distribution", "module", "path"},
            location,
        )
        members.append(
            PackageSpec(
                distribution=_string(member["distribution"], f"{location}.distribution"),
                module=_string(member["module"], f"{location}.module"),
                path=_relative_path(member["path"], f"{location}.path"),
                allowed_workspace_distributions=_string_tuple(
                    member["allowed_workspace_distributions"],
                    f"{location}.allowed_workspace_distributions",
                ),
            )
        )
    manifest = PackageSpikeManifest(
        schema_version=_integer(raw["schema_version"], "manifest.schema_version"),
        python_version=_string(raw["python_version"], "manifest.python_version"),
        uv_version=_string(raw["uv_version"], "manifest.uv_version"),
        source_date_epoch=_integer(raw["source_date_epoch"], "manifest.source_date_epoch"),
        container_metadata_inputs=_relative_path_tuple(
            raw["container_metadata_inputs"], "manifest.container_metadata_inputs"
        ),
        forbidden_dev_distributions=_string_tuple(
            raw["forbidden_dev_distributions"],
            "manifest.forbidden_dev_distributions",
        ),
        members=tuple(members),
    )
    _validate_manifest_values(manifest)
    return manifest


def validate_repository(root: Path, manifest: PackageSpikeManifest) -> None:
    """Require the policy to cover every and only current workspace member."""
    expected_paths = {member.path for member in manifest.members}
    discovered_paths = {
        path.parent.relative_to(root).as_posix()
        for parent in (root / "packages", root / "apps")
        if parent.is_dir()
        for path in parent.glob("*/pyproject.toml")
    }
    if expected_paths != discovered_paths:
        raise PackageSpikeFailure("PACKAGE_MEMBER_COVERAGE_MISMATCH")

    python_pin = (root / ".python-version").read_text(encoding="utf-8").strip()
    if python_pin != manifest.python_version:
        raise PackageSpikeFailure("PACKAGE_PYTHON_PIN_MISMATCH")

    member_names = {member.distribution for member in manifest.members}
    module_names = {member.module for member in manifest.members}
    if len(member_names) != len(manifest.members) or len(module_names) != len(manifest.members):
        raise PackageSpikeFailure("PACKAGE_MEMBER_IDENTITY_DUPLICATE")

    for member in manifest.members:
        package_root = root / member.path
        metadata = _toml_mapping(package_root / "pyproject.toml")
        project = _mapping(metadata.get("project"), f"{member.path}.project")
        build_system = _mapping(metadata.get("build-system"), f"{member.path}.build-system")
        if _string(project.get("name"), f"{member.path}.project.name") != member.distribution:
            raise PackageSpikeFailure("PACKAGE_DISTRIBUTION_MISMATCH")
        if _string(project.get("requires-python"), f"{member.path}.requires-python") != (
            f"=={manifest.python_version}"
        ):
            raise PackageSpikeFailure("PACKAGE_PYTHON_REQUIREMENT_MISMATCH")
        build_requirements = _string_tuple(
            build_system.get("requires"), f"{member.path}.build-system.requires"
        )
        if build_requirements != (_BUILD_BACKEND_REQUIREMENT,):
            raise PackageSpikeFailure("PACKAGE_BUILD_BACKEND_NOT_EXACT")
        if member.distribution not in member.allowed_workspace_distributions:
            raise PackageSpikeFailure("PACKAGE_SELF_IMPORT_NOT_ALLOWED")
        if not set(member.allowed_workspace_distributions) <= member_names:
            raise PackageSpikeFailure("PACKAGE_UNKNOWN_WORKSPACE_DEPENDENCY")

    for relative_path in manifest.container_metadata_inputs:
        if not (root / relative_path).is_file():
            raise PackageSpikeFailure("PACKAGE_CONTAINER_INPUT_MISSING")


def verify_uv(uv_executable: Path, expected_version: str) -> None:
    """Require the exact uv CLI selected by the checked-in policy."""
    result = _run((str(uv_executable), "--version"), cwd=uv_executable.parent)
    fields = result.stdout.strip().split(maxsplit=2)
    if len(fields) != 3 or fields[:2] != ["uv", expected_version]:
        raise PackageSpikeFailure("PACKAGE_UV_VERSION_MISMATCH")


def compare_wheel_directories(first: Path, second: Path) -> tuple[FileArtifact, ...]:
    """Require exactly matching wheel names and bytes across two builds."""
    first_wheels = {path.name: path for path in first.glob("*.whl")}
    second_wheels = {path.name: path for path in second.glob("*.whl")}
    if not first_wheels or first_wheels.keys() != second_wheels.keys():
        raise PackageSpikeFailure("PACKAGE_WHEEL_SET_MISMATCH")
    artifacts: list[FileArtifact] = []
    for name in sorted(first_wheels):
        first_path = first_wheels[name]
        second_path = second_wheels[name]
        first_bytes = first_path.read_bytes()
        second_bytes = second_path.read_bytes()
        if first_bytes != second_bytes:
            raise PackageSpikeFailure("PACKAGE_WHEEL_BYTES_MISMATCH")
        verify_wheel(first_path)
        verify_wheel(second_path)
        artifacts.append(_artifact(name, first_bytes))
    return tuple(artifacts)


def verify_wheel(path: Path) -> None:
    """Reject unsafe paths and verify every wheel RECORD digest and size."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise PackageSpikeFailure("PACKAGE_WHEEL_DUPLICATE_PATH")
        for name in names:
            _validate_archive_path(name)
            if name.endswith((".pyc", ".pyo")) or "__pycache__" in PurePosixPath(name).parts:
                raise PackageSpikeFailure("PACKAGE_WHEEL_GENERATED_BYTECODE")
        record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(record_names) != 1:
            raise PackageSpikeFailure("PACKAGE_WHEEL_RECORD_COUNT")
        record_name = record_names[0]
        rows = csv.reader(io.StringIO(archive.read(record_name).decode("utf-8")))
        recorded_paths: set[str] = set()
        for row in rows:
            if len(row) != 3:
                raise PackageSpikeFailure("PACKAGE_WHEEL_RECORD_INVALID")
            member_name, digest, size_text = row
            _validate_archive_path(member_name)
            recorded_paths.add(member_name)
            if member_name == record_name:
                if digest or size_text:
                    raise PackageSpikeFailure("PACKAGE_WHEEL_RECORD_SELF_HASHED")
                continue
            try:
                member_bytes = archive.read(member_name)
            except KeyError as error:
                raise PackageSpikeFailure("PACKAGE_WHEEL_RECORD_PATH_MISSING") from error
            expected_digest = _record_digest(member_bytes)
            if digest != expected_digest or size_text != str(len(member_bytes)):
                raise PackageSpikeFailure("PACKAGE_WHEEL_RECORD_HASH_MISMATCH")
        expected_recorded_paths = {name for name in names if not name.endswith("/")}
        if recorded_paths != expected_recorded_paths:
            raise PackageSpikeFailure("PACKAGE_WHEEL_RECORD_COVERAGE_MISMATCH")


def create_container_input_bundle(
    root: Path,
    wheel_directory: Path,
    manifest: PackageSpikeManifest,
) -> bytes:
    """Create deterministic wheel-plus-lock bytes suitable as container inputs."""
    entries: dict[str, bytes] = {}
    for wheel in sorted(wheel_directory.glob("*.whl")):
        entries[f"wheels/{wheel.name}"] = wheel.read_bytes()
    if not entries:
        raise PackageSpikeFailure("PACKAGE_CONTAINER_WHEELS_MISSING")
    for relative_path in manifest.container_metadata_inputs:
        entries[f"metadata/{relative_path}"] = (root / relative_path).read_bytes()

    entry_artifacts = [_artifact(name, value) for name, value in sorted(entries.items())]
    bundle_manifest = {
        "entries": [artifact.to_json() for artifact in entry_artifacts],
        "python_version": manifest.python_version,
        "schema_version": 1,
        "source_date_epoch": manifest.source_date_epoch,
        "uv_version": manifest.uv_version,
    }
    entries["manifest.json"] = _canonical_json_bytes(bundle_manifest)

    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, value in sorted(entries.items()):
            info = tarfile.TarInfo(name)
            info.size = len(value)
            info.mode = _FIXED_FILE_MODE
            info.mtime = manifest.source_date_epoch
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(value))
    return output.getvalue()


def run_spike(root: Path, uv_executable: Path, work_root: Path) -> PackageSpikeReport:
    """Execute the complete network-disabled package proof."""
    manifest = load_manifest(root / MANIFEST_PATH)
    validate_repository(root, manifest)
    verify_uv(uv_executable, manifest.uv_version)
    expected_python = tuple(int(part) for part in manifest.python_version.split("."))
    if sys.version_info[:3] != expected_python:
        raise PackageSpikeFailure("PACKAGE_RUNNING_PYTHON_MISMATCH")

    original_lock_hash = _sha256((root / "uv.lock").read_bytes())
    first_source = work_root / "source-a"
    second_source = work_root / "source-b"
    _copy_workspace(root, first_source, manifest)
    _copy_workspace(root, second_source, manifest)
    first_wheels = work_root / "wheels-a"
    second_wheels = work_root / "wheels-b"
    _build_wheels(uv_executable, first_source, first_wheels, manifest)
    _build_wheels(uv_executable, second_source, second_wheels, manifest)
    wheel_artifacts = compare_wheel_directories(first_wheels, second_wheels)

    first_bundle = create_container_input_bundle(first_source, first_wheels, manifest)
    second_bundle = create_container_input_bundle(second_source, second_wheels, manifest)
    if first_bundle != second_bundle:
        raise PackageSpikeFailure("PACKAGE_CONTAINER_INPUT_BYTES_MISMATCH")
    container_artifact = _artifact("asklegal-package-inputs.tar", first_bundle)

    import_proofs: list[ImportProof] = []
    for member in manifest.members:
        install_source = work_root / "installs" / _safe_directory_name(member.distribution)
        _copy_workspace(root, install_source, manifest)
        import_proofs.append(
            _prove_offline_install(
                uv_executable,
                install_source,
                member,
                manifest,
                original_lock_hash,
            )
        )

    if _sha256((root / "uv.lock").read_bytes()) != original_lock_hash:
        raise PackageSpikeFailure("PACKAGE_SOURCE_LOCK_CHANGED")
    return PackageSpikeReport(
        lock_sha256=original_lock_hash,
        wheel_artifacts=wheel_artifacts,
        container_input_artifact=container_artifact,
        import_proofs=tuple(import_proofs),
    )


def _prove_offline_install(
    uv_executable: Path,
    source_root: Path,
    member: PackageSpec,
    manifest: PackageSpikeManifest,
    expected_lock_hash: str,
) -> ImportProof:
    environment = _proof_environment(manifest)
    _run(
        (
            str(uv_executable),
            "sync",
            "--project",
            str(source_root),
            "--package",
            member.distribution,
            "--locked",
            "--offline",
            "--no-dev",
            "--no-editable",
            "--no-python-downloads",
            "--python",
            sys.executable,
        ),
        cwd=source_root,
        environment=environment,
    )
    if _sha256((source_root / "uv.lock").read_bytes()) != expected_lock_hash:
        raise PackageSpikeFailure("PACKAGE_INSTALL_LOCK_CHANGED")

    python_executable = source_root / ".venv" / "bin" / "python"
    if not python_executable.is_file():
        raise PackageSpikeFailure("PACKAGE_CLEAN_ENVIRONMENT_MISSING")
    module_by_distribution = {spec.distribution: spec.module for spec in manifest.members}
    allowed_modules = sorted(
        module_by_distribution[name] for name in member.allowed_workspace_distributions
    )
    probe_policy = {
        "all_modules": sorted(module_by_distribution.values()),
        "target_module": member.module,
    }
    result = _run(
        (
            str(python_executable),
            "-I",
            "-c",
            _IMPORT_PROBE,
            _canonical_json_bytes(probe_policy).decode("utf-8"),
        ),
        cwd=source_root.parent,
        environment=environment,
    )
    probe = _mapping(cast("object", json.loads(result.stdout)), "package import probe")
    imported_modules = _string_tuple(
        probe.get("importable_modules"), "package import probe.importable_modules"
    )
    installed_distributions = _string_tuple(
        probe.get("installed_distributions"),
        "package import probe.installed_distributions",
    )
    module_file = Path(_string(probe.get("target_file"), "package import probe.target_file"))
    expected_site_root = (source_root / ".venv").resolve()
    if not module_file.resolve().is_relative_to(expected_site_root):
        raise PackageSpikeFailure("PACKAGE_IMPORT_ESCAPED_CLEAN_ENVIRONMENT")
    if imported_modules != tuple(allowed_modules):
        raise PackageSpikeFailure("PACKAGE_IMPORT_ISOLATION_MISMATCH")

    workspace_names = {spec.distribution for spec in manifest.members}
    installed_workspace = tuple(
        sorted(name for name in installed_distributions if name in workspace_names)
    )
    if installed_workspace != tuple(sorted(member.allowed_workspace_distributions)):
        raise PackageSpikeFailure("PACKAGE_DISTRIBUTION_ISOLATION_MISMATCH")
    if set(manifest.forbidden_dev_distributions) & set(installed_distributions):
        raise PackageSpikeFailure("PACKAGE_DEV_DEPENDENCY_LEAK")
    return ImportProof(member.distribution, installed_workspace, imported_modules)


def _build_wheels(
    uv_executable: Path,
    source_root: Path,
    output_directory: Path,
    manifest: PackageSpikeManifest,
) -> None:
    _run(
        (
            str(uv_executable),
            "build",
            "--project",
            str(source_root),
            "--all-packages",
            "--wheel",
            "--offline",
            "--no-python-downloads",
            "--out-dir",
            str(output_directory),
            "--no-create-gitignore",
        ),
        cwd=source_root,
        environment=_proof_environment(manifest),
    )


def _copy_workspace(
    source_root: Path,
    destination_root: Path,
    manifest: PackageSpikeManifest,
) -> None:
    if destination_root.exists():
        raise PackageSpikeFailure("PACKAGE_TEMPORARY_TARGET_EXISTS")
    destination_root.mkdir(parents=True)
    for relative_path in manifest.container_metadata_inputs:
        _copy_exact_file(
            source_root / relative_path,
            destination_root / relative_path,
            manifest.source_date_epoch,
        )
    for member in manifest.members:
        member_root = source_root / member.path
        paths = [member_root / "pyproject.toml"]
        readme = member_root / "README.md"
        if readme.is_file():
            paths.append(readme)
        paths.extend(path for path in (member_root / "src").rglob("*") if path.is_file())
        for source_path in paths:
            if source_path.suffix in {".pyc", ".pyo"} or "__pycache__" in source_path.parts:
                continue
            relative_path = source_path.relative_to(source_root)
            _copy_exact_file(
                source_path,
                destination_root / relative_path,
                manifest.source_date_epoch,
            )


def _copy_exact_file(source: Path, destination: Path, timestamp: int) -> None:
    if not source.is_file():
        raise PackageSpikeFailure("PACKAGE_SOURCE_INPUT_MISSING")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    destination.chmod(_FIXED_FILE_MODE)
    os.utime(destination, (timestamp, timestamp))


def _proof_environment(manifest: PackageSpikeManifest) -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "SOURCE_DATE_EPOCH": str(manifest.source_date_epoch),
            "TZ": "UTC",
            "UV_LOCKED": "1",
            "UV_OFFLINE": "1",
            "UV_PYTHON_DOWNLOADS": "never",
        }
    )
    return environment


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=None if environment is None else dict(environment),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        stable_detail = detail[-1] if detail else "no subprocess detail"
        raise PackageSpikeFailure(f"PACKAGE_SUBPROCESS_FAILED: {stable_detail}")
    return result


def _validate_manifest_values(manifest: PackageSpikeManifest) -> None:
    if manifest.schema_version != 1:
        raise PackageSpikeFailure("PACKAGE_MANIFEST_SCHEMA_UNSUPPORTED")
    if manifest.source_date_epoch < 315532800:
        raise PackageSpikeFailure("PACKAGE_SOURCE_DATE_EPOCH_INVALID")
    if not manifest.members:
        raise PackageSpikeFailure("PACKAGE_MANIFEST_EMPTY")
    if tuple(sorted(manifest.members, key=lambda member: member.distribution)) != manifest.members:
        raise PackageSpikeFailure("PACKAGE_MANIFEST_MEMBERS_NOT_SORTED")
    if tuple(sorted(manifest.container_metadata_inputs)) != manifest.container_metadata_inputs:
        raise PackageSpikeFailure("PACKAGE_CONTAINER_INPUTS_NOT_SORTED")
    if tuple(sorted(manifest.forbidden_dev_distributions)) != (
        manifest.forbidden_dev_distributions
    ):
        raise PackageSpikeFailure("PACKAGE_FORBIDDEN_DISTRIBUTIONS_NOT_SORTED")
    for member in manifest.members:
        if tuple(sorted(member.allowed_workspace_distributions)) != (
            member.allowed_workspace_distributions
        ):
            raise PackageSpikeFailure("PACKAGE_ALLOWED_DISTRIBUTIONS_NOT_SORTED")


def _toml_mapping(path: Path) -> dict[str, object]:
    value = cast("object", tomllib.loads(path.read_text(encoding="utf-8")))
    return _mapping(value, path.as_posix())


def _mapping(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PackageSpikeFailure(f"PACKAGE_EXPECTED_MAPPING: {location}")
    raw = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in raw):
        raise PackageSpikeFailure(f"PACKAGE_EXPECTED_STRING_KEY: {location}")
    return {str(key): item for key, item in raw.items()}


def _sequence(value: object, location: str) -> list[object]:
    if not isinstance(value, list):
        raise PackageSpikeFailure(f"PACKAGE_EXPECTED_LIST: {location}")
    return cast("list[object]", value)


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise PackageSpikeFailure(f"PACKAGE_EXPECTED_STRING: {location}")
    return value


def _integer(value: object, location: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PackageSpikeFailure(f"PACKAGE_EXPECTED_INTEGER: {location}")
    return value


def _string_tuple(value: object, location: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{location}[{index}]")
        for index, item in enumerate(_sequence(value, location))
    )


def _relative_path(value: object, location: str) -> str:
    text = _string(value, location)
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts or ".." in path.parts or text != path.as_posix():
        raise PackageSpikeFailure(f"PACKAGE_EXPECTED_RELATIVE_PATH: {location}")
    return text


def _relative_path_tuple(value: object, location: str) -> tuple[str, ...]:
    return tuple(
        _relative_path(item, f"{location}[{index}]")
        for index, item in enumerate(_sequence(value, location))
    )


def _require_exact_keys(mapping: Mapping[str, object], expected: set[str], location: str) -> None:
    if set(mapping) != expected:
        raise PackageSpikeFailure(f"PACKAGE_MANIFEST_KEYS_INVALID: {location}")


def _validate_archive_path(name: str) -> None:
    normalized_name = name.removesuffix("/")
    path = PurePosixPath(normalized_name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or normalized_name != path.as_posix()
        or name not in {normalized_name, f"{normalized_name}/"}
    ):
        raise PackageSpikeFailure("PACKAGE_ARCHIVE_PATH_UNSAFE")


def _record_digest(value: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b"=")
    return f"sha256={digest.decode('ascii')}"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _artifact(name: str, value: bytes) -> FileArtifact:
    return FileArtifact(name=name, size=len(value), sha256=_sha256(value))


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _safe_directory_name(value: str) -> str:
    return value.replace("-", "_")


_IMPORT_PROBE = """
import importlib
import importlib.metadata
import json
import sys

policy = json.loads(sys.argv[1])
target = importlib.import_module(policy["target_module"])
target_file = getattr(target, "__file__", None)
if not isinstance(target_file, str):
    raise SystemExit("PACKAGE_TARGET_FILE_MISSING")
importable = []
for module_name in policy["all_modules"]:
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
    else:
        importable.append(module_name)
installed = sorted(
    {
        distribution.metadata["Name"].lower()
        for distribution in importlib.metadata.distributions()
        if distribution.metadata["Name"]
    }
)
print(json.dumps({
    "importable_modules": importable,
    "installed_distributions": installed,
    "target_file": target_file,
}, sort_keys=True))
""".strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", required=True, type=Path, help="exact uv 0.12.5 executable")
    return parser


def main() -> int:
    """Run the proof in disposable directories and print its canonical report."""
    arguments = _parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    uv_executable = arguments.uv.resolve()
    if not uv_executable.is_file():
        raise PackageSpikeFailure("PACKAGE_UV_EXECUTABLE_MISSING")
    with tempfile.TemporaryDirectory(prefix="asklegal-package-spike-") as temporary:
        report = run_spike(root, uv_executable, Path(temporary))
    print(_canonical_json_bytes(report.to_json()).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
