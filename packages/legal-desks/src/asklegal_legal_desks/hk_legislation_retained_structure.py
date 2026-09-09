"""Text-free structural profiler for one Ready retained HKeL observation.

The profiler re-reads only the paired English and Traditional-Chinese XML
members from the retained archive closure.  It emits tag and attribute-name
counts plus fingerprints that bind structure, attribute values, text, and tail
values.  Element text, tail text, and raw attribute values are never returned.
No result from this module grants evidence admission or legal authority.
"""

from __future__ import annotations

import codecs
import io
import re
import stat
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import IO, BinaryIO, Never, Protocol

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value

from asklegal_legal_desks.hk_legislation_retained import (
    HkelRetainedArchiveMember,
    HkelRetainedBilingualXmlPair,
    HkelRetainedEndpointObject,
    HkelRetainedEvidenceReader,
    HkelRetainedObjectReference,
    HkelRetainedSourceObservationIndex,
)

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_XML_DECLARATION_ENCODING = re.compile(
    r'^\ufeff?<\?xml\b[^>]*\bencoding\s*=\s*["\'](?P<encoding>[^"\']+)["\']',
    re.IGNORECASE,
)
_HKLM_NAMESPACE = "http://www.xml.gov.hk/schemas/hklm/1.0"
_XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
_XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
_XINCLUDE_NAMESPACE = "http://www.w3.org/2001/XInclude"
_SCHEMA_LOCATION = (
    "http://www.xml.gov.hk/schemas/hklm/1.0 https://www.elegislation.gov.hk/schemas/hklm.xsd"
)
_SCHEMA_LOCATION_ATTRIBUTE = f"{{{_XSI_NAMESPACE}}}schemaLocation"
_LANGUAGE_ATTRIBUTE = f"{{{_XML_NAMESPACE}}}lang"
_XINCLUDE_PREFIX = f"{{{_XINCLUDE_NAMESPACE}}}"
_ALLOWED_ROOTS = frozenset(
    f"{{{_HKLM_NAMESPACE}}}{local_name}"
    for local_name in ("lawDoc", "ordinance", "resolution", "subLeg")
)
_MAX_MEMBER_BYTES = 32 << 20
_MAX_XSD_BYTES = 16 << 20
_MAX_NODES = 250_000
_MAX_DEPTH = 64
_MAX_ATTRIBUTES = 64
_READ_CHUNK = 64 << 10
_SCAN_TAIL = 16
_DECLARATION_PREFIX = 1024
_NONE = "NONE"
_SCHEMA_VALIDATION_NOT_PERFORMED = "SCHEMA_VALIDATION_NOT_PERFORMED"
_PROFILE_ID = "HKEL_RETAINED_STRUCTURE_1.0.0"
_RETAINED_PUBLICATION_PROFILE_ID = "HKEL_RETAINED_CURRENT_DATA_1.0.0"
_EXPECTED_ENDPOINTS = 56
_EXPECTED_PAIRS = 3157
_EXPECTED_SPECIFICATIONS = 7
_EXPECTED_TARGET_ARCHIVES = (
    ("sep_00000000000000000000000000000000000000000000000a", "en", 1377),
    ("sep_00000000000000000000000000000000000000000000000b", "en", 1380),
    ("sep_00000000000000000000000000000000000000000000000c", "en", 338),
    ("sep_00000000000000000000000000000000000000000000000d", "en", 62),
    ("sep_00000000000000000000000000000000000000000000000e", "zh-Hant-HK", 1377),
    ("sep_00000000000000000000000000000000000000000000000f", "zh-Hant-HK", 1380),
    ("sep_000000000000000000000000000000000000000000000010", "zh-Hant-HK", 338),
    ("sep_000000000000000000000000000000000000000000000011", "zh-Hant-HK", 62),
)
_SCHEMA_CHILD_DEPTH = 2
_XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
_XSD_PREFIX = f"{{{_XSD_NAMESPACE}}}"
_ROOT_LOCAL_NAMES = ("lawDoc", "ordinance", "resolution", "subLeg")
_EXPECTED_XSD_IMPORTS = (
    (
        "http://www.w3.org/XML/1998/namespace",
        "http://www.w3.org/2001/xml.xsd",
    ),
    ("http://purl.org/dc/terms/", None),
    ("http://www.w3.org/1999/xhtml", None),
    ("http://www.w3.org/1998/Math/MathML", None),
)


class HkelRetainedStructureErrorCode(StrEnum):
    """Closed profiler failures that never carry source bytes."""

    INDEX_INVALID = "HKEL_RETAINED_STRUCTURE_INDEX_INVALID"
    OBJECT_READ_FAILED = "HKEL_RETAINED_STRUCTURE_OBJECT_READ_FAILED"
    ARCHIVE_INVALID = "HKEL_RETAINED_STRUCTURE_ARCHIVE_INVALID"
    MEMBER_MISMATCH = "HKEL_RETAINED_STRUCTURE_MEMBER_MISMATCH"
    XML_INVALID = "HKEL_RETAINED_STRUCTURE_XML_INVALID"
    XML_FORBIDDEN_DECLARATION = "HKEL_RETAINED_STRUCTURE_XML_FORBIDDEN_DECLARATION"
    XML_XINCLUDE_FORBIDDEN = "HKEL_RETAINED_STRUCTURE_XML_XINCLUDE_FORBIDDEN"
    XML_LIMIT_EXCEEDED = "HKEL_RETAINED_STRUCTURE_XML_LIMIT_EXCEEDED"
    ROOT_PROFILE_INVALID = "HKEL_RETAINED_STRUCTURE_ROOT_PROFILE_INVALID"
    SCHEMA_PROFILE_INVALID = "HKEL_RETAINED_STRUCTURE_SCHEMA_PROFILE_INVALID"


