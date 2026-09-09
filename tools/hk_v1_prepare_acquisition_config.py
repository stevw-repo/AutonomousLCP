"""Materialize exact retained Task 10 Acquisition inputs without network access.

The first publication performs the expensive retained HKeL admission pass.  An
exact replay validates the already published receipt and all five generated
files, so it does not rescan the multi-gigabyte archive set.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, Never

from asklegal_acquisition_worker.hk_legislation_acquisition import (
    parse_gld_gazette_window_snapshot,
)
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks.hk_legislation_authentic import (
    HkelAuthenticAdmissionReceipt,
    admit_retained_hkel_observation,
)
from asklegal_legal_desks.hk_legislation_retained import (
    HkelRetainedAttemptReference,
    HkelRetainedEvidenceReader,
    HkelRetainedObjectReference,
)
from asklegal_source_connectors.hkel_legislation import HkelArchiveReuseKey

CONFIG_FILENAMES = (
    "gld-window-snapshot.json",
    "hkel-admission-receipt.json",
    "hkel-archive-observation.json",
    "judiciary-advanced-search-form.html",
    "judiciary-advanced-search-form.sha256",
)

_MAX_REPORT_BYTES = 16_777_216
_MAX_FORM_BYTES = 8_388_608
_MAX_CONFIG_BYTES = 1_048_576
_OUTPUT_DIRECTORY_MODE = 0o700
_OUTPUT_FILE_MODE = 0o600
_FINGERPRINT_LENGTH = 71
_HTTP_OK = 200
_GLD_INVALID = "GLD_WINDOW_INPUT_INVALID"
_HKEL_INPUT_INVALID = "RETAINED_HKEL_INPUT_INVALID"
_HKEL_ADMISSION_INVALID = "RETAINED_HKEL_ADMISSION_INVALID"
_OUTPUT_INVALID = "ACQUISITION_CONFIG_OUTPUT_INVALID"
_OUTPUT_DRIFT = "ACQUISITION_CONFIG_OUTPUT_DRIFT"


class AcquisitionConfigPreparationError(ValueError):
    """One closed local preparation failure without leaking filesystem paths."""

    def __init__(self, code: str) -> None:
        """Expose the exact operator-facing failure code."""
        self.code = code
        super().__init__(code)


def _fail(code: str) -> Never:
    raise AcquisitionConfigPreparationError(code)


@dataclass(frozen=True, slots=True)
class RetainedAcquisitionProfile:
    """Exact retained reports and Judiciary form selected for this V1."""

    hkel_report_relative: Path
    hkel_report_fingerprint: str
    judiciary_report_relative: Path
    judiciary_report_fingerprint: str
    judiciary_form_endpoint_id: str
    judiciary_form_fingerprint: str


@dataclass(frozen=True, slots=True)
class AcquisitionConfigInputs:
    """Explicit paths and byte pin required for one local publication."""

    source_root: Path
    gld_window_path: Path
    expected_gld_window_fingerprint: str
    output_root: Path


_KNOWN_PROFILE = RetainedAcquisitionProfile(
    hkel_report_relative=Path(
        "hkel-attempt-b/attempts/hkel-live-baseline-basic-law20-20260828b/report.json"
    ),
    hkel_report_fingerprint=(
        "sha256:5f6b8625fd7c0ff4093d96b7a2f72e4ededc9b8af54b6c1add02b95e81549b50"
    ),
    judiciary_report_relative=Path(
        "judiciary-attempt-p/attempts/judiciary-live-baseline-20260831w/report.json"
    ),
    judiciary_report_fingerprint=(
        "sha256:83c98ee3b139d61b8c790772b7b4408fa5aac63dc891fc1bda3572085c84b92a"
    ),
    judiciary_form_endpoint_id="sep_000000000000000000000000000000000000000000000204",
    judiciary_form_fingerprint=(
        "sha256:695f73ff240fc93341d22feaa122c26d7ac9044263159e4e71afec421fb0b864"
    ),
)


@dataclass(frozen=True, slots=True)
class _RetainedInputs:
    hkel_report_path: Path
    hkel_report: dict[str, JsonValue]
    judiciary_report: dict[str, JsonValue]
    form: bytes
    gld_window: bytes
    gld_listing_fingerprint: str


AdmissionBuilder = Callable[[object, HkelRetainedEvidenceReader], HkelAuthenticAdmissionReceipt]


def _fingerprint(value: object, *, code: str) -> str:
    if (
        type(value) is not str
        or len(value) != _FINGERPRINT_LENGTH
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        _fail(code)
    return value


def _relative(path: object, *, code: str) -> Path:
    if (
        type(path) is not type(Path())
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail(code)
    return path


def _existing_root(path: object, *, code: str) -> Path:
    if type(path) is not type(Path()) or not path.is_absolute():
        _fail(code)
    try:
        absolute = path.absolute()
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
    except OSError as error:
        raise AcquisitionConfigPreparationError(code) from error
    if resolved != absolute or not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail(code)
    return resolved


def _confined_path(root: Path, relative: Path, *, code: str) -> Path:
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise AcquisitionConfigPreparationError(code) from error
    if resolved != candidate or not resolved.is_relative_to(root):
        _fail(code)
    return resolved


def _read_regular(path: Path, *, maximum: int, code: str) -> bytes:
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size < 1
            or metadata.st_size > maximum
            or path.resolve(strict=True) != path
        ):
            _fail(code)
        body = path.read_bytes()
    except AcquisitionConfigPreparationError:
        raise
    except OSError as error:
        raise AcquisitionConfigPreparationError(code) from error
    if len(body) != metadata.st_size:
        _fail(code)
    return body


def _parse_report(  # noqa: PLR0913 - explicit report expectations are security pins.
    body: bytes,
    *,
    expected_fingerprint: str,
    source_family: str,
    result: str,
    endpoint_counts: Mapping[str, int],
    code: str,
) -> dict[str, JsonValue]:
    if f"sha256:{sha256(body).hexdigest()}" != expected_fingerprint:
        _fail(code)
    try:
        parsed = parse_json_bytes(body, max_bytes=len(body))
    except ValueError as error:
        raise AcquisitionConfigPreparationError(code) from error
    if (
        type(parsed) is not dict
        or parsed.get("source_family") != source_family
        or parsed.get("result") != result
        or parsed.get("readback_verified") is not True
        or parsed.get("endpoint_counts") != dict(endpoint_counts)
        or type(parsed.get("attempt_id")) is not str
        or not parsed["attempt_id"]
        or type(parsed.get("observation_cutoff")) is not str
        or not parsed["observation_cutoff"]
    ):
        _fail(code)
    return parsed


def _gld_window(path: Path, expected_fingerprint: str) -> tuple[bytes, str]:
    _fingerprint(expected_fingerprint, code="GLD_WINDOW_INPUT_INVALID")
    try:
        body = _read_regular(path, maximum=_MAX_CONFIG_BYTES, code="GLD_WINDOW_INPUT_REQUIRED")
    except AcquisitionConfigPreparationError as error:
        if error.code == "GLD_WINDOW_INPUT_REQUIRED":
            raise
        raise AcquisitionConfigPreparationError(_GLD_INVALID) from error
    if f"sha256:{sha256(body).hexdigest()}" != expected_fingerprint:
        _fail("GLD_WINDOW_INPUT_INVALID")
    try:
        document = parse_json_bytes(body, max_bytes=len(body))
        if canonicalize(document) != body:
            _fail("GLD_WINDOW_INPUT_INVALID")
        window = parse_gld_gazette_window_snapshot(document)
    except AcquisitionConfigPreparationError:
        raise
    except (TypeError, ValueError) as error:
        raise AcquisitionConfigPreparationError(_GLD_INVALID) from error
    listing_fingerprint = _fingerprint(window.listing_fingerprint, code="GLD_WINDOW_INPUT_INVALID")
    return body, listing_fingerprint


def _retained_inputs(
    inputs: AcquisitionConfigInputs,
    profile: RetainedAcquisitionProfile,
) -> _RetainedInputs:
    if (
        type(inputs) is not AcquisitionConfigInputs
        or type(profile) is not RetainedAcquisitionProfile
    ):
        _fail("ACQUISITION_CONFIG_INPUT_INVALID")
    source_root = _existing_root(inputs.source_root, code="RETAINED_SOURCE_ROOT_INVALID")
    hkel_relative = _relative(profile.hkel_report_relative, code="RETAINED_HKEL_INPUT_INVALID")
    judiciary_relative = _relative(
        profile.judiciary_report_relative, code="RETAINED_JUDICIARY_INPUT_INVALID"
    )
    _fingerprint(profile.hkel_report_fingerprint, code="RETAINED_HKEL_INPUT_INVALID")
    _fingerprint(profile.judiciary_report_fingerprint, code="RETAINED_JUDICIARY_INPUT_INVALID")
    _fingerprint(profile.judiciary_form_fingerprint, code="RETAINED_JUDICIARY_INPUT_INVALID")
    if (
        type(profile.judiciary_form_endpoint_id) is not str
        or not profile.judiciary_form_endpoint_id
    ):
        _fail("RETAINED_JUDICIARY_INPUT_INVALID")

    gld_path = inputs.gld_window_path
    if type(gld_path) is not type(Path()) or not gld_path.is_absolute():
        _fail("GLD_WINDOW_INPUT_REQUIRED")
    gld, listing_fingerprint = _gld_window(gld_path, inputs.expected_gld_window_fingerprint)

    hkel_path = _confined_path(source_root, hkel_relative, code="RETAINED_HKEL_INPUT_INVALID")
    hkel_raw = _read_regular(
        hkel_path, maximum=_MAX_REPORT_BYTES, code="RETAINED_HKEL_INPUT_INVALID"
    )
    hkel = _parse_report(
        hkel_raw,
        expected_fingerprint=profile.hkel_report_fingerprint,
        source_family="HKEL",
        result="COMPLETE",
        endpoint_counts={"CAPTURED": 56},
        code="RETAINED_HKEL_INPUT_INVALID",
    )

    judiciary_path = _confined_path(
        source_root, judiciary_relative, code="RETAINED_JUDICIARY_INPUT_INVALID"
    )
    judiciary_raw = _read_regular(
        judiciary_path,
        maximum=_MAX_REPORT_BYTES,
        code="RETAINED_JUDICIARY_INPUT_INVALID",
    )
    judiciary = _parse_report(
        judiciary_raw,
        expected_fingerprint=profile.judiciary_report_fingerprint,
        source_family="JUDICIARY",
        result="SOURCE_OUTAGE",
        endpoint_counts={"CAPTURED": 5_590, "OUTAGE": 1},
        code="RETAINED_JUDICIARY_INPUT_INVALID",
    )
    form = _judiciary_form(source_root, judiciary_path, judiciary, profile)
    return _RetainedInputs(
        hkel_path,
        hkel,
        judiciary,
        form,
        gld,
        listing_fingerprint,
    )


def _judiciary_form(
    source_root: Path,
    report_path: Path,
    report: Mapping[str, JsonValue],
    profile: RetainedAcquisitionProfile,
) -> bytes:
    endpoints = report.get("endpoints")
    if type(endpoints) is not list:
        _fail("RETAINED_JUDICIARY_INPUT_INVALID")
    selected = [
        value
        for value in endpoints
        if type(value) is dict and value.get("endpoint_id") == profile.judiciary_form_endpoint_id
    ]
    if len(selected) != 1:
        _fail("RETAINED_JUDICIARY_INPUT_INVALID")
    endpoint = selected[0]
    object_key = endpoint.get("object_key")
    expected_length = endpoint.get("byte_length")
    if (
        endpoint.get("body_fingerprint") != profile.judiciary_form_fingerprint
        or endpoint.get("media_type") != "text/html"
        or endpoint.get("method") != "GET"
        or endpoint.get("status") != _HTTP_OK
        or endpoint.get("terminal_code") != "CAPTURED"
        or type(object_key) is not str
        or object_key != f"objects/{profile.judiciary_form_fingerprint.removeprefix('sha256:')}.bin"
        or type(expected_length) is not int
        or expected_length < 1
        or expected_length > _MAX_FORM_BYTES
    ):
        _fail("RETAINED_JUDICIARY_INPUT_INVALID")
    attempt_root = report_path.parents[2]
    if not attempt_root.is_relative_to(source_root):
        _fail("RETAINED_JUDICIARY_INPUT_INVALID")
    form_path = _confined_path(
        attempt_root, Path(object_key), code="RETAINED_JUDICIARY_INPUT_INVALID"
    )
    body = _read_regular(
        form_path, maximum=_MAX_FORM_BYTES, code="RETAINED_JUDICIARY_INPUT_INVALID"
    )
    if (
        len(body) != expected_length
        or f"sha256:{sha256(body).hexdigest()}" != profile.judiciary_form_fingerprint
    ):
        _fail("RETAINED_JUDICIARY_INPUT_INVALID")
    return body


class _FilesystemHkelReader:
    """Confined no-follow stream reader for the owning retained HKeL parser."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @contextmanager
    def open_exact(self, reference: HkelRetainedObjectReference) -> Generator[BinaryIO]:
        if type(reference) is not HkelRetainedObjectReference:
            _fail("RETAINED_HKEL_INPUT_INVALID")
        relative = _relative(Path(reference.logical_key), code="RETAINED_HKEL_INPUT_INVALID")
        path = _confined_path(self._root, relative, code="RETAINED_HKEL_INPUT_INVALID")
        descriptor = -1
        stream: BinaryIO | None = None
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != reference.byte_length:
                _fail("RETAINED_HKEL_INPUT_INVALID")
            stream = os.fdopen(descriptor, "rb")
            descriptor = -1
            yield stream
        except AcquisitionConfigPreparationError:
            raise
        except OSError as error:
            raise AcquisitionConfigPreparationError(_HKEL_INPUT_INVALID) from error
        finally:
            if stream is not None:
                stream.close()
            if descriptor >= 0:
                os.close(descriptor)


