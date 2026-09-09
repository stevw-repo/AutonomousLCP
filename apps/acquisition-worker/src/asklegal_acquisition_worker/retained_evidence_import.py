"""Offline import of previously captured and fully read-back source evidence."""

from __future__ import annotations

import os
import re
import stat
import weakref
import zipfile
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from hashlib import sha256
from itertools import pairwise
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Never, Protocol, TypeIs
from urllib.parse import urlsplit

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value

from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionJournalError,
    CycleSafetyProfilePayload,
    DiscoveredPayload,
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    WorkItemIdentity,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_OBJECT_KEY = re.compile(r"objects/(?P<digest>[0-9a-f]{64})\.bin", re.ASCII)
_LISTING = re.compile(r"judiciary-year-(?P<year>[0-9]{4})-page-(?P<page>[0-9]+)", re.ASCII)
_ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", re.ASCII)
_MAX_REPORT_BYTES = 16_777_216
_MAX_OBJECT_BYTES = 1_073_741_824
_READ_CHUNK = 1_048_576
_PAIR_LENGTH = 2
_MAX_TRANSPORT_ATTEMPTS = 2
_HTTP_OK = 200
_HTTP_SUCCESS_LIMIT = 300
_HTTP_STATUS_LIMIT = 599
_MAINTENANCE_BODY_LENGTH = 255
_ASCII_CONTROL_LIMIT = 32
_ASCII_DELETE = 127
_AUTHORITY_PROVENANCE = "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING"
_HKEL_REPORT_KEYS = frozenset(
    {
        "attempt_id",
        "authority_manifest_fingerprint",
        "authority_provenance",
        "change_state",
        "endpoint_counts",
        "endpoints",
        "execution_authorization_fingerprint",
        "observation_cutoff",
        "predecessor_attempt_id",
        "readback_verified",
        "result",
        "source_family",
        "source_procedures",
    }
)
_JUDICIARY_RETRY_REPORT_KEYS = frozenset(
    {
        "attempt_id",
        "authority_manifest_fingerprint",
        "authority_provenance",
        "change_state",
        "endpoint_counts",
        "endpoints",
        "execution_authorization_fingerprint",
        "execution_policy",
        "execution_policy_fingerprint",
        "observation_accounting",
        "observation_cutoff",
        "predecessor_attempt_id",
        "readback_verified",
        "report_schema_version",
        "result",
        "source_family",
        "source_procedures",
        "transport_attempts",
    }
)
_JUDICIARY_CONTINUATION_REPORT_KEYS = _JUDICIARY_RETRY_REPORT_KEYS | frozenset(
    {"continuation_binding", "cumulative_observation_accounting"}
)
_ENDPOINT_KEYS = frozenset(
    {
        "body_fingerprint",
        "byte_length",
        "endpoint_id",
        "endpoint_version",
        "media_type",
        "method",
        "object_key",
        "requested_url",
        "status",
        "terminal_code",
    }
)
_TRANSPORT_ATTEMPT_KEYS = _ENDPOINT_KEYS | frozenset(
    {
        "attempt_number",
        "final_url",
        "max_bytes",
        "redirect_rejected",
        "sequence",
        "start_elapsed_seconds",
    }
)
_PROCEDURE_KEYS = frozenset({"declared_member_count", "source_id", "terminal_code"})
_JUDICIARY_PROCEDURES: tuple[tuple[str, int, str], ...] = (
    ("HK-CASE-HKLII-DISCOVERY", 1, "COMPLETE"),
    ("HK-CASE-JUDICIARY-LRS-INVENTORY", 0, "INCOMPLETE"),
)
_HKEL_PROCEDURES: tuple[tuple[str, int, str], ...] = (
    ("HK-LEG-BASIC-LAW-PORTAL", 20, "COMPLETE"),
    ("HK-LEG-HKEL-CURRENT-DATA", 12, "COMPLETE"),
    ("HK-LEG-HKEL-CURRENT-INVENTORY", 3_157, "COMPLETE"),
    ("HK-LEG-HKEL-EDITORIAL-RECORDS", 2, "COMPLETE"),
    ("HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS", 7, "COMPLETE"),
)
_HKEL_ARCHIVE_PROFILE: tuple[tuple[str, str], ...] = tuple(
    (f"sep_{value:048x}", language)
    for value, language in (
        (10, "en"),
        (11, "en"),
        (12, "en"),
        (13, "en"),
        (14, "zh-Hant"),
        (15, "zh-Hant"),
        (16, "zh-Hant"),
        (17, "zh-Hant"),
        (18, "zh-Hans"),
        (19, "zh-Hans"),
        (20, "zh-Hans"),
        (21, "zh-Hans"),
    )
)
_HKEL_SPECIFICATION_ENDPOINT_IDS = tuple(
    f"sep_{value:048x}" for value in (53, 54, 55, 56, 57, 58, 81)
)
_HKEL_SPECIFICATION_MEDIA_TYPES = (
    "application/xml",
    "application/pdf",
    "application/pdf",
    "application/pdf",
    "text/html",
    "text/html",
    "text/html",
)
_HKEL_XML_MEMBER = re.compile(
    r"^(?P<chapter>(?:cap_[0-9A-Z]+|A[0-9A-Z]+))_"
    r"(?P<language>en|zh-Hant|zh-Hans)_c/"
    r"(?P=chapter)_(?P<version>[0-9]{14}|-{14})_"
    r"(?P=language)_c\.xml$"
)
_MAX_ARCHIVE_MEMBERS = 4_096
_MAX_ARCHIVE_MEMBER_BYTES = 32 << 20
_MAX_ARCHIVE_EXPANDED_BYTES = 1 << 30
_MAX_COMPRESSION_RATIO = 100
_EXPECTED_HKEL_ARCHIVE_MEMBERS = 12_858
_EXPECTED_HKEL_BILINGUAL_PAIRS = 3_157
_EXPECTED_HKEL_PUBLICATION_SPECIFICATIONS = 7
_JUDICIARY_CURRENT_POLICY = {
    "maximum_attempts_per_logical_request": 2,
    "minimum_start_interval_seconds": 2.0,
    "name": "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0",
    "retry_eligibility": {
        "normalized_transport_failure": {
            "body_byte_length": 0,
            "final_url": None,
            "media_type": "application/octet-stream",
            "redirect_rejected": False,
            "status": 0,
        },
        "publisher_maintenance_outage": {
            "body_byte_length": 255,
            "body_sha256": "39f0a4df3dc88efbd6216caeaa03dc9fd1acbed9e73a477508e86f7e4229594f",
            "final_url": "EXACT_REQUESTED_ADMITTED_HTTPS_URL",
            "media_type": "text/plain",
            "redirect_rejected": False,
            "status": 200,
        },
        "publisher_server_error": {
            "body_byte_length": "INTEGER_0_TO_REQUEST_MAX_BYTES",
            "final_url": "EXACT_REQUESTED_ADMITTED_HTTPS_URL",
            "media_type": "ANY_RETAINED_MEDIA_TYPE",
            "redirect_rejected": False,
            "statuses": [500, 502, 503, 504],
        },
    },
}
_JUDICIARY_CURRENT_POLICY_FINGERPRINT = (
    "sha256:6e3f5849e2e7fb60a56b8b5adad35b370c123f017b0cb5854db9e8aeb656590a"
)
_JUDICIARY_MAINTENANCE_POLICY = {
    "maximum_attempts_per_logical_request": 2,
    "minimum_start_interval_seconds": 2.0,
    "name": "JUDICIARY_TRANSPORT_ATTEMPTS_1.1.0",
    "retry_eligibility": {
        "normalized_transport_failure": {
            "body_byte_length": 0,
            "final_url": None,
            "media_type": "application/octet-stream",
            "redirect_rejected": False,
            "status": 0,
        },
        "publisher_maintenance_outage": {
            "body_byte_length": 255,
            "body_sha256": "39f0a4df3dc88efbd6216caeaa03dc9fd1acbed9e73a477508e86f7e4229594f",
            "final_url": "EXACT_REQUESTED_ADMITTED_HTTPS_URL",
            "media_type": "text/plain",
            "redirect_rejected": False,
            "status": 200,
        },
    },
}
_JUDICIARY_LEGACY_POLICY = {
    "maximum_attempts_per_logical_request": 2,
    "minimum_start_interval_seconds": 2.0,
    "name": "JUDICIARY_TRANSPORT_ATTEMPTS_1.0.0",
    "retry_eligibility": {
        "body_byte_length": 0,
        "final_url": None,
        "media_type": "application/octet-stream",
        "redirect_rejected": False,
        "status": 0,
    },
}
_JUDICIARY_POLICIES = (
    (
        _JUDICIARY_LEGACY_POLICY,
        "sha256:9993c64e7cc62654d773cf1e860699cd9b56737d1cea4c4c17ee016308bf8353",
    ),
    (
        _JUDICIARY_MAINTENANCE_POLICY,
        "sha256:d42d817e27d08896358a0fcf218833b1feaf9b285e5f71fc902731dff136a349",
    ),
    (_JUDICIARY_CURRENT_POLICY, _JUDICIARY_CURRENT_POLICY_FINGERPRINT),
)
_JUDICIARY_ACCOUNTING_KEYS = frozenset(
    {
        "elapsed_seconds",
        "profile",
        "profile_fingerprint",
        "rejected_response_bytes",
        "request_starts",
        "retained_response_bytes",
        "stop_code",
    }
)
_JUDICIARY_OBSERVATION_PROFILE = {
    "elapsed_seconds_limit": 259200.0,
    "minimum_start_interval_seconds": 2.0,
    "request_start_limit": 50000,
    "retained_response_byte_limit": 68719476736,
}
_JUDICIARY_OBSERVATION_PROFILE_FINGERPRINT = (
    "sha256:11dd904c60b673e8445a70b64c748464825142382df472fd07b950cc9ba54cb3"
)


