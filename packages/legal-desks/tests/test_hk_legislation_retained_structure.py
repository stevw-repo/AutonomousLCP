"""Text-free structural profiling tests for retained authentic HKeL XML."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from typing import BinaryIO

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks.hk_legislation_retained import (
    HkelRetainedArchiveMember,
    HkelRetainedBilingualXmlPair,
    HkelRetainedEndpointObject,
    HkelRetainedObjectReference,
    HkelRetainedSourceObservationIndex,
)
from asklegal_legal_desks.hk_legislation_retained_structure import (
    HkelRetainedStructureError,
    HkelRetainedStructureIssueCode,
    profile_retained_hkel_structure,
)

_HKLM = "http://www.xml.gov.hk/schemas/hklm/1.0"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"
_SCHEMA_LOCATION = (
    "http://www.xml.gov.hk/schemas/hklm/1.0 https://www.elegislation.gov.hk/schemas/hklm.xsd"
)
_ARCHIVE_LAYOUT = (
    ("sep_00000000000000000000000000000000000000000000000a", "en", 0, 1377),
    ("sep_00000000000000000000000000000000000000000000000b", "en", 1377, 1380),
    ("sep_00000000000000000000000000000000000000000000000c", "en", 2757, 338),
    ("sep_00000000000000000000000000000000000000000000000d", "en", 3095, 62),
    ("sep_00000000000000000000000000000000000000000000000e", "zh-Hant", 0, 1377),
    (
        "sep_00000000000000000000000000000000000000000000000f",
        "zh-Hant",
        1377,
        1380,
    ),
    ("sep_000000000000000000000000000000000000000000000010", "zh-Hant", 2757, 338),
    ("sep_000000000000000000000000000000000000000000000011", "zh-Hant", 3095, 62),
)
_XSD_ENDPOINT = "sep_000000000000000000000000000000000000000000000035"
_PAIR_COUNT = 3157


class _Reader:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values
        self.calls: list[HkelRetainedObjectReference] = []

    @contextmanager
    def open_exact(self, reference: HkelRetainedObjectReference) -> Generator[BinaryIO]:
        self.calls.append(reference)
        yield io.BytesIO(self.values[reference.logical_key])


def _reference(key: str, body: bytes) -> HkelRetainedObjectReference:
    return HkelRetainedObjectReference(
        logical_key=key,
        fingerprint=f"sha256:{sha256(body).hexdigest()}",
        byte_length=len(body),
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


def _xml(
    root_kind: str,
    language: str,
    **overrides: str,
) -> bytes:
    child_kind = overrides.pop("child_kind", "body")
    attribute_name = overrides.pop("attribute_name", "identifier")
    attribute_value = overrides.pop("attribute_value", "private-attribute-value")
    text = overrides.pop("text", "private legal wording")
    schema_location = overrides.pop("schema_location", _SCHEMA_LOCATION)
    namespace = overrides.pop("namespace", _HKLM)
    assert not overrides
    return (
        f'<{root_kind} xmlns="{namespace}" xmlns:xsi="{_XSI}" '
        f'xsi:schemaLocation="{schema_location}" xml:lang="{language}" '
        f'{attribute_name}="{attribute_value}">'
        f'<{child_kind} marker="private-child-value">{text}</{child_kind}>'
        f"</{root_kind}>"
    ).encode()


def _archive(
    entries: tuple[tuple[str, bytes], ...],
) -> tuple[bytes, tuple[zipfile.ZipInfo, ...]]:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries:
            archive.writestr(name, body)
    raw = target.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
        infos = tuple(archive.infolist())
    return raw, infos


def _member(
    endpoint: HkelRetainedEndpointObject,
    info: zipfile.ZipInfo,
    body: bytes,
    coordinates: tuple[str, str, str],
) -> HkelRetainedArchiveMember:
    chapter, version, language = coordinates
    return HkelRetainedArchiveMember(
        archive_endpoint_id=endpoint.endpoint_id,
        archive_fingerprint=endpoint.reference.fingerprint,
        raw_name=info.filename,
        canonical_path=info.filename.replace("\\", "/"),
        media_kind="XML",
        member_fingerprint=f"sha256:{sha256(body).hexdigest()}",
        byte_length=len(body),
        compressed_byte_length=info.compress_size,
        crc32=info.CRC,
        chapter_id=chapter,
        version_signal=version,
        language=language,
    )


def _fixture(
    *,
    english: tuple[bytes, ...] | None = None,
    traditional_chinese: tuple[bytes, ...] | None = None,
    xsd: bytes | None = None,
) -> tuple[HkelRetainedSourceObservationIndex, _Reader]:
    en_prefix = english or (
        _xml(root_kind="ordinance", language="en"),
        _xml(root_kind="resolution", language="en", child_kind="schedule"),
    )
    zh_prefix = traditional_chinese or (
        _xml(root_kind="ordinance", language="zh-Hant-HK"),
        _xml(root_kind="resolution", language="zh-Hant-HK", child_kind="schedule"),
    )
    assert len(en_prefix) == len(zh_prefix)
    en_bodies = en_prefix + tuple(
        _xml(root_kind="ordinance", language="en") for _ in range(len(en_prefix), _PAIR_COUNT)
    )
    zh_bodies = zh_prefix + tuple(
        _xml(root_kind="ordinance", language="zh-Hant-HK")
        for _ in range(len(zh_prefix), _PAIR_COUNT)
    )
    versions = tuple(f"20260828{index:06d}" for index in range(_PAIR_COUNT))
    chapters = tuple(f"cap_{index + 1}" for index in range(_PAIR_COUNT))
    en_entries = tuple(
        (
            f"{chapter}_en_c\\{chapter}_{version}_en_c.xml",
            body,
        )
        for chapter, version, body in zip(chapters, versions, en_bodies, strict=True)
    )
    zh_entries = tuple(
        (
            f"{chapter}_zh-Hant_c\\{chapter}_{version}_zh-Hant_c.xml",
            body,
        )
        for chapter, version, body in zip(chapters, versions, zh_bodies, strict=True)
    )
    entries_by_language = {"en": en_entries, "zh-Hant": zh_entries}
    bodies_by_language = {"en": en_bodies, "zh-Hant": zh_bodies}
    archive_endpoints: list[HkelRetainedEndpointObject] = []
    archive_values: dict[str, bytes] = {}
    member_by_coordinates: dict[tuple[str, str, str], HkelRetainedArchiveMember] = {}
    for endpoint_id, language, start, count in _ARCHIVE_LAYOUT:
        selected_entries = entries_by_language[language][start : start + count]
        archive_body, infos = _archive(selected_entries)
        reference = _reference(f"objects/{endpoint_id}.bin", archive_body)
        endpoint = HkelRetainedEndpointObject(
            endpoint_id,
            "1.0.0",
            "application/zip",
            reference,
        )
        archive_endpoints.append(endpoint)
        archive_values[reference.logical_key] = archive_body
        for offset, info in enumerate(infos):
            index = start + offset
            member = _member(
                endpoint,
                info,
                bodies_by_language[language][index],
                (chapters[index], versions[index], language),
            )
            member_by_coordinates[(chapters[index], versions[index], language)] = member
    xsd_body = (
        xsd
        or (
            f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
            f'targetNamespace="{_HKLM}" version="1.0" '
            'elementFormDefault="qualified" attributeFormDefault="unqualified">'
            '<xs:import namespace="http://www.w3.org/XML/1998/namespace" '
            'schemaLocation="http://www.w3.org/2001/xml.xsd"/>'
            '<xs:import namespace="http://purl.org/dc/terms/"/>'
            '<xs:import namespace="http://www.w3.org/1999/xhtml"/>'
            '<xs:import namespace="http://www.w3.org/1998/Math/MathML"/>'
            '<xs:complexType name="LawDocType"/>'
            '<xs:element name="lawDoc" type="LawDocType"/>'
            '<xs:element name="ordinance" type="LawDocType"/>'
            '<xs:element name="resolution" type="LawDocType"/>'
            '<xs:element name="subLeg" type="LawDocType"/>'
            "</xs:schema>"
        ).encode()
    )
    xsd_ref = _reference("objects/schema.bin", xsd_body)
    xsd_endpoint = HkelRetainedEndpointObject(_XSD_ENDPOINT, "1.0.0", "application/xml", xsd_ref)
    specification_endpoints: list[HkelRetainedEndpointObject] = [xsd_endpoint]
    for number in range(6):
        body = f"specification-{number}".encode()
        specification_endpoints.append(
            HkelRetainedEndpointObject(
                f"specification-endpoint-{number}",
                "1.0.0",
                "application/octet-stream",
                _reference(f"objects/specification-{number}.bin", body),
            )
        )
    supporting_endpoints: list[HkelRetainedEndpointObject] = []
    for number in range(41):
        body = f"supporting-{number}".encode()
        supporting_endpoints.append(
            HkelRetainedEndpointObject(
                f"supporting-endpoint-{number}",
                "1.0.0",
                "application/octet-stream",
                _reference(f"objects/supporting-{number}.bin", body),
            )
        )
    endpoint_objects = (
        *archive_endpoints,
        *specification_endpoints,
        *supporting_endpoints,
    )
    assert len(endpoint_objects) == 56
    members: list[HkelRetainedArchiveMember] = []
    pairs: list[HkelRetainedBilingualXmlPair] = []
    for chapter, version in zip(chapters, versions, strict=True):
        en_member = member_by_coordinates[(chapter, version, "en")]
        zh_member = member_by_coordinates[(chapter, version, "zh-Hant")]
        members.extend((en_member, zh_member))
        pairs.append(HkelRetainedBilingualXmlPair(chapter, version, en_member, zh_member))
    publication_profile: dict[str, JsonValue] = {
        "profile": "HKEL_RETAINED_CURRENT_DATA_1.0.0",
        "specifications": [_endpoint_projection(item) for item in specification_endpoints],
    }
    publication_profile_fingerprint = _canonical_fingerprint(publication_profile)
    observation: dict[str, JsonValue] = {
        "attempt_id": "hkel-retained-structure-fixture",
        "observation_cutoff": "2026-08-28T22:20:23+08:00",
        "report_fingerprint": "sha256:" + "1" * 64,
        "authority_manifest_fingerprint": "sha256:" + "2" * 64,
        "execution_authorization_fingerprint": "sha256:" + "3" * 64,
        "endpoint_objects": [_endpoint_projection(item) for item in endpoint_objects],
        "archive_members": [_member_projection(item) for item in members],
        "publication_profile_fingerprint": publication_profile_fingerprint,
    }
    index = HkelRetainedSourceObservationIndex(
        attempt_id="hkel-retained-structure-fixture",
        observation_cutoff="2026-08-28T22:20:23+08:00",
        report_fingerprint="sha256:" + "1" * 64,
        authority_manifest_fingerprint="sha256:" + "2" * 64,
        execution_authorization_fingerprint="sha256:" + "3" * 64,
        endpoint_objects=endpoint_objects,
        archive_members=tuple(members),
        bilingual_xml_pairs=tuple(pairs),
        xsd_reference=xsd_endpoint,
        publication_specifications=tuple(specification_endpoints),
        publication_profile_fingerprint=publication_profile_fingerprint,
        source_observation_fingerprint=_canonical_fingerprint(observation),
    )
    return index, _Reader(
        {
            **archive_values,
            xsd_ref.logical_key: xsd_body,
        }
    )


def _expanded_counts(profile: object, field: str) -> dict[str, int]:
    values = getattr(profile, field)
    return {item.expanded_name: item.count for item in values}


def _recompute_source_fingerprint(
    index: HkelRetainedSourceObservationIndex,
) -> HkelRetainedSourceObservationIndex:
    observation: dict[str, JsonValue] = {
        "attempt_id": index.attempt_id,
        "observation_cutoff": index.observation_cutoff,
        "report_fingerprint": index.report_fingerprint,
        "authority_manifest_fingerprint": index.authority_manifest_fingerprint,
        "execution_authorization_fingerprint": index.execution_authorization_fingerprint,
        "endpoint_objects": [_endpoint_projection(item) for item in index.endpoint_objects],
        "archive_members": [_member_projection(item) for item in index.archive_members],
        "publication_profile_fingerprint": index.publication_profile_fingerprint,
    }
    return replace(index, source_observation_fingerprint=_canonical_fingerprint(observation))


def test_profile_emits_text_free_structure_counts_and_non_authorizing_schema_state() -> None:
    index, reader = _fixture()

    result = profile_retained_hkel_structure(index, reader)

    assert result.admission_authority == "NONE"
    assert result.schema_profile.admission_authority == "NONE"
    assert result.schema_profile.validation_state == "SCHEMA_VALIDATION_NOT_PERFORMED"
    assert result.schema_profile.xsd_fingerprint == index.xsd_reference.reference.fingerprint
    assert result.schema_profile.publication_profile_fingerprint == (
        index.publication_profile_fingerprint
    )
    assert result.schema_profile.target_namespace == _HKLM
    assert result.schema_profile.schema_version == "1.0"
    assert result.schema_profile.element_form_default == "qualified"
    assert result.schema_profile.attribute_form_default == "unqualified"
    assert result.schema_profile.root_local_names == (
        "lawDoc",
        "ordinance",
        "resolution",
        "subLeg",
    )
    assert result.schema_profile.imports == (
        (
            "http://www.w3.org/XML/1998/namespace",
            "http://www.w3.org/2001/xml.xsd",
        ),
        ("http://purl.org/dc/terms/", None),
        ("http://www.w3.org/1999/xhtml", None),
        ("http://www.w3.org/1998/Math/MathML", None),
    )
    assert len(result.bilingual_records) == _PAIR_COUNT
    english = result.bilingual_records[0].english
    assert english.root_expanded_name == f"{{{_HKLM}}}ordinance"
    assert english.node_count == 2
    assert english.maximum_depth == 2
    assert english.maximum_attribute_count == 3
    assert _expanded_counts(english, "element_expanded_name_counts") == {
        f"{{{_HKLM}}}body": 1,
        f"{{{_HKLM}}}ordinance": 1,
    }
    assert _expanded_counts(english, "attribute_expanded_name_counts") == {
        "identifier": 1,
        "marker": 1,
        f"{{{_XSI}}}schemaLocation": 1,
        "{http://www.w3.org/XML/1998/namespace}lang": 1,
    }
    rendered = repr(result)
    assert "private legal wording" not in rendered
    assert "private-attribute-value" not in rendered
    assert "private-child-value" not in rendered
    assert reader.calls[0] == index.xsd_reference.reference
    assert [call.logical_key for call in reader.calls[1:]] == [
        f"objects/{endpoint_id}.bin" for endpoint_id, _language, _start, _count in _ARCHIVE_LAYOUT
    ]


def test_attribute_values_change_only_the_value_binding_fingerprint() -> None:
    original_index, original_reader = _fixture()
    changed_index, changed_reader = _fixture(
        english=(
            _xml(
                root_kind="ordinance",
                language="en",
                attribute_value="changed-private-value",
            ),
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )

    original = profile_retained_hkel_structure(original_index, original_reader)
    changed = profile_retained_hkel_structure(changed_index, changed_reader)

    original_profile = original.bilingual_records[0].english
    changed_profile = changed.bilingual_records[0].english
    assert original_profile.structure_fingerprint == changed_profile.structure_fingerprint
    assert original_profile.value_binding_fingerprint != changed_profile.value_binding_fingerprint


def test_text_changes_only_the_value_binding_fingerprint() -> None:
    original_index, original_reader = _fixture()
    changed_index, changed_reader = _fixture(
        english=(
            _xml(root_kind="ordinance", language="en", text="different private wording"),
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )

    original = profile_retained_hkel_structure(original_index, original_reader)
    changed = profile_retained_hkel_structure(changed_index, changed_reader)

    original_profile = original.bilingual_records[0].english
    changed_profile = changed.bilingual_records[0].english
    assert original_profile.structure_fingerprint == changed_profile.structure_fingerprint
    assert original_profile.value_binding_fingerprint != changed_profile.value_binding_fingerprint


def test_attribute_order_changes_neither_fingerprint() -> None:
    reordered = (
        f'<ordinance xmlns="{_HKLM}" xmlns:xsi="{_XSI}" '
        'identifier="private-attribute-value" xml:lang="en" '
        f'xsi:schemaLocation="{_SCHEMA_LOCATION}">'
        '<body marker="private-child-value">private legal wording</body>'
        "</ordinance>"
    ).encode()
    original_index, original_reader = _fixture()
    changed_index, changed_reader = _fixture(
        english=(
            reordered,
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )

    original = profile_retained_hkel_structure(original_index, original_reader)
    changed = profile_retained_hkel_structure(changed_index, changed_reader)

    original_profile = original.bilingual_records[0].english
    changed_profile = changed.bilingual_records[0].english
    assert original_profile.structure_fingerprint == changed_profile.structure_fingerprint
    assert original_profile.value_binding_fingerprint == changed_profile.value_binding_fingerprint


def test_element_name_or_order_changes_the_structure_fingerprint() -> None:
    changed_index, changed_reader = _fixture(
        english=(
            _xml(root_kind="ordinance", language="en", child_kind="schedule"),
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )
    original_index, original_reader = _fixture()

    original = profile_retained_hkel_structure(original_index, original_reader)
    changed = profile_retained_hkel_structure(changed_index, changed_reader)

    assert (
        original.bilingual_records[0].english.structure_fingerprint
        != changed.bilingual_records[0].english.structure_fingerprint
    )


def test_equal_local_names_in_different_namespaces_remain_distinct() -> None:
    namespaced = (
        f'<ordinance xmlns="{_HKLM}" xmlns:xsi="{_XSI}" xmlns:e="urn:extension" '
        f'xsi:schemaLocation="{_SCHEMA_LOCATION}" xml:lang="en">'
        "<body/><e:body/></ordinance>"
    ).encode()
    index, reader = _fixture(
        english=(
            namespaced,
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )

    result = profile_retained_hkel_structure(index, reader)

    counts = _expanded_counts(
        result.bilingual_records[0].english,
        "element_expanded_name_counts",
    )
    assert counts[f"{{{_HKLM}}}body"] == 1
    assert counts["{urn:extension}body"] == 1


def test_archive_root_language_conflict_requires_review_without_returning_value() -> None:
    index, reader = _fixture(
        english=(
            _xml(root_kind="ordinance", language="zh-Hant-HK"),
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )

    result = profile_retained_hkel_structure(index, reader)

    record = result.bilingual_records[0]
    assert record.review_state == "REVIEW_REQUIRED"
    assert record.english.issue_codes == (
        HkelRetainedStructureIssueCode.ARCHIVE_ROOT_LANGUAGE_CONFLICT,
    )
    assert record.issue_codes == (HkelRetainedStructureIssueCode.ARCHIVE_ROOT_LANGUAGE_CONFLICT,)
    assert "zh-Hant-HK" not in repr(record.english)


def test_bilingual_root_kind_conflict_requires_review() -> None:
    index, reader = _fixture(
        traditional_chinese=(
            _xml(root_kind="subLeg", language="zh-Hant-HK"),
            _xml(root_kind="resolution", language="zh-Hant-HK", child_kind="schedule"),
        )
    )

    result = profile_retained_hkel_structure(index, reader)

    record = result.bilingual_records[0]
    assert record.review_state == "REVIEW_REQUIRED"
    assert record.issue_codes == (HkelRetainedStructureIssueCode.BILINGUAL_ROOT_KIND_CONFLICT,)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b'<?xml version="1.0" encoding="utf-16"?><ordinance/>', "XML_INVALID"),
        (b'<!DOCTYPE x><ordinance xmlns="urn:test"/>', "XML_FORBIDDEN_DECLARATION"),
        (
            b'<!DOCTYPE x [<!ENTITY e "x">]><ordinance xmlns="urn:test">&e;</ordinance>',
            "XML_FORBIDDEN_DECLARATION",
        ),
        (b'<ordinance xmlns="urn:test">\x00</ordinance>', "XML_INVALID"),
        (
            (
                f'<ordinance xmlns="{_HKLM}" xmlns:xi="http://www.w3.org/2001/XInclude" '
                f'xmlns:xsi="{_XSI}" xsi:schemaLocation="{_SCHEMA_LOCATION}" '
                'xml:lang="en"><xi:include href="anything"/></ordinance>'
            ).encode(),
            "XML_XINCLUDE_FORBIDDEN",
        ),
    ],
)
def test_inert_xml_gate_rejects_unsafe_member(body: bytes, code: str) -> None:
    index, reader = _fixture(
        english=(body, _xml(root_kind="resolution", language="en", child_kind="schedule"))
    )

    with pytest.raises(HkelRetainedStructureError, match=code):
        profile_retained_hkel_structure(index, reader)


@pytest.mark.parametrize("encoding", ["iso-8859-1", "unknown-private-encoding"])
def test_overlong_xml_declaration_cannot_bypass_utf8_revalidation(encoding: str) -> None:
    body = (
        '<?xml version="1.0" '
        + " " * 1100
        + f'encoding="{encoding}"?>'
        + f'<ordinance xmlns="{_HKLM}" xmlns:xsi="{_XSI}" '
        + f'xsi:schemaLocation="{_SCHEMA_LOCATION}" xml:lang="en"/>'
    ).encode()
    index, reader = _fixture(
        english=(body, _xml(root_kind="resolution", language="en", child_kind="schedule"))
    )

    with pytest.raises(HkelRetainedStructureError, match="XML_INVALID"):
        profile_retained_hkel_structure(index, reader)


def test_invalid_utf8_error_graph_does_not_retain_source_bytes() -> None:
    sentinel = b"private-attribute-sentinel"
    body = (
        (
            f'<ordinance xmlns="{_HKLM}" xmlns:xsi="{_XSI}" '
            f'xsi:schemaLocation="{_SCHEMA_LOCATION}" xml:lang="en" marker="'
        ).encode()
        + sentinel
        + b'\xff"/>'
    )
    index, reader = _fixture(
        english=(body, _xml(root_kind="resolution", language="en", child_kind="schedule"))
    )

    with pytest.raises(HkelRetainedStructureError, match="XML_INVALID") as caught:
        profile_retained_hkel_structure(index, reader)

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert sentinel not in repr(caught.value).encode()


def test_noncanonical_archive_topology_is_rejected_before_read() -> None:
    index, reader = _fixture()
    original_endpoint_id = _ARCHIVE_LAYOUT[0][0]
    replacement_endpoint_id = "sep_noncanonical_archive_endpoint"
    changed_endpoints = tuple(
        replace(endpoint, endpoint_id=replacement_endpoint_id)
        if endpoint.endpoint_id == original_endpoint_id
        else endpoint
        for endpoint in index.endpoint_objects
    )
    changed_members = tuple(
        replace(member, archive_endpoint_id=replacement_endpoint_id)
        if member.archive_endpoint_id == original_endpoint_id
        else member
        for member in index.archive_members
    )
    changed_pairs = tuple(
        replace(
            pair,
            english=replace(pair.english, archive_endpoint_id=replacement_endpoint_id),
        )
        if pair.english.archive_endpoint_id == original_endpoint_id
        else pair
        for pair in index.bilingual_xml_pairs
    )
    detached = replace(
        index,
        endpoint_objects=changed_endpoints,
        archive_members=changed_members,
        bilingual_xml_pairs=changed_pairs,
    )
    changed = _recompute_source_fingerprint(detached)

    with pytest.raises(HkelRetainedStructureError, match="INDEX_INVALID"):
        profile_retained_hkel_structure(changed, reader)

    assert reader.calls == []


def test_equal_count_english_and_chinese_archive_ids_cannot_be_swapped() -> None:
    index, reader = _fixture()
    english_id = _ARCHIVE_LAYOUT[0][0]
    chinese_id = _ARCHIVE_LAYOUT[4][0]

    def swapped(endpoint_id: str) -> str:
        if endpoint_id == english_id:
            return chinese_id
        if endpoint_id == chinese_id:
            return english_id
        return endpoint_id

    detached = replace(
        index,
        endpoint_objects=tuple(
            replace(endpoint, endpoint_id=swapped(endpoint.endpoint_id))
            for endpoint in index.endpoint_objects
        ),
        archive_members=tuple(
            replace(member, archive_endpoint_id=swapped(member.archive_endpoint_id))
            for member in index.archive_members
        ),
        bilingual_xml_pairs=tuple(
            replace(
                pair,
                english=replace(
                    pair.english,
                    archive_endpoint_id=swapped(pair.english.archive_endpoint_id),
                ),
                traditional_chinese=replace(
                    pair.traditional_chinese,
                    archive_endpoint_id=swapped(pair.traditional_chinese.archive_endpoint_id),
                ),
            )
            for pair in index.bilingual_xml_pairs
        ),
    )
    changed = _recompute_source_fingerprint(detached)

    with pytest.raises(HkelRetainedStructureError, match="INDEX_INVALID"):
        profile_retained_hkel_structure(changed, reader)

    assert reader.calls == []


def test_root_requires_exact_hklm_namespace_and_schema_location() -> None:
    wrong_namespace_index, wrong_namespace_reader = _fixture(
        english=(
            _xml(root_kind="ordinance", language="en", namespace="urn:not-hklm"),
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )
    wrong_schema_index, wrong_schema_reader = _fixture(
        english=(
            _xml(root_kind="ordinance", language="en", schema_location="urn:not-schema"),
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )

    with pytest.raises(HkelRetainedStructureError, match="ROOT_PROFILE_INVALID"):
        profile_retained_hkel_structure(wrong_namespace_index, wrong_namespace_reader)
    with pytest.raises(HkelRetainedStructureError, match="ROOT_PROFILE_INVALID"):
        profile_retained_hkel_structure(wrong_schema_index, wrong_schema_reader)


def test_xsd_profile_relationships_are_verified_before_archive_reads() -> None:
    wrong_xsd = (
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        b'targetNamespace="urn:not-hklm" version="1.0" '
        b'elementFormDefault="qualified" attributeFormDefault="unqualified"/>'
    )
    index, reader = _fixture(xsd=wrong_xsd)

    with pytest.raises(HkelRetainedStructureError, match="SCHEMA_PROFILE_INVALID"):
        profile_retained_hkel_structure(index, reader)

    assert reader.calls == [index.xsd_reference.reference]


def test_member_depth_and_attribute_limits_are_closed() -> None:
    nested = (
        f'<ordinance xmlns="{_HKLM}" xmlns:xsi="{_XSI}" '
        f'xsi:schemaLocation="{_SCHEMA_LOCATION}" xml:lang="en">'
        + "<node>" * 64
        + "</node>" * 64
        + "</ordinance>"
    ).encode()
    attributes = " ".join(f'a{index}="x"' for index in range(65))
    too_many_attributes = (
        f'<ordinance xmlns="{_HKLM}" xmlns:xsi="{_XSI}" '
        f'xsi:schemaLocation="{_SCHEMA_LOCATION}" xml:lang="en">'
        f"<node {attributes}/></ordinance>"
    ).encode()
    depth_index, depth_reader = _fixture(
        english=(nested, _xml(root_kind="resolution", language="en", child_kind="schedule"))
    )
    attrs_index, attrs_reader = _fixture(
        english=(
            too_many_attributes,
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )

    with pytest.raises(HkelRetainedStructureError, match="XML_LIMIT_EXCEEDED"):
        profile_retained_hkel_structure(depth_index, depth_reader)
    with pytest.raises(HkelRetainedStructureError, match="XML_LIMIT_EXCEEDED"):
        profile_retained_hkel_structure(attrs_index, attrs_reader)


def test_member_node_ceiling_is_exactly_250000() -> None:
    too_many_nodes = (
        f'<ordinance xmlns="{_HKLM}" xmlns:xsi="{_XSI}" '
        f'xsi:schemaLocation="{_SCHEMA_LOCATION}" xml:lang="en">'
        + "<n/>" * 250_000
        + "</ordinance>"
    ).encode()
    index, reader = _fixture(
        english=(
            too_many_nodes,
            _xml(root_kind="resolution", language="en", child_kind="schedule"),
        )
    )

    with pytest.raises(HkelRetainedStructureError, match="XML_LIMIT_EXCEEDED"):
        profile_retained_hkel_structure(index, reader)


def test_declared_member_over_32_mib_is_rejected_before_read() -> None:
    index, reader = _fixture()
    pair = index.bilingual_xml_pairs[0]
    oversized = replace(pair.english, byte_length=(32 << 20) + 1)
    changed_members = tuple(
        oversized if member == pair.english else member for member in index.archive_members
    )
    changed_pairs = (
        replace(pair, english=oversized),
        *index.bilingual_xml_pairs[1:],
    )
    changed = replace(
        index,
        archive_members=changed_members,
        bilingual_xml_pairs=changed_pairs,
    )

    with pytest.raises(HkelRetainedStructureError, match="INDEX_INVALID"):
        profile_retained_hkel_structure(changed, reader)

    assert reader.calls == []


def test_archive_or_member_byte_drift_fails_closed() -> None:
    index, reader = _fixture()
    reader.values[index.bilingual_xml_pairs[0].english.archive_fingerprint] = b"unused"
    en_reference = index.endpoint_objects[0].reference
    reader.values[en_reference.logical_key] = reader.values[en_reference.logical_key] + b"tamper"

    with pytest.raises(HkelRetainedStructureError, match="OBJECT_READ_FAILED"):
        profile_retained_hkel_structure(index, reader)


def test_duplicate_or_unindexed_pair_member_is_rejected_before_read() -> None:
    index, reader = _fixture()
    pair = index.bilingual_xml_pairs[0]
    duplicate = replace(index, bilingual_xml_pairs=(pair, pair))
    unindexed_member = replace(pair.english, member_fingerprint="sha256:" + "9" * 64)
    unindexed = replace(
        index,
        bilingual_xml_pairs=(replace(pair, english=unindexed_member),),
    )

    with pytest.raises(HkelRetainedStructureError, match="INDEX_INVALID"):
        profile_retained_hkel_structure(duplicate, reader)
    with pytest.raises(HkelRetainedStructureError, match="INDEX_INVALID"):
        profile_retained_hkel_structure(unindexed, reader)
    assert reader.calls == []


def test_detached_index_canonical_fingerprint_drift_is_rejected_before_read() -> None:
    index, reader = _fixture()
    changed = replace(index, source_observation_fingerprint="sha256:" + "9" * 64)

    with pytest.raises(HkelRetainedStructureError, match="INDEX_INVALID"):
        profile_retained_hkel_structure(changed, reader)

    assert reader.calls == []