def _hkel_reference(
    retained: _RetainedInputs, profile: RetainedAcquisitionProfile
) -> tuple[HkelRetainedAttemptReference, _FilesystemHkelReader]:
    attempt_id = retained.hkel_report["attempt_id"]
    cutoff = retained.hkel_report["observation_cutoff"]
    if type(attempt_id) is not str or type(cutoff) is not str:
        _fail("RETAINED_HKEL_INPUT_INVALID")
    attempt_root = retained.hkel_report_path.parents[2]
    report_key = retained.hkel_report_path.relative_to(attempt_root).as_posix()
    return (
        HkelRetainedAttemptReference(
            attempt_id,
            cutoff,
            HkelRetainedObjectReference(
                report_key,
                profile.hkel_report_fingerprint,
                retained.hkel_report_path.stat().st_size,
            ),
        ),
        _FilesystemHkelReader(attempt_root),
    )


def _validated_receipt(
    receipt: object,
    retained: _RetainedInputs,
    profile: RetainedAcquisitionProfile,
) -> HkelAuthenticAdmissionReceipt:
    if type(receipt) is not HkelAuthenticAdmissionReceipt:
        _fail("RETAINED_HKEL_ADMISSION_INVALID")
    attempt_id = retained.hkel_report["attempt_id"]
    cutoff = retained.hkel_report["observation_cutoff"]
    try:
        reproduced = HkelAuthenticAdmissionReceipt.from_json(receipt.to_json())
    except (TypeError, ValueError) as error:
        raise AcquisitionConfigPreparationError(_HKEL_ADMISSION_INVALID) from error
    if (
        reproduced != receipt
        or receipt.attempt_id != attempt_id
        or receipt.observation_cutoff != cutoff
        or receipt.report_fingerprint != profile.hkel_report_fingerprint
    ):
        _fail("RETAINED_HKEL_ADMISSION_INVALID")
    return receipt