class HkelRetainedStructureIssueCode(StrEnum):
    """Closed non-authorizing observations that require later review."""

    ARCHIVE_ROOT_LANGUAGE_CONFLICT = "HKEL_ARCHIVE_ROOT_LANGUAGE_CONFLICT"
    BILINGUAL_ROOT_KIND_CONFLICT = "HKEL_BILINGUAL_ROOT_KIND_CONFLICT"


class HkelRetainedStructureError(ValueError):
    """One normalized structural rejection without parser or source prose."""

    code: HkelRetainedStructureErrorCode

    def __init__(self, code: HkelRetainedStructureErrorCode) -> None:
        """Create one stable closed rejection."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HkelExpandedNameCount:
    """One expanded XML name and its exact occurrence count."""

    expanded_name: str
    count: int


@dataclass(frozen=True, slots=True)
class HkelRetainedSchemaProfile:
    """Bound retained schema inputs without claiming schema validation."""

    profile_id: str
    xsd_fingerprint: str
    publication_profile_fingerprint: str
    target_namespace: str
    schema_version: str
    element_form_default: str
    attribute_form_default: str
    root_local_names: tuple[str, ...]
    imports: tuple[tuple[str, str | None], ...]
    root_namespace_binding_fingerprint: str
    schema_location_binding_fingerprint: str
    validation_state: str
    profile_fingerprint: str
    admission_authority: str


@dataclass(frozen=True, slots=True)
class HkelRetainedXmlStructureProfile:
    """Text-free facts for one exact XML member."""

    archive_endpoint_id: str
    archive_fingerprint: str
    canonical_path: str
    member_fingerprint: str
    chapter_id: str
    version_signal: str
    language: str
    root_expanded_name: str
    node_count: int
    maximum_depth: int
    maximum_attribute_count: int
    element_expanded_name_counts: tuple[HkelExpandedNameCount, ...]
    attribute_expanded_name_counts: tuple[HkelExpandedNameCount, ...]
    structure_fingerprint: str
    value_binding_fingerprint: str
    profile_fingerprint: str
    issue_codes: tuple[HkelRetainedStructureIssueCode, ...]
    admission_authority: str


@dataclass(frozen=True, slots=True)
class HkelRetainedBilingualStructureRecord:
    """Detached bilingual pairing with no identity or legal-state decision."""

    chapter_id: str
    version_signal: str
    english: HkelRetainedXmlStructureProfile
    traditional_chinese: HkelRetainedXmlStructureProfile
    issue_codes: tuple[HkelRetainedStructureIssueCode, ...]
    review_state: str
    record_fingerprint: str
    admission_authority: str


@dataclass(frozen=True, slots=True)
class HkelRetainedStructureIssueCount:
    """One stable issue-code count across the detached bilingual records."""

    issue_code: HkelRetainedStructureIssueCode
    count: int


@dataclass(frozen=True, slots=True)
class HkelRetainedStructureResult:
    """Complete text-free profile of the retained bilingual XML pairs."""

    source_observation_fingerprint: str
    schema_profile: HkelRetainedSchemaProfile
    bilingual_records: tuple[HkelRetainedBilingualStructureRecord, ...]
    issue_counts: tuple[HkelRetainedStructureIssueCount, ...]
    review_required_pair_count: int
    maximum_depth: int
    profile_fingerprint: str
    admission_authority: str


@dataclass(frozen=True, slots=True)
class _TargetMember:
    pair_key: tuple[str, str]
    expected_root_language: str
    member: HkelRetainedArchiveMember


@dataclass(frozen=True, slots=True)
class _ValidatedInput:
    index: HkelRetainedSourceObservationIndex
    endpoint_by_id: dict[str, HkelRetainedEndpointObject]
    targets_by_endpoint: dict[str, tuple[_TargetMember, ...]]


@dataclass(frozen=True, slots=True)
class _ParsedStructure:
    root_expanded_name: str
    node_count: int
    maximum_depth: int
    maximum_attribute_count: int
    element_counts: tuple[HkelExpandedNameCount, ...]
    attribute_counts: tuple[HkelExpandedNameCount, ...]
    structure_fingerprint: str
    value_binding_fingerprint: str
    issue_codes: tuple[HkelRetainedStructureIssueCode, ...]


class _Digest(Protocol):
    def update(self, value: bytes, /) -> None:
        """Add bytes to the digest."""
        ...

    def hexdigest(self) -> str:
        """Return the lowercase hexadecimal digest."""
        ...


def _fail(code: HkelRetainedStructureErrorCode) -> Never:
    raise HkelRetainedStructureError(code)


def _valid_fingerprint(value: object) -> bool:
    return type(value) is str and _FINGERPRINT.fullmatch(value) is not None


def _frame(digest: _Digest, value: str) -> None:
    raw = value.encode("utf-8")
    digest.update(len(raw).to_bytes(8, "big"))
    digest.update(raw)


def _fingerprint(values: tuple[str, ...]) -> str:
    digest = sha256()
    for value in values:
        _frame(digest, value)
    return f"sha256:{digest.hexdigest()}"


def _count_values(values: Counter[str]) -> tuple[HkelExpandedNameCount, ...]:
    return tuple(HkelExpandedNameCount(name, count) for name, count in sorted(values.items()))


def _member_identity(member: HkelRetainedArchiveMember) -> tuple[object, ...]:
    return (
        member.archive_endpoint_id,
        member.archive_fingerprint,
        member.raw_name,
        member.canonical_path,
        member.media_kind,
        member.member_fingerprint,
        member.byte_length,
        member.compressed_byte_length,
        member.crc32,
        member.chapter_id,
        member.version_signal,
        member.language,
    )


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


def _canonical_fingerprint(value: dict[str, JsonValue]) -> str:
    return f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"


def _validate_canonical_fingerprints(index: HkelRetainedSourceObservationIndex) -> None:
    specifications = index.publication_specifications
    if len(specifications) != _EXPECTED_SPECIFICATIONS or any(
        type(item) is not HkelRetainedEndpointObject for item in specifications
    ):
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    profile: dict[str, JsonValue] = {
        "profile": _RETAINED_PUBLICATION_PROFILE_ID,
        "specifications": [_endpoint_projection(item) for item in specifications],
    }
    profile_fingerprint = _canonical_fingerprint(profile)
    if profile_fingerprint != index.publication_profile_fingerprint:
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    observation: dict[str, JsonValue] = {
        "attempt_id": index.attempt_id,
        "observation_cutoff": index.observation_cutoff,
        "report_fingerprint": index.report_fingerprint,
        "authority_manifest_fingerprint": index.authority_manifest_fingerprint,
        "execution_authorization_fingerprint": index.execution_authorization_fingerprint,
        "endpoint_objects": [_endpoint_projection(item) for item in index.endpoint_objects],
        "archive_members": [_member_projection(item) for item in index.archive_members],
        "publication_profile_fingerprint": profile_fingerprint,
    }
    if _canonical_fingerprint(observation) != index.source_observation_fingerprint:
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)


def _validate_member(
    value: object,
    *,
    chapter_id: str,
    version_signal: str,
    language: str,
) -> HkelRetainedArchiveMember:
    if type(value) is not HkelRetainedArchiveMember:
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    if (
        value.media_kind != "XML"
        or value.chapter_id != chapter_id
        or value.version_signal != version_signal
        or value.language != language
        or type(value.archive_endpoint_id) is not str
        or not value.archive_endpoint_id
        or not _valid_fingerprint(value.archive_fingerprint)
        or type(value.raw_name) is not str
        or not value.raw_name
        or type(value.canonical_path) is not str
        or not value.canonical_path
        or not _valid_fingerprint(value.member_fingerprint)
        or type(value.byte_length) is not int
        or value.byte_length <= 0
        or value.byte_length > _MAX_MEMBER_BYTES
        or type(value.compressed_byte_length) is not int
        or value.compressed_byte_length < 0
        or type(value.crc32) is not int
        or value.crc32 < 0
    ):
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    return value


def _validate_endpoint(value: object) -> HkelRetainedEndpointObject:
    if type(value) is not HkelRetainedEndpointObject:
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    reference = value.reference
    if (
        type(value.endpoint_id) is not str
        or not value.endpoint_id
        or type(value.endpoint_version) is not str
        or not value.endpoint_version
        or type(value.media_type) is not str
        or not value.media_type
        or type(reference) is not HkelRetainedObjectReference
        or type(reference.logical_key) is not str
        or not reference.logical_key
        or not _valid_fingerprint(reference.fingerprint)
        or type(reference.byte_length) is not int
        or reference.byte_length <= 0
    ):
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    return value


def _validate_pair(value: object) -> HkelRetainedBilingualXmlPair:
    if type(value) is not HkelRetainedBilingualXmlPair:
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    if (
        type(value.chapter_id) is not str
        or not value.chapter_id
        or type(value.version_signal) is not str
        or not value.version_signal
    ):
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    _validate_member(
        value.english,
        chapter_id=value.chapter_id,
        version_signal=value.version_signal,
        language="en",
    )
    _validate_member(
        value.traditional_chinese,
        chapter_id=value.chapter_id,
        version_signal=value.version_signal,
        language="zh-Hant",
    )
    return value


def _indexed_member_identities(
    members: tuple[HkelRetainedArchiveMember, ...],
) -> set[tuple[object, ...]]:
    indexed: set[tuple[object, ...]] = set()
    for member in members:
        if type(member) is not HkelRetainedArchiveMember:
            _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
        identity = _member_identity(member)
        if identity in indexed:
            _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
        indexed.add(identity)
    return indexed


def _pair_targets(
    pairs: tuple[HkelRetainedBilingualXmlPair, ...],
    endpoint_by_id: dict[str, HkelRetainedEndpointObject],
    indexed_members: set[tuple[object, ...]],
) -> dict[str, tuple[_TargetMember, ...]]:
    pair_keys: set[tuple[str, str]] = set()
    target_identities: set[tuple[object, ...]] = set()
    targets: dict[str, list[_TargetMember]] = {}
    for raw_pair in pairs:
        pair = _validate_pair(raw_pair)
        pair_key = (pair.chapter_id, pair.version_signal)
        if pair_key in pair_keys:
            _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
        pair_keys.add(pair_key)
        for member, expected_root_language in (
            (pair.english, "en"),
            (pair.traditional_chinese, "zh-Hant-HK"),
        ):
            identity = _member_identity(member)
            endpoint = endpoint_by_id.get(member.archive_endpoint_id)
            if (
                identity not in indexed_members
                or identity in target_identities
                or endpoint is None
                or endpoint.media_type != "application/zip"
                or endpoint.reference.fingerprint != member.archive_fingerprint
            ):
                _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
            target_identities.add(identity)
            targets.setdefault(member.archive_endpoint_id, []).append(
                _TargetMember(pair_key, expected_root_language, member)
            )
    frozen_targets = {
        endpoint_id: tuple(sorted(items, key=lambda item: item.member.canonical_path))
        for endpoint_id, items in targets.items()
    }
    topology = tuple(
        (
            endpoint_id,
            expected_language,
            len(frozen_targets.get(endpoint_id, ())),
        )
        for endpoint_id, expected_language, _expected_count in _EXPECTED_TARGET_ARCHIVES
        if all(
            item.expected_root_language == expected_language
            for item in frozen_targets.get(endpoint_id, ())
        )
    )
    if topology != _EXPECTED_TARGET_ARCHIVES or set(frozen_targets) != {
        endpoint_id
        for endpoint_id, _expected_language, _expected_count in _EXPECTED_TARGET_ARCHIVES
    }:
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    return frozen_targets


def _validated_input(value: object) -> _ValidatedInput:
    if type(value) is not HkelRetainedSourceObservationIndex:
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    if (
        not _valid_fingerprint(value.source_observation_fingerprint)
        or not _valid_fingerprint(value.publication_profile_fingerprint)
        or type(value.xsd_reference) is not HkelRetainedEndpointObject
        or not _valid_fingerprint(value.xsd_reference.reference.fingerprint)
        or len(value.bilingual_xml_pairs) != _EXPECTED_PAIRS
        or len(value.endpoint_objects) != _EXPECTED_ENDPOINTS
    ):
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    endpoints = tuple(_validate_endpoint(item) for item in value.endpoint_objects)
    endpoint_by_id = {item.endpoint_id: item for item in endpoints}
    if len(endpoint_by_id) != len(endpoints):
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    indexed_members = _indexed_member_identities(value.archive_members)
    if (
        value.xsd_reference not in endpoints
        or value.xsd_reference not in value.publication_specifications
    ):
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    _validate_canonical_fingerprints(value)
    return _ValidatedInput(
        value,
        endpoint_by_id,
        _pair_targets(value.bilingual_xml_pairs, endpoint_by_id, indexed_members),
    )


class _InertMemberStream:
    """Small-read UTF-8 and forbidden-declaration guard for iterparse."""

    def __init__(self, source: IO[bytes], member: HkelRetainedArchiveMember) -> None:
        self._source = source
        self._member = member
        self._digest = sha256()
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._byte_count = 0
        self._scan_tail = ""
        self._declaration_prefix = ""
        self._declaration_complete = False
        self._eof = False

    def _inspect_text(self, decoded: str) -> None:
        if "\x00" in decoded:
            _fail(HkelRetainedStructureErrorCode.XML_INVALID)
        probe = (self._scan_tail + decoded).upper()
        if "<!DOCTYPE" in probe or "<!ENTITY" in probe:
            _fail(HkelRetainedStructureErrorCode.XML_FORBIDDEN_DECLARATION)
        self._scan_tail = probe[-_SCAN_TAIL:]
        if self._declaration_complete:
            return
        remaining = _DECLARATION_PREFIX - len(self._declaration_prefix)
        self._declaration_prefix += decoded[:remaining]
        declaration_probe = self._declaration_prefix.removeprefix("\ufeff")
        if "<?xml".startswith(declaration_probe):
            return
        if not declaration_probe.startswith("<?xml"):
            self._declaration_complete = True
            return
        declaration_end = declaration_probe.find("?>")
        if declaration_end < 0:
            if len(self._declaration_prefix) >= _DECLARATION_PREFIX:
                _fail(HkelRetainedStructureErrorCode.XML_INVALID)
            return
        declaration = _XML_DECLARATION_ENCODING.match(self._declaration_prefix)
        if declaration is not None and (
            declaration.group("encoding").lower().replace("_", "-") != "utf-8"
        ):
            _fail(HkelRetainedStructureErrorCode.XML_INVALID)
        self._declaration_complete = True

    def read(self, size: int = -1) -> bytes:
        if self._eof:
            return b""
        requested = _READ_CHUNK if size < 0 or size > _READ_CHUNK else size
        try:
            chunk = self._source.read(requested)
        except Exception as error:
            raise HkelRetainedStructureError(
                HkelRetainedStructureErrorCode.ARCHIVE_INVALID
            ) from error
        if type(chunk) is not bytes:
            _fail(HkelRetainedStructureErrorCode.ARCHIVE_INVALID)
        if not chunk:
            try:
                decoded = self._decoder.decode(b"", final=True)
            except UnicodeDecodeError as error:
                raise HkelRetainedStructureError(
                    HkelRetainedStructureErrorCode.XML_INVALID
                ) from error
            self._inspect_text(decoded)
            self._eof = True
            return b""
        self._byte_count += len(chunk)
        if self._byte_count > self._member.byte_length or self._byte_count > _MAX_MEMBER_BYTES:
            _fail(HkelRetainedStructureErrorCode.XML_LIMIT_EXCEEDED)
        self._digest.update(chunk)
        try:
            decoded = self._decoder.decode(chunk, final=False)
        except UnicodeDecodeError as error:
            raise HkelRetainedStructureError(HkelRetainedStructureErrorCode.XML_INVALID) from error
        self._inspect_text(decoded)
        return chunk

    def verify_complete(self) -> None:
        if not self._eof:
            _fail(HkelRetainedStructureErrorCode.MEMBER_MISMATCH)
        if (
            self._byte_count != self._member.byte_length
            or f"sha256:{self._digest.hexdigest()}" != self._member.member_fingerprint
        ):
            _fail(HkelRetainedStructureErrorCode.MEMBER_MISMATCH)


def _verify_archive_stream(
    endpoint: HkelRetainedEndpointObject,
    stream: BinaryIO,
) -> None:
    digest = sha256()
    byte_count = 0
    try:
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            if type(chunk) is not bytes:
                _fail(HkelRetainedStructureErrorCode.OBJECT_READ_FAILED)
            byte_count += len(chunk)
            if byte_count > endpoint.reference.byte_length:
                _fail(HkelRetainedStructureErrorCode.OBJECT_READ_FAILED)
            digest.update(chunk)
        if (
            byte_count != endpoint.reference.byte_length
            or f"sha256:{digest.hexdigest()}" != endpoint.reference.fingerprint
        ):
            _fail(HkelRetainedStructureErrorCode.OBJECT_READ_FAILED)
        stream.seek(0)
    except HkelRetainedStructureError:
        raise
    except Exception as error:
        raise HkelRetainedStructureError(
            HkelRetainedStructureErrorCode.OBJECT_READ_FAILED
        ) from error


def _matching_info(
    archive: zipfile.ZipFile,
    member: HkelRetainedArchiveMember,
) -> zipfile.ZipInfo:
    matches = tuple(info for info in archive.infolist() if info.filename == member.raw_name)
    if len(matches) != 1:
        _fail(HkelRetainedStructureErrorCode.MEMBER_MISMATCH)
    info = matches[0]
    unix_mode = info.external_attr >> 16
    file_type = stat.S_IFMT(unix_mode)
    if (
        info.is_dir()
        or file_type not in {0, stat.S_IFREG}
        or info.flag_bits & 0x1
        or info.file_size != member.byte_length
        or info.compress_size != member.compressed_byte_length
        or member.crc32 != info.CRC
    ):
        _fail(HkelRetainedStructureErrorCode.MEMBER_MISMATCH)
    return info


def _member_profile_fingerprint(
    member: HkelRetainedArchiveMember,
    parsed: _ParsedStructure,
) -> str:
    values = [
        "HKEL_RETAINED_XML_STRUCTURE_PROFILE_1.0.0",
        member.archive_endpoint_id,
        member.archive_fingerprint,
        member.canonical_path,
        member.member_fingerprint,
        member.chapter_id or "",
        member.version_signal or "",
        member.language or "",
        parsed.root_expanded_name,
        str(parsed.node_count),
        str(parsed.maximum_depth),
        str(parsed.maximum_attribute_count),
        parsed.structure_fingerprint,
        parsed.value_binding_fingerprint,
    ]
    values.extend(f"E:{item.expanded_name}:{item.count}" for item in parsed.element_counts)
    values.extend(f"A:{item.expanded_name}:{item.count}" for item in parsed.attribute_counts)
    values.extend(f"I:{item.value}" for item in parsed.issue_codes)
    values.append(_NONE)
    return _fingerprint(tuple(values))


class _ParseAccumulator:
    """Bounded mutable state for one streaming member parse."""

    def __init__(self) -> None:
        self.structure = sha256()
        self.value_binding = sha256()
        self.element_names: Counter[str] = Counter()
        self.attribute_names: Counter[str] = Counter()
        self.node_count = 0
        self.maximum_depth = 0
        self.maximum_attribute_count = 0
        self.depth = 0
        self.root_expanded_name: str | None = None
        self.root_language: str | None = None
        self.root_schema_location: str | None = None

    def start(self, element: ET.Element) -> None:
        """Account one start event before any child is visited."""
        if type(element.tag) is not str:
            _fail(HkelRetainedStructureErrorCode.XML_INVALID)
        self.depth += 1
        self.node_count += 1
        if self.node_count > _MAX_NODES or self.depth > _MAX_DEPTH:
            _fail(HkelRetainedStructureErrorCode.XML_LIMIT_EXCEEDED)
        attribute_count = len(element.attrib)
        if attribute_count > _MAX_ATTRIBUTES:
            _fail(HkelRetainedStructureErrorCode.XML_LIMIT_EXCEEDED)
        self.maximum_depth = max(self.maximum_depth, self.depth)
        self.maximum_attribute_count = max(self.maximum_attribute_count, attribute_count)
        self.element_names[element.tag] += 1
        _frame(self.structure, "START")
        _frame(self.structure, str(self.depth))
        _frame(self.structure, element.tag)
        _frame(self.value_binding, "START")
        _frame(self.value_binding, str(self.node_count))
        _frame(self.value_binding, element.tag)
        self._attributes(element)
        if self.node_count == 1:
            self.root_expanded_name = element.tag
            self.root_language = element.attrib.get(_LANGUAGE_ATTRIBUTE)
            self.root_schema_location = element.attrib.get(_SCHEMA_LOCATION_ATTRIBUTE)
        if element.tag.startswith(_XINCLUDE_PREFIX):
            _fail(HkelRetainedStructureErrorCode.XML_XINCLUDE_FORBIDDEN)

    def _attributes(self, element: ET.Element) -> None:
        for name, raw_value in sorted(element.attrib.items()):
            if type(name) is not str or type(raw_value) is not str:
                _fail(HkelRetainedStructureErrorCode.XML_INVALID)
            self.attribute_names[name] += 1
            _frame(self.structure, name)
            _frame(self.value_binding, name)
            _frame(self.value_binding, str(len(raw_value.encode("utf-8"))))
            _frame(
                self.value_binding,
                f"sha256:{sha256(raw_value.encode('utf-8')).hexdigest()}",
            )

    def _text_binding(self, role: str, value: str | None) -> None:
        raw = b"" if value is None else value.encode("utf-8")
        _frame(self.value_binding, role)
        _frame(self.value_binding, str(len(raw)))
        _frame(self.value_binding, f"sha256:{sha256(raw).hexdigest()}")

    def end(self, element: ET.Element) -> None:
        """Account one end event and release the completed subtree."""
        if type(element.tag) is not str:
            _fail(HkelRetainedStructureErrorCode.XML_INVALID)
        _frame(self.structure, "END")
        _frame(self.structure, str(self.depth))
        _frame(self.structure, element.tag)
        _frame(self.value_binding, "END")
        _frame(self.value_binding, str(self.depth))
        _frame(self.value_binding, element.tag)
        self._text_binding("TEXT", element.text)
        self._text_binding("TAIL", element.tail)
        self.depth -= 1
        element.clear()

    def result(self, expected_root_language: str) -> _ParsedStructure:
        """Seal the text-free parse facts after the member reached EOF."""
        root = self.root_expanded_name
        if (
            self.node_count == 0
            or self.depth != 0
            or root not in _ALLOWED_ROOTS
            or self.root_schema_location != _SCHEMA_LOCATION
        ):
            _fail(HkelRetainedStructureErrorCode.ROOT_PROFILE_INVALID)
        issue_codes = (
            (HkelRetainedStructureIssueCode.ARCHIVE_ROOT_LANGUAGE_CONFLICT,)
            if self.root_language != expected_root_language
            else ()
        )
        return _ParsedStructure(
            root,
            self.node_count,
            self.maximum_depth,
            self.maximum_attribute_count,
            _count_values(self.element_names),
            _count_values(self.attribute_names),
            f"sha256:{self.structure.hexdigest()}",
            f"sha256:{self.value_binding.hexdigest()}",
            issue_codes,
        )


def _parse_member(
    guarded: _InertMemberStream,
    expected_root_language: str,
) -> _ParsedStructure:
    accumulator = _ParseAccumulator()
    # The byte stream is independently bounded and rejects declarations first.
    events = ET.iterparse(guarded, events=("start", "end"))  # noqa: S314
    for event, element in events:
        if event == "start":
            accumulator.start(element)
        else:
            accumulator.end(element)
    guarded.verify_complete()
    return accumulator.result(expected_root_language)


def _profile_member(
    archive: zipfile.ZipFile,
    target: _TargetMember,
) -> HkelRetainedXmlStructureProfile:
    member = target.member
    info = _matching_info(archive, member)
    try:
        with archive.open(info, "r") as raw_member:
            guarded = _InertMemberStream(raw_member, member)
            parsed = _parse_member(guarded, target.expected_root_language)
    except HkelRetainedStructureError:
        raise
    except (ET.ParseError, LookupError, UnicodeError, ValueError) as error:
        raise HkelRetainedStructureError(HkelRetainedStructureErrorCode.XML_INVALID) from error
    except Exception as error:
        raise HkelRetainedStructureError(HkelRetainedStructureErrorCode.ARCHIVE_INVALID) from error
    profile_fingerprint = _member_profile_fingerprint(member, parsed)
    return HkelRetainedXmlStructureProfile(
        member.archive_endpoint_id,
        member.archive_fingerprint,
        member.canonical_path,
        member.member_fingerprint,
        member.chapter_id or "",
        member.version_signal or "",
        member.language or "",
        parsed.root_expanded_name,
        parsed.node_count,
        parsed.maximum_depth,
        parsed.maximum_attribute_count,
        parsed.element_counts,
        parsed.attribute_counts,
        parsed.structure_fingerprint,
        parsed.value_binding_fingerprint,
        profile_fingerprint,
        parsed.issue_codes,
        _NONE,
    )


def _read_profiles(
    validated: _ValidatedInput,
    reader: HkelRetainedEvidenceReader,
) -> dict[tuple[str, str, str], HkelRetainedXmlStructureProfile]:
    profiles: dict[tuple[str, str, str], HkelRetainedXmlStructureProfile] = {}
    for endpoint_id in sorted(validated.targets_by_endpoint):
        endpoint = validated.endpoint_by_id[endpoint_id]
        reference = HkelRetainedObjectReference(
            endpoint.reference.logical_key,
            endpoint.reference.fingerprint,
            endpoint.reference.byte_length,
        )
        try:
            with reader.open_exact(reference) as stream:
                _verify_archive_stream(endpoint, stream)
                with zipfile.ZipFile(stream, "r") as archive:
                    for target in validated.targets_by_endpoint[endpoint_id]:
                        profile = _profile_member(archive, target)
                        key = (*target.pair_key, profile.language)
                        if key in profiles:
                            _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
                        profiles[key] = profile
        except HkelRetainedStructureError:
            raise
        except Exception as error:
            raise HkelRetainedStructureError(
                HkelRetainedStructureErrorCode.OBJECT_READ_FAILED
            ) from error
    return profiles


def _read_xsd(
    index: HkelRetainedSourceObservationIndex,
    reader: HkelRetainedEvidenceReader,
) -> bytes:
    reference = index.xsd_reference.reference
    if reference.byte_length > _MAX_XSD_BYTES:
        _fail(HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID)
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
                    _fail(HkelRetainedStructureErrorCode.OBJECT_READ_FAILED)
                body.extend(chunk)
                digest.update(chunk)
                if len(body) > reference.byte_length:
                    _fail(HkelRetainedStructureErrorCode.OBJECT_READ_FAILED)
    except HkelRetainedStructureError:
        raise
    except Exception as error:
        raise HkelRetainedStructureError(
            HkelRetainedStructureErrorCode.OBJECT_READ_FAILED
        ) from error
    if (
        len(body) != reference.byte_length
        or f"sha256:{digest.hexdigest()}" != reference.fingerprint
    ):
        _fail(HkelRetainedStructureErrorCode.OBJECT_READ_FAILED)
    return bytes(body)


def _inert_xsd_text(raw: bytes) -> None:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HkelRetainedStructureError(
            HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID
        ) from error
    declaration = _XML_DECLARATION_ENCODING.match(decoded)
    upper = decoded.upper()
    if (
        "\x00" in decoded
        or "<!DOCTYPE" in upper
        or "<!ENTITY" in upper
        or (
            declaration is not None
            and declaration.group("encoding").lower().replace("_", "-") != "utf-8"
        )
    ):
        _fail(HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID)


class _XsdAccumulator:
    """Small structural projection of the retained XSD profile."""

    def __init__(self) -> None:
        self.root_attributes: dict[str, str] | None = None
        self.imports: list[tuple[str, str | None]] = []
        self.root_declarations: dict[str, str] = {}
        self.depth = 0

    def start(self, element: ET.Element) -> None:
        """Account one XSD start event without retaining the schema tree."""
        if type(element.tag) is not str:
            _fail(HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID)
        self.depth += 1
        if self.depth == 1:
            if element.tag != f"{_XSD_PREFIX}schema":
                _fail(HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID)
            self.root_attributes = dict(element.attrib)
        elif self.depth == _SCHEMA_CHILD_DEPTH:
            self._schema_child(element)
        if element.tag.startswith(_XINCLUDE_PREFIX):
            _fail(HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID)

    def _schema_child(self, element: ET.Element) -> None:
        local_name = element.tag.removeprefix(_XSD_PREFIX)
        if element.tag in {
            f"{_XSD_PREFIX}include",
            f"{_XSD_PREFIX}redefine",
        }:
            _fail(HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID)
        if element.tag == f"{_XSD_PREFIX}import":
            namespace = element.attrib.get("namespace")
            if namespace is None:
                _fail(HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID)
            self.imports.append((namespace, element.attrib.get("schemaLocation")))
        elif local_name == "element":
            name = element.attrib.get("name")
            declared_type = element.attrib.get("type")
            if name is not None and declared_type is not None:
                self.root_declarations[name] = declared_type

    def end(self, element: ET.Element) -> None:
        """Release one completed schema subtree."""
        self.depth -= 1
        element.clear()

    def result(self) -> tuple[str, str, str, str, tuple[tuple[str, str | None], ...]]:
        """Validate and return the exact retained schema relationship facts."""
        if self.depth != 0 or self.root_attributes is None:
            _fail(HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID)
        expected_attributes = {
            "targetNamespace": _HKLM_NAMESPACE,
            "version": "1.0",
            "elementFormDefault": "qualified",
            "attributeFormDefault": "unqualified",
        }
        if (
            self.root_attributes != expected_attributes
            or tuple(self.imports) != _EXPECTED_XSD_IMPORTS
            or any(self.root_declarations.get(name) != "LawDocType" for name in _ROOT_LOCAL_NAMES)
        ):
            _fail(HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID)
        return (
            expected_attributes["targetNamespace"],
            expected_attributes["version"],
            expected_attributes["elementFormDefault"],
            expected_attributes["attributeFormDefault"],
            tuple(self.imports),
        )


def _xsd_facts(
    raw: bytes,
) -> tuple[str, str, str, str, tuple[tuple[str, str | None], ...]]:
    _inert_xsd_text(raw)
    accumulator = _XsdAccumulator()
    try:
        events = ET.iterparse(io.BytesIO(raw), events=("start", "end"))  # noqa: S314
        for event, element in events:
            if event == "start":
                accumulator.start(element)
            else:
                accumulator.end(element)
    except HkelRetainedStructureError:
        raise
    except (ET.ParseError, LookupError, UnicodeError, ValueError) as error:
        raise HkelRetainedStructureError(
            HkelRetainedStructureErrorCode.SCHEMA_PROFILE_INVALID
        ) from error
    return accumulator.result()


def _schema_profile(
    index: HkelRetainedSourceObservationIndex,
    reader: HkelRetainedEvidenceReader,
) -> HkelRetainedSchemaProfile:
    target_namespace, version, element_form, attribute_form, imports = _xsd_facts(
        _read_xsd(index, reader)
    )
    root_namespace_fingerprint = _fingerprint(("HKEL_ROOT_NAMESPACE_1.0.0", _HKLM_NAMESPACE))
    schema_location_fingerprint = _fingerprint(("HKEL_SCHEMA_LOCATION_1.0.0", _SCHEMA_LOCATION))
    xsd_fingerprint = index.xsd_reference.reference.fingerprint
    profile_fingerprint = _fingerprint(
        (
            _PROFILE_ID,
            xsd_fingerprint,
            index.publication_profile_fingerprint,
            target_namespace,
            version,
            element_form,
            attribute_form,
            *_ROOT_LOCAL_NAMES,
            *(f"{namespace}:{location or ''}" for namespace, location in imports),
            root_namespace_fingerprint,
            schema_location_fingerprint,
            _SCHEMA_VALIDATION_NOT_PERFORMED,
            _NONE,
        )
    )
    return HkelRetainedSchemaProfile(
        _PROFILE_ID,
        xsd_fingerprint,
        index.publication_profile_fingerprint,
        target_namespace,
        version,
        element_form,
        attribute_form,
        _ROOT_LOCAL_NAMES,
        imports,
        root_namespace_fingerprint,
        schema_location_fingerprint,
        _SCHEMA_VALIDATION_NOT_PERFORMED,
        profile_fingerprint,
        _NONE,
    )


def _record(
    pair: HkelRetainedBilingualXmlPair,
    profiles: dict[tuple[str, str, str], HkelRetainedXmlStructureProfile],
) -> HkelRetainedBilingualStructureRecord:
    try:
        english = profiles[(pair.chapter_id, pair.version_signal, "en")]
        traditional_chinese = profiles[(pair.chapter_id, pair.version_signal, "zh-Hant")]
    except KeyError as error:
        raise HkelRetainedStructureError(HkelRetainedStructureErrorCode.INDEX_INVALID) from error
    observed = set(english.issue_codes) | set(traditional_chinese.issue_codes)
    if english.root_expanded_name != traditional_chinese.root_expanded_name:
        observed.add(HkelRetainedStructureIssueCode.BILINGUAL_ROOT_KIND_CONFLICT)
    issue_codes = tuple(code for code in HkelRetainedStructureIssueCode if code in observed)
    review_state = "REVIEW_REQUIRED" if issue_codes else "NO_REVIEW_REQUIRED"
    record_fingerprint = _fingerprint(
        (
            "HKEL_RETAINED_BILINGUAL_STRUCTURE_RECORD_1.0.0",
            pair.chapter_id,
            pair.version_signal,
            english.profile_fingerprint,
            traditional_chinese.profile_fingerprint,
            *(item.value for item in issue_codes),
            review_state,
            _NONE,
        )
    )
    return HkelRetainedBilingualStructureRecord(
        pair.chapter_id,
        pair.version_signal,
        english,
        traditional_chinese,
        issue_codes,
        review_state,
        record_fingerprint,
        _NONE,
    )


def _profile_retained_hkel_structure(
    index: object,
    reader: HkelRetainedEvidenceReader,
) -> HkelRetainedStructureResult:
    validated = _validated_input(index)
    schema_profile = _schema_profile(validated.index, reader)
    profiles = _read_profiles(validated, reader)
    records = tuple(
        _record(pair, profiles)
        for pair in sorted(
            validated.index.bilingual_xml_pairs,
            key=lambda item: (item.chapter_id, item.version_signal),
        )
    )
    if len(profiles) != len(records) * 2:
        _fail(HkelRetainedStructureErrorCode.INDEX_INVALID)
    counts = Counter(code for record in records for code in record.issue_codes)
    issue_counts = tuple(
        HkelRetainedStructureIssueCount(code, counts[code])
        for code in HkelRetainedStructureIssueCode
        if counts[code]
    )
    review_required = sum(record.review_state == "REVIEW_REQUIRED" for record in records)
    maximum_depth = max(
        max(record.english.maximum_depth, record.traditional_chinese.maximum_depth)
        for record in records
    )
    result_fingerprint = _fingerprint(
        (
            "HKEL_RETAINED_STRUCTURE_RESULT_1.0.0",
            validated.index.source_observation_fingerprint,
            schema_profile.profile_fingerprint,
            *(record.record_fingerprint for record in records),
            *(f"{item.issue_code.value}:{item.count}" for item in issue_counts),
            str(review_required),
            str(maximum_depth),
            _NONE,
        )
    )
    return HkelRetainedStructureResult(
        validated.index.source_observation_fingerprint,
        schema_profile,
        records,
        issue_counts,
        review_required,
        maximum_depth,
        result_fingerprint,
        _NONE,
    )


def profile_retained_hkel_structure(
    index: object,
    reader: HkelRetainedEvidenceReader,
) -> HkelRetainedStructureResult:
    """Profile every retained bilingual XML pair without emitting source text."""
    failure: HkelRetainedStructureErrorCode | None = None
    try:
        return _profile_retained_hkel_structure(index, reader)
    except HkelRetainedStructureError as error:
        failure = error.code
    _fail(failure)
