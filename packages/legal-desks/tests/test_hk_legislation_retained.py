"""Hostile retained-archive tests for the pre-admission HKeL member index."""

from __future__ import annotations

import gc
import io
import stat
import tracemalloc
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from typing import BinaryIO

import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks.hk_legislation_retained import (
    HkelRetainedAttemptReference,
    HkelRetainedEvidenceError,
    HkelRetainedObjectReference,
    index_retained_hkel_observation,
)

_ATTEMPT_ID = "hkel-live-baseline-basic-law20-fixture"
_CUTOFF = "2026-08-28T22:20:23+08:00"
_ARCHIVES = (
    ("sep_00000000000000000000000000000000000000000000000a", "en", 0, 1377),
    ("sep_00000000000000000000000000000000000000000000000b", "en", 1377, 1380),
    ("sep_00000000000000000000000000000000000000000000000c", "en", 2757, 338),
    ("sep_00000000000000000000000000000000000000000000000d", "en", 3095, 62),
    (
        "sep_00000000000000000000000000000000000000000000000e",
        "zh-Hant",
        0,
        1377,
    ),
    (
        "sep_00000000000000000000000000000000000000000000000f",
        "zh-Hant",
        1377,
        1380,
    ),
    ("sep_000000000000000000000000000000000000000000000010", "zh-Hant", 2757, 338),
    ("sep_000000000000000000000000000000000000000000000011", "zh-Hant", 3095, 62),
    ("sep_000000000000000000000000000000000000000000000012", "zh-Hans", 0, 1377),
    ("sep_000000000000000000000000000000000000000000000013", "zh-Hans", 1377, 1380),
    ("sep_000000000000000000000000000000000000000000000014", "zh-Hans", 2757, 338),
    ("sep_000000000000000000000000000000000000000000000015", "zh-Hans", 3095, 62),
)
_SPECIFICATION_IDS = (
    "sep_000000000000000000000000000000000000000000000035",
    "sep_000000000000000000000000000000000000000000000036",
    "sep_000000000000000000000000000000000000000000000037",
    "sep_000000000000000000000000000000000000000000000038",
    "sep_000000000000000000000000000000000000000000000039",
    "sep_00000000000000000000000000000000000000000000003a",
    "sep_000000000000000000000000000000000000000000000051",
)


class _Reader:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values
        self.calls: list[HkelRetainedObjectReference] = []

    @contextmanager
    def open_exact(self, reference: HkelRetainedObjectReference) -> Generator[BinaryIO]:
        self.calls.append(reference)
        yield io.BytesIO(self.values[reference.logical_key])


def _canonical(value: JsonValue) -> bytes:
    return canonicalize(checked_json_value(value))