def _archive_observation(receipt: HkelAuthenticAdmissionReceipt) -> bytes:
    try:
        keys = tuple(
            HkelArchiveReuseKey.issue(
                item.archive_endpoint_id,
                item.archive_fingerprint,
                item.publication_profile_fingerprint,
            )
            for item in receipt.archive_reuse_keys
        )
    except (TypeError, ValueError) as error:
        raise AcquisitionConfigPreparationError(_HKEL_ADMISSION_INVALID) from error
    if tuple(item.fingerprint for item in keys) != tuple(
        item.fingerprint for item in receipt.archive_reuse_keys
    ):
        _fail("RETAINED_HKEL_ADMISSION_INVALID")
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hkel-archive-observation",
        "schema_version": "1.0.0",
        "archive_reuse_keys": [
            {
                "archive_endpoint_id": item.archive_endpoint_id,
                "archive_fingerprint": item.archive_fingerprint,
                "publication_profile_fingerprint": item.publication_profile_fingerprint,
                "fingerprint": item.fingerprint,
            }
            for item in keys
        ],
    }
    checked = checked_json_value(body)
    if type(checked) is not dict:
        _fail("RETAINED_HKEL_ADMISSION_INVALID")
    return canonicalize(
        {**checked, "fingerprint": f"sha256:{sha256(canonicalize(checked)).hexdigest()}"}
    )


