"""Deterministic hostile-content and transport admission checks."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from asklegal_evidence_vault import HostileClassification, HostileReason

from .model import EndpointContract, SyntheticResponse


@dataclass(frozen=True, slots=True)
class ResponseAdmissionPolicy:
    """Closed local hostile-response thresholds."""

    max_archive_depth: int = 2
    max_expansion_ratio: int = 100

    def __post_init__(self) -> None:
        if type(self.max_archive_depth) is not int or self.max_archive_depth < 0:
            raise TypeError("max_archive_depth must be a non-negative exact integer")
        if type(self.max_expansion_ratio) is not int or self.max_expansion_ratio < 1:
            raise TypeError("max_expansion_ratio must be a positive exact integer")


@dataclass(frozen=True, slots=True)
class ContentAdmissionInput:
    """Transport-neutral inert bytes and their declared envelope."""

    body: bytes
    media_type: str
    max_bytes: int
    declared_length: int
    truncated: bool
    character_encoding: str


def admit_response(
    response: SyntheticResponse,
    endpoint: EndpointContract,
    policy: ResponseAdmissionPolicy,
) -> HostileClassification:
    """Classify exact inert bytes without executing active source content."""
    if type(response) is not SyntheticResponse or type(endpoint) is not EndpointContract:
        raise TypeError("response and endpoint must be exact M4 values")
    if type(policy) is not ResponseAdmissionPolicy:
        raise TypeError("policy must be an exact ResponseAdmissionPolicy")
    content_classification = classify_content(
        ContentAdmissionInput(
            body=response.body,
            media_type=response.media_type,
            max_bytes=endpoint.max_bytes,
            declared_length=response.declared_length,
            truncated=response.truncated,
            character_encoding=response.character_encoding,
        ),
        policy,
    )
    reasons = set(content_classification.reasons)
    if response.host != endpoint.allowed_host or not response.path.startswith(
        endpoint.allowed_path_prefix
    ):
        reasons.add(HostileReason.PATH_TRAVERSAL)
    if response.redirect_host not in endpoint.redirect_hosts:
        reasons.add(HostileReason.PATH_TRAVERSAL)
    if response.media_type not in endpoint.media_types:
        reasons.add(HostileReason.MEDIA_TYPE)
    ordered = tuple(sorted(reasons, key=lambda item: item.value))
    return HostileClassification(not ordered, ordered)


def classify_content(
    content: ContentAdmissionInput,
    policy: ResponseAdmissionPolicy,
) -> HostileClassification:
    """Classify bounded inert content independently of any transport adapter."""
    if type(content) is not ContentAdmissionInput:
        raise TypeError("content must be an exact ContentAdmissionInput")
    body = content.body
    media_type = content.media_type
    max_bytes = content.max_bytes
    declared_length = content.declared_length
    truncated = content.truncated
    character_encoding = content.character_encoding
    if type(body) is not bytes:
        raise TypeError("body must be exact bytes")
    if type(media_type) is not str or not media_type:
        raise TypeError("media_type must be an exact non-empty string")
    if type(max_bytes) is not int or max_bytes < 1:
        raise TypeError("max_bytes must be a positive exact integer")
    if type(declared_length) is not int or declared_length < 0:
        raise TypeError("declared_length must be a non-negative exact integer")
    if type(truncated) is not bool:
        raise TypeError("truncated must be an exact boolean")
    if type(character_encoding) is not str or not character_encoding:
        raise TypeError("character_encoding must be an exact non-empty string")
    if type(policy) is not ResponseAdmissionPolicy:
        raise TypeError("policy must be an exact ResponseAdmissionPolicy")
    reasons: set[HostileReason] = set()
    if len(body) > max_bytes:
        reasons.add(HostileReason.SIZE_LIMIT)
    if declared_length != len(body):
        reasons.add(HostileReason.LENGTH_MISMATCH)
    if truncated:
        reasons.add(HostileReason.TRUNCATED)
    if character_encoding.lower() not in {"binary", "utf-8"}:
        reasons.add(HostileReason.ENCODING_DECLARATION)
    lowered = body.lower()
    if b"eicar-standard-antivirus-test-file" in lowered:
        reasons.add(HostileReason.MALWARE_SIGNATURE)
    if media_type in {"text/html", "application/xhtml+xml"} and (
        b"<script" in lowered or b"javascript:" in lowered
    ):
        reasons.add(HostileReason.ACTIVE_CONTENT)
    if media_type in {
        "application/xml",
        "application/rss+xml",
        "application/xhtml+xml",
        "text/xml",
    } and (b"<!doctype" in lowered or b"<!entity" in lowered):
        reasons.add(HostileReason.ACTIVE_CONTENT)
    if media_type in {"application/zip", "application/x-zip-compressed"}:
        reasons.update(_archive_reasons(body, policy, depth=0))
    ordered = tuple(sorted(reasons, key=lambda item: item.value))
    return HostileClassification(not ordered, ordered)


def _archive_reasons(
    content: bytes,
    policy: ResponseAdmissionPolicy,
    *,
    depth: int,
) -> set[HostileReason]:
    reasons: set[HostileReason] = set()
    if depth > policy.max_archive_depth:
        return {HostileReason.ARCHIVE_RECURSION}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            total_compressed = 0
            total_uncompressed = 0
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts:
                    reasons.add(HostileReason.PATH_TRAVERSAL)
                total_compressed += max(info.compress_size, 1)
                total_uncompressed += info.file_size
                if info.filename.lower().endswith(".zip"):
                    if depth >= policy.max_archive_depth:
                        reasons.add(HostileReason.ARCHIVE_RECURSION)
                    else:
                        reasons.update(
                            _archive_reasons(archive.read(info), policy, depth=depth + 1)
                        )
            if total_uncompressed > total_compressed * policy.max_expansion_ratio:
                reasons.add(HostileReason.DECOMPRESSION_RATIO)
    except OSError, ValueError, zipfile.BadZipFile:
        reasons.add(HostileReason.TRUNCATED)
    return reasons
