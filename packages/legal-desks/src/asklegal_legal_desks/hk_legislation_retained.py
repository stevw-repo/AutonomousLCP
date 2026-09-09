"""Read-only indexer for one frozen complete HKeL source observation.

This module stops before legal interpretation.  It validates the retained
Plan 2 report and object closure, treats every ZIP as hostile, checks inert XML
well-formedness, and emits only detached source/member facts for a later Plan 3
adapter.  It grants no current-law, release, package, or serving authority.
"""

from __future__ import annotations

import re
import stat
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import BinaryIO, Never, Protocol, TypeIs

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_ATTEMPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,159}$")
_OBSERVATION_CUTOFF = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_OBJECT_KEY = re.compile(r"^objects/[0-9a-f]{64}\.bin$")
_MEMBER_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")
_XML_MEMBER = re.compile(
    r"^(?P<chapter>(?:cap_[0-9A-Z]+|A[0-9A-Z]+))_"
    r"(?P<language>en|zh-Hant|zh-Hans)_c/"
    r"(?P=chapter)_(?P<version>[0-9]{14}|-{14})_"
    r"(?P=language)_c\.xml$"
)
_XML_DECLARATION_ENCODING = re.compile(
    r'^\ufeff?<\?xml\b[^>]*\bencoding\s*=\s*["\'](?P<encoding>[^"\']+)["\']',
    re.IGNORECASE,
)
_REPORT_FIELDS = frozenset(
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
_ENDPOINT_FIELDS = frozenset(
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
_PROCEDURE_FIELDS = frozenset({"declared_member_count", "source_id", "terminal_code"})
_EXPECTED_PROCEDURES = (
    ("HK-LEG-BASIC-LAW-PORTAL", 20),
    ("HK-LEG-HKEL-CURRENT-DATA", 12),
    ("HK-LEG-HKEL-CURRENT-INVENTORY", 3157),
    ("HK-LEG-HKEL-EDITORIAL-RECORDS", 2),
    ("HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS", 7),
)
_ARCHIVE_PROFILE = (
    ("sep_00000000000000000000000000000000000000000000000a", "en"),
    ("sep_00000000000000000000000000000000000000000000000b", "en"),
    ("sep_00000000000000000000000000000000000000000000000c", "en"),
    ("sep_00000000000000000000000000000000000000000000000d", "en"),
    ("sep_00000000000000000000000000000000000000000000000e", "zh-Hant"),
    ("sep_00000000000000000000000000000000000000000000000f", "zh-Hant"),
    ("sep_000000000000000000000000000000000000000000000010", "zh-Hant"),
    ("sep_000000000000000000000000000000000000000000000011", "zh-Hant"),
    ("sep_000000000000000000000000000000000000000000000012", "zh-Hans"),
    ("sep_000000000000000000000000000000000000000000000013", "zh-Hans"),
    ("sep_000000000000000000000000000000000000000000000014", "zh-Hans"),
    ("sep_000000000000000000000000000000000000000000000015", "zh-Hans"),
)
_ARCHIVE_LANGUAGE = dict(_ARCHIVE_PROFILE)
_SPECIFICATION_ENDPOINT_IDS = (
    "sep_000000000000000000000000000000000000000000000035",
    "sep_000000000000000000000000000000000000000000000036",
    "sep_000000000000000000000000000000000000000000000037",
    "sep_000000000000000000000000000000000000000000000038",
    "sep_000000000000000000000000000000000000000000000039",
    "sep_00000000000000000000000000000000000000000000003a",
    "sep_000000000000000000000000000000000000000000000051",
)
_SPECIFICATION_MEDIA_TYPES = {
    _SPECIFICATION_ENDPOINT_IDS[0]: "application/xml",
    _SPECIFICATION_ENDPOINT_IDS[1]: "application/pdf",
    _SPECIFICATION_ENDPOINT_IDS[2]: "application/pdf",
    _SPECIFICATION_ENDPOINT_IDS[3]: "application/pdf",
    _SPECIFICATION_ENDPOINT_IDS[4]: "text/html",
    _SPECIFICATION_ENDPOINT_IDS[5]: "text/html",
    _SPECIFICATION_ENDPOINT_IDS[6]: "text/html",
}
_XSD_ENDPOINT_ID = _SPECIFICATION_ENDPOINT_IDS[0]
_MAX_REPORT_BYTES = 1 << 20
_MAX_XSD_BYTES = 16 << 20
_MAX_ARCHIVE_MEMBERS = 4096
_MAX_ARCHIVE_MEMBER_BYTES = 32 << 20
_MAX_ARCHIVE_EXPANDED_BYTES = 1 << 30
_MAX_COMPRESSION_RATIO = 100
_EXPECTED_CAPTURED_ENDPOINTS = 56
_EXPECTED_CURRENT_INSTRUMENTS = 3157
_HTTP_OK = 200
_READ_CHUNK = 1 << 20
_XINCLUDE_NAMESPACE = "{http://www.w3.org/2001/XInclude}"


class HkelRetainedEvidenceErrorCode(StrEnum):
    """Closed failures at the retained HKeL archive boundary."""

    REFERENCE_INVALID = "HKEL_RETAINED_REFERENCE_INVALID"
    REPORT_READ_FAILED = "HKEL_RETAINED_REPORT_READ_FAILED"
    REPORT_INVALID = "HKEL_RETAINED_REPORT_INVALID"
    REPORT_NOT_COMPLETE = "HKEL_RETAINED_REPORT_NOT_COMPLETE"
    OBJECT_READ_FAILED = "HKEL_RETAINED_OBJECT_READ_FAILED"
    ARCHIVE_INVALID = "HKEL_RETAINED_ARCHIVE_INVALID"
    ARCHIVE_UNSAFE_MEMBER = "HKEL_RETAINED_ARCHIVE_UNSAFE_MEMBER"
    ARCHIVE_MEMBER_COLLISION = "HKEL_RETAINED_ARCHIVE_MEMBER_COLLISION"
    ARCHIVE_LIMIT_EXCEEDED = "HKEL_RETAINED_ARCHIVE_LIMIT_EXCEEDED"
    XML_INVALID = "HKEL_RETAINED_XML_INVALID"
    BILINGUAL_PAIRING_INVALID = "HKEL_RETAINED_BILINGUAL_PAIRING_INVALID"
    SPECIFICATION_BINDING_INVALID = "HKEL_RETAINED_SPECIFICATION_BINDING_INVALID"


class HkelRetainedEvidenceError(ValueError):
    """One normalized rejection without a raw reader, ZIP, or parser failure."""

    code: HkelRetainedEvidenceErrorCode

    def __init__(self, code: HkelRetainedEvidenceErrorCode) -> None:
        """Create one stable closed rejection."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HkelRetainedObjectReference:
    """One content-addressed retained object without a filesystem path."""

    logical_key: str
    fingerprint: str
    byte_length: int


@dataclass(frozen=True, slots=True)
class HkelRetainedAttemptReference:
    """Exact caller-selected report identity for one immutable attempt."""

    attempt_id: str
    observation_cutoff: str
    report: HkelRetainedObjectReference


@dataclass(frozen=True, slots=True)
class HkelRetainedEndpointObject:
    """Detached report-to-object binding for one captured endpoint."""

    endpoint_id: str
    endpoint_version: str
    media_type: str
    reference: HkelRetainedObjectReference


@dataclass(frozen=True, slots=True)
class HkelRetainedArchiveMember:
    """One safely enumerated and fully read-back ZIP member."""

    archive_endpoint_id: str
    archive_fingerprint: str
    raw_name: str
    canonical_path: str
    media_kind: str
    member_fingerprint: str
    byte_length: int
    compressed_byte_length: int
    crc32: int
    chapter_id: str | None
    version_signal: str | None
    language: str | None


@dataclass(frozen=True, slots=True)
class HkelRetainedBilingualXmlPair:
    """Exact English/Traditional-Chinese XML pair; no parsed legal meaning."""

    chapter_id: str
    version_signal: str
    english: HkelRetainedArchiveMember
    traditional_chinese: HkelRetainedArchiveMember


@dataclass(frozen=True, slots=True)
class HkelRetainedSourceObservationIndex:
    """Detached pre-admission observation suitable for later Plan 3 parsing."""

    attempt_id: str
    observation_cutoff: str
    report_fingerprint: str
    authority_manifest_fingerprint: str
    execution_authorization_fingerprint: str
    endpoint_objects: tuple[HkelRetainedEndpointObject, ...]
    archive_members: tuple[HkelRetainedArchiveMember, ...]
    bilingual_xml_pairs: tuple[HkelRetainedBilingualXmlPair, ...]
    xsd_reference: HkelRetainedEndpointObject
    publication_specifications: tuple[HkelRetainedEndpointObject, ...]
    publication_profile_fingerprint: str
    source_observation_fingerprint: str


class HkelRetainedEvidenceReader(Protocol):
    """Open one exact retained object as a seekable binary stream."""

    def open_exact(
        self, reference: HkelRetainedObjectReference
    ) -> AbstractContextManager[BinaryIO]:
        """Open the exact object selected by its detached reference."""
        ...


@dataclass(frozen=True, slots=True)
class _ValidatedReport:
    attempt_id: str
    observation_cutoff: str
    report_fingerprint: str
    authority_manifest_fingerprint: str
    execution_authorization_fingerprint: str
    endpoint_objects: tuple[HkelRetainedEndpointObject, ...]


def _fail(code: HkelRetainedEvidenceErrorCode) -> Never:
    raise HkelRetainedEvidenceError(code)


def _object(value: JsonValue) -> TypeIs[dict[str, JsonValue]]:
    return type(value) is dict and all(type(key) is str for key in value)


def _list(value: JsonValue) -> TypeIs[list[JsonValue]]:
    return type(value) is list


def _text(value: JsonValue) -> TypeIs[str]:
    return type(value) is str


def _validate_reference(
    value: object,
    *,
    report: bool = False,
) -> HkelRetainedObjectReference:
    if type(value) is not HkelRetainedObjectReference:
        _fail(HkelRetainedEvidenceErrorCode.REFERENCE_INVALID)
    if (
        type(value.logical_key) is not str
        or not value.logical_key
        or value.logical_key.startswith(("/", "\\"))
        or "\\" in value.logical_key
        or any(part in {"", ".", ".."} for part in value.logical_key.split("/"))
        or type(value.fingerprint) is not str
        or _FINGERPRINT.fullmatch(value.fingerprint) is None
        or type(value.byte_length) is not int
        or value.byte_length < 0
        or (report and value.byte_length > _MAX_REPORT_BYTES)
    ):
        _fail(HkelRetainedEvidenceErrorCode.REFERENCE_INVALID)
    return HkelRetainedObjectReference(
        value.logical_key,
        value.fingerprint,
        value.byte_length,
    )


def _read_exact_bytes(
    reference: HkelRetainedObjectReference,
    reader: HkelRetainedEvidenceReader,
    *,
    failure: HkelRetainedEvidenceErrorCode,
    max_bytes: int,
) -> bytes:
    if reference.byte_length > max_bytes:
        _fail(failure)
    digest = sha256()
    body = bytearray()
    try:
        with reader.open_exact(
            HkelRetainedObjectReference(
                reference.logical_key,
                reference.fingerprint,
                reference.byte_length,
            )
        ) as stream:
            while True:
                chunk = stream.read(_READ_CHUNK)
                if not chunk:
                    break
                if type(chunk) is not bytes:
                    _fail(failure)
                body.extend(chunk)
                digest.update(chunk)
                if len(body) > reference.byte_length:
                    _fail(failure)
    except HkelRetainedEvidenceError:
        raise
    except Exception as error:
        raise HkelRetainedEvidenceError(failure) from error
    raw = bytes(body)
    if len(raw) != reference.byte_length or f"sha256:{digest.hexdigest()}" != reference.fingerprint:
        _fail(failure)
    return raw


def _verify_exact_object(
    reference: HkelRetainedObjectReference,
    reader: HkelRetainedEvidenceReader,
) -> None:
    """Hash and discard one exact object without retaining its body."""
    digest = sha256()
    byte_length = 0
    try:
        with reader.open_exact(
            HkelRetainedObjectReference(
                reference.logical_key,
                reference.fingerprint,
                reference.byte_length,
            )
        ) as stream:
            while True:
                chunk = stream.read(_READ_CHUNK)
                if not chunk:
                    break
                if type(chunk) is not bytes:
                    _fail(HkelRetainedEvidenceErrorCode.OBJECT_READ_FAILED)
                byte_length += len(chunk)
                if byte_length > reference.byte_length:
                    _fail(HkelRetainedEvidenceErrorCode.OBJECT_READ_FAILED)
                digest.update(chunk)
    except HkelRetainedEvidenceError:
        raise
    except Exception as error:
        raise HkelRetainedEvidenceError(HkelRetainedEvidenceErrorCode.OBJECT_READ_FAILED) from error
    if (
        byte_length != reference.byte_length
        or f"sha256:{digest.hexdigest()}" != reference.fingerprint
    ):
        _fail(HkelRetainedEvidenceErrorCode.OBJECT_READ_FAILED)


def _read_exact_archive_members(
    endpoint: HkelRetainedEndpointObject,
    reader: HkelRetainedEvidenceReader,
) -> tuple[HkelRetainedArchiveMember, ...]:
    """Verify one archive stream, rewind it, and enumerate without buffering it."""
    reference = endpoint.reference
    digest = sha256()
    byte_length = 0
    try:
        with reader.open_exact(
            HkelRetainedObjectReference(
                reference.logical_key,
                reference.fingerprint,
                reference.byte_length,
            )
        ) as stream:
            while True:
                chunk = stream.read(_READ_CHUNK)
                if not chunk:
                    break
                if type(chunk) is not bytes:
                    _fail(HkelRetainedEvidenceErrorCode.OBJECT_READ_FAILED)
                byte_length += len(chunk)
                if byte_length > reference.byte_length:
                    _fail(HkelRetainedEvidenceErrorCode.OBJECT_READ_FAILED)
                digest.update(chunk)
            if (
                byte_length != reference.byte_length
                or f"sha256:{digest.hexdigest()}" != reference.fingerprint
            ):
                _fail(HkelRetainedEvidenceErrorCode.OBJECT_READ_FAILED)
            stream.seek(0)
            return _archive_members(endpoint, stream)
    except HkelRetainedEvidenceError:
        raise
    except Exception as error:
        raise HkelRetainedEvidenceError(HkelRetainedEvidenceErrorCode.OBJECT_READ_FAILED) from error


def _validate_attempt_reference(value: object) -> HkelRetainedAttemptReference:
    if type(value) is not HkelRetainedAttemptReference:
        _fail(HkelRetainedEvidenceErrorCode.REFERENCE_INVALID)
    if (
        type(value.attempt_id) is not str
        or _ATTEMPT_ID.fullmatch(value.attempt_id) is None
        or type(value.observation_cutoff) is not str
        or _OBSERVATION_CUTOFF.fullmatch(value.observation_cutoff) is None
    ):
        _fail(HkelRetainedEvidenceErrorCode.REFERENCE_INVALID)
    try:
        datetime.strptime(value.observation_cutoff, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError as error:
        raise HkelRetainedEvidenceError(HkelRetainedEvidenceErrorCode.REFERENCE_INVALID) from error
    report = _validate_reference(value.report, report=True)
    if report.logical_key != f"attempts/{value.attempt_id}/report.json":
        _fail(HkelRetainedEvidenceErrorCode.REFERENCE_INVALID)
    return HkelRetainedAttemptReference(
        value.attempt_id,
        value.observation_cutoff,
        report,
    )


def _endpoint_object(value: JsonValue) -> HkelRetainedEndpointObject:
    if not _object(value) or frozenset(value) not in {
        _ENDPOINT_FIELDS,
        _ENDPOINT_FIELDS | {"comparison_fingerprint"},
    }:
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    endpoint_id = value["endpoint_id"]
    endpoint_version = value["endpoint_version"]
    media_type = value["media_type"]
    object_key = value["object_key"]
    body_fingerprint = value["body_fingerprint"]
    byte_length = value["byte_length"]
    if (
        not _text(endpoint_id)
        or not endpoint_id
        or not _text(endpoint_version)
        or _VERSION.fullmatch(endpoint_version) is None
        or not _text(media_type)
        or not media_type
        or value["method"] != "GET"
        or value["status"] != _HTTP_OK
        or value["terminal_code"] != "CAPTURED"
        or not _text(value["requested_url"])
        or not value["requested_url"].startswith("https://")
        or not _text(object_key)
        or _OBJECT_KEY.fullmatch(object_key) is None
        or not _text(body_fingerprint)
        or _FINGERPRINT.fullmatch(body_fingerprint) is None
        or object_key != f"objects/{body_fingerprint.removeprefix('sha256:')}.bin"
        or type(byte_length) is not int
        or byte_length < 0
    ):
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    comparison = value.get("comparison_fingerprint")
    if comparison is not None and (
        not _text(comparison) or _FINGERPRINT.fullmatch(comparison) is None
    ):
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    return HkelRetainedEndpointObject(
        endpoint_id,
        endpoint_version,
        media_type,
        HkelRetainedObjectReference(object_key, body_fingerprint, byte_length),
    )


def _report_object(
    reference: HkelRetainedAttemptReference,
    raw: bytes,
) -> dict[str, JsonValue]:
    try:
        value = parse_json_bytes(raw, max_bytes=reference.report.byte_length)
    except Exception as error:
        raise HkelRetainedEvidenceError(HkelRetainedEvidenceErrorCode.REPORT_INVALID) from error
    if not _object(value) or frozenset(value) != _REPORT_FIELDS:
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    return value


def _validate_report_identity(
    value: dict[str, JsonValue],
    reference: HkelRetainedAttemptReference,
) -> tuple[str, str]:
    if (
        value["attempt_id"] != reference.attempt_id
        or value["observation_cutoff"] != reference.observation_cutoff
        or value["source_family"] != "HKEL"
        or value["authority_provenance"] != "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING"
        or value["predecessor_attempt_id"] is not None
        or value["change_state"] != "FIRST_OBSERVATION"
        or value["readback_verified"] is not True
    ):
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    if value["result"] != "COMPLETE":
        _fail(HkelRetainedEvidenceErrorCode.REPORT_NOT_COMPLETE)
    authority = value["authority_manifest_fingerprint"]
    execution = value["execution_authorization_fingerprint"]
    if (
        not _text(authority)
        or _FINGERPRINT.fullmatch(authority) is None
        or not _text(execution)
        or _FINGERPRINT.fullmatch(execution) is None
        or value["endpoint_counts"] != {"CAPTURED": _EXPECTED_CAPTURED_ENDPOINTS}
    ):
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    return authority, execution


def _validated_endpoints(
    value: dict[str, JsonValue],
) -> tuple[HkelRetainedEndpointObject, ...]:
    endpoints_raw = value["endpoints"]
    if not _list(endpoints_raw) or len(endpoints_raw) != _EXPECTED_CAPTURED_ENDPOINTS:
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    endpoints = tuple(_endpoint_object(item) for item in endpoints_raw)
    endpoint_ids = tuple(item.endpoint_id for item in endpoints)
    object_keys = tuple(item.reference.logical_key for item in endpoints)
    if len(set(endpoint_ids)) != len(endpoint_ids) or len(set(object_keys)) != len(object_keys):
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    return endpoints


def _validate_procedures(value: dict[str, JsonValue]) -> None:
    procedures_raw = value["source_procedures"]
    if not _list(procedures_raw) or len(procedures_raw) != len(_EXPECTED_PROCEDURES):
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    procedures: list[tuple[str, int]] = []
    for item in procedures_raw:
        if (
            not _object(item)
            or frozenset(item) != _PROCEDURE_FIELDS
            or item["terminal_code"] != "COMPLETE"
            or not _text(item["source_id"])
            or type(item["declared_member_count"]) is not int
        ):
            _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
        procedures.append((item["source_id"], item["declared_member_count"]))
    if tuple(procedures) != _EXPECTED_PROCEDURES:
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)


def _validate_profile_endpoints(
    endpoints: tuple[HkelRetainedEndpointObject, ...],
) -> None:
    by_id = {item.endpoint_id: item for item in endpoints}
    if frozenset(_ARCHIVE_LANGUAGE) - frozenset(by_id) or frozenset(
        _SPECIFICATION_ENDPOINT_IDS
    ) - frozenset(by_id):
        _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    for endpoint_id in _ARCHIVE_LANGUAGE:
        if by_id[endpoint_id].media_type != "application/zip":
            _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)
    for endpoint_id, media_type in _SPECIFICATION_MEDIA_TYPES.items():
        if by_id[endpoint_id].media_type != media_type:
            _fail(HkelRetainedEvidenceErrorCode.REPORT_INVALID)


def _validate_report(
    reference: HkelRetainedAttemptReference,
    raw: bytes,
) -> _ValidatedReport:
    value = _report_object(reference, raw)
    authority, execution = _validate_report_identity(value, reference)
    endpoints = _validated_endpoints(value)
    _validate_procedures(value)
    _validate_profile_endpoints(endpoints)
    return _ValidatedReport(
        reference.attempt_id,
        reference.observation_cutoff,
        reference.report.fingerprint,
        authority,
        execution,
        endpoints,
    )


def _canonical_member_path(raw_name: str) -> str:
    if (
        type(raw_name) is not str
        or not raw_name
        or "\x00" in raw_name
        or ("/" in raw_name and "\\" in raw_name)
        or raw_name.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", raw_name) is not None
        or any(unicodedata.category(character).startswith("C") for character in raw_name)
    ):
        _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_UNSAFE_MEMBER)
    canonical = unicodedata.normalize("NFC", raw_name.replace("\\", "/"))
    parts = canonical.split("/")
    if any(part in {"", ".", ".."} or _MEMBER_SEGMENT.fullmatch(part) is None for part in parts):
        _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_UNSAFE_MEMBER)
    return "/".join(parts)


def _validate_inert_xml(raw: bytes) -> None:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HkelRetainedEvidenceError(HkelRetainedEvidenceErrorCode.XML_INVALID) from error
    declaration = _XML_DECLARATION_ENCODING.match(decoded)
    if "\x00" in decoded or (
        declaration is not None
        and declaration.group("encoding").lower().replace("_", "-") != "utf-8"
    ):
        _fail(HkelRetainedEvidenceErrorCode.XML_INVALID)
    upper = decoded.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        _fail(HkelRetainedEvidenceErrorCode.XML_INVALID)
    try:
        # DTD/entity declarations are rejected above; stdlib parsing is inert here.
        root = ET.fromstring(raw)  # noqa: S314
    except (ET.ParseError, LookupError, ValueError) as error:
        raise HkelRetainedEvidenceError(HkelRetainedEvidenceErrorCode.XML_INVALID) from error
    if any(element.tag.startswith(_XINCLUDE_NAMESPACE) for element in root.iter()):
        _fail(HkelRetainedEvidenceErrorCode.XML_INVALID)


def _member_bytes(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[bytes, str]:
    digest = sha256()
    body = bytearray()
    try:
        with archive.open(info, "r") as member:
            while True:
                chunk = member.read(_READ_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                body.extend(chunk)
                if len(body) > _MAX_ARCHIVE_MEMBER_BYTES:
                    _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_LIMIT_EXCEEDED)
    except HkelRetainedEvidenceError:
        raise
    except Exception as error:
        raise HkelRetainedEvidenceError(HkelRetainedEvidenceErrorCode.ARCHIVE_INVALID) from error
    if len(body) != info.file_size:
        _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_INVALID)
    return bytes(body), f"sha256:{digest.hexdigest()}"


def _open_archive(archive_stream: BinaryIO) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(archive_stream, "r")
    except (OSError, zipfile.BadZipFile) as error:
        raise HkelRetainedEvidenceError(HkelRetainedEvidenceErrorCode.ARCHIVE_INVALID) from error
    return archive


def _validated_archive_infos(
    infos: list[zipfile.ZipInfo],
) -> tuple[tuple[zipfile.ZipInfo, str], ...]:
    if not infos or len(infos) > _MAX_ARCHIVE_MEMBERS:
        _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_LIMIT_EXCEEDED)
    total = 0
    names: set[str] = set()
    folded_names: set[str] = set()
    validated: list[tuple[zipfile.ZipInfo, str]] = []
    for info in infos:
        canonical = _canonical_member_path(info.filename.rstrip("/\\"))
        folded = canonical.casefold()
        if canonical in names or folded in folded_names:
            _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_MEMBER_COLLISION)
        names.add(canonical)
        folded_names.add(folded)
        unix_mode = info.external_attr >> 16
        file_type = stat.S_IFMT(unix_mode)
        if file_type not in {0, stat.S_IFREG} or info.is_dir():
            _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_UNSAFE_MEMBER)
        if (
            info.flag_bits & 0x1
            or info.compress_type != zipfile.ZIP_DEFLATED
            or info.file_size < 0
            or info.compress_size < 0
            or info.file_size > _MAX_ARCHIVE_MEMBER_BYTES
            or (
                info.file_size > 0
                and (
                    info.compress_size == 0
                    or info.file_size > info.compress_size * _MAX_COMPRESSION_RATIO
                )
            )
        ):
            _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_LIMIT_EXCEEDED)
        total += info.file_size
        if total > _MAX_ARCHIVE_EXPANDED_BYTES:
            _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_LIMIT_EXCEEDED)
        validated.append((info, canonical))
    return tuple(validated)


def _archive_members(
    endpoint: HkelRetainedEndpointObject,
    archive_stream: BinaryIO,
) -> tuple[HkelRetainedArchiveMember, ...]:
    language = _ARCHIVE_LANGUAGE[endpoint.endpoint_id]
    archive = _open_archive(archive_stream)
    with archive:
        validated = _validated_archive_infos(archive.infolist())
        members: list[HkelRetainedArchiveMember] = []
        for info, canonical in validated:
            raw, fingerprint = _member_bytes(archive, info)
            xml = _XML_MEMBER.fullmatch(canonical)
            if canonical.lower().endswith(".xml"):
                _validate_inert_xml(raw)
                if xml is None or xml.group("language") != language:
                    _fail(HkelRetainedEvidenceErrorCode.BILINGUAL_PAIRING_INVALID)
            members.append(
                HkelRetainedArchiveMember(
                    endpoint.endpoint_id,
                    endpoint.reference.fingerprint,
                    info.filename,
                    canonical,
                    "XML" if xml is not None else "ASSET",
                    fingerprint,
                    info.file_size,
                    info.compress_size,
                    info.CRC,
                    None if xml is None else xml.group("chapter"),
                    None if xml is None else xml.group("version"),
                    None if xml is None else xml.group("language"),
                )
            )
    return tuple(sorted(members, key=lambda item: item.canonical_path))


def _pairs(
    members: tuple[HkelRetainedArchiveMember, ...],
) -> tuple[HkelRetainedBilingualXmlPair, ...]:
    by_language: dict[str, dict[tuple[str, str], HkelRetainedArchiveMember]] = {
        "en": {},
        "zh-Hant": {},
        "zh-Hans": {},
    }
    for member in members:
        if member.media_kind != "XML":
            continue
        chapter = member.chapter_id
        version = member.version_signal
        language = member.language
        if chapter is None or version is None or language not in by_language:
            _fail(HkelRetainedEvidenceErrorCode.BILINGUAL_PAIRING_INVALID)
        key = (chapter, version)
        if key in by_language[language]:
            _fail(HkelRetainedEvidenceErrorCode.BILINGUAL_PAIRING_INVALID)
        by_language[language][key] = member
    expected = frozenset(by_language["en"])
    if (
        len(expected) != _EXPECTED_CURRENT_INSTRUMENTS
        or frozenset(by_language["zh-Hant"]) != expected
        or frozenset(by_language["zh-Hans"]) != expected
    ):
        _fail(HkelRetainedEvidenceErrorCode.BILINGUAL_PAIRING_INVALID)
    return tuple(
        HkelRetainedBilingualXmlPair(
            chapter,
            version,
            by_language["en"][key],
            by_language["zh-Hant"][key],
        )
        for key in sorted(expected)
        for chapter, version in (key,)
    )


def _validate_profile_member_collisions(
    members: tuple[HkelRetainedArchiveMember, ...],
) -> None:
    names: set[str] = set()
    folded_names: set[str] = set()
    for member in members:
        folded = member.canonical_path.casefold()
        if member.canonical_path in names or folded in folded_names:
            _fail(HkelRetainedEvidenceErrorCode.ARCHIVE_MEMBER_COLLISION)
        names.add(member.canonical_path)
        folded_names.add(folded)


def _endpoint_projection(endpoint: HkelRetainedEndpointObject) -> dict[str, JsonValue]:
    return {
        "byte_length": endpoint.reference.byte_length,
        "endpoint_id": endpoint.endpoint_id,
        "endpoint_version": endpoint.endpoint_version,
        "fingerprint": endpoint.reference.fingerprint,
        "logical_key": endpoint.reference.logical_key,
        "media_type": endpoint.media_type,
    }


def _member_projection(member: HkelRetainedArchiveMember) -> dict[str, JsonValue]:
    return {
        "archive_endpoint_id": member.archive_endpoint_id,
        "archive_fingerprint": member.archive_fingerprint,
        "byte_length": member.byte_length,
        "canonical_path": member.canonical_path,
        "chapter_id": member.chapter_id,
        "compressed_byte_length": member.compressed_byte_length,
        "crc32": member.crc32,
        "language": member.language,
        "media_kind": member.media_kind,
        "member_fingerprint": member.member_fingerprint,
        "version_signal": member.version_signal,
    }


def index_retained_hkel_observation(
    reference: object,
    reader: HkelRetainedEvidenceReader,
) -> HkelRetainedSourceObservationIndex:
    """Validate and index one frozen COMPLETE attempt without legal admission."""
    exact_reference = _validate_attempt_reference(reference)
    report_raw = _read_exact_bytes(
        exact_reference.report,
        reader,
        failure=HkelRetainedEvidenceErrorCode.REPORT_READ_FAILED,
        max_bytes=_MAX_REPORT_BYTES,
    )
    report = _validate_report(exact_reference, report_raw)
    by_id = {item.endpoint_id: item for item in report.endpoint_objects}
    xsd_body: bytes | None = None
    archive_members: list[HkelRetainedArchiveMember] = []
    for endpoint in report.endpoint_objects:
        if endpoint.endpoint_id in _ARCHIVE_LANGUAGE:
            archive_members.extend(_read_exact_archive_members(endpoint, reader))
            continue
        if endpoint.endpoint_id == _XSD_ENDPOINT_ID:
            xsd_body = _read_exact_bytes(
                endpoint.reference,
                reader,
                failure=HkelRetainedEvidenceErrorCode.OBJECT_READ_FAILED,
                max_bytes=_MAX_XSD_BYTES,
            )
        else:
            _verify_exact_object(endpoint.reference, reader)
    stable_members = tuple(
        sorted(
            archive_members,
            key=lambda item: (item.archive_endpoint_id, item.canonical_path),
        )
    )
    _validate_profile_member_collisions(stable_members)
    pairs = _pairs(stable_members)
    if xsd_body is None:
        _fail(HkelRetainedEvidenceErrorCode.SPECIFICATION_BINDING_INVALID)
    try:
        _validate_inert_xml(xsd_body)
    except HkelRetainedEvidenceError as error:
        raise HkelRetainedEvidenceError(
            HkelRetainedEvidenceErrorCode.SPECIFICATION_BINDING_INVALID
        ) from error
    specifications = tuple(by_id[item] for item in _SPECIFICATION_ENDPOINT_IDS)
    profile_body: dict[str, JsonValue] = {
        "profile": "HKEL_RETAINED_CURRENT_DATA_1.0.0",
        "specifications": [_endpoint_projection(item) for item in specifications],
    }
    profile_fingerprint = f"sha256:{sha256(canonicalize(profile_body)).hexdigest()}"
    observation_body: dict[str, JsonValue] = {
        "attempt_id": report.attempt_id,
        "observation_cutoff": report.observation_cutoff,
        "report_fingerprint": report.report_fingerprint,
        "authority_manifest_fingerprint": report.authority_manifest_fingerprint,
        "execution_authorization_fingerprint": report.execution_authorization_fingerprint,
        "endpoint_objects": [_endpoint_projection(item) for item in report.endpoint_objects],
        "archive_members": [_member_projection(item) for item in stable_members],
        "publication_profile_fingerprint": profile_fingerprint,
    }
    observation_fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(observation_body))).hexdigest()}"
    )
    return HkelRetainedSourceObservationIndex(
        report.attempt_id,
        report.observation_cutoff,
        report.report_fingerprint,
        report.authority_manifest_fingerprint,
        report.execution_authorization_fingerprint,
        report.endpoint_objects,
        stable_members,
        pairs,
        by_id[_XSD_ENDPOINT_ID],
        specifications,
        profile_fingerprint,
        observation_fingerprint,
    )