def _files(retained: _RetainedInputs, receipt: HkelAuthenticAdmissionReceipt) -> dict[str, bytes]:
    return {
        "gld-window-snapshot.json": retained.gld_window,
        "hkel-admission-receipt.json": canonicalize(receipt.to_json()),
        "hkel-archive-observation.json": _archive_observation(receipt),
        "judiciary-advanced-search-form.html": retained.form,
        "judiciary-advanced-search-form.sha256": (
            f"sha256:{sha256(retained.form).hexdigest()}\n".encode()
        ),
    }


def _report(
    files: Mapping[str, bytes],
    retained: _RetainedInputs,
    profile: RetainedAcquisitionProfile,
) -> bytes:
    artifacts: list[JsonValue] = [
        {
            "filename": name,
            "byte_length": len(files[name]),
            "fingerprint": f"sha256:{sha256(files[name]).hexdigest()}",
        }
        for name in CONFIG_FILENAMES
    ]
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1.acquisition-config-preparation",
        "schema_version": "1.0.0",
        "result": "READY",
        "artifact_count": len(CONFIG_FILENAMES),
        "artifacts": artifacts,
        "hkel_report_fingerprint": profile.hkel_report_fingerprint,
        "judiciary_report_fingerprint": profile.judiciary_report_fingerprint,
        "gld_window_fingerprint": f"sha256:{sha256(retained.gld_window).hexdigest()}",
        "gld_listing_fingerprint": retained.gld_listing_fingerprint,
    }
    checked = checked_json_value(body)
    if type(checked) is not dict:
        _fail("ACQUISITION_CONFIG_REPORT_INVALID")
    return canonicalize(
        {**checked, "fingerprint": f"sha256:{sha256(canonicalize(checked)).hexdigest()}"}
    )


