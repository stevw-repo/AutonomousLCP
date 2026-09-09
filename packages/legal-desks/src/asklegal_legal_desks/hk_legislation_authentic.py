"""HKeL provenance gates and full retained-observation admission."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Never, Protocol, TypeIs

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import ExactObjectReference, VaultName

from asklegal_legal_desks.hk_legislation_retained import (
    HkelRetainedEvidenceReader,
    index_retained_hkel_observation,
)
from asklegal_legal_desks.hk_legislation_retained_structure import (
    profile_retained_hkel_structure,
)

_ENVELOPE_SCHEMA_ID = "asklegal.hk-legislation-authentic-envelope"
_ENVELOPE_SCHEMA_VERSION = "1.0.0"
_PLAN_SCHEMA_ID = "asklegal.hkel-evidence-plan"
_PLAN_SCHEMA_VERSION = "1.0.0"
_CURRENT_SOURCE_ID = "HK-LEG-HKEL-CURRENT-INVENTORY"
_CURRENT_CYCLE_KIND = "DAILY_CURRENT_LAW"
_PLAN_PREFIX = "poc/report/hkel-evidence-plan"
_ATTEMPT_PREFIX = "poc/report/hkel-evidence-attempt"
_SHA256_HEX_LENGTH = 64
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_CYCLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,159}$")
_INSTRUMENT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,159}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_PLAN_FIELDS = frozenset(
    {
        "authentic_source_admitted",
        "instrument_id",
        "inventory_fingerprint",
        "members",
        "missing_member_ids",
        "observation_cutoff",
        "parser_profile",
        "projection_fingerprint",
        "plan_fingerprint",
        "schema_id",
        "schema_version",
        "source_register_fingerprint",
        "source_register_id",
    }
)
_PLAN_MEMBER_FIELDS = frozenset(
    {
        "archive_member",
        "artifact_id",
        "declared_sha256",
        "endpoint_id",
        "endpoint_version",
        "inventory_member_fingerprint",
        "instrument_id",
        "language",
        "locator",
        "resource_id",
        "role",
        "source_id",
        "source_disposition",
        "status_signal",
        "version_signal",
    }
)
_PLAN_FINGERPRINT_FIELDS = (
    "authentic_source_admitted",
    "instrument_id",
    "inventory_fingerprint",
    "members",
    "missing_member_ids",
    "observation_cutoff",
    "projection_fingerprint",
    "source_register_fingerprint",
    "source_register_id",
)
_ADMISSION_SCHEMA_ID = "asklegal.hkel-authentic-admission"
_ADMISSION_SCHEMA_VERSION = "1.0.0"
_ADMISSION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "attempt_id",
        "observation_cutoff",
        "report_fingerprint",
        "source_observation_fingerprint",
        "structure_profile_fingerprint",
        "archive_member_count",
        "bilingual_pair_count",
        "publication_specification_count",
        "archive_reuse_keys",
        "review_issue_refs",
        "fingerprint",
    }
)
_REUSE_KEY_FIELDS = frozenset(
    {
        "archive_endpoint_id",
        "archive_fingerprint",
        "publication_profile_fingerprint",
        "fingerprint",
    }
)
_ENDPOINT_ID = re.compile(r"^sep_[0-9a-f]{48}$")
_EXPECTED_ENDPOINTS = 56
_EXPECTED_ARCHIVE_MEMBERS = 12_858
_EXPECTED_BILINGUAL_PAIRS = 3_157
_EXPECTED_SPECIFICATIONS = 7
_EXPECTED_ARCHIVES = 12


def _object_mapping(value: object) -> TypeIs[dict[str, object]]:
    return type(value) is dict


def _object_list(value: object) -> TypeIs[list[object]]:
    return type(value) is list


class HKLegislationEvidenceErrorCode(StrEnum):
    """Closed failures at the authentic-legislation evidence boundary."""

    AUTHENTIC_SOURCE_NOT_ADMITTED = "AUTHENTIC_SOURCE_NOT_ADMITTED"
    ENVELOPE_INVALID = "HK_LEGISLATION_EVIDENCE_ENVELOPE_INVALID"
    PLAN_INVALID = "HK_LEGISLATION_EVIDENCE_PLAN_INVALID"
    PLAN_REFERENCE_REQUIRED = "HK_LEGISLATION_PLAN_REFERENCE_REQUIRED"
    PROVENANCE_MISMATCH = "HK_LEGISLATION_EVIDENCE_PROVENANCE_MISMATCH"
    READ_FAILED = "HK_LEGISLATION_EVIDENCE_READ_FAILED"
    REFERENCE_INVALID = "HK_LEGISLATION_EVIDENCE_REFERENCE_INVALID"
    RETAINED_ADMISSION_INVALID = "RETAINED_ADMISSION_INVALID"


class HKLegislationEvidenceError(ValueError):
    """One normalized rejection without a raw parser or reader failure."""

    code: HKLegislationEvidenceErrorCode

    def __init__(self, code: HKLegislationEvidenceErrorCode) -> None:
        """Create one stable closed rejection."""
        self.code = code
        super().__init__(code.value)


class HKLegislationEvidenceReader(Protocol):
    """Read only one exact immutable object selected by the closed envelope."""

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        """Return the bytes for the exact object version and digest."""
        ...


@dataclass(frozen=True, slots=True)
class HKLegislationEvidenceEnvelope:
    """Frozen provenance references; not itself an authentic-admission assertion."""

    schema_id: str
    schema_version: str
    cycle_id: str
    cycle_kind: str
    source_id: str
    instrument_id: str
    observation_cutoff: str
    source_cycle_manifest_reference: ExactObjectReference
    plan_manifest_reference: ExactObjectReference | None
    terminal_attempt_reference: ExactObjectReference
    admission_result_reference: ExactObjectReference | None
    member_references: tuple[ExactObjectReference, ...]


@dataclass(frozen=True, slots=True)
class HkelAuthenticArchiveReuseKey:
    """Exact archive/publication-profile identity for safe parse reuse."""

    archive_endpoint_id: str
    archive_fingerprint: str
    publication_profile_fingerprint: str
    fingerprint: str

    @classmethod
    def issue(
        cls,
        archive_endpoint_id: object,
        archive_fingerprint: object,
        publication_profile_fingerprint: object,
    ) -> HkelAuthenticArchiveReuseKey:
        """Issue one canonical exact reuse key."""
        if (
            type(archive_endpoint_id) is not str
            or _ENDPOINT_ID.fullmatch(archive_endpoint_id) is None
            or type(archive_fingerprint) is not str
            or _FINGERPRINT.fullmatch(archive_fingerprint) is None
            or type(publication_profile_fingerprint) is not str
            or _FINGERPRINT.fullmatch(publication_profile_fingerprint) is None
        ):
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        body: dict[str, JsonValue] = {
            "archive_endpoint_id": archive_endpoint_id,
            "archive_fingerprint": archive_fingerprint,
            "publication_profile_fingerprint": publication_profile_fingerprint,
        }
        fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
        return cls(
            archive_endpoint_id,
            archive_fingerprint,
            publication_profile_fingerprint,
            fingerprint,
        )

    @classmethod
    def from_json(cls, value: object) -> HkelAuthenticArchiveReuseKey:
        """Parse one closed reuse-key object and reproduce its fingerprint."""
        if not _object_mapping(value) or frozenset(value) != _REUSE_KEY_FIELDS:
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        issued = cls.issue(
            value["archive_endpoint_id"],
            value["archive_fingerprint"],
            value["publication_profile_fingerprint"],
        )
        if value["fingerprint"] != issued.fingerprint:
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        return issued

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed canonical JSON projection."""
        return {
            "archive_endpoint_id": self.archive_endpoint_id,
            "archive_fingerprint": self.archive_fingerprint,
            "publication_profile_fingerprint": self.publication_profile_fingerprint,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HkelAuthenticAdmissionFacts:
    """Exact inputs used to issue one retained-observation admission receipt."""

    attempt_id: str
    observation_cutoff: str
    report_fingerprint: str
    source_observation_fingerprint: str
    structure_profile_fingerprint: str
    archive_member_count: int
    bilingual_pair_count: int
    publication_specification_count: int
    archive_reuse_keys: tuple[HkelAuthenticArchiveReuseKey, ...]
    review_issue_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HkelAuthenticAdmissionReceipt:
    """Complete body/XML admission facts without a legal-effect assertion."""

    attempt_id: str
    observation_cutoff: str
    report_fingerprint: str
    source_observation_fingerprint: str
    structure_profile_fingerprint: str
    archive_member_count: int
    bilingual_pair_count: int
    publication_specification_count: int
    archive_reuse_keys: tuple[HkelAuthenticArchiveReuseKey, ...]
    review_issue_refs: tuple[str, ...]
    fingerprint: str

    @classmethod
    def issue(cls, value: object) -> HkelAuthenticAdmissionReceipt:
        """Issue one receipt only for the exact known complete retained profile."""
        if type(value) is not HkelAuthenticAdmissionFacts:
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        if (
            type(value.attempt_id) is not str
            or _CYCLE_ID.fullmatch(value.attempt_id) is None
            or type(value.observation_cutoff) is not str
            or type(value.report_fingerprint) is not str
            or _FINGERPRINT.fullmatch(value.report_fingerprint) is None
            or type(value.source_observation_fingerprint) is not str
            or _FINGERPRINT.fullmatch(value.source_observation_fingerprint) is None
            or type(value.structure_profile_fingerprint) is not str
            or _FINGERPRINT.fullmatch(value.structure_profile_fingerprint) is None
            or type(value.archive_member_count) is not int
            or value.archive_member_count != _EXPECTED_ARCHIVE_MEMBERS
            or type(value.bilingual_pair_count) is not int
            or value.bilingual_pair_count != _EXPECTED_BILINGUAL_PAIRS
            or type(value.publication_specification_count) is not int
            or value.publication_specification_count != _EXPECTED_SPECIFICATIONS
            or type(value.archive_reuse_keys) is not tuple
            or len(value.archive_reuse_keys) != _EXPECTED_ARCHIVES
            or type(value.review_issue_refs) is not tuple
        ):
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        keys = tuple(
            HkelAuthenticArchiveReuseKey.issue(
                item.archive_endpoint_id,
                item.archive_fingerprint,
                item.publication_profile_fingerprint,
            )
            for item in value.archive_reuse_keys
        )
        reviews = tuple(value.review_issue_refs)
        if (
            tuple(item.archive_endpoint_id for item in keys)
            != tuple(sorted(item.archive_endpoint_id for item in keys))
            or len({item.archive_endpoint_id for item in keys}) != len(keys)
            or any(type(item) is not str or not item for item in reviews)
            or reviews != tuple(sorted(set(reviews)))
        ):
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        draft = cls(
            value.attempt_id,
            value.observation_cutoff,
            value.report_fingerprint,
            value.source_observation_fingerprint,
            value.structure_profile_fingerprint,
            value.archive_member_count,
            value.bilingual_pair_count,
            value.publication_specification_count,
            keys,
            reviews,
            "",
        )
        body = _admission_body(draft)
        fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
        return HkelAuthenticAdmissionReceipt(
            draft.attempt_id,
            draft.observation_cutoff,
            draft.report_fingerprint,
            draft.source_observation_fingerprint,
            draft.structure_profile_fingerprint,
            draft.archive_member_count,
            draft.bilingual_pair_count,
            draft.publication_specification_count,
            draft.archive_reuse_keys,
            draft.review_issue_refs,
            fingerprint,
        )

    @classmethod
    def from_json(cls, value: object) -> HkelAuthenticAdmissionReceipt:
        """Parse and reproduce one closed admission receipt."""
        if not _object_mapping(value) or frozenset(value) != _ADMISSION_FIELDS:
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        raw_keys = value["archive_reuse_keys"]
        raw_reviews = value["review_issue_refs"]
        if (
            value["schema_id"] != _ADMISSION_SCHEMA_ID
            or value["schema_version"] != _ADMISSION_SCHEMA_VERSION
            or not _object_list(raw_keys)
            or not _object_list(raw_reviews)
        ):
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        issued = cls.issue(
            HkelAuthenticAdmissionFacts(
                _admission_text(value["attempt_id"]),
                _admission_text(value["observation_cutoff"]),
                _admission_text(value["report_fingerprint"]),
                _admission_text(value["source_observation_fingerprint"]),
                _admission_text(value["structure_profile_fingerprint"]),
                _admission_integer(value["archive_member_count"]),
                _admission_integer(value["bilingual_pair_count"]),
                _admission_integer(value["publication_specification_count"]),
                tuple(HkelAuthenticArchiveReuseKey.from_json(item) for item in raw_keys),
                tuple(_admission_text(item) for item in raw_reviews),
            )
        )
        if value["fingerprint"] != issued.fingerprint:
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        return issued

    def to_json(self) -> dict[str, JsonValue]:
        """Return the canonical closed receipt document."""
        return {**_admission_body(self), "fingerprint": self.fingerprint}


def _admission_text(value: object) -> str:
    if type(value) is not str:
        _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
    return value


def _admission_integer(value: object) -> int:
    if type(value) is not int:
        _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
    return value


def _admission_body(receipt: HkelAuthenticAdmissionReceipt) -> dict[str, JsonValue]:
    return {
        "schema_id": _ADMISSION_SCHEMA_ID,
        "schema_version": _ADMISSION_SCHEMA_VERSION,
        "attempt_id": receipt.attempt_id,
        "observation_cutoff": receipt.observation_cutoff,
        "report_fingerprint": receipt.report_fingerprint,
        "source_observation_fingerprint": receipt.source_observation_fingerprint,
        "structure_profile_fingerprint": receipt.structure_profile_fingerprint,
        "archive_member_count": receipt.archive_member_count,
        "bilingual_pair_count": receipt.bilingual_pair_count,
        "publication_specification_count": receipt.publication_specification_count,
        "archive_reuse_keys": [item.to_json() for item in receipt.archive_reuse_keys],
        "review_issue_refs": list(receipt.review_issue_refs),
    }


@dataclass(frozen=True, slots=True)
class _ValidatedEnvelope:
    cycle_id: str
    source_id: str
    instrument_id: str
    observation_cutoff: str
    source_cycle_manifest_reference: ExactObjectReference
    plan_manifest_reference: _ExactReferenceSnapshot
    terminal_attempt_reference: ExactObjectReference
    admission_result_reference: ExactObjectReference | None
    member_references: tuple[ExactObjectReference, ...]


@dataclass(frozen=True, slots=True)
class _ExactReferenceSnapshot:
    """Detached exact primitives retained across one untrusted reader call."""

    vault: VaultName
    logical_key: str
    version_id: str
    fingerprint: str
    byte_length: int


def _fail(code: HKLegislationEvidenceErrorCode) -> Never:
    raise HKLegislationEvidenceError(code)


def _exact_object(value: JsonValue) -> TypeIs[dict[str, JsonValue]]:
    return type(value) is dict and all(type(key) is str for key in value)


def _exact_list(value: JsonValue) -> TypeIs[list[JsonValue]]:
    return type(value) is list


def _exact_text(value: JsonValue) -> TypeIs[str]:
    return type(value) is str


def _rebuilt_reference(value: object) -> ExactObjectReference:
    if type(value) is not ExactObjectReference:
        _fail(HKLegislationEvidenceErrorCode.REFERENCE_INVALID)
    try:
        return ExactObjectReference(
            value.vault,
            value.logical_key,
            value.version_id,
            value.fingerprint,
            value.byte_length,
        )
    except Exception as error:
        raise HKLegislationEvidenceError(
            HKLegislationEvidenceErrorCode.REFERENCE_INVALID
        ) from error


def _cycle_manifest_key(cycle_id: str) -> str:
    raw = cycle_id.encode("utf-8")
    hex_value = raw.hex()
    chunks = tuple(
        f"hex-{hex_value[index : index + 112]}" for index in range(0, len(hex_value), 112)
    )
    return "/".join(
        (
            "hk-v1",
            "due-cycles",
            "cycle",
            f"sha256-{sha256(raw).hexdigest()}",
            *chunks,
            "manifest.json",
        )
    )


def _plan_key_is_bound(logical_key: str, instrument_id: str) -> bool:
    prefix = f"{_PLAN_PREFIX}/{instrument_id}/"
    if not logical_key.startswith(prefix):
        return False
    suffix = logical_key.removeprefix(prefix)
    return len(suffix) == _SHA256_HEX_LENGTH and all(
        character in "0123456789abcdef" for character in suffix
    )


def _canonical_utc(value: object) -> TypeIs[str]:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value


def _reference_snapshot(reference: ExactObjectReference) -> _ExactReferenceSnapshot:
    return _ExactReferenceSnapshot(
        reference.vault,
        reference.logical_key,
        reference.version_id,
        reference.fingerprint,
        reference.byte_length,
    )


def _disposable_reference(snapshot: _ExactReferenceSnapshot) -> ExactObjectReference:
    return ExactObjectReference(
        snapshot.vault,
        snapshot.logical_key,
        snapshot.version_id,
        snapshot.fingerprint,
        snapshot.byte_length,
    )


def _reference_identity(reference: ExactObjectReference) -> tuple[str, str, str, str, int]:
    return (
        reference.vault.value,
        reference.logical_key,
        reference.version_id,
        reference.fingerprint,
        reference.byte_length,
    )


def _validated_envelope(value: object) -> _ValidatedEnvelope:
    if type(value) is not HKLegislationEvidenceEnvelope:
        _fail(HKLegislationEvidenceErrorCode.ENVELOPE_INVALID)
    if (
        type(value.schema_id) is not str
        or value.schema_id != _ENVELOPE_SCHEMA_ID
        or type(value.schema_version) is not str
        or value.schema_version != _ENVELOPE_SCHEMA_VERSION
        or type(value.cycle_id) is not str
        or _CYCLE_ID.fullmatch(value.cycle_id) is None
        or type(value.cycle_kind) is not str
        or value.cycle_kind != _CURRENT_CYCLE_KIND
        or type(value.source_id) is not str
        or value.source_id != _CURRENT_SOURCE_ID
        or type(value.instrument_id) is not str
        or _INSTRUMENT_ID.fullmatch(value.instrument_id) is None
        or not _canonical_utc(value.observation_cutoff)
    ):
        _fail(HKLegislationEvidenceErrorCode.ENVELOPE_INVALID)
    if value.plan_manifest_reference is None:
        _fail(HKLegislationEvidenceErrorCode.PLAN_REFERENCE_REQUIRED)
    cycle_reference = _rebuilt_reference(value.source_cycle_manifest_reference)
    plan_reference = _rebuilt_reference(value.plan_manifest_reference)
    attempt_reference = _rebuilt_reference(value.terminal_attempt_reference)
    admission_reference = (
        None
        if value.admission_result_reference is None
        else _rebuilt_reference(value.admission_result_reference)
    )
    if type(value.member_references) is not tuple or not value.member_references:
        _fail(HKLegislationEvidenceErrorCode.REFERENCE_INVALID)
    member_references = tuple(_rebuilt_reference(item) for item in value.member_references)
    identities = tuple(_reference_identity(item) for item in member_references)
    if len(set(identities)) != len(identities):
        _fail(HKLegislationEvidenceErrorCode.REFERENCE_INVALID)
    if (
        cycle_reference.vault is not VaultName.PRIMARY
        or plan_reference.vault is not VaultName.PRIMARY
        or attempt_reference.vault is not VaultName.PRIMARY
        or cycle_reference.logical_key != _cycle_manifest_key(value.cycle_id)
        or not _plan_key_is_bound(plan_reference.logical_key, value.instrument_id)
        or not attempt_reference.logical_key.startswith(f"{_ATTEMPT_PREFIX}/{value.instrument_id}/")
        or attempt_reference.logical_key
        != f"{_ATTEMPT_PREFIX}/{value.instrument_id}/"
        f"{attempt_reference.fingerprint.removeprefix('sha256:')}"
    ):
        _fail(HKLegislationEvidenceErrorCode.REFERENCE_INVALID)
    return _ValidatedEnvelope(
        value.cycle_id,
        value.source_id,
        value.instrument_id,
        value.observation_cutoff,
        cycle_reference,
        _reference_snapshot(plan_reference),
        attempt_reference,
        admission_reference,
        member_references,
    )


def _read_plan(
    envelope: _ValidatedEnvelope, reader: HKLegislationEvidenceReader
) -> dict[str, JsonValue]:
    reference = envelope.plan_manifest_reference
    try:
        raw = reader.read_exact(_disposable_reference(reference))
    except Exception as error:
        raise HKLegislationEvidenceError(HKLegislationEvidenceErrorCode.READ_FAILED) from error
    if (
        type(raw) is not bytes
        or len(raw) != reference.byte_length
        or f"sha256:{sha256(raw).hexdigest()}" != reference.fingerprint
    ):
        _fail(HKLegislationEvidenceErrorCode.READ_FAILED)
    try:
        value = parse_json_bytes(raw, max_bytes=reference.byte_length)
        if canonicalize(value) != raw:
            _fail(HKLegislationEvidenceErrorCode.PLAN_INVALID)
    except HKLegislationEvidenceError:
        raise
    except Exception as error:
        raise HKLegislationEvidenceError(HKLegislationEvidenceErrorCode.PLAN_INVALID) from error
    if not _exact_object(value) or frozenset(value) != _PLAN_FIELDS:
        _fail(HKLegislationEvidenceErrorCode.PLAN_INVALID)
    return value


def _validate_plan(plan: dict[str, JsonValue], envelope: _ValidatedEnvelope) -> bool:
    schema_id = plan["schema_id"]
    schema_version = plan["schema_version"]
    instrument_id = plan["instrument_id"]
    cutoff = plan["observation_cutoff"]
    plan_fingerprint = plan["plan_fingerprint"]
    admitted = plan["authentic_source_admitted"]
    fingerprints = (
        plan["inventory_fingerprint"],
        plan["projection_fingerprint"],
        plan["source_register_fingerprint"],
    )
    if (
        not _exact_text(schema_id)
        or schema_id != _PLAN_SCHEMA_ID
        or not _exact_text(schema_version)
        or schema_version != _PLAN_SCHEMA_VERSION
        or not _exact_text(plan_fingerprint)
        or _FINGERPRINT.fullmatch(plan_fingerprint) is None
        or type(admitted) is not bool
        or not all(
            _exact_text(item) and _FINGERPRINT.fullmatch(item) is not None for item in fingerprints
        )
        or not _exact_text(plan["parser_profile"])
        or not plan["parser_profile"]
        or not _exact_text(plan["source_register_id"])
        or not plan["source_register_id"]
    ):
        _fail(HKLegislationEvidenceErrorCode.PLAN_INVALID)
    if (
        not _exact_text(instrument_id)
        or instrument_id != envelope.instrument_id
        or not _exact_text(cutoff)
        or cutoff != envelope.observation_cutoff
    ):
        _fail(HKLegislationEvidenceErrorCode.PROVENANCE_MISMATCH)
    members = plan["members"]
    missing_member_ids = plan["missing_member_ids"]
    if not _exact_list(members) or not members or not _exact_list(missing_member_ids):
        _fail(HKLegislationEvidenceErrorCode.PLAN_INVALID)
    for member in members:
        if not _exact_object(member) or frozenset(member) != _PLAN_MEMBER_FIELDS:
            _fail(HKLegislationEvidenceErrorCode.PLAN_INVALID)
        member_source = member["source_id"]
        member_instrument = member["instrument_id"]
        if (
            not _exact_text(member_source)
            or member_source != envelope.source_id
            or not _exact_text(member_instrument)
            or member_instrument != envelope.instrument_id
        ):
            _fail(HKLegislationEvidenceErrorCode.PROVENANCE_MISMATCH)
    if any(not _exact_text(item) for item in missing_member_ids):
        _fail(HKLegislationEvidenceErrorCode.PLAN_INVALID)
    fingerprint_body: dict[str, JsonValue] = {
        field: plan[field] for field in _PLAN_FINGERPRINT_FIELDS
    }
    reproduced = f"sha256:{sha256(canonicalize(fingerprint_body)).hexdigest()}"
    if reproduced != plan_fingerprint:
        _fail(HKLegislationEvidenceErrorCode.PLAN_INVALID)
    expected_key = (
        f"{_PLAN_PREFIX}/{envelope.instrument_id}/{plan_fingerprint.removeprefix('sha256:')}"
    )
    if envelope.plan_manifest_reference.logical_key != expected_key:
        _fail(HKLegislationEvidenceErrorCode.PROVENANCE_MISMATCH)
    return admitted


def admit_retained_hkel_observation(
    reference: object,
    reader: HkelRetainedEvidenceReader,
) -> HkelAuthenticAdmissionReceipt:
    """Run the full retained body/ZIP/XML profile and issue its closed receipt.

    This admits only the exact source observation as completely and safely read.
    It does not infer commencement, current-law effect, corpus eligibility, or
    release authority.
    """
    try:
        index = index_retained_hkel_observation(reference, reader)
        structure = profile_retained_hkel_structure(index, reader)
        endpoint_objects = index.endpoint_objects
        archive_members = index.archive_members
        pairs = index.bilingual_xml_pairs
        specifications = index.publication_specifications
        records = structure.bilingual_records
        if (
            type(endpoint_objects) is not tuple
            or len(endpoint_objects) != _EXPECTED_ENDPOINTS
            or type(archive_members) is not tuple
            or len(archive_members) != _EXPECTED_ARCHIVE_MEMBERS
            or type(pairs) is not tuple
            or len(pairs) != _EXPECTED_BILINGUAL_PAIRS
            or type(specifications) is not tuple
            or len(specifications) != _EXPECTED_SPECIFICATIONS
            or type(records) is not tuple
            or len(records) != _EXPECTED_BILINGUAL_PAIRS
            or structure.admission_authority != "NONE"
        ):
            _fail(HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID)
        reuse_keys = tuple(
            sorted(
                (
                    HkelAuthenticArchiveReuseKey.issue(
                        endpoint.endpoint_id,
                        endpoint.reference.fingerprint,
                        index.publication_profile_fingerprint,
                    )
                    for endpoint in endpoint_objects
                    if getattr(endpoint, "media_type", None) == "application/zip"
                ),
                key=lambda item: item.archive_endpoint_id,
            )
        )
        issue_refs = tuple(
            sorted(
                f"hkel-structure/{item.issue_code.value}/{item.count}"
                for item in structure.issue_counts
            )
        )
        return HkelAuthenticAdmissionReceipt.issue(
            HkelAuthenticAdmissionFacts(
                index.attempt_id,
                index.observation_cutoff,
                index.report_fingerprint,
                index.source_observation_fingerprint,
                structure.profile_fingerprint,
                len(archive_members),
                len(pairs),
                len(specifications),
                reuse_keys,
                issue_refs,
            )
        )
    except HKLegislationEvidenceError:
        raise
    except Exception as error:
        raise HKLegislationEvidenceError(
            HKLegislationEvidenceErrorCode.RETAINED_ADMISSION_INVALID
        ) from error


def load_authentic_legislation_bundle(
    envelope: object,
    reader: HKLegislationEvidenceReader,
) -> Never:
    """Reject current HKeL candidates until Task 7 freezes authentic admission.

    Only the exact plan is reread in this negative slice. The cycle, terminal,
    admission, and member references are retained as provenance bindings but
    cannot be consumed as authentic evidence yet.
    """
    try:
        validated = _validated_envelope(envelope)
    except HKLegislationEvidenceError:
        raise
    except Exception as error:
        raise HKLegislationEvidenceError(HKLegislationEvidenceErrorCode.ENVELOPE_INVALID) from error
    plan = _read_plan(validated, reader)
    _validate_plan(plan, validated)
    _fail(HKLegislationEvidenceErrorCode.AUTHENTIC_SOURCE_NOT_ADMITTED)