def _zip(entries: tuple[tuple[str, bytes, zipfile.ZipInfo | None], ...]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body, info in entries:
            if info is None:
                archive.writestr(name, body)
            else:
                archive.writestr(info, body)
    return target.getvalue()


def _archive_body(language: str, offset: int, count: int) -> bytes:
    entries: list[tuple[str, bytes, zipfile.ZipInfo | None]] = []
    for index in range(offset, offset + count):
        chapter = f"cap_{index + 1:04d}"
        version = "20260828000000"
        name = f"{chapter}_{language}_c\\{chapter}_{version}_{language}_c.xml"
        body = f'<legislation chapter="{chapter}" version="{version}"/>'.encode()
        entries.append((name, body, None))
    return _zip(tuple(entries))


def _endpoint(endpoint_id: str, body: bytes, media_type: str) -> dict[str, JsonValue]:
    digest = sha256(body).hexdigest()
    return {
        "body_fingerprint": f"sha256:{digest}",
        "byte_length": len(body),
        "endpoint_id": endpoint_id,
        "endpoint_version": "1.0.0",
        "media_type": media_type,
        "method": "GET",
        "object_key": f"objects/{digest}.bin",
        "requested_url": f"https://fixture.invalid/{endpoint_id}",
        "status": 200,
        "terminal_code": "CAPTURED",
    }


def _reference(logical_key: str, body: bytes) -> HkelRetainedObjectReference:
    return HkelRetainedObjectReference(
        logical_key=logical_key,
        fingerprint=f"sha256:{sha256(body).hexdigest()}",
        byte_length=len(body),
    )


def _fixture() -> tuple[HkelRetainedAttemptReference, _Reader]:
    values: dict[str, bytes] = {}
    endpoints: list[JsonValue] = []
    for endpoint_id, language, offset, count in _ARCHIVES:
        body = _archive_body(language, offset, count)
        endpoint = _endpoint(endpoint_id, body, "application/zip")
        endpoints.append(endpoint)
        values[str(endpoint["object_key"])] = body
    xsd = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'
    for index, endpoint_id in enumerate(_SPECIFICATION_IDS):
        if index == 0:
            body = xsd
            media_type = "application/xml"
        elif index < 4:
            body = f"%PDF-1.7\nfixture-{index}\n%%EOF\n".encode()
            media_type = "application/pdf"
        else:
            body = f"<html><body>specification-{index}</body></html>".encode()
            media_type = "text/html"
        endpoint = _endpoint(endpoint_id, body, media_type)
        endpoints.append(endpoint)
        values[str(endpoint["object_key"])] = body
    for index in range(56 - len(endpoints)):
        body = f"supporting-object-{index}".encode()
        endpoint = _endpoint(f"supporting-endpoint-{index:02d}", body, "application/octet-stream")
        endpoints.append(endpoint)
        values[str(endpoint["object_key"])] = body
    report: dict[str, JsonValue] = {
        "attempt_id": _ATTEMPT_ID,
        "authority_manifest_fingerprint": "sha256:" + "1" * 64,
        "authority_provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "change_state": "FIRST_OBSERVATION",
        "endpoint_counts": {"CAPTURED": 56},
        "endpoints": endpoints,
        "execution_authorization_fingerprint": "sha256:" + "2" * 64,
        "observation_cutoff": _CUTOFF,
        "predecessor_attempt_id": None,
        "readback_verified": True,
        "result": "COMPLETE",
        "source_family": "HKEL",
        "source_procedures": [
            {
                "declared_member_count": 20,
                "source_id": "HK-LEG-BASIC-LAW-PORTAL",
                "terminal_code": "COMPLETE",
            },
            {
                "declared_member_count": 12,
                "source_id": "HK-LEG-HKEL-CURRENT-DATA",
                "terminal_code": "COMPLETE",
            },
            {
                "declared_member_count": 3157,
                "source_id": "HK-LEG-HKEL-CURRENT-INVENTORY",
                "terminal_code": "COMPLETE",
            },
            {
                "declared_member_count": 2,
                "source_id": "HK-LEG-HKEL-EDITORIAL-RECORDS",
                "terminal_code": "COMPLETE",
            },
            {
                "declared_member_count": 7,
                "source_id": "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
                "terminal_code": "COMPLETE",
            },
        ],
    }
    report_body = _canonical(report)
    report_key = f"attempts/{_ATTEMPT_ID}/report.json"
    values[report_key] = report_body
    return (
        HkelRetainedAttemptReference(
            attempt_id=_ATTEMPT_ID,
            observation_cutoff=_CUTOFF,
            report=_reference(report_key, report_body),
        ),
        _Reader(values),
    )


def _replace_endpoint_body(
    reference: HkelRetainedAttemptReference,
    reader: _Reader,
    endpoint_id: str,
    body: bytes,
) -> HkelRetainedAttemptReference:
    report_raw = reader.values[reference.report.logical_key]
    report = parse_json_bytes(report_raw, max_bytes=len(report_raw))
    assert type(report) is dict
    endpoints = report["endpoints"]
    assert type(endpoints) is list
    for raw_endpoint in endpoints:
        assert type(raw_endpoint) is dict
        if raw_endpoint["endpoint_id"] != endpoint_id:
            continue
        prior_key = raw_endpoint["object_key"]
        assert type(prior_key) is str
        replacement = _endpoint(endpoint_id, body, str(raw_endpoint["media_type"]))
        raw_endpoint.clear()
        raw_endpoint.update(replacement)
        reader.values.pop(prior_key)
        reader.values[str(replacement["object_key"])] = body
        break
    else:  # pragma: no cover - fixture defect.
        raise AssertionError(endpoint_id)
    new_report = _canonical(report)
    reader.values[reference.report.logical_key] = new_report
    return replace(reference, report=_reference(reference.report.logical_key, new_report))


@pytest.fixture(scope="module")
def retained_fixture() -> tuple[HkelRetainedAttemptReference, _Reader]:
    return _fixture()


def test_retained_complete_attempt_builds_detached_bilingual_member_index(
    retained_fixture: tuple[HkelRetainedAttemptReference, _Reader],
) -> None:
    reference, original = retained_fixture
    reader = _Reader(dict(original.values))

    result = index_retained_hkel_observation(reference, reader)

    assert result.attempt_id == _ATTEMPT_ID
    assert result.observation_cutoff == _CUTOFF
    assert len(result.endpoint_objects) == 56
    assert len(result.archive_members) == 3157 * 3
    assert len(result.bilingual_xml_pairs) == 3157
    assert len(result.publication_specifications) == 7
    assert result.xsd_reference.endpoint_id == _SPECIFICATION_IDS[0]
    assert result.source_observation_fingerprint.startswith("sha256:")
    assert len(reader.calls) == 57
    assert reader.calls[0] == reference.report


def test_non_complete_attempt_rejects_before_member_read() -> None:
    reference, reader = _fixture()
    raw = parse_json_bytes(
        reader.values[reference.report.logical_key],
        max_bytes=reference.report.byte_length,
    )
    assert type(raw) is dict
    raw["result"] = "SOURCE_CONTRACT_CHANGED"
    body = _canonical(raw)
    reader.values[reference.report.logical_key] = body
    reference = replace(reference, report=_reference(reference.report.logical_key, body))

    with pytest.raises(HkelRetainedEvidenceError, match="RETAINED_REPORT_NOT_COMPLETE"):
        index_retained_hkel_observation(reference, reader)

    assert reader.calls == [reference.report]


def test_attempt_reference_requires_canonical_hong_kong_cutoff() -> None:
    reference, reader = _fixture()
    reference = replace(reference, observation_cutoff="2026-08-28T14:20:23Z")

    with pytest.raises(HkelRetainedEvidenceError, match="REFERENCE_INVALID"):
        index_retained_hkel_observation(reference, reader)

    assert reader.calls == []


@pytest.mark.parametrize("name", ["../escape.xml", "safe\\..\\escape.xml", "/abs.xml"])
def test_archive_member_traversal_is_rejected(name: str) -> None:
    reference, reader = _fixture()
    hostile = _zip(((name, b"<root/>", None),))
    reference = _replace_endpoint_body(reference, reader, _ARCHIVES[0][0], hostile)

    with pytest.raises(HkelRetainedEvidenceError, match="ARCHIVE_UNSAFE_MEMBER"):
        index_retained_hkel_observation(reference, reader)


def test_archive_symlink_is_rejected() -> None:
    reference, reader = _fixture()
    info = zipfile.ZipInfo("cap_0001_en_c\\cap_0001_20260828000000_en_c.xml")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    hostile = _zip(((info.filename, b"target", info),))
    reference = _replace_endpoint_body(reference, reader, _ARCHIVES[0][0], hostile)

    with pytest.raises(HkelRetainedEvidenceError, match="ARCHIVE_UNSAFE_MEMBER"):
        index_retained_hkel_observation(reference, reader)


def test_archive_casefold_collision_is_rejected() -> None:
    reference, reader = _fixture()
    hostile = _zip(
        (
            ("SAFE\\Member.xml", b"<root/>", None),
            ("safe\\member.xml", b"<root/>", None),
        )
    )
    reference = _replace_endpoint_body(reference, reader, _ARCHIVES[0][0], hostile)

    with pytest.raises(HkelRetainedEvidenceError, match="ARCHIVE_MEMBER_COLLISION"):
        index_retained_hkel_observation(reference, reader)


def test_archive_exact_duplicate_is_rejected() -> None:
    reference, reader = _fixture()
    name = "safe\\member.xml"
    with pytest.warns(UserWarning, match="Duplicate name"):
        hostile = _zip(((name, b"<root/>", None), (name, b"<root/>", None)))
    reference = _replace_endpoint_body(reference, reader, _ARCHIVES[0][0], hostile)

    with pytest.raises(HkelRetainedEvidenceError, match="ARCHIVE_MEMBER_COLLISION"):
        index_retained_hkel_observation(reference, reader)


def test_content_bearing_archive_directory_is_rejected() -> None:
    reference, reader = _fixture()
    info = zipfile.ZipInfo("hidden/")
    info.create_system = 3
    info.external_attr = (stat.S_IFDIR | 0o755) << 16
    hostile = _zip(((info.filename, b"unaccounted", info),))
    reference = _replace_endpoint_body(reference, reader, _ARCHIVES[0][0], hostile)

    with pytest.raises(HkelRetainedEvidenceError, match="ARCHIVE_UNSAFE_MEMBER"):
        index_retained_hkel_observation(reference, reader)


def test_archive_bomb_is_rejected_from_declared_size_and_ratio() -> None:
    reference, reader = _fixture()
    hostile = _zip((("safe\\bomb.bin", b"0" * (33 * 1024 * 1024), None),))
    reference = _replace_endpoint_body(reference, reader, _ARCHIVES[0][0], hostile)

    with pytest.raises(HkelRetainedEvidenceError, match="ARCHIVE_LIMIT_EXCEEDED"):
        index_retained_hkel_observation(reference, reader)


@pytest.mark.parametrize(
    "xml",
    [
        b"<legislation>",
        b'<!DOCTYPE x [<!ENTITY e "x">]><legislation>&e;</legislation>',
        (
            '<?xml version="1.0" encoding="utf-16"?>'
            '<!DOCTYPE x [<!ENTITY e "EXPANDED">]>'
            "<legislation>&e;</legislation>"
        ).encode("utf-16"),
        b'<?xml version="1.0" encoding="unknown-xml"?><legislation/>',
    ],
)
def test_malformed_or_entity_bearing_xml_is_rejected(xml: bytes) -> None:
    reference, reader = _fixture()
    name = "cap_0001_en_c\\cap_0001_20260828000000_en_c.xml"
    hostile = _zip(((name, xml, None),))
    reference = _replace_endpoint_body(reference, reader, _ARCHIVES[0][0], hostile)

    with pytest.raises(HkelRetainedEvidenceError, match="XML_INVALID"):
        index_retained_hkel_observation(reference, reader)


def test_bilingual_xml_pairing_requires_exact_chapter_and_version_match() -> None:
    reference, reader = _fixture()
    name = "cap_9999_en_c\\cap_9999_20260828000000_en_c.xml"
    hostile = _zip(((name, b"<legislation/>", None),))
    reference = _replace_endpoint_body(reference, reader, _ARCHIVES[0][0], hostile)

    with pytest.raises(HkelRetainedEvidenceError, match="BILINGUAL_PAIRING_INVALID"):
        index_retained_hkel_observation(reference, reader)


def test_xsd_and_specification_fingerprints_are_bound_to_exact_objects() -> None:
    reference, reader = _fixture()
    report = parse_json_bytes(
        reader.values[reference.report.logical_key],
        max_bytes=reference.report.byte_length,
    )
    assert type(report) is dict
    endpoints = report["endpoints"]
    assert type(endpoints) is list
    xsd = next(
        item
        for item in endpoints
        if type(item) is dict and item["endpoint_id"] == _SPECIFICATION_IDS[0]
    )
    object_key = xsd["object_key"]
    assert type(object_key) is str
    reader.values[object_key] = b"<not-the-retained-xsd/>"

    with pytest.raises(HkelRetainedEvidenceError, match="RETAINED_OBJECT_READ_FAILED"):
        index_retained_hkel_observation(reference, reader)


def test_malformed_retained_xsd_is_rejected_as_profile_binding_failure() -> None:
    reference, reader = _fixture()
    reference = _replace_endpoint_body(
        reference,
        reader,
        _SPECIFICATION_IDS[0],
        b"<xs:schema>",
    )

    with pytest.raises(HkelRetainedEvidenceError, match="SPECIFICATION_BINDING_INVALID"):
        index_retained_hkel_observation(reference, reader)


def test_large_supporting_object_is_verified_without_full_body_buffering() -> None:
    reference, reader = _fixture()
    body = b"0" * (40 << 20)
    reference = _replace_endpoint_body(reference, reader, "supporting-endpoint-00", body)
    del body
    gc.collect()

    tracemalloc.start()
    try:
        index_retained_hkel_observation(reference, reader)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < 48 << 20