def _output_parent(path: Path) -> Path:
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        _fail("ACQUISITION_CONFIG_OUTPUT_INVALID")
    return _existing_root(path.parent, code="ACQUISITION_CONFIG_OUTPUT_INVALID")


def _read_existing_receipt(output_root: Path) -> HkelAuthenticAdmissionReceipt:
    path = output_root / "hkel-admission-receipt.json"
    raw = _read_regular(path, maximum=_MAX_CONFIG_BYTES, code="ACQUISITION_CONFIG_OUTPUT_DRIFT")
    try:
        document = parse_json_bytes(raw, max_bytes=len(raw))
        if canonicalize(document) != raw:
            _fail("ACQUISITION_CONFIG_OUTPUT_DRIFT")
        return HkelAuthenticAdmissionReceipt.from_json(document)
    except AcquisitionConfigPreparationError:
        raise
    except (TypeError, ValueError) as error:
        raise AcquisitionConfigPreparationError(_OUTPUT_DRIFT) from error


def _verify_output(output_root: Path, expected: Mapping[str, bytes]) -> None:
    try:
        metadata = output_root.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != _OUTPUT_DIRECTORY_MODE
            or output_root.resolve(strict=True) != output_root
            or {item.name for item in output_root.iterdir()} != set(CONFIG_FILENAMES)
        ):
            _fail("ACQUISITION_CONFIG_OUTPUT_DRIFT")
        for name in CONFIG_FILENAMES:
            path = output_root / name
            file_metadata = path.lstat()
            if (
                stat.S_ISLNK(file_metadata.st_mode)
                or not stat.S_ISREG(file_metadata.st_mode)
                or stat.S_IMODE(file_metadata.st_mode) != _OUTPUT_FILE_MODE
                or path.resolve(strict=True) != path
                or path.read_bytes() != expected[name]
            ):
                _fail("ACQUISITION_CONFIG_OUTPUT_DRIFT")
    except AcquisitionConfigPreparationError:
        raise
    except OSError as error:
        raise AcquisitionConfigPreparationError(_OUTPUT_DRIFT) from error


