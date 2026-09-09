"""Select exact complete two-family Task 10 acceptance cutoffs from retained manifests."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Never, TypeIs

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_reporting import (
    FamilyAcquisitionCoverage,
    parse_hk_v1_cases_acquisition_manifest,
    parse_hk_v1_legislation_acquisition_manifest,
)

_MAX_MANIFEST_BYTES = 16_777_216
_FINGERPRINT_LENGTH = 71
_DEFAULT_ROOT = Path("var/hk-v1/acceptance-cutoffs")
_CASES_NAME = "cases-acquisition-manifest.json"
_LEGISLATION_NAME = "legislation-acquisition-manifest.json"
_FAMILY_EVIDENCE_NAME = "family-acquisition-evidence.json"
_FAMILIES = ("CASES", "LEGISLATION")
_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_INCOMPLETE = "COMMON_CUTOFF_INCOMPLETE"
_OUTPUT_INVALID = "ACCEPTANCE_CUTOFF_OUTPUT_INVALID"
_OUTPUT_CONFLICT = "ACCEPTANCE_CUTOFF_OUTPUT_CONFLICT"
_OUTPUT_READBACK_FAILED = "ACCEPTANCE_CUTOFF_OUTPUT_READBACK_FAILED"
_OUTPUT_MODE = 0o600


class AcceptanceCutoffSelectionError(ValueError):
    """One closed, machine-readable cutoff-selection failure."""

    def __init__(self, code: str) -> None:
        """Retain the exact public failure code without adding path details."""
        self.code = code
        super().__init__(code)


def _fail(code: str) -> Never:
    raise AcceptanceCutoffSelectionError(code)


@dataclass(frozen=True, slots=True)
class _Pair:
    cutoff: str
    cases: FamilyAcquisitionCoverage
    legislation: FamilyAcquisitionCoverage
    family_acquisition_evidence: dict[str, JsonValue]


def _root(path: Path) -> Path:
    try:
        absolute = path.absolute()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise AcceptanceCutoffSelectionError(_INCOMPLETE) from error
    if path.is_symlink() or not resolved.is_dir() or resolved != absolute:
        _fail("COMMON_CUTOFF_INCOMPLETE")
    return resolved


def _read(root: Path, label: str, filename: str) -> bytes:
    path = root / label / filename
    try:
        if path.is_symlink() or not path.is_file():
            _fail("COMMON_CUTOFF_INCOMPLETE")
        resolved = path.resolve(strict=True)
        if resolved != path or not resolved.is_relative_to(root):
            _fail("COMMON_CUTOFF_INCOMPLETE")
        content = resolved.read_bytes()
    except AcceptanceCutoffSelectionError:
        raise
    except OSError as error:
        raise AcceptanceCutoffSelectionError(_INCOMPLETE) from error
    if not content or len(content) > _MAX_MANIFEST_BYTES:
        _fail("COMMON_CUTOFF_INCOMPLETE")
    return content


def _parse(
    content: bytes,
    parser: object,
) -> tuple[FamilyAcquisitionCoverage, dict[str, JsonValue]]:
    try:
        document = parse_json_bytes(content, max_bytes=_MAX_MANIFEST_BYTES)
        if type(document) is not dict or canonicalize(document) != content:
            _fail("COMMON_CUTOFF_INCOMPLETE")
        if document.get("result") != "COMPLETE":
            _fail("COMMON_CUTOFF_INCOMPLETE")
        if parser is parse_hk_v1_cases_acquisition_manifest:
            projection = parse_hk_v1_cases_acquisition_manifest(content)
        elif parser is parse_hk_v1_legislation_acquisition_manifest:
            projection = parse_hk_v1_legislation_acquisition_manifest(content)
        else:
            _fail("COMMON_CUTOFF_INCOMPLETE")
    except AcceptanceCutoffSelectionError:
        raise
    except (TypeError, ValueError) as error:
        raise AcceptanceCutoffSelectionError(_INCOMPLETE) from error
    return projection, document


def _pair(root: Path, label: str) -> _Pair:
    cases_content = _read(root, label, _CASES_NAME)
    legislation_content = _read(root, label, _LEGISLATION_NAME)
    cases, cases_document = _parse(cases_content, parse_hk_v1_cases_acquisition_manifest)
    legislation, legislation_document = _parse(
        legislation_content,
        parse_hk_v1_legislation_acquisition_manifest,
    )
    if (
        cases.material_family != "CASES"
        or legislation.material_family != "LEGISLATION"
        or cases.scope_ids + legislation.scope_ids != _SCOPES
        or cases.observation_cutoff != legislation.observation_cutoff
        or cases.retryable_count != 0
        or legislation.retryable_count != 0
    ):
        _fail("COMMON_CUTOFF_INCOMPLETE")
    evidence = _family_evidence(
        _read(root, label, _FAMILY_EVIDENCE_NAME),
        (
            (cases, cases_document, cases_content),
            (legislation, legislation_document, legislation_content),
        ),
    )
    return _Pair(cases.observation_cutoff, cases, legislation, evidence)


def _family_evidence(
    content: bytes,
    manifests: tuple[
        tuple[FamilyAcquisitionCoverage, dict[str, JsonValue], bytes],
        tuple[FamilyAcquisitionCoverage, dict[str, JsonValue], bytes],
    ],
) -> dict[str, JsonValue]:
    """Validate the exact retained Acquisition lineage Legal will later consume."""
    try:
        value = parse_json_bytes(content, max_bytes=_MAX_MANIFEST_BYTES)
        if (
            type(value) is not dict
            or canonicalize(value) != content
            or frozenset(value)
            != frozenset(
                {
                    "schema_id",
                    "schema_version",
                    "root_cycle_id",
                    "root_plan_fingerprint",
                    "evidence_reference",
                    "children",
                }
            )
            or value["schema_id"] != "asklegal.hk-v1.acceptance-family-acquisition-evidence"
            or value["schema_version"] != "1.0.0"
            or not _nonempty_text(value["root_cycle_id"])
            or not _fingerprint(value["root_plan_fingerprint"])
            or not _reference(value["evidence_reference"])
        ):
            _fail(_INCOMPLETE)
        children = value["children"]
        if type(children) is not list or len(children) != len(_FAMILIES):
            _fail(_INCOMPLETE)
        for expected_family, raw_child, manifest in zip(
            _FAMILIES, children, manifests, strict=True
        ):
            projection, document, raw_manifest = manifest
            if type(raw_child) is not dict or frozenset(raw_child) != frozenset(
                {
                    "source_family",
                    "cycle_id",
                    "journal_ref",
                    "manifest_fingerprint",
                    "journal_head_fingerprint",
                    "result",
                    "manifest_reference",
                }
            ):
                _fail(_INCOMPLETE)
            cycle_id = raw_child["cycle_id"]
            reference = raw_child["manifest_reference"]
            if (
                raw_child["source_family"] != expected_family
                or not _nonempty_text(cycle_id)
                or cycle_id != document.get("cycle_id")
                or raw_child["journal_ref"] != f"acquisition-journals/{cycle_id}"
                or raw_child["manifest_fingerprint"] != projection.manifest_fingerprint
                or raw_child["journal_head_fingerprint"] != document.get("journal_head_fingerprint")
                or raw_child["result"] != document.get("result")
                or not _reference(reference)
                or reference["byte_length"] != len(raw_manifest)
                or reference["fingerprint"] != f"sha256:{sha256(raw_manifest).hexdigest()}"
            ):
                _fail(_INCOMPLETE)
    except AcceptanceCutoffSelectionError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise AcceptanceCutoffSelectionError(_INCOMPLETE) from error
    return value


def _nonempty_text(value: object) -> bool:
    return type(value) is str and bool(value)


def _fingerprint(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _FINGERPRINT_LENGTH
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _reference(value: JsonValue) -> TypeIs[dict[str, JsonValue]]:
    if type(value) is not dict:
        return False
    reference = value
    return (
        frozenset(reference)
        == frozenset({"vault", "logical_key", "version_id", "fingerprint", "byte_length"})
        and reference["vault"] == "PRIMARY"
        and _nonempty_text(reference["logical_key"])
        and _nonempty_text(reference["version_id"])
        and _fingerprint(reference["fingerprint"])
        and type(reference["byte_length"]) is int
        and reference["byte_length"] > 0
    )


def _instant(cutoff: str) -> datetime:
    try:
        return datetime.fromisoformat(cutoff.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise AcceptanceCutoffSelectionError(_INCOMPLETE) from error


def _pair_json(pair: _Pair, changed_families: tuple[str, ...]) -> dict[str, JsonValue]:
    return {
        "observation_cutoff": pair.cutoff,
        "cases_manifest_fingerprint": pair.cases.manifest_fingerprint,
        "legislation_manifest_fingerprint": pair.legislation.manifest_fingerprint,
        "authentic_changed_families": list(changed_families),
        "family_acquisition_evidence": pair.family_acquisition_evidence,
    }


def select_acceptance_cutoffs(retained_root: Path) -> bytes:
    """Return one canonical selection only for exact complete changed T1/T2 pairs."""
    root = _root(retained_root)
    t1 = _pair(root, "t1")
    t2 = _pair(root, "t2")
    if _instant(t1.cutoff) >= _instant(t2.cutoff):
        _fail("COMMON_CUTOFF_INCOMPLETE")
    changed = tuple(
        family
        for family, previous, current in (
            ("CASES", t1.cases.verified_evidence_refs, t2.cases.verified_evidence_refs),
            (
                "LEGISLATION",
                t1.legislation.verified_evidence_refs,
                t2.legislation.verified_evidence_refs,
            ),
        )
        if previous != current
    )
    if not changed:
        _fail("AUTHENTIC_CHANGE_NOT_FOUND")
    body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1.acceptance-cutoff-selection",
            "schema_version": "1.0.0",
            "families": list(_FAMILIES),
            "scope_ids": list(_SCOPES),
            "t1": _pair_json(t1, ()),
            "t2": _pair_json(t2, changed),
        }
    )
    if type(body) is not dict:
        _fail("COMMON_CUTOFF_INCOMPLETE")
    document = dict(body)
    document["fingerprint"] = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    return canonicalize(document)


def _read_output(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise AcceptanceCutoffSelectionError(_OUTPUT_READBACK_FAILED) from error


def _output_parent(path: Path, content: bytes) -> Path:
    try:
        document = parse_json_bytes(content, max_bytes=_MAX_MANIFEST_BYTES)
    except ValueError as error:
        raise AcceptanceCutoffSelectionError(_OUTPUT_INVALID) from error
    if canonicalize(document) != content or not path.is_absolute():
        _fail(_OUTPUT_INVALID)
    try:
        parent = path.parent
        absolute_parent = parent.absolute()
        resolved_parent = parent.resolve(strict=True)
        if (
            parent.is_symlink()
            or not resolved_parent.is_dir()
            or resolved_parent != absolute_parent
        ):
            _fail(_OUTPUT_INVALID)
        if os.path.lexists(path):
            _fail(_OUTPUT_CONFLICT)
    except AcceptanceCutoffSelectionError:
        raise
    except OSError as error:
        raise AcceptanceCutoffSelectionError(_OUTPUT_INVALID) from error
    return resolved_parent


def _write_temporary(parent: Path, path: Path, content: bytes) -> Path:
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
    except OSError as error:
        raise AcceptanceCutoffSelectionError(_OUTPUT_INVALID) from error
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, _OUTPUT_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        with suppress(FileNotFoundError):
            temporary_path.unlink()
        raise AcceptanceCutoffSelectionError(_OUTPUT_INVALID) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return temporary_path


def _publish_temporary(temporary_path: Path, path: Path, parent: Path) -> None:
    try:
        try:
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise AcceptanceCutoffSelectionError(_OUTPUT_CONFLICT) from error
        temporary_path.unlink()
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except AcceptanceCutoffSelectionError:
        raise
    except OSError as error:
        raise AcceptanceCutoffSelectionError(_OUTPUT_INVALID) from error
    finally:
        with suppress(FileNotFoundError):
            temporary_path.unlink()


def _verify_output(path: Path, content: bytes) -> None:
    try:
        metadata = path.lstat()
        readback = _read_output(path)
        if (
            stat.S_IMODE(metadata.st_mode) != _OUTPUT_MODE
            or not stat.S_ISREG(metadata.st_mode)
            or path.is_symlink()
            or path.resolve(strict=True) != path
            or readback != content
            or canonicalize(parse_json_bytes(readback, max_bytes=_MAX_MANIFEST_BYTES)) != readback
        ):
            _fail(_OUTPUT_READBACK_FAILED)
    except AcceptanceCutoffSelectionError:
        raise
    except (OSError, ValueError) as error:
        raise AcceptanceCutoffSelectionError(_OUTPUT_READBACK_FAILED) from error


def write_acceptance_cutoff_selection(path: Path, content: bytes) -> None:
    """Atomically freeze exact canonical selection bytes at one new absolute path."""
    parent = _output_parent(path, content)
    temporary_path = _write_temporary(parent, path, content)
    _publish_temporary(temporary_path, path, parent)
    _verify_output(path, content)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the read-only selector and emit canonical JSON only on success."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--retained-root", type=Path, default=_DEFAULT_ROOT)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    try:
        content = select_acceptance_cutoffs(arguments.retained_root)
        if arguments.output is not None:
            write_acceptance_cutoff_selection(arguments.output, content)
    except AcceptanceCutoffSelectionError as error:
        sys.stderr.write(f"{error.code}\n")
        return 2
    if arguments.output is None:
        sys.stdout.buffer.write(content + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
