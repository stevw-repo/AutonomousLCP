"""Source-neutral authentic admission for one HKeL current-data archive."""

from __future__ import annotations

import codecs
import re
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from io import BytesIO
from typing import IO, Never
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_MEMBER = re.compile(
    r"^(?P<chapter>(?:cap_[0-9A-Z]+|A[0-9A-Z]+))_"
    r"(?P<language>en|zh-Hant|zh-Hans)_c/"
    r"(?P=chapter)_(?P<version>[0-9]{14}|-{14})_"
    r"(?P=language)_c\.xml$"
)
_XML_DECLARATION_ENCODING = re.compile(
    r'^\ufeff?<\?xml\b[^>]*\bencoding\s*=\s*["\'](?P<encoding>[^"\']+)["\']',
    re.IGNORECASE,
)
_HKLM_NAMESPACE = "http://www.xml.gov.hk/schemas/hklm/1.0"
_XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
_XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
_XINCLUDE_PREFIX = "{http://www.w3.org/2001/XInclude}"
_SCHEMA_LOCATION = (
    "http://www.xml.gov.hk/schemas/hklm/1.0 https://www.elegislation.gov.hk/schemas/hklm.xsd"
)
_SCHEMA_LOCATION_ATTRIBUTE = f"{{{_XSI_NAMESPACE}}}schemaLocation"
_LANGUAGE_ATTRIBUTE = f"{{{_XML_NAMESPACE}}}lang"
_ALLOWED_ROOTS = frozenset(
    f"{{{_HKLM_NAMESPACE}}}{name}" for name in ("lawDoc", "ordinance", "resolution", "subLeg")
)
_SOURCE_ROLE = "HK_LEG_HKEL_CURRENT_DATA"
_PROFILE_ID = "HKEL_CURRENT_ARCHIVE_ADMISSION_1.0.0"
_ARCHIVE_LANGUAGE = {
    **{f"sep_{value:048x}": ("en", "en") for value in range(10, 14)},
    **{f"sep_{value:048x}": ("zh-Hant", "zh-Hant-HK") for value in range(14, 18)},
    **{f"sep_{value:048x}": ("zh-Hans", "zh-Hans-HK") for value in range(18, 22)},
}
_MAX_ARCHIVE_MEMBERS = 4_096
_MAX_MEMBER_BYTES = 32 << 20
_MAX_EXPANDED_BYTES = 1 << 30
_MAX_COMPRESSION_RATIO = 100
_MAX_NODES = 250_000
_MAX_DEPTH = 64
_MAX_ATTRIBUTES = 64
_READ_CHUNK = 64 << 10
_SCAN_TAIL = 16
_DECLARATION_PREFIX = 1_024


class HkelArchiveAdmissionErrorCode(StrEnum):
    """Closed reasons one changed archive cannot be treated as authentic HKeL."""

    IDENTITY_INVALID = "HKEL_ARCHIVE_IDENTITY_INVALID"
    OBJECT_INVALID = "HKEL_ARCHIVE_OBJECT_INVALID"
    ARCHIVE_INVALID = "HKEL_ARCHIVE_INVALID"
    MEMBER_INVALID = "HKEL_ARCHIVE_MEMBER_INVALID"
    LIMIT_EXCEEDED = "HKEL_ARCHIVE_LIMIT_EXCEEDED"
    XML_INVALID = "HKEL_ARCHIVE_XML_INVALID"
    XML_DECLARATION_FORBIDDEN = "HKEL_ARCHIVE_XML_DECLARATION_FORBIDDEN"
    ROOT_PROFILE_INVALID = "HKEL_ARCHIVE_ROOT_PROFILE_INVALID"