def _publish(output_root: Path, files: Mapping[str, bytes]) -> None:
    parent = _output_parent(output_root)
    if os.path.lexists(output_root):
        _fail("ACQUISITION_CONFIG_OUTPUT_DRIFT")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", suffix=".tmp", dir=parent))
    try:
        temporary.chmod(_OUTPUT_DIRECTORY_MODE)
        for name in CONFIG_FILENAMES:
            path = temporary / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _OUTPUT_FILE_MODE)
            try:
                os.fchmod(descriptor, _OUTPUT_FILE_MODE)
                with os.fdopen(descriptor, "wb") as stream:
                    descriptor = -1
                    stream.write(files[name])
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        directory_descriptor = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        if os.path.lexists(output_root):
            _fail("ACQUISITION_CONFIG_OUTPUT_DRIFT")
        temporary.rename(output_root)
        parent_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except AcquisitionConfigPreparationError:
        raise
    except OSError as error:
        raise AcquisitionConfigPreparationError(_OUTPUT_INVALID) from error
    finally:
        if temporary.exists():
            for name in CONFIG_FILENAMES:
                with suppress(FileNotFoundError):
                    (temporary / name).unlink()
            with suppress(FileNotFoundError):
                temporary.rmdir()
    _verify_output(output_root, files)


def prepare_acquisition_config(
    inputs: AcquisitionConfigInputs,
    *,
    profile: RetainedAcquisitionProfile = _KNOWN_PROFILE,
    admit_hkel: AdmissionBuilder = admit_retained_hkel_observation,
) -> bytes:
    """Create or replay the five exact local inputs and return a stable report."""
    retained = _retained_inputs(inputs, profile)
    output_root = inputs.output_root
    if type(output_root) is not type(Path()):
        _fail("ACQUISITION_CONFIG_OUTPUT_INVALID")
    _output_parent(output_root)
    if os.path.lexists(output_root):
        try:
            receipt = _validated_receipt(_read_existing_receipt(output_root), retained, profile)
            files = _files(retained, receipt)
            _verify_output(output_root, files)
        except AcquisitionConfigPreparationError as error:
            if error.code == "ACQUISITION_CONFIG_OUTPUT_DRIFT":
                raise
            raise AcquisitionConfigPreparationError(_OUTPUT_DRIFT) from error
        return _report(files, retained, profile)

    reference, reader = _hkel_reference(retained, profile)
    try:
        receipt = _validated_receipt(admit_hkel(reference, reader), retained, profile)
    except AcquisitionConfigPreparationError:
        raise
    except Exception as error:
        raise AcquisitionConfigPreparationError(_HKEL_ADMISSION_INVALID) from error
    files = _files(retained, receipt)
    _publish(output_root, files)
    return _report(files, retained, profile)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one explicit offline materialization; no default output is permitted."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--gld-window", required=True, type=Path)
    parser.add_argument("--gld-window-sha256", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        report = prepare_acquisition_config(
            AcquisitionConfigInputs(
                arguments.source_root,
                arguments.gld_window,
                arguments.gld_window_sha256,
                arguments.output_root,
            )
        )
    except AcquisitionConfigPreparationError as error:
        sys.stderr.write(f"{error.code}\n")
        return 2
    sys.stdout.buffer.write(report + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