class RetainedEvidenceImportError(ValueError):
    """One fail-closed retained report, object, projection, or journal mismatch."""


class WorkItemProjection(Protocol):
    """Project one validated captured endpoint to a stable modern work item."""

    def __call__(self, retained_record: JsonValue) -> WorkItemIdentity:
        """Return one exact work item for the retained endpoint."""
        ...


@dataclass(frozen=True, slots=True)
class RetainedLineageReportPin:
    """One exact recursive predecessor report selected for offline verification."""

    attempt_id: str
    expected_report_fingerprint: str
    predecessor_attempt_id: str | None

    def __post_init__(self) -> None:
        """Reject malformed or ambiguous lineage pins."""
        if (
            type(self.attempt_id) is not str
            or _ATTEMPT_ID.fullmatch(self.attempt_id) is None
            or type(self.expected_report_fingerprint) is not str
            or _FINGERPRINT.fullmatch(self.expected_report_fingerprint) is None
            or (
                self.predecessor_attempt_id is not None
                and (
                    type(self.predecessor_attempt_id) is not str
                    or _ATTEMPT_ID.fullmatch(self.predecessor_attempt_id) is None
                )
            )
        ):
            _fail("RETAINED_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True)
class RetainedReportReference:
    """Caller-selected immutable retained report and expected authority facts."""

    report_path: Path
    expected_report_fingerprint: str
    expected_authority_manifest_fingerprint: str
    expected_execution_authorization_fingerprint: str
    product_family: str
    cycle_id: str
    expected_source_result: str
    expected_imported_item_count: int
    lineage_report_pins: tuple[RetainedLineageReportPin, ...] = ()
    expected_last_listing: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        """Validate exact paths, fingerprints, family, cycle, and expected counts."""
        if (
            type(self.report_path) is not type(Path())
            or not self.report_path.is_absolute()
            or any(part in {"", ".", ".."} for part in self.report_path.parts[1:])
            or self.report_path.name != "report.json"
            or self.report_path.parent.parent.name != "attempts"
            or _ATTEMPT_ID.fullmatch(self.report_path.parent.name) is None
            or type(self.expected_report_fingerprint) is not str
            or _FINGERPRINT.fullmatch(self.expected_report_fingerprint) is None
            or type(self.expected_authority_manifest_fingerprint) is not str
            or _FINGERPRINT.fullmatch(self.expected_authority_manifest_fingerprint) is None
            or type(self.expected_execution_authorization_fingerprint) is not str
            or _FINGERPRINT.fullmatch(self.expected_execution_authorization_fingerprint) is None
            or self.product_family not in {"CASES", "LEGISLATION"}
            or type(self.product_family) is not str
            or type(self.cycle_id) is not str
            or not self.cycle_id
            or type(self.expected_source_result) is not str
            or not self.expected_source_result
            or type(self.expected_imported_item_count) is not int
            or self.expected_imported_item_count < 1
            or type(self.lineage_report_pins) is not tuple
            or any(type(pin) is not RetainedLineageReportPin for pin in self.lineage_report_pins)
            or len({pin.attempt_id for pin in self.lineage_report_pins})
            != len(self.lineage_report_pins)
            or (
                self.expected_last_listing is not None
                and (
                    type(self.expected_last_listing) is not tuple
                    or len(self.expected_last_listing) != _PAIR_LENGTH
                    or any(
                        type(value) is not int or value < 1 for value in self.expected_last_listing
                    )
                )
            )
        ):
            _fail("RETAINED_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True)
class RetainedImportedObjectReference:
    """Exact imported work/object binding reproduced from the retained report."""

    endpoint_id: str
    work_item_id: str
    media_type: str
    final_url: str
    body_length: int
    content_fingerprint: str
    object_ref: str
    authority_manifest_fingerprint: str
    execution_authorization_fingerprint: str


@dataclass(frozen=True, slots=True, weakref_slot=True)
class RetainedImportReceipt:
    """Deterministic receipt for one exact retained report import."""

    source_family: str
    source_report_fingerprint: str
    imported_item_count: int
    reused_object_bytes: int
    journal_head_fingerprint: str
    archive_members: int | None
    archive_pairs: int | None
    publication_specifications: int | None
    semantic_proof_fingerprint: str
    last_listing: tuple[int, int] | None
    cycle_id: str = ""
    source_attempt_id: str = ""
    imported_work_item_ids: tuple[str, ...] = ()
    work_item_lineage_fingerprint: str = ""
    imported_checkpoint_fingerprint: str = ""
    imported_object_references: tuple[RetainedImportedObjectReference, ...] = ()
    issuance_fingerprint: str = dataclass_field(init=False, default="", repr=False)

    def assert_factory_issued(self) -> None:
        """Require this live receipt to originate from the verified import transaction."""
        snapshot = _receipt_fingerprint(self)
        issued = _RECEIPT_ISSUANCE.get(id(self))
        if (
            issued is None
            or issued.reference() is not self
            or issued.snapshot != snapshot
            or self.issuance_fingerprint != snapshot
        ):
            _fail("RETAINED_RECEIPT_NOT_FACTORY_ISSUED")


@dataclass(frozen=True, slots=True)
class KnownV1RetainedImportReceipts:
    """Exact receipts for the two retained V1 source families."""

    hkel: RetainedImportReceipt
    judiciary: RetainedImportReceipt


@dataclass(frozen=True, slots=True)
class _IssuedReceipt:
    """Private live-object provenance for an importer-issued receipt."""

    reference: weakref.ReferenceType[object]
    snapshot: str


_RECEIPT_ISSUANCE: dict[int, _IssuedReceipt] = {}


def _receipt_fingerprint(receipt: RetainedImportReceipt) -> str:
    body = {
        "archive_members": receipt.archive_members,
        "archive_pairs": receipt.archive_pairs,
        "cycle_id": receipt.cycle_id,
        "imported_item_count": receipt.imported_item_count,
        "imported_work_item_ids": list(receipt.imported_work_item_ids),
        "imported_checkpoint_fingerprint": receipt.imported_checkpoint_fingerprint,
        "imported_object_references": [
            {
                "authority_manifest_fingerprint": item.authority_manifest_fingerprint,
                "body_length": item.body_length,
                "content_fingerprint": item.content_fingerprint,
                "endpoint_id": item.endpoint_id,
                "execution_authorization_fingerprint": item.execution_authorization_fingerprint,
                "final_url": item.final_url,
                "media_type": item.media_type,
                "object_ref": item.object_ref,
                "work_item_id": item.work_item_id,
            }
            for item in receipt.imported_object_references
        ],
        "journal_head_fingerprint": receipt.journal_head_fingerprint,
        "last_listing": None if receipt.last_listing is None else list(receipt.last_listing),
        "publication_specifications": receipt.publication_specifications,
        "reused_object_bytes": receipt.reused_object_bytes,
        "semantic_proof_fingerprint": receipt.semantic_proof_fingerprint,
        "source_attempt_id": receipt.source_attempt_id,
        "source_family": receipt.source_family,
        "source_report_fingerprint": receipt.source_report_fingerprint,
        "work_item_lineage_fingerprint": receipt.work_item_lineage_fingerprint,
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"


def _issue_receipt(receipt: RetainedImportReceipt) -> RetainedImportReceipt:
    identity = id(receipt)
    snapshot = _receipt_fingerprint(receipt)
    object.__setattr__(receipt, "issuance_fingerprint", snapshot)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        issued = _RECEIPT_ISSUANCE.get(identity)
        if issued is not None and issued.reference is reference:
            del _RECEIPT_ISSUANCE[identity]

    _RECEIPT_ISSUANCE[identity] = _IssuedReceipt(weakref.ref(receipt, cleanup), snapshot)
    receipt.assert_factory_issued()
    return receipt


@dataclass(frozen=True, slots=True)
class _CapturedEndpoint:
    raw: dict[str, JsonValue]
    endpoint_id: str
    endpoint_version: str
    media_type: str
    requested_url: str
    status: int
    object_key: str
    body_length: int
    content_fingerprint: str


def _fail(code: str) -> Never:
    raise RetainedEvidenceImportError(code)


def _object(value: JsonValue) -> TypeIs[dict[str, JsonValue]]:
    return type(value) is dict and all(type(key) is str for key in value)


def _text(value: JsonValue, *, code: str, maximum: int = 4_096) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(
            ord(character) < _ASCII_CONTROL_LIMIT or ord(character) == _ASCII_DELETE
            for character in value
        )
    ):
        _fail(code)
    return value


def _fingerprint(value: JsonValue, *, code: str) -> str:
    text = _text(value, code=code, maximum=71)
    if _FINGERPRINT.fullmatch(text) is None:
        _fail(code)
    return text


def _integer(value: JsonValue, *, minimum: int, maximum: int, code: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(code)
    return value


def _number(value: JsonValue, *, code: str) -> int | float:
    if type(value) is int or type(value) is float:
        return value
    _fail(code)


def _endpoint_counts(value: JsonValue) -> dict[str, int]:
    """Return one exact non-empty terminal-count mapping."""
    if not _object(value) or not value:
        _fail("RETAINED_REPORT_INVALID")
    counts: dict[str, int] = {}
    for terminal, count in value.items():
        if not terminal or type(count) is not int or count < 1:
            _fail("RETAINED_REPORT_INVALID")
        counts[terminal] = count
    return counts


def _https_authority(value: JsonValue, *, code: str) -> str:
    text = _text(value, code=code)
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as error:
        raise RetainedEvidenceImportError(code) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        _fail(code)
    return parsed.hostname


def _assert_no_symlink_path(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            details = current.lstat()
        except OSError as error:
            msg = "RETAINED_OBJECT_READ_FAILED"
            raise RetainedEvidenceImportError(msg) from error
        if stat.S_ISLNK(details.st_mode):
            _fail("RETAINED_SYMLINK_REJECTED")


def _read_regular(path: Path, *, maximum: int, expected_length: int | None = None) -> bytes:
    _assert_no_symlink_path(path)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_size > maximum:
            _fail("RETAINED_OBJECT_INVALID")
        if expected_length is not None and details.st_size != expected_length:
            _fail("RETAINED_OBJECT_INVALID")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(_READ_CHUNK, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b"".join(chunks)
        if len(body) > maximum or (expected_length is not None and len(body) != expected_length):
            _fail("RETAINED_OBJECT_INVALID")
    except RetainedEvidenceImportError:
        raise
    except OSError as error:
        msg = "RETAINED_OBJECT_READ_FAILED"
        raise RetainedEvidenceImportError(msg) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return body


def _verify_regular_fingerprint(
    path: Path,
    *,
    expected_length: int,
    expected_fingerprint: str,
) -> None:
    """Stream one retained object once without duplicating it in memory."""
    _assert_no_symlink_path(path)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_size != expected_length:
            _fail("RETAINED_OBJECT_INVALID")
        digest = sha256()
        observed = 0
        while True:
            chunk = os.read(descriptor, _READ_CHUNK)
            if not chunk:
                break
            observed += len(chunk)
            if observed > expected_length:
                _fail("RETAINED_OBJECT_INVALID")
            digest.update(chunk)
        if observed != expected_length or f"sha256:{digest.hexdigest()}" != expected_fingerprint:
            _fail("RETAINED_OBJECT_INVALID")
    except RetainedEvidenceImportError:
        raise
    except OSError as error:
        msg = "RETAINED_OBJECT_READ_FAILED"
        raise RetainedEvidenceImportError(msg) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def _open_verified_regular(
    path: Path,
    *,
    expected_length: int,
    expected_fingerprint: str,
) -> Generator[BinaryIO]:
    """Inspect and hash one immutable regular file through the same descriptor."""
    _assert_no_symlink_path(path)
    descriptor: int | None = None
    stream: BinaryIO | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_length:
            _fail("RETAINED_OBJECT_INVALID")
        stream = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = None
        yield stream
        stream.seek(0)
        digest = sha256()
        observed = 0
        while True:
            chunk = stream.read(_READ_CHUNK)
            if not chunk:
                break
            observed += len(chunk)
            if observed > expected_length:
                _fail("RETAINED_OBJECT_INVALID")
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if (
            not stable
            or observed != expected_length
            or f"sha256:{digest.hexdigest()}" != expected_fingerprint
        ):
            _fail("RETAINED_OBJECT_INVALID")
    except RetainedEvidenceImportError:
        raise
    except (OSError, ValueError) as error:
        msg = "RETAINED_OBJECT_READ_FAILED"
        raise RetainedEvidenceImportError(msg) from error
    finally:
        if stream is not None:
            stream.close()
        if descriptor is not None:
            os.close(descriptor)


def _canonical_fingerprint(value: JsonValue) -> str:
    return f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"


def _procedure_rows(report: dict[str, JsonValue]) -> tuple[tuple[str, int, str], ...]:
    raw = report.get("source_procedures")
    if type(raw) is not list:
        _fail("RETAINED_REPORT_INVALID")
    rows: list[tuple[str, int, str]] = []
    for item in raw:
        if not _object(item) or frozenset(item) != _PROCEDURE_KEYS:
            _fail("RETAINED_REPORT_INVALID")
        rows.append(
            (
                _text(item.get("source_id"), code="RETAINED_REPORT_INVALID", maximum=127),
                _integer(
                    item.get("declared_member_count"),
                    minimum=0,
                    maximum=1_000_000,
                    code="RETAINED_REPORT_INVALID",
                ),
                _text(item.get("terminal_code"), code="RETAINED_REPORT_INVALID", maximum=127),
            )
        )
    return tuple(rows)


def _validate_closed_report(  # noqa: C901 - one closed two-family envelope.
    report: dict[str, JsonValue],
) -> str:
    """Validate the closed source-report envelope before any object or journal use."""
    source = report.get("source_family")
    if report.get("authority_provenance") != _AUTHORITY_PROVENANCE:
        _fail("RETAINED_REPORT_INVALID")
    if source == "HKEL":
        if (
            frozenset(report) != _HKEL_REPORT_KEYS
            or report.get("predecessor_attempt_id") is not None
            or report.get("change_state") != "FIRST_OBSERVATION"
            or report.get("result") != "COMPLETE"
            or _procedure_rows(report) != _HKEL_PROCEDURES
        ):
            _fail("RETAINED_REPORT_INVALID")
        return "HKEL_COMPLETE_1.0.0"
    if source != "JUDICIARY":
        _fail("RETAINED_REPORT_INVALID")
    schema = report.get("report_schema_version")
    if schema == "1.1.0":
        if frozenset(report) != _JUDICIARY_RETRY_REPORT_KEYS:
            _fail("RETAINED_REPORT_INVALID")
    elif schema == "1.2.0":
        if frozenset(report) != _JUDICIARY_CONTINUATION_REPORT_KEYS:
            _fail("RETAINED_REPORT_INVALID")
    else:
        _fail("RETAINED_REPORT_INVALID")
    predecessor = report.get("predecessor_attempt_id")
    if (
        (predecessor is not None and (type(predecessor) is not str or not predecessor))
        or report.get("change_state")
        != ("CHANGED_OBSERVED" if predecessor is not None else report.get("change_state"))
        or report.get("change_state") not in {"FIRST_OBSERVATION", "CHANGED_OBSERVED"}
        or report.get("result") not in {"SOURCE_OUTAGE", "SOURCE_CONTRACT_CHANGED"}
        or _procedure_rows(report) != _JUDICIARY_PROCEDURES
    ):
        _fail("RETAINED_REPORT_INVALID")
    if schema == "1.2.0" and predecessor is None:
        _fail("RETAINED_REPORT_INVALID")
    if schema == "1.1.0" and predecessor is not None:
        _fail("RETAINED_REPORT_INVALID")
    return f"JUDICIARY_{schema}"


def _derived_result(counts: dict[str, int], procedures: tuple[tuple[str, int, str], ...]) -> str:
    if counts.get("OUTAGE") or counts.get("EMPTY_RESPONSE"):
        return "SOURCE_OUTAGE"
    if counts.get("SOURCE_CONTRACT_CHANGED") or any(
        terminal == "SOURCE_CONTRACT_CHANGED" for _, _, terminal in procedures
    ):
        return "SOURCE_CONTRACT_CHANGED"
    if procedures and all(terminal == "COMPLETE" for _, _, terminal in procedures):
        return "COMPLETE"
    return "EVIDENCE_CAPTURED_INCOMPLETE"


def _retry_eligible(attempt: dict[str, JsonValue], policy_name: JsonValue) -> bool:
    """Return whether one retained physical result truthfully permits a retry."""
    requested_url = attempt.get("requested_url")
    normalized_failure = (
        attempt.get("status") == 0
        and attempt.get("byte_length") == 0
        and attempt.get("body_fingerprint")
        == "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        and attempt.get("media_type") == "application/octet-stream"
        and attempt.get("final_url") is None
        and attempt.get("redirect_rejected") is False
    )
    maintenance = (
        policy_name in {"JUDICIARY_TRANSPORT_ATTEMPTS_1.1.0", "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0"}
        and attempt.get("status") == _HTTP_OK
        and attempt.get("byte_length") == _MAINTENANCE_BODY_LENGTH
        and attempt.get("body_fingerprint")
        == "sha256:39f0a4df3dc88efbd6216caeaa03dc9fd1acbed9e73a477508e86f7e4229594f"
        and attempt.get("media_type") == "text/plain"
        and attempt.get("final_url") == requested_url
        and attempt.get("redirect_rejected") is False
    )
    byte_length = _integer(
        attempt.get("byte_length"),
        minimum=0,
        maximum=_MAX_OBJECT_BYTES,
        code="RETAINED_REPORT_INVALID",
    )
    max_bytes = _integer(
        attempt.get("max_bytes"),
        minimum=1,
        maximum=_MAX_OBJECT_BYTES,
        code="RETAINED_REPORT_INVALID",
    )
    server_error = (
        policy_name == "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0"
        and attempt.get("status") in {500, 502, 503, 504}
        and byte_length <= max_bytes
        and attempt.get("final_url") == requested_url
        and attempt.get("redirect_rejected") is False
    )
    return normalized_failure or maintenance or server_error


def _verify_transport_attempts(  # noqa: C901, PLR0912, PLR0915 - closed ledger verifier.
    report: dict[str, JsonValue],
    root: Path,
    *,
    verified_objects: set[tuple[str, int, str]],
) -> dict[str, str]:
    """Verify the physical ledger and return each finalized endpoint's actual URL."""
    raw_attempts = report.get("transport_attempts")
    raw_endpoints = report.get("endpoints")
    if type(raw_attempts) is not list or not raw_attempts or type(raw_endpoints) is not list:
        _fail("RETAINED_REPORT_INVALID")
    policy = report.get("execution_policy")
    policy_fingerprint = report.get("execution_policy_fingerprint")
    accounting = report.get("observation_accounting")
    if (
        not _object(policy)
        or not any(
            policy == expected_policy and policy_fingerprint == expected_fingerprint
            for expected_policy, expected_fingerprint in _JUDICIARY_POLICIES
        )
        or not _object(accounting)
        or frozenset(accounting) != _JUDICIARY_ACCOUNTING_KEYS
        or accounting.get("profile") != _JUDICIARY_OBSERVATION_PROFILE
        or accounting.get("profile_fingerprint") != _JUDICIARY_OBSERVATION_PROFILE_FINGERPRINT
        or accounting.get("stop_code") is not None
    ):
        _fail("RETAINED_REPORT_INVALID")
    prefix_count = 0
    if report.get("report_schema_version") == "1.2.0":
        binding = report.get("continuation_binding")
        if not _object(binding):
            _fail("RETAINED_REPORT_INVALID")
        prefix_count = _integer(
            binding.get("prefix_endpoint_count"),
            minimum=0,
            maximum=len(raw_endpoints),
            code="RETAINED_REPORT_INVALID",
        )
    segment: dict[str, dict[str, JsonValue]] = {}
    for raw_endpoint in raw_endpoints[prefix_count:]:
        if not _object(raw_endpoint):
            _fail("RETAINED_REPORT_INVALID")
        endpoint_id = _text(
            raw_endpoint.get("endpoint_id"), code="RETAINED_REPORT_INVALID", maximum=255
        )
        segment[endpoint_id] = raw_endpoint
    groups: list[list[dict[str, JsonValue]]] = []
    typed_attempts: list[dict[str, JsonValue]] = []
    for sequence, raw_attempt in enumerate(raw_attempts, start=1):
        if not _object(raw_attempt) or frozenset(raw_attempt) != _TRANSPORT_ATTEMPT_KEYS:
            _fail("RETAINED_REPORT_INVALID")
        if type(raw_attempt.get("sequence")) is not int or raw_attempt.get("sequence") != sequence:
            _fail("RETAINED_REPORT_INVALID")
        endpoint_id = _text(
            raw_attempt.get("endpoint_id"), code="RETAINED_REPORT_INVALID", maximum=255
        )
        typed_attempts.append(raw_attempt)
        body_length = _integer(
            raw_attempt.get("byte_length"),
            minimum=0,
            maximum=_MAX_OBJECT_BYTES,
            code="RETAINED_REPORT_INVALID",
        )
        fingerprint = _fingerprint(
            raw_attempt.get("body_fingerprint"), code="RETAINED_REPORT_INVALID"
        )
        object_key = _text(
            raw_attempt.get("object_key"), code="RETAINED_REPORT_INVALID", maximum=255
        )
        match = _OBJECT_KEY.fullmatch(object_key)
        start_elapsed = _number(
            raw_attempt.get("start_elapsed_seconds"), code="RETAINED_REPORT_INVALID"
        )
        max_bytes = _integer(
            raw_attempt.get("max_bytes"),
            minimum=1,
            maximum=_MAX_OBJECT_BYTES,
            code="RETAINED_REPORT_INVALID",
        )
        status = _integer(
            raw_attempt.get("status"),
            minimum=0,
            maximum=_HTTP_STATUS_LIMIT,
            code="RETAINED_REPORT_INVALID",
        )
        if (
            match is None
            or fingerprint != f"sha256:{match.group('digest')}"
            or raw_attempt.get("method") != "GET"
            or type(raw_attempt.get("redirect_rejected")) is not bool
            or type(raw_attempt.get("attempt_number")) is not int
            or not isfinite(start_elapsed)
        ):
            _fail("RETAINED_REPORT_INVALID")
        requested_authority = _https_authority(
            raw_attempt.get("requested_url"), code="RETAINED_REPORT_INVALID"
        )
        final_url = raw_attempt.get("final_url")
        if (
            final_url is not None
            and _https_authority(final_url, code="RETAINED_REPORT_INVALID") != requested_authority
        ):
            _fail("RETAINED_REPORT_INVALID")
        terminal = raw_attempt.get("terminal_code")
        exact_maintenance = (
            policy.get("name") != "JUDICIARY_TRANSPORT_ATTEMPTS_1.0.0"
            and raw_attempt.get("status") == _HTTP_OK
            and body_length == _MAINTENANCE_BODY_LENGTH
            and fingerprint
            == "sha256:39f0a4df3dc88efbd6216caeaa03dc9fd1acbed9e73a477508e86f7e4229594f"
            and raw_attempt.get("media_type") == "text/plain"
            and final_url == raw_attempt.get("requested_url")
            and raw_attempt.get("redirect_rejected") is False
        )
        if raw_attempt.get("redirect_rejected") is True:
            derived_terminal = "SOURCE_CONTRACT_CHANGED"
        elif body_length > max_bytes:
            derived_terminal = "TRUNCATED"
        elif exact_maintenance or not _HTTP_OK <= status < _HTTP_SUCCESS_LIMIT:
            derived_terminal = "OUTAGE"
        elif body_length == 0:
            derived_terminal = "EMPTY_RESPONSE"
        else:
            derived_terminal = "CAPTURED"
        if terminal != derived_terminal:
            _fail("RETAINED_REPORT_INVALID")
        key = (object_key, body_length, fingerprint)
        if key not in verified_objects:
            _verify_regular_fingerprint(
                root / object_key,
                expected_length=body_length,
                expected_fingerprint=fingerprint,
            )
            verified_objects.add(key)
        if not groups or groups[-1][-1]["endpoint_id"] != endpoint_id:
            groups.append([raw_attempt])
        else:
            groups[-1].append(raw_attempt)
    final_urls: dict[str, str] = {}
    observed_ids: list[str] = []
    for group in groups:
        endpoint_id = _text(
            group[0].get("endpoint_id"), code="RETAINED_REPORT_INVALID", maximum=255
        )
        if endpoint_id in final_urls or [item.get("attempt_number") for item in group] != list(
            range(1, len(group) + 1)
        ):
            _fail("RETAINED_REPORT_INVALID")
        if len(group) > _MAX_TRANSPORT_ATTEMPTS or any(
            item.get(field) != group[0].get(field)
            for item in group[1:]
            for field in ("endpoint_id", "endpoint_version", "max_bytes", "method", "requested_url")
        ):
            _fail("RETAINED_REPORT_INVALID")
        if any(not _retry_eligible(item, policy.get("name")) for item in group[:-1]):
            _fail("RETAINED_REPORT_INVALID")
        logical = segment.get(endpoint_id)
        if logical is None:
            _fail("RETAINED_REPORT_INVALID")
        final = group[-1]
        for field in (
            "body_fingerprint",
            "byte_length",
            "endpoint_id",
            "endpoint_version",
            "media_type",
            "method",
            "object_key",
            "requested_url",
            "status",
        ):
            if logical.get(field) != final.get(field):
                _fail("RETAINED_REPORT_INVALID")
        logical_terminal = logical.get("terminal_code")
        physical_terminal = final.get("terminal_code")
        if logical_terminal == "SOURCE_CONTRACT_CHANGED":
            if physical_terminal not in {"CAPTURED", "SOURCE_CONTRACT_CHANGED"}:
                _fail("RETAINED_REPORT_INVALID")
        elif logical_terminal != physical_terminal:
            _fail("RETAINED_REPORT_INVALID")
        actual_url = final.get("final_url")
        if type(actual_url) is not str:
            _fail("RETAINED_REPORT_INVALID")
        final_urls[endpoint_id] = actual_url
        observed_ids.append(endpoint_id)
    if observed_ids != [
        _text(item.get("endpoint_id"), code="RETAINED_REPORT_INVALID", maximum=255)
        for item in raw_endpoints[prefix_count:]
        if _object(item)
    ]:
        _fail("RETAINED_REPORT_INVALID")
    starts = len(typed_attempts)
    retained_bytes = sum(
        _integer(
            item.get("byte_length"),
            minimum=0,
            maximum=_MAX_OBJECT_BYTES,
            code="RETAINED_REPORT_INVALID",
        )
        for item in typed_attempts
    )
    elapsed = _number(accounting.get("elapsed_seconds"), code="RETAINED_REPORT_INVALID")
    last_start = _number(
        typed_attempts[-1].get("start_elapsed_seconds"), code="RETAINED_REPORT_INVALID"
    )
    if (
        accounting.get("request_starts") != starts
        or accounting.get("retained_response_bytes") != retained_bytes
        or accounting.get("rejected_response_bytes") != 0
        or elapsed < last_start
        or elapsed >= _JUDICIARY_OBSERVATION_PROFILE["elapsed_seconds_limit"]
        or starts > _JUDICIARY_OBSERVATION_PROFILE["request_start_limit"]
        or retained_bytes > _JUDICIARY_OBSERVATION_PROFILE["retained_response_byte_limit"]
        or typed_attempts[0].get("start_elapsed_seconds") != 0
        or any(
            _number(later.get("start_elapsed_seconds"), code="RETAINED_REPORT_INVALID")
            - _number(earlier.get("start_elapsed_seconds"), code="RETAINED_REPORT_INVALID")
            < _JUDICIARY_OBSERVATION_PROFILE["minimum_start_interval_seconds"]
            for earlier, later in pairwise(typed_attempts)
        )
    ):
        _fail("RETAINED_REPORT_INVALID")
    return final_urls


def _validate_continuation_binding(
    child: dict[str, JsonValue],
    parent: dict[str, JsonValue],
    *,
    parent_fingerprint: str,
) -> None:
    binding = child.get("continuation_binding")
    child_endpoints = child.get("endpoints")
    parent_endpoints = parent.get("endpoints")
    if (
        not _object(binding)
        or type(child_endpoints) is not list
        or type(parent_endpoints) is not list
    ):
        _fail("RETAINED_LINEAGE_INVALID")
    expected_keys = frozenset(
        {
            "continuation_authority_manifest_fingerprint",
            "continuation_execution_authorization_fingerprint",
            "next_request",
            "predecessor_attempt_id",
            "predecessor_observation_accounting",
            "predecessor_report_fingerprint",
            "prefix_endpoint_count",
            "prefix_endpoints_fingerprint",
        }
    )
    parent_capture = [
        item
        for item in parent_endpoints
        if _object(item) and item.get("terminal_code") == "CAPTURED"
    ]
    parent_accounting = (
        parent.get("cumulative_observation_accounting")
        if parent.get("report_schema_version") == "1.2.0"
        else parent.get("observation_accounting")
    )
    segment_accounting = child.get("observation_accounting")
    cumulative_accounting = child.get("cumulative_observation_accounting")
    prefix_count = len(parent_capture)
    attempts = child.get("transport_attempts")
    if type(attempts) is not list or not attempts or not _object(attempts[0]):
        _fail("RETAINED_LINEAGE_INVALID")
    first_attempt = attempts[0]
    expected_next: dict[str, JsonValue] = {
        key: first_attempt.get(key)
        for key in ("endpoint_id", "endpoint_version", "max_bytes", "method", "requested_url")
    }
    if (
        frozenset(binding) != expected_keys
        or child.get("predecessor_attempt_id") != parent.get("attempt_id")
        or binding.get("predecessor_attempt_id") != parent.get("attempt_id")
        or binding.get("predecessor_report_fingerprint") != parent_fingerprint
        or binding.get("continuation_authority_manifest_fingerprint")
        != child.get("authority_manifest_fingerprint")
        or binding.get("continuation_execution_authorization_fingerprint")
        != child.get("execution_authorization_fingerprint")
        or binding.get("prefix_endpoint_count") != prefix_count
        or child_endpoints[:prefix_count] != parent_capture
        or binding.get("prefix_endpoints_fingerprint")
        != _canonical_fingerprint(checked_json_value(parent_capture))
        or binding.get("next_request") != expected_next
        or binding.get("predecessor_observation_accounting") != parent_accounting
        or not _object(parent_accounting)
        or not _object(segment_accounting)
        or not _object(cumulative_accounting)
    ):
        _fail("RETAINED_LINEAGE_INVALID")
    expected_cumulative = dict(segment_accounting)
    for field in (
        "request_starts",
        "retained_response_bytes",
        "rejected_response_bytes",
        "elapsed_seconds",
    ):
        left = _number(parent_accounting.get(field), code="RETAINED_LINEAGE_INVALID")
        right = _number(segment_accounting.get(field), code="RETAINED_LINEAGE_INVALID")
        expected_cumulative[field] = left + right
    if cumulative_accounting != expected_cumulative:
        _fail("RETAINED_LINEAGE_INVALID")


def _verify_hkel_semantic_graph(  # noqa: C901 - bounded ZIP graph verifier.
    captured: tuple[_CapturedEndpoint, ...],
    root: Path,
    *,
    report_fingerprint: str,
) -> tuple[int, int, int, str]:
    """Derive HKeL member, bilingual-pair, and specification facts from evidence."""
    by_id = {endpoint.endpoint_id: endpoint for endpoint in captured}
    archive_projection: list[JsonValue] = []
    language_keys: dict[str, set[tuple[str, str]]] = {
        "en": set(),
        "zh-Hant": set(),
        "zh-Hans": set(),
    }
    member_count = 0
    for endpoint_id, expected_language in _HKEL_ARCHIVE_PROFILE:
        endpoint = by_id.get(endpoint_id)
        if endpoint is None or endpoint.media_type != "application/zip":
            _fail("RETAINED_HKEL_SEMANTIC_INVALID")
        seen_paths: set[str] = set()
        expanded = 0
        with _open_verified_regular(
            root / endpoint.object_key,
            expected_length=endpoint.body_length,
            expected_fingerprint=endpoint.content_fingerprint,
        ) as stream:
            try:
                with zipfile.ZipFile(stream) as archive:
                    infos = archive.infolist()
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                msg = "RETAINED_HKEL_SEMANTIC_INVALID"
                raise RetainedEvidenceImportError(msg) from error
        if not infos or len(infos) > _MAX_ARCHIVE_MEMBERS:
            _fail("RETAINED_HKEL_SEMANTIC_INVALID")
        for info in infos:
            canonical_path = info.filename.replace("\\", "/")
            parts = canonical_path.split("/")
            mode = (info.external_attr >> 16) & 0o170000
            if (
                info.is_dir()
                or not canonical_path
                or canonical_path.startswith("/")
                or any(part in {"", ".", ".."} for part in parts)
                or "\x00" in canonical_path
                or canonical_path in seen_paths
                or mode == stat.S_IFLNK
                or info.flag_bits & 0x1
                or info.file_size < 0
                or info.file_size > _MAX_ARCHIVE_MEMBER_BYTES
                or info.compress_size < 0
                or (
                    info.file_size > 0
                    and info.file_size > max(1, info.compress_size) * _MAX_COMPRESSION_RATIO
                )
            ):
                _fail("RETAINED_HKEL_SEMANTIC_INVALID")
            seen_paths.add(canonical_path)
            expanded += info.file_size
            if expanded > _MAX_ARCHIVE_EXPANDED_BYTES:
                _fail("RETAINED_HKEL_SEMANTIC_INVALID")
            match = _HKEL_XML_MEMBER.fullmatch(canonical_path)
            if match is not None:
                language = match.group("language")
                if language != expected_language:
                    _fail("RETAINED_HKEL_SEMANTIC_INVALID")
                identity = (match.group("chapter"), match.group("version"))
                if identity in language_keys[language]:
                    _fail("RETAINED_HKEL_SEMANTIC_INVALID")
                language_keys[language].add(identity)
            archive_projection.append(
                {
                    "archive_endpoint_id": endpoint_id,
                    "canonical_path": canonical_path,
                    "compressed_byte_length": info.compress_size,
                    "crc32": info.CRC,
                    "byte_length": info.file_size,
                }
            )
        member_count += len(infos)
    if not (language_keys["en"] == language_keys["zh-Hant"] == language_keys["zh-Hans"]):
        _fail("RETAINED_HKEL_SEMANTIC_INVALID")
    pair_count = len(language_keys["en"])
    specifications = tuple(
        by_id.get(endpoint_id) for endpoint_id in _HKEL_SPECIFICATION_ENDPOINT_IDS
    )
    if any(
        endpoint is None or endpoint.media_type != expected_media_type
        for endpoint, expected_media_type in zip(
            specifications,
            _HKEL_SPECIFICATION_MEDIA_TYPES,
            strict=True,
        )
    ):
        _fail("RETAINED_HKEL_SEMANTIC_INVALID")
    specification_projection: list[JsonValue] = [
        {
            "endpoint_id": endpoint.endpoint_id,
            "fingerprint": endpoint.content_fingerprint,
            "media_type": endpoint.media_type,
        }
        for endpoint in specifications
        if endpoint is not None
    ]
    proof: dict[str, JsonValue] = {
        "archive_members": archive_projection,
        "bilingual_pair_count": pair_count,
        "publication_specifications": specification_projection,
        "report_fingerprint": report_fingerprint,
        "verifier": "ASKLEGAL_HKEL_RETAINED_GRAPH_1.0.0",
    }
    return member_count, pair_count, len(specification_projection), _canonical_fingerprint(proof)


def _load_and_verify_judiciary_lineage(  # noqa: C901, PLR0912, PLR0915 - closed chain verifier.
    current: dict[str, JsonValue],
    reference: RetainedReportReference,
    root: Path,
    *,
    verified_objects: set[tuple[str, int, str]],
) -> tuple[dict[str, str], str]:
    """Verify the exact predecessor chain and physical URL provenance recursively."""
    pins = reference.lineage_report_pins
    schema = current.get("report_schema_version")
    if schema == "1.1.0":
        if pins:
            _fail("RETAINED_LINEAGE_INVALID")
        reports = (current,)
        fingerprints = (reference.expected_report_fingerprint,)
    else:
        if not pins or current.get("predecessor_attempt_id") != pins[-1].attempt_id:
            _fail("RETAINED_LINEAGE_INVALID")
        loaded: list[dict[str, JsonValue]] = []
        loaded_fingerprints: list[str] = []
        attempts_root = reference.report_path.parent.parent
        previous_attempt: str | None = None
        for pin in pins:
            if pin.predecessor_attempt_id != previous_attempt:
                _fail("RETAINED_LINEAGE_INVALID")
            report_path = attempts_root / pin.attempt_id / "report.json"
            raw = _read_regular(report_path, maximum=_MAX_REPORT_BYTES)
            fingerprint = f"sha256:{sha256(raw).hexdigest()}"
            if fingerprint != pin.expected_report_fingerprint:
                _fail("RETAINED_LINEAGE_INVALID")
            try:
                parsed = parse_json_bytes(raw, max_bytes=len(raw))
            except (TypeError, ValueError) as error:
                msg = "RETAINED_LINEAGE_INVALID"
                raise RetainedEvidenceImportError(msg) from error
            if (
                not _object(parsed)
                or parsed.get("attempt_id") != pin.attempt_id
                or parsed.get("predecessor_attempt_id") != pin.predecessor_attempt_id
            ):
                _fail("RETAINED_LINEAGE_INVALID")
            _validate_closed_report(parsed)
            loaded.append(parsed)
            loaded_fingerprints.append(fingerprint)
            previous_attempt = pin.attempt_id
        reports = (*loaded, current)
        fingerprints = (*loaded_fingerprints, reference.expected_report_fingerprint)
        for parent, child, parent_fingerprint in zip(
            reports[:-1],
            reports[1:],
            fingerprints[:-1],
            strict=True,
        ):
            _validate_continuation_binding(
                child,
                parent,
                parent_fingerprint=parent_fingerprint,
            )
    final_urls: dict[str, str] = {}
    lineage_projection: list[JsonValue] = []
    for report, report_fingerprint in zip(reports, fingerprints, strict=True):
        endpoints = report.get("endpoints")
        if type(endpoints) is not list:
            _fail("RETAINED_LINEAGE_INVALID")
        counts: dict[str, int] = {}
        for raw_endpoint in endpoints:
            selected, _body_length, terminal = _endpoint(
                raw_endpoint,
                root,
                verified_objects=verified_objects,
            )
            counts[terminal] = counts.get(terminal, 0) + 1
            del selected
        if _endpoint_counts(report.get("endpoint_counts")) != counts or report.get(
            "result"
        ) != _derived_result(counts, _procedure_rows(report)):
            _fail("RETAINED_LINEAGE_INVALID")
        final_urls.update(
            _verify_transport_attempts(
                report,
                root,
                verified_objects=verified_objects,
            )
        )
        lineage_projection.append(
            {
                "attempt_id": report.get("attempt_id"),
                "predecessor_attempt_id": report.get("predecessor_attempt_id"),
                "report_fingerprint": report_fingerprint,
                "endpoint_count": len(endpoints),
                "captured_endpoint_count": counts.get("CAPTURED", 0),
            }
        )
    current_endpoints = current.get("endpoints")
    if type(current_endpoints) is not list or any(
        _object(endpoint)
        and endpoint.get("terminal_code") == "CAPTURED"
        and endpoint.get("endpoint_id") not in final_urls
        for endpoint in current_endpoints
    ):
        _fail("RETAINED_LINEAGE_INVALID")
    proof: dict[str, JsonValue] = {
        "lineage": lineage_projection,
        "physical_endpoint_final_urls": dict(sorted(final_urls.items())),
        "verifier": "ASKLEGAL_JUDICIARY_RETAINED_LINEAGE_1.0.0",
    }
    return final_urls, _canonical_fingerprint(proof)


def _endpoint(
    value: JsonValue,
    root: Path,
    *,
    verified_objects: set[tuple[str, int, str]] | None = None,
    defer_object_verification: bool = False,
) -> tuple[_CapturedEndpoint | None, int, str]:
    if not _object(value):
        _fail("RETAINED_REPORT_INVALID")
    extra_keys: frozenset[str] = (
        frozenset({"comparison_fingerprint"}) if "comparison_fingerprint" in value else frozenset()
    )
    allowed_keys = _ENDPOINT_KEYS | extra_keys
    if frozenset(value) != allowed_keys:
        _fail("RETAINED_REPORT_INVALID")
    if "comparison_fingerprint" in value:
        _fingerprint(value.get("comparison_fingerprint"), code="RETAINED_REPORT_INVALID")
    endpoint_id = _text(value.get("endpoint_id"), code="RETAINED_REPORT_INVALID", maximum=255)
    endpoint_version = _text(
        value.get("endpoint_version"), code="RETAINED_REPORT_INVALID", maximum=127
    )
    media_type = _text(value.get("media_type"), code="RETAINED_REPORT_INVALID", maximum=127)
    requested_url = _text(value.get("requested_url"), code="RETAINED_REPORT_INVALID")
    _https_authority(requested_url, code="RETAINED_REPORT_INVALID")
    if value.get("method") != "GET":
        _fail("RETAINED_REPORT_INVALID")
    status = _integer(value.get("status"), minimum=100, maximum=599, code="RETAINED_REPORT_INVALID")
    body_length = _integer(
        value.get("byte_length"),
        minimum=1,
        maximum=_MAX_OBJECT_BYTES,
        code="RETAINED_REPORT_INVALID",
    )
    content_fingerprint = _fingerprint(
        value.get("body_fingerprint"), code="RETAINED_REPORT_INVALID"
    )
    object_key = _text(value.get("object_key"), code="RETAINED_REPORT_INVALID", maximum=255)
    match = _OBJECT_KEY.fullmatch(object_key)
    if match is None or content_fingerprint != f"sha256:{match.group('digest')}":
        _fail("RETAINED_REPORT_INVALID")
    verified_key = (object_key, body_length, content_fingerprint)
    if not defer_object_verification and (
        verified_objects is None or verified_key not in verified_objects
    ):
        _verify_regular_fingerprint(
            root / object_key,
            expected_length=body_length,
            expected_fingerprint=content_fingerprint,
        )
        if verified_objects is not None:
            verified_objects.add(verified_key)
    terminal_code = _text(value.get("terminal_code"), code="RETAINED_REPORT_INVALID", maximum=127)
    if terminal_code != "CAPTURED":
        return None, body_length, terminal_code
    return (
        _CapturedEndpoint(
            value,
            endpoint_id,
            endpoint_version,
            media_type,
            requested_url,
            status,
            object_key,
            body_length,
            content_fingerprint,
        ),
        body_length,
        terminal_code,
    )


def _default_projection(
    reference: RetainedReportReference,
    attempt_id: str,
    cutoff: str,
) -> Callable[[JsonValue], WorkItemIdentity]:
    def project(value: JsonValue) -> WorkItemIdentity:
        if not _object(value):
            _fail("RETAINED_PROJECTION_INVALID")
        endpoint_id = _text(
            value.get("endpoint_id"), code="RETAINED_PROJECTION_INVALID", maximum=255
        )
        return WorkItemIdentity.issue(
            source_family=reference.product_family,
            source_role=(
                "HK_CASE_RETAINED_EVIDENCE"
                if reference.product_family == "CASES"
                else "HK_LEGISLATION_RETAINED_EVIDENCE"
            ),
            cycle_id=reference.cycle_id,
            observation_cutoff=cutoff,
            procedure_version=_text(
                value.get("endpoint_version"), code="RETAINED_PROJECTION_INVALID", maximum=127
            ),
            locator=_text(value.get("requested_url"), code="RETAINED_PROJECTION_INVALID"),
            stage="RETAINED_IMPORT",
            parent_id=f"{attempt_id}:{endpoint_id}",
            media_type=_text(value.get("media_type"), code="RETAINED_PROJECTION_INVALID"),
            max_bytes=_integer(
                value.get("byte_length"),
                minimum=1,
                maximum=1_073_741_824,
                code="RETAINED_PROJECTION_INVALID",
            ),
        )

    return project


def _cycle_epoch_microseconds(cutoff: str) -> int:
    try:
        parsed = datetime.fromisoformat(cutoff)
    except ValueError as error:
        msg = "RETAINED_REPORT_INVALID"
        raise RetainedEvidenceImportError(msg) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("RETAINED_REPORT_INVALID")
    elapsed = parsed.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return elapsed.days * 86_400_000_000 + elapsed.seconds * 1_000_000 + elapsed.microseconds


def import_retained_report(  # noqa: C901, PLR0912, PLR0915 - one closed import transaction.
    cycle_state_root: Path,
    reference: RetainedReportReference,
    *,
    projection: WorkItemProjection | None = None,
    transport: object | None = None,
) -> RetainedImportReceipt:
    """Validate a complete retained graph, then append only offline-import facts."""
    del transport
    if type(reference) is not RetainedReportReference:
        _fail("RETAINED_REFERENCE_INVALID")
    report_raw = _read_regular(reference.report_path, maximum=_MAX_REPORT_BYTES)
    report_fingerprint = f"sha256:{sha256(report_raw).hexdigest()}"
    if report_fingerprint != reference.expected_report_fingerprint:
        _fail("RETAINED_REPORT_FINGERPRINT_MISMATCH")
    try:
        parsed = parse_json_bytes(report_raw, max_bytes=len(report_raw))
        # Historical source-execution reports preserve integral policy values as
        # JSON floats (for example ``259200.0``), while the shared canonicalizer
        # normalizes them to integers. The caller-bound raw SHA-256 is therefore
        # the byte authority; parsing must still yield an exact JSON object.
        if not _object(parsed):
            _fail("RETAINED_REPORT_INVALID")
    except (TypeError, ValueError) as error:
        if isinstance(error, RetainedEvidenceImportError):
            raise
        msg = "RETAINED_REPORT_INVALID"
        raise RetainedEvidenceImportError(msg) from error
    report = parsed
    _validate_closed_report(report)
    attempt_id = _text(report.get("attempt_id"), code="RETAINED_REPORT_INVALID", maximum=255)
    cutoff = _text(report.get("observation_cutoff"), code="RETAINED_REPORT_INVALID", maximum=40)
    authority = _fingerprint(
        report.get("authority_manifest_fingerprint"), code="RETAINED_REPORT_INVALID"
    )
    execution = _fingerprint(
        report.get("execution_authorization_fingerprint"), code="RETAINED_REPORT_INVALID"
    )
    expected_source = "HKEL" if reference.product_family == "LEGISLATION" else "JUDICIARY"
    if (
        attempt_id != reference.report_path.parent.name
        or authority != reference.expected_authority_manifest_fingerprint
        or execution != reference.expected_execution_authorization_fingerprint
        or report.get("source_family") != expected_source
        or report.get("result") != reference.expected_source_result
        or report.get("readback_verified") is not True
    ):
        _fail("RETAINED_BINDING_INVALID")
    raw_endpoints = report.get("endpoints")
    if type(raw_endpoints) is not list or not raw_endpoints:
        _fail("RETAINED_REPORT_INVALID")
    counts = _endpoint_counts(report.get("endpoint_counts"))
    root = reference.report_path.parents[2]
    verified_objects: set[tuple[str, int, str]] = set()
    physical_final_urls: dict[str, str] = {}
    semantic_proof_fingerprint: str
    if reference.product_family == "CASES":
        physical_final_urls, semantic_proof_fingerprint = _load_and_verify_judiciary_lineage(
            report,
            reference,
            root,
            verified_objects=verified_objects,
        )
    else:
        if reference.lineage_report_pins:
            _fail("RETAINED_LINEAGE_INVALID")
        semantic_proof_fingerprint = ""
    captured: list[_CapturedEndpoint] = []
    actual_counts: dict[str, int] = {}
    unique_bytes: dict[str, int] = {}
    seen_endpoint_ids: set[str] = set()
    for raw_endpoint in raw_endpoints:
        selected, body_length, terminal_code = _endpoint(
            raw_endpoint,
            root,
            verified_objects=verified_objects,
            defer_object_verification=(
                reference.product_family == "LEGISLATION"
                and _object(raw_endpoint)
                and raw_endpoint.get("media_type") == "application/zip"
            ),
        )
        actual_counts[terminal_code] = actual_counts.get(terminal_code, 0) + 1
        if selected is None:
            continue
        if selected.endpoint_id in seen_endpoint_ids:
            _fail("RETAINED_IDENTITY_COLLISION")
        seen_endpoint_ids.add(selected.endpoint_id)
        unique_bytes.setdefault(selected.object_key, body_length)
        captured.append(selected)
    if (
        counts != actual_counts
        or not captured
        or report.get("result") != _derived_result(actual_counts, _procedure_rows(report))
    ):
        _fail("RETAINED_REPORT_INVALID")
    if len(captured) != reference.expected_imported_item_count:
        _fail("RETAINED_REPORT_INVALID")
    last_listing: tuple[int, int] | None = None
    for endpoint in captured:
        match = _LISTING.fullmatch(endpoint.endpoint_id)
        if match is None:
            continue
        listing = (int(match.group("year")), int(match.group("page")))
        if last_listing is None or listing > last_listing:
            last_listing = listing
    if last_listing != reference.expected_last_listing:
        _fail("RETAINED_REPORT_INVALID")
    archive_members: int | None = None
    archive_pairs: int | None = None
    publication_specifications: int | None = None
    if reference.product_family == "LEGISLATION":
        if any(endpoint.status != _HTTP_OK for endpoint in captured):
            _fail("RETAINED_HKEL_SEMANTIC_INVALID")
        (
            archive_members,
            archive_pairs,
            publication_specifications,
            semantic_proof_fingerprint,
        ) = _verify_hkel_semantic_graph(
            tuple(captured),
            root,
            report_fingerprint=report_fingerprint,
        )
        if (
            archive_members != _EXPECTED_HKEL_ARCHIVE_MEMBERS
            or archive_pairs != _EXPECTED_HKEL_BILINGUAL_PAIRS
            or publication_specifications != _EXPECTED_HKEL_PUBLICATION_SPECIFICATIONS
        ):
            _fail("RETAINED_HKEL_SEMANTIC_INVALID")
        physical_final_urls = {
            endpoint.endpoint_id: endpoint.requested_url for endpoint in captured
        }
    selected_projection = projection or _default_projection(reference, attempt_id, cutoff)
    projected: list[tuple[WorkItemIdentity, _CapturedEndpoint]] = []
    work_item_ids: set[str] = set()
    for endpoint in captured:
        try:
            item = selected_projection(endpoint.raw)
        except RetainedEvidenceImportError:
            raise
        except (AttributeError, TypeError, ValueError) as error:
            msg = "RETAINED_PROJECTION_INVALID"
            raise RetainedEvidenceImportError(msg) from error
        if (
            type(item) is not WorkItemIdentity
            or item.cycle_id != reference.cycle_id
            or item.source_family != reference.product_family
            or item.observation_cutoff != cutoff
            or item.procedure_version != endpoint.endpoint_version
            or item.locator != endpoint.requested_url
            or item.media_type != endpoint.media_type
            or item.max_bytes != endpoint.body_length
        ):
            _fail("RETAINED_PROJECTION_INVALID")
        if item.work_item_id in work_item_ids:
            _fail("RETAINED_IDENTITY_COLLISION")
        work_item_ids.add(item.work_item_id)
        projected.append((item, endpoint))
    epoch = _cycle_epoch_microseconds(cutoff)
    profile = CycleSafetyProfilePayload(
        schema_id="asklegal.acquisition-cycle-safety-profile",
        schema_version="1.0.0",
        maximum_starts=0,
        maximum_retained_bytes=0,
        maximum_elapsed_seconds=0,
        maximum_redirects=0,
        per_host_limit=4,
        minimum_start_interval_ns=0,
        maximum_attempts_per_item=1,
        maximum_redirects_per_start=0,
        cycle_started_at_epoch_us=epoch,
    )
    additions: list[tuple[WorkItemIdentity, JournalTransition, object]] = [
        (item, JournalTransition.DISCOVERED, DiscoveredPayload(epoch)) for item, _ in projected
    ]
    additions.append((projected[0][0], JournalTransition.CYCLE_SAFETY_PROFILE_BOUND, profile))
    additions.extend(
        (
            item,
            JournalTransition.IMPORTED_CAPTURE_VERIFIED,
            ImportedCaptureVerifiedPayload(
                source_attempt_id=attempt_id,
                source_report_fingerprint=report_fingerprint,
                authority_manifest_fingerprint=authority,
                execution_authorization_fingerprint=execution,
                status=endpoint.status,
                media_type=endpoint.media_type,
                final_url=physical_final_urls[endpoint.endpoint_id],
                body_length=endpoint.body_length,
                content_fingerprint=endpoint.content_fingerprint,
                object_ref=endpoint.object_key,
                read_back_verified=True,
            ),
        )
        for item, endpoint in projected
    )
    expected = tuple(additions)
    try:
        with LocalAcquisitionJournal(cycle_state_root, reference.cycle_id) as journal:
            existing = journal.replay()
            if len(existing) > len(expected):
                _fail("RETAINED_JOURNAL_MISMATCH")
            for entry, addition in zip(existing, expected, strict=False):
                item, transition, payload = addition
                if (
                    entry.work_item != item
                    or entry.transition is not transition
                    or entry.payload != payload
                ):
                    _fail("RETAINED_JOURNAL_MISMATCH")
            if len(existing) < len(expected):
                journal.append_many(expected[len(existing) :])
            checkpoint = journal.write_checkpoint()
    except AcquisitionJournalError as error:
        msg = "RETAINED_JOURNAL_MISMATCH"
        raise RetainedEvidenceImportError(msg) from error
    lineage_body = {
        "cycle_id": reference.cycle_id,
        "source_attempt_id": attempt_id,
        "items": [
            {
                "body_length": endpoint.body_length,
                "content_fingerprint": endpoint.content_fingerprint,
                "object_ref": endpoint.object_key,
                "work_item": item.to_json(),
            }
            for item, endpoint in sorted(projected, key=lambda value: value[0].work_item_id)
        ],
    }
    work_item_lineage_fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(lineage_body))).hexdigest()}"
    )
    checkpoint_body = {
        "cycle_id": reference.cycle_id,
        "items": [item.to_json() for item in checkpoint.items],
    }
    imported_checkpoint_fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(checkpoint_body))).hexdigest()}"
    )
    return _issue_receipt(
        RetainedImportReceipt(
            source_family=reference.product_family,
            source_report_fingerprint=report_fingerprint,
            imported_item_count=len(projected),
            reused_object_bytes=sum(unique_bytes.values()),
            journal_head_fingerprint=checkpoint.journal_head_fingerprint,
            archive_members=archive_members,
            archive_pairs=archive_pairs,
            publication_specifications=publication_specifications,
            semantic_proof_fingerprint=semantic_proof_fingerprint,
            last_listing=last_listing,
            cycle_id=reference.cycle_id,
            source_attempt_id=attempt_id,
            imported_work_item_ids=tuple(sorted(work_item_ids)),
            work_item_lineage_fingerprint=work_item_lineage_fingerprint,
            imported_checkpoint_fingerprint=imported_checkpoint_fingerprint,
            imported_object_references=tuple(
                RetainedImportedObjectReference(
                    endpoint.endpoint_id,
                    item.work_item_id,
                    endpoint.media_type,
                    physical_final_urls[endpoint.endpoint_id],
                    endpoint.body_length,
                    endpoint.content_fingerprint,
                    endpoint.object_key,
                    authority,
                    execution,
                )
                for item, endpoint in sorted(projected, key=lambda value: value[1].endpoint_id)
            ),
        )
    )