class HkelArchiveAdmissionError(ValueError):
    """One normalized changed-archive rejection without retained source bytes."""

    code: HkelArchiveAdmissionErrorCode

    def __init__(self, code: HkelArchiveAdmissionErrorCode) -> None:
        """Create one normalized admission failure."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HkelCurrentArchiveAdmission:
    """Detached proof that every member crossed the authentic archive contract."""

    endpoint_id: str
    source_role: str
    content_fingerprint: str
    language: str
    member_count: int
    profile_id: str


def _fail(code: HkelArchiveAdmissionErrorCode) -> Never:
    raise HkelArchiveAdmissionError(code)


class _InertXmlStream:
    """Bounded UTF-8 stream that sees forbidden declarations across every chunk."""

    def __init__(self, source: IO[bytes], expected_bytes: int) -> None:
        self._source = source
        self._expected_bytes = expected_bytes
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._byte_count = 0
        self._scan_tail = ""
        self._declaration_prefix = ""
        self._declaration_complete = False
        self._eof = False

    def _inspect(self, decoded: str) -> None:
        if "\x00" in decoded:
            _fail(HkelArchiveAdmissionErrorCode.XML_INVALID)
        probe = (self._scan_tail + decoded).upper()
        if "<!DOCTYPE" in probe or "<!ENTITY" in probe:
            _fail(HkelArchiveAdmissionErrorCode.XML_DECLARATION_FORBIDDEN)
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
        end = declaration_probe.find("?>")
        if end < 0:
            if len(self._declaration_prefix) >= _DECLARATION_PREFIX:
                _fail(HkelArchiveAdmissionErrorCode.XML_INVALID)
            return
        declaration = _XML_DECLARATION_ENCODING.match(self._declaration_prefix)
        if declaration is not None and (
            declaration.group("encoding").lower().replace("_", "-") != "utf-8"
        ):
            _fail(HkelArchiveAdmissionErrorCode.XML_INVALID)
        self._declaration_complete = True

    def read(self, size: int = -1) -> bytes:
        if self._eof:
            return b""
        requested = _READ_CHUNK if size < 0 or size > _READ_CHUNK else size
        try:
            chunk = self._source.read(requested)
        except Exception as error:
            raise HkelArchiveAdmissionError(
                HkelArchiveAdmissionErrorCode.ARCHIVE_INVALID
            ) from error
        if type(chunk) is not bytes:
            _fail(HkelArchiveAdmissionErrorCode.ARCHIVE_INVALID)
        if not chunk:
            try:
                decoded = self._decoder.decode(b"", final=True)
            except UnicodeDecodeError as error:
                raise HkelArchiveAdmissionError(
                    HkelArchiveAdmissionErrorCode.XML_INVALID
                ) from error
            self._inspect(decoded)
            self._eof = True
            return b""
        self._byte_count += len(chunk)
        if self._byte_count > self._expected_bytes or self._byte_count > _MAX_MEMBER_BYTES:
            _fail(HkelArchiveAdmissionErrorCode.LIMIT_EXCEEDED)
        try:
            decoded = self._decoder.decode(chunk, final=False)
        except UnicodeDecodeError as error:
            raise HkelArchiveAdmissionError(HkelArchiveAdmissionErrorCode.XML_INVALID) from error
        self._inspect(decoded)
        return chunk

    def verify_complete(self) -> None:
        if not self._eof or self._byte_count != self._expected_bytes:
            _fail(HkelArchiveAdmissionErrorCode.MEMBER_INVALID)


def _canonical_member_name(value: str) -> str:
    """Accept the publisher's one separator spelling without creating a path alias."""
    if "\\" in value:
        if "/" in value:
            _fail(HkelArchiveAdmissionErrorCode.MEMBER_INVALID)
        return value.replace("\\", "/")
    return value


def _validate_info(info: ZipInfo, expected_language: str) -> str:
    canonical_name = _canonical_member_name(info.filename)
    match = _MEMBER.fullmatch(canonical_name)
    unix_mode = info.external_attr >> 16
    if (
        match is None
        or match.group("language") != expected_language
        or info.is_dir()
        or stat.S_IFMT(unix_mode) not in {0, stat.S_IFREG}
        or info.flag_bits & 0x1
        or info.compress_type != ZIP_DEFLATED
        or info.file_size <= 0
        or info.file_size > _MAX_MEMBER_BYTES
        or info.compress_size <= 0
        or info.file_size > info.compress_size * _MAX_COMPRESSION_RATIO
    ):
        _fail(HkelArchiveAdmissionErrorCode.MEMBER_INVALID)
    return canonical_name


def _parse_member(archive: ZipFile, info: ZipInfo, expected_root_language: str) -> None:
    depth = 0
    nodes = 0
    root_name: str | None = None
    root_language: str | None = None
    root_schema: str | None = None
    try:
        with archive.open(info, "r") as source:
            guarded = _InertXmlStream(source, info.file_size)
            events = ET.iterparse(guarded, events=("start", "end"))  # noqa: S314
            for event, element in events:
                if event == "start":
                    depth += 1
                    nodes += 1
                    if (
                        nodes > _MAX_NODES
                        or depth > _MAX_DEPTH
                        or len(element.attrib) > _MAX_ATTRIBUTES
                        or type(element.tag) is not str
                        or element.tag.startswith(_XINCLUDE_PREFIX)
                    ):
                        _fail(HkelArchiveAdmissionErrorCode.XML_INVALID)
                    if nodes == 1:
                        root_name = element.tag
                        root_language = element.attrib.get(_LANGUAGE_ATTRIBUTE)
                        root_schema = element.attrib.get(_SCHEMA_LOCATION_ATTRIBUTE)
                else:
                    depth -= 1
                    element.clear()
            guarded.verify_complete()
    except HkelArchiveAdmissionError:
        raise
    except (BadZipFile, ET.ParseError, LookupError, UnicodeError, ValueError) as error:
        raise HkelArchiveAdmissionError(HkelArchiveAdmissionErrorCode.XML_INVALID) from error
    if (
        depth != 0
        or nodes == 0
        or root_name not in _ALLOWED_ROOTS
        or root_language != expected_root_language
        or root_schema != _SCHEMA_LOCATION
    ):
        _fail(HkelArchiveAdmissionErrorCode.ROOT_PROFILE_INVALID)


def admit_hkel_current_archive(
    *,
    endpoint_id: object,
    source_role: object,
    content_fingerprint: object,
    body: object,
) -> HkelCurrentArchiveAdmission:
    """Read and parse every exact XML member of one registered current archive."""
    if type(endpoint_id) is not str or type(source_role) is not str:
        _fail(HkelArchiveAdmissionErrorCode.IDENTITY_INVALID)
    profile = _ARCHIVE_LANGUAGE.get(endpoint_id)
    if profile is None or source_role != _SOURCE_ROLE:
        _fail(HkelArchiveAdmissionErrorCode.IDENTITY_INVALID)
    if (
        type(content_fingerprint) is not str
        or _FINGERPRINT.fullmatch(content_fingerprint) is None
        or type(body) is not bytes
        or not body
        or f"sha256:{sha256(body).hexdigest()}" != content_fingerprint
    ):
        _fail(HkelArchiveAdmissionErrorCode.OBJECT_INVALID)
    expected_language, expected_root_language = profile
    try:
        with ZipFile(BytesIO(body), "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > _MAX_ARCHIVE_MEMBERS:
                _fail(HkelArchiveAdmissionErrorCode.LIMIT_EXCEEDED)
            names: set[str] = set()
            folded: set[str] = set()
            expanded = 0
            for info in infos:
                canonical_name = _validate_info(info, expected_language)
                if canonical_name in names or canonical_name.casefold() in folded:
                    _fail(HkelArchiveAdmissionErrorCode.MEMBER_INVALID)
                names.add(canonical_name)
                folded.add(canonical_name.casefold())
                expanded += info.file_size
                if expanded > _MAX_EXPANDED_BYTES:
                    _fail(HkelArchiveAdmissionErrorCode.LIMIT_EXCEEDED)
                _parse_member(archive, info, expected_root_language)
    except HkelArchiveAdmissionError:
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError) as error:
        raise HkelArchiveAdmissionError(HkelArchiveAdmissionErrorCode.ARCHIVE_INVALID) from error
    return HkelCurrentArchiveAdmission(
        endpoint_id,
        source_role,
        content_fingerprint,
        expected_language,
        len(infos),
        _PROFILE_ID,
    )