def import_known_v1_retained_evidence(
    cycle_state_root: Path,
    *,
    source_admission_root: Path | None = None,
    transport: object | None = None,
) -> KnownV1RetainedImportReceipts:
    """Import the exact frozen HKeL and Judiciary baselines selected for V1."""
    root = source_admission_root or (Path.cwd() / "var" / "hk-v1" / "source-admission")
    if type(root) is not type(Path()) or not root.is_absolute():
        _fail("RETAINED_REFERENCE_INVALID")
    hkel = import_retained_report(
        cycle_state_root,
        RetainedReportReference(
            report_path=(
                root
                / "hkel-attempt-b"
                / "attempts"
                / "hkel-live-baseline-basic-law20-20260828b"
                / "report.json"
            ),
            expected_report_fingerprint=(
                "sha256:5f6b8625fd7c0ff4093d96b7a2f72e4ededc9b8af54b6c1add02b95e81549b50"
            ),
            expected_authority_manifest_fingerprint=(
                "sha256:ef67b8dd0a6f00d23ca4ec1e8ac157d3fdd6423bf88dbd4f6b4346c0df296c66"
            ),
            expected_execution_authorization_fingerprint=(
                "sha256:4d43ac6c66e938777942d4d09e22de05542d065a39b34f6c2c2a4c48ced9ad88"
            ),
            product_family="LEGISLATION",
            cycle_id="cyc_20260903_import_hkel",
            expected_source_result="COMPLETE",
            expected_imported_item_count=56,
        ),
        transport=transport,
    )
    judiciary = import_retained_report(
        cycle_state_root,
        RetainedReportReference(
            report_path=(
                root
                / "judiciary-attempt-p"
                / "attempts"
                / "judiciary-live-baseline-20260831w"
                / "report.json"
            ),
            expected_report_fingerprint=(
                "sha256:83c98ee3b139d61b8c790772b7b4408fa5aac63dc891fc1bda3572085c84b92a"
            ),
            expected_authority_manifest_fingerprint=(
                "sha256:19add305980db4b4b18b2baffbc3550dea1f763d180024825a7ac882894e63e5"
            ),
            expected_execution_authorization_fingerprint=(
                "sha256:7f3510cf6e90bb312af3b93ea5feb4cc97a7dfd56e1a8e6d0be8b1dc0010acea"
            ),
            product_family="CASES",
            cycle_id="cyc_20260903_import_cases",
            expected_source_result="SOURCE_OUTAGE",
            expected_imported_item_count=5_590,
            lineage_report_pins=(
                RetainedLineageReportPin(
                    "judiciary-live-baseline-20260831p",
                    "sha256:e8cc1c5e11a4c25f7a23e89b8889761c14aca240f5f717dc6f29966a3a96e918",
                    None,
                ),
                RetainedLineageReportPin(
                    "judiciary-live-baseline-20260831q",
                    "sha256:7e5f8d86a289f6ca0581e869a51b6e89831bdf42896b50d822c7c87eec2883c9",
                    "judiciary-live-baseline-20260831p",
                ),
                RetainedLineageReportPin(
                    "judiciary-live-baseline-20260831r",
                    "sha256:ab67805a5bde97f6f0903e452c38b9e2e95f822516445a36e1ce93d9347016fd",
                    "judiciary-live-baseline-20260831q",
                ),
                RetainedLineageReportPin(
                    "judiciary-live-baseline-20260831s",
                    "sha256:6b9345452d0b75f16b6393e98b91bf61422a5f2f9e4c835a15c275934a1dfe66",
                    "judiciary-live-baseline-20260831r",
                ),
                RetainedLineageReportPin(
                    "judiciary-live-baseline-20260831t",
                    "sha256:32e9ebb809a22688fcab9877022303ee6f02139038dc5d84f81e1e0b9516e2b5",
                    "judiciary-live-baseline-20260831s",
                ),
                RetainedLineageReportPin(
                    "judiciary-live-baseline-20260831u",
                    "sha256:20f6413f3879dedbb7be276f82427313e898e5a8be7e6b25405fbf3cfe2d0ca3",
                    "judiciary-live-baseline-20260831t",
                ),
                RetainedLineageReportPin(
                    "judiciary-live-baseline-20260831v",
                    "sha256:c21bc686475981994952d16c99e36693dbd745ede92bf0670d6fa86cd62dd290",
                    "judiciary-live-baseline-20260831u",
                ),
            ),
            expected_last_listing=(2011, 363),
        ),
        transport=transport,
    )
    return KnownV1RetainedImportReceipts(hkel=hkel, judiciary=judiciary)
