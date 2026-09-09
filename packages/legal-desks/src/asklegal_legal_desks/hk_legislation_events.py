"""Pure evidence-bound Hong Kong legislation event timeline decisions."""

from __future__ import annotations

import re
import weakref
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Never, TypeIs

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .hk_reconstruction_report import (
    ReconstructionExecutionReport,
    validate_reconstruction_execution_report,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_SCHEMA_ID = "asklegal.hk-legislation-event-timeline"
_SCHEMA_VERSION = "1.0.0"
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,159}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,159}$")
_OFFICIAL_VERSION_ID = re.compile(r"^ofv_[0-9a-f]{48}$")
_LEGAL_STATUS_EVENT_ID = re.compile(r"^lse_[0-9a-f]{48}$")
_LEGAL_LOCATION_ID = re.compile(r"^loc_[0-9a-f]{48}$")
_REPORT_ID = re.compile(r"^rex_[0-9a-f]{48}$")
_PLAN_ID = re.compile(r"^rpl_[0-9a-f]{48}$")
_ENGINE_BUILD_ID = re.compile(r"^eng_[0-9a-f]{48}$")
_ARTIFACT_ID = re.compile(r"^art_[0-9a-f]{48}$")
_RECONSTRUCTED_ARTIFACT_ID = re.compile(r"^rca_[0-9a-f]{48}$")
_REFERENCE_PAIR_SIZE = 2
_MIN_SOURCE_FACT_REF = 3
_MAX_SOURCE_FACT_REF = 1_024
_ASCII_CONTROL_LIMIT = 32
_ASCII_DELETE = 127
_REPORT_PACKAGE_ROOT = Path(__file__).resolve().parent / "_hk_legislation_package"


class HKLegislationEventErrorCode(StrEnum):
    """Closed malformed timeline and replay failures."""

    CUTOFF_INVALID = "HK_LEGISLATION_EVENT_CUTOFF_INVALID"
    DECISION_INVALID = "HK_LEGISLATION_EVENT_DECISION_INVALID"
    EVENT_INVALID = "HK_LEGISLATION_EVENT_INVALID"
    TIMELINE_INVALID = "HK_LEGISLATION_EVENT_TIMELINE_INVALID"


class HKLegislationEventError(ValueError):
    """One normalized event-boundary rejection."""

    code: HKLegislationEventErrorCode

    def __init__(self, code: HKLegislationEventErrorCode) -> None:
        """Create one stable closed rejection."""
        self.code = code
        super().__init__(code.value)


class HKLegislationEventKind(StrEnum):
    """Closed legal-event facts accepted by this pure merge boundary."""

    PUBLICATION = "PUBLICATION"
    COMMENCEMENT = "COMMENCEMENT"
    CESSATION = "CESSATION"
    REVIVAL = "REVIVAL"
    AMENDMENT = "AMENDMENT"
    CORRECTION = "CORRECTION"
    EDITORIAL = "EDITORIAL"
    RECONSTRUCTION = "RECONSTRUCTION"


class HKLegislationEventSource(StrEnum):
    """Closed admitted-shaped source classes without an authenticity claim."""

    PUBLISHER = "PUBLISHER"
    GAZETTE = "GAZETTE"
    EDITORIAL_RECORD = "EDITORIAL_RECORD"
    ACCEPTED_RECONSTRUCTION = "ACCEPTED_RECONSTRUCTION"


class HKLegislationDisposition(StrEnum):
    """The five accepted Hong Kong legislation legal dispositions."""

    SEARCHABLE_CURRENT = "SEARCHABLE_CURRENT"
    WAITING_ROOM = "WAITING_ROOM"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    HISTORICAL = "HISTORICAL"
    QUARANTINE = "QUARANTINE"


class HKLegislationProcessingOutcome(StrEnum):
    """Processing status, deliberately separate from legal disposition."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


class HKLegislationCoverageEffect(StrEnum):
    """Coverage consequence, separate from processing and legal state."""

    NONE = "NONE"
    COVERAGE_GAP = "COVERAGE_GAP"


class HKLegislationSourceContractReview(StrEnum):
    """Source-contract review dimension, never a legal-effect inference."""

    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"


@dataclass(frozen=True, slots=True)
class HKLegislationAcquiredEventFacts:
    """Canonical acquired source refs before any legal-event inference."""

    verified_item_refs: tuple[str, ...]
    review_issue_refs: tuple[str, ...]


def bind_hk_legislation_acquired_event_facts(
    verified_item_refs: object,
    review_issue_refs: object,
) -> HKLegislationAcquiredEventFacts:
    """Bind exact acquisition refs while deliberately adding no effect fields."""

    def exact_refs(value: object) -> tuple[str, ...]:
        if not _exact_object_tuple(value):
            _fail(HKLegislationEventErrorCode.EVENT_INVALID)
        result: list[str] = []
        for item in value:
            if (
                type(item) is not str
                or not _MIN_SOURCE_FACT_REF <= len(item) <= _MAX_SOURCE_FACT_REF
                or item != item.strip()
                or any(
                    ord(character) < _ASCII_CONTROL_LIMIT or ord(character) == _ASCII_DELETE
                    for character in item
                )
            ):
                _fail(HKLegislationEventErrorCode.EVENT_INVALID)
            result.append(item)
        exact = tuple(result)
        if exact != tuple(sorted(set(exact))):
            _fail(HKLegislationEventErrorCode.EVENT_INVALID)
        return exact

    verified = exact_refs(verified_item_refs)
    reviews = exact_refs(review_issue_refs)
    if not verified:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return HKLegislationAcquiredEventFacts(verified, reviews)


@dataclass(frozen=True, slots=True)
class HKLegislationReconstructionAuthority:
    """Detached authority facts that a reconstruction Report cannot self-assert."""

    accepted_report_id: str
    accepted_report_fingerprint: str
    reconstruction_plan_id: str
    reconstruction_plan_fingerprint: str
    base_official_version_id: str
    base_official_version_fingerprint: str
    engine_build_id: str
    engine_build_fingerprint: str
    expected_alignment_id: str
    expected_alignment_fingerprint: str
    affected_location_refs: tuple[tuple[str, str], ...]
    reconstructed_artifact_id: str
    reconstructed_artifact_fingerprint: str
    canonical_output_fingerprint: str
    canonical_output_byte_size: int


@dataclass(frozen=True, slots=True)
class HKLegislationEvent:
    """One admitted-shaped pure legal-event fact and its exact evidence binding."""

    event_ref: str
    event_identity: str
    legal_location_id: str
    official_version_id: str
    kind: HKLegislationEventKind
    source: HKLegislationEventSource
    effective_at: str
    evidence_fingerprint: str
    basis_event_refs: tuple[str, ...]
    reconstruction_report: ReconstructionExecutionReport | None
    reconstruction_authority: HKLegislationReconstructionAuthority | None = None


@dataclass(frozen=True, slots=True)
class HKLegislationEventTimeline:
    """One location/version event inventory at an explicit processing boundary."""

    schema_id: str
    schema_version: str
    legal_location_id: str
    official_version_id: str
    source_facts_complete: bool
    known_stale: bool
    source_contract_review: HKLegislationSourceContractReview
    events: tuple[HKLegislationEvent, ...]


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HKLegislationEventDecision:
    """One event decision with four independent outcome dimensions."""

    legal_location_id: str
    official_version_id: str
    processing_outcome: HKLegislationProcessingOutcome
    legal_disposition: HKLegislationDisposition | None
    coverage_effect: HKLegislationCoverageEffect
    source_contract_review: HKLegislationSourceContractReview
    reason_code: str
    controlling_event_refs: tuple[str, ...]
    unresolved_fact_codes: tuple[str, ...]
    timeline_fingerprint: str
    decision_fingerprint: str = dataclass_field(init=False, default="", repr=False)

    def __post_init__(self) -> None:
        """Validate exact outcome coherence independently of factory issuance."""
        _validate_decision_structure(self)

    def assert_factory_issued(self) -> None:
        """Require this exact live decision and its current primitive snapshot."""
        try:
            self.__post_init__()
            snapshot = _decision_fingerprint(self)
        except (AttributeError, TypeError, ValueError) as error:
            raise HKLegislationEventError(HKLegislationEventErrorCode.DECISION_INVALID) from error
        issued = _DECISION_ISSUANCE.get(id(self))
        if (
            issued is None
            or issued.reference() is not self
            or issued.snapshot != snapshot
            or self.decision_fingerprint != snapshot
        ):
            _fail(HKLegislationEventErrorCode.DECISION_INVALID)


@dataclass(frozen=True, slots=True)
class _IssuedDecision:
    reference: weakref.ReferenceType[object]
    snapshot: str


@dataclass(frozen=True, slots=True)
class _TimelineHeaderSnapshot:
    schema_id: str
    schema_version: str
    legal_location_id: str
    official_version_id: str
    source_facts_complete: bool
    known_stale: bool
    source_contract_review: HKLegislationSourceContractReview


@dataclass(frozen=True, slots=True)
class _EventPrimitiveSnapshot:
    event_ref: str
    event_identity: str
    legal_location_id: str
    official_version_id: str
    kind: HKLegislationEventKind
    source: HKLegislationEventSource
    effective_at: str
    evidence_fingerprint: str
    basis_event_refs: tuple[str, ...]
    reconstruction_report: ReconstructionExecutionReport | None
    reconstruction_authority: HKLegislationReconstructionAuthority | None


_DECISION_ISSUANCE: dict[int, _IssuedDecision] = {}


def _fail(code: HKLegislationEventErrorCode) -> Never:
    raise HKLegislationEventError(code)


def _canonical_utc(value: object) -> TypeIs[str]:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value


def _identity(value: object) -> str:
    if type(value) is not str or _IDENTITY.fullmatch(value) is None:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return value


def _family_identity(value: object, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return value


def _exact_fingerprint(value: object) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return value


def _reconstruction_authority_snapshot(
    value: object,
) -> HKLegislationReconstructionAuthority:
    if type(value) is not HKLegislationReconstructionAuthority:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    affected = _authority_location_inventory(value.affected_location_refs)
    return HKLegislationReconstructionAuthority(
        _family_identity(value.accepted_report_id, _REPORT_ID),
        _exact_fingerprint(value.accepted_report_fingerprint),
        _family_identity(value.reconstruction_plan_id, _PLAN_ID),
        _exact_fingerprint(value.reconstruction_plan_fingerprint),
        _family_identity(value.base_official_version_id, _OFFICIAL_VERSION_ID),
        _exact_fingerprint(value.base_official_version_fingerprint),
        _family_identity(value.engine_build_id, _ENGINE_BUILD_ID),
        _exact_fingerprint(value.engine_build_fingerprint),
        _family_identity(value.expected_alignment_id, _ARTIFACT_ID),
        _exact_fingerprint(value.expected_alignment_fingerprint),
        affected,
        _family_identity(value.reconstructed_artifact_id, _RECONSTRUCTED_ARTIFACT_ID),
        _exact_fingerprint(value.reconstructed_artifact_fingerprint),
        _exact_fingerprint(value.canonical_output_fingerprint),
        _positive_exact_int(value.canonical_output_byte_size),
    )


def _authority_location_inventory(value: object) -> tuple[tuple[str, str], ...]:
    if not _exact_object_tuple(value) or not value:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    snapshot: list[tuple[str, str]] = []
    for item in value:
        if not _exact_object_tuple(item) or len(item) != _REFERENCE_PAIR_SIZE:
            _fail(HKLegislationEventErrorCode.EVENT_INVALID)
        snapshot.append(
            (
                _family_identity(item[0], _LEGAL_LOCATION_ID),
                _exact_fingerprint(item[1]),
            )
        )
    if len({ref_id for ref_id, _fingerprint in snapshot}) != len(snapshot):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return tuple(snapshot)


def _positive_exact_int(value: object) -> int:
    if type(value) is not int or value <= 0:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return value


def _exact_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _event_basis(
    evidence_fingerprint: object,
    basis_event_refs: object,
) -> tuple[str, ...]:
    if (
        type(evidence_fingerprint) is not str
        or _FINGERPRINT.fullmatch(evidence_fingerprint) is None
        or not _exact_object_tuple(basis_event_refs)
    ):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    basis = tuple(_identity(item) for item in basis_event_refs)
    if len(set(basis)) != len(basis):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return basis


def _report_object(value: JsonValue | None) -> dict[str, JsonValue]:
    if type(value) is not dict:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return value


def _report_array(value: JsonValue | None) -> list[JsonValue]:
    if type(value) is not list:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return value


def _report_ref(
    value: JsonValue | None,
    expected_type: str,
    identity_pattern: re.Pattern[str] | None = None,
) -> tuple[str, str]:
    reference = _report_object(value)
    if frozenset(reference) != frozenset(("ref_type", "ref_id", "fingerprint")):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    ref_type = reference.get("ref_type")
    ref_id = reference.get("ref_id")
    fingerprint = reference.get("fingerprint")
    if (
        type(ref_type) is not str
        or ref_type != expected_type
        or type(ref_id) is not str
        or (identity_pattern is not None and identity_pattern.fullmatch(ref_id) is None)
        or type(fingerprint) is not str
        or _FINGERPRINT.fullmatch(fingerprint) is None
    ):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return ref_id, fingerprint


def _event_report_refs(document: dict[str, JsonValue]) -> tuple[tuple[str, str], ...]:
    validation = _report_object(document.get("event_chain_validation"))
    refs = _report_array(validation.get("event_refs"))
    event_refs: list[tuple[str, str]] = []
    for value in refs:
        event_ref = _report_ref(
            value,
            "LEGAL_STATUS_EVENT",
            _LEGAL_STATUS_EVENT_ID,
        )
        event_refs.append((_identity(event_ref[0]), event_ref[1]))
    if len(set(event_refs)) != len(event_refs):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return tuple(event_refs)


def _affected_report_refs(document: dict[str, JsonValue]) -> tuple[tuple[str, str], ...]:
    dependency = _report_object(document.get("dependency_validation"))
    values = _report_array(dependency.get("affected_location_refs"))
    refs = tuple(_report_ref(value, "LEGAL_LOCATION", _LEGAL_LOCATION_ID) for value in values)
    if not refs or len({ref_id for ref_id, _fingerprint in refs}) != len(refs):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return refs


def _validate_report_authority_binding(
    report: ReconstructionExecutionReport,
    document: dict[str, JsonValue],
    legal_location_id: str,
    official_version_id: str,
    authority: HKLegislationReconstructionAuthority,
) -> None:
    affected = _affected_report_refs(document)
    plan = _report_ref(
        document.get("reconstruction_plan_ref"),
        "RECONSTRUCTION_PLAN",
        _PLAN_ID,
    )
    base = _report_object(document.get("base_validation"))
    report_version = _report_ref(
        base.get("official_version_ref"),
        "OFFICIAL_VERSION",
        _OFFICIAL_VERSION_ID,
    )
    engine_build = _report_ref(
        document.get("engine_build_ref"),
        "ENGINE_BUILD",
        _ENGINE_BUILD_ID,
    )
    bilingual = _report_object(document.get("bilingual_validation"))
    expected_alignment = _report_ref(
        bilingual.get("expected_alignment_map_ref"),
        "ARTIFACT",
        _ARTIFACT_ID,
    )
    output = _report_object(document.get("artifact_output"))
    reconstructed_artifact = _report_ref(
        output.get("reconstructed_consolidation_artifact_ref"),
        "RECONSTRUCTED_CONSOLIDATION_ARTIFACT",
        _RECONSTRUCTED_ARTIFACT_ID,
    )
    canonical_output = _report_object(output.get("canonical_bilingual_output_ref"))
    canonical_output_fingerprint = _exact_fingerprint(canonical_output.get("fingerprint"))
    canonical_output_byte_size = _positive_exact_int(canonical_output.get("byte_size"))
    if (
        (report.reconstruction_execution_report_id, report.fingerprint)
        != (authority.accepted_report_id, authority.accepted_report_fingerprint)
        or plan != (authority.reconstruction_plan_id, authority.reconstruction_plan_fingerprint)
        or report_version
        != (
            authority.base_official_version_id,
            authority.base_official_version_fingerprint,
        )
        or report_version[0] != official_version_id
        or engine_build != (authority.engine_build_id, authority.engine_build_fingerprint)
        or expected_alignment
        != (
            authority.expected_alignment_id,
            authority.expected_alignment_fingerprint,
        )
        or affected != authority.affected_location_refs
        or legal_location_id not in {ref_id for ref_id, _fingerprint in affected}
        or reconstructed_artifact
        != (
            authority.reconstructed_artifact_id,
            authority.reconstructed_artifact_fingerprint,
        )
        or canonical_output_fingerprint != authority.canonical_output_fingerprint
        or canonical_output_byte_size != authority.canonical_output_byte_size
    ):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)


def _reconstruction_report_snapshot(
    event: _EventPrimitiveSnapshot,
) -> tuple[
    ReconstructionExecutionReport | None,
    HKLegislationReconstructionAuthority | None,
]:
    report = event.reconstruction_report
    authority = event.reconstruction_authority
    if event.kind is not HKLegislationEventKind.RECONSTRUCTION:
        if report is not None or authority is not None:
            _fail(HKLegislationEventErrorCode.EVENT_INVALID)
        return None, None
    if (
        event.source is not HKLegislationEventSource.ACCEPTED_RECONSTRUCTION
        or not event.basis_event_refs
        or type(report) is not ReconstructionExecutionReport
    ):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    authority_snapshot = _reconstruction_authority_snapshot(authority)
    validated = validate_reconstruction_execution_report(_REPORT_PACKAGE_ROOT, report)
    if event.evidence_fingerprint != validated.fingerprint:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    _validate_report_authority_binding(
        validated,
        validated.document(),
        event.legal_location_id,
        event.official_version_id,
        authority_snapshot,
    )
    return validated, authority_snapshot


def _validate_event_source_authority(
    kind: HKLegislationEventKind,
    source: HKLegislationEventSource,
) -> None:
    if kind is HKLegislationEventKind.RECONSTRUCTION:
        authorized = source is HKLegislationEventSource.ACCEPTED_RECONSTRUCTION
    elif kind is HKLegislationEventKind.EDITORIAL:
        authorized = source is HKLegislationEventSource.EDITORIAL_RECORD
    else:
        authorized = source in {
            HKLegislationEventSource.PUBLISHER,
            HKLegislationEventSource.GAZETTE,
        }
    if not authorized:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)


def _report_envelope_snapshot(value: object) -> ReconstructionExecutionReport | None:
    if value is None:
        return None
    if type(value) is not ReconstructionExecutionReport:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    report_id = value.reconstruction_execution_report_id
    fingerprint = value.fingerprint
    canonical_bytes = value.canonical_bytes
    if (
        type(report_id) is not str
        or type(fingerprint) is not str
        or type(canonical_bytes) is not bytes
    ):
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    return ReconstructionExecutionReport(report_id, fingerprint, bytes(canonical_bytes))


def _capture_event_primitives(value: object) -> _EventPrimitiveSnapshot:
    if type(value) is not HKLegislationEvent:
        _fail(HKLegislationEventErrorCode.EVENT_INVALID)
    try:
        event_ref = _identity(value.event_ref)
        event_identity = _identity(value.event_identity)
        legal_location_id = _family_identity(value.legal_location_id, _LEGAL_LOCATION_ID)
        official_version_id = _family_identity(value.official_version_id, _OFFICIAL_VERSION_ID)
        kind = value.kind
        source = value.source
        effective_at = value.effective_at
        evidence_fingerprint = _exact_fingerprint(value.evidence_fingerprint)
        basis_event_refs_value = value.basis_event_refs
        reconstruction_report_value = _report_envelope_snapshot(value.reconstruction_report)
        reconstruction_authority_value = value.reconstruction_authority
        if type(kind) is not HKLegislationEventKind:
            _fail(HKLegislationEventErrorCode.EVENT_INVALID)
        if type(source) is not HKLegislationEventSource:
            _fail(HKLegislationEventErrorCode.EVENT_INVALID)
        _validate_event_source_authority(kind, source)
        if not _canonical_utc(effective_at):
            _fail(HKLegislationEventErrorCode.EVENT_INVALID)
        basis_event_refs = _event_basis(evidence_fingerprint, basis_event_refs_value)
        reconstruction_authority = (
            None
            if reconstruction_authority_value is None
            else _reconstruction_authority_snapshot(reconstruction_authority_value)
        )
        return _EventPrimitiveSnapshot(
            event_ref=event_ref,
            event_identity=event_identity,
            legal_location_id=legal_location_id,
            official_version_id=official_version_id,
            kind=kind,
            source=source,
            effective_at=effective_at,
            evidence_fingerprint=evidence_fingerprint,
            basis_event_refs=basis_event_refs,
            reconstruction_report=reconstruction_report_value,
            reconstruction_authority=reconstruction_authority,
        )
    except HKLegislationEventError:
        raise
    except Exception as error:
        raise HKLegislationEventError(HKLegislationEventErrorCode.EVENT_INVALID) from error


def _event_snapshot(primitive_snapshot: _EventPrimitiveSnapshot) -> HKLegislationEvent:
    try:
        reconstruction_report, reconstruction_authority = _reconstruction_report_snapshot(
            primitive_snapshot
        )
    except HKLegislationEventError:
        raise
    except Exception as error:
        raise HKLegislationEventError(HKLegislationEventErrorCode.EVENT_INVALID) from error
    return HKLegislationEvent(
        primitive_snapshot.event_ref,
        primitive_snapshot.event_identity,
        primitive_snapshot.legal_location_id,
        primitive_snapshot.official_version_id,
        primitive_snapshot.kind,
        primitive_snapshot.source,
        primitive_snapshot.effective_at,
        primitive_snapshot.evidence_fingerprint,
        primitive_snapshot.basis_event_refs,
        reconstruction_report,
        reconstruction_authority,
    )


def _timeline_header(
    value: HKLegislationEventTimeline,
) -> tuple[_TimelineHeaderSnapshot, tuple[HKLegislationEvent, ...]]:
    schema_id = value.schema_id
    schema_version = value.schema_version
    legal_location_id = value.legal_location_id
    official_version_id = value.official_version_id
    source_facts_complete = value.source_facts_complete
    known_stale = value.known_stale
    source_contract_review = value.source_contract_review
    events = value.events
    if (
        type(schema_id) is not str
        or schema_id != _SCHEMA_ID
        or type(schema_version) is not str
        or schema_version != _SCHEMA_VERSION
        or type(source_facts_complete) is not bool
        or type(known_stale) is not bool
        or type(source_contract_review) is not HKLegislationSourceContractReview
        or type(events) is not tuple
        or not events
    ):
        _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
    return (
        _TimelineHeaderSnapshot(
            schema_id,
            schema_version,
            _family_identity(legal_location_id, _LEGAL_LOCATION_ID),
            _family_identity(official_version_id, _OFFICIAL_VERSION_ID),
            source_facts_complete,
            known_stale,
            source_contract_review,
        ),
        events,
    )


def _validate_event_binding(
    event: HKLegislationEvent, by_ref: dict[str, HKLegislationEvent]
) -> None:
    if any(
        basis not in by_ref
        or basis == event.event_ref
        or by_ref[basis].effective_at > event.effective_at
        for basis in event.basis_event_refs
    ):
        _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
    if event.kind is HKLegislationEventKind.REVIVAL:
        if (
            len(event.basis_event_refs) != 1
            or by_ref[event.basis_event_refs[0]].kind is not HKLegislationEventKind.CESSATION
        ):
            _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
        return
    if event.kind is HKLegislationEventKind.RECONSTRUCTION:
        permitted = {
            HKLegislationEventKind.AMENDMENT,
            HKLegislationEventKind.CORRECTION,
            HKLegislationEventKind.EDITORIAL,
        }
        if any(by_ref[basis].kind not in permitted for basis in event.basis_event_refs):
            _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
        report = event.reconstruction_report
        if type(report) is not ReconstructionExecutionReport:
            _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
        expected_refs = tuple(
            (basis, by_ref[basis].evidence_fingerprint) for basis in event.basis_event_refs
        )
        if _event_report_refs(report.document()) != expected_refs:
            _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
        return
    if event.basis_event_refs:
        _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)


def _validate_event_inventory(
    events: tuple[HKLegislationEvent, ...], location: str, version: str
) -> None:
    if any(
        event.legal_location_id != location or event.official_version_id != version
        for event in events
    ):
        _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
    refs = tuple(event.event_ref for event in events)
    identities = tuple(event.event_identity for event in events)
    if len(set(refs)) != len(refs) or len(set(identities)) != len(identities):
        _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
    by_ref = {event.event_ref: event for event in events}
    reconstructed_basis: set[str] = set()
    for event in events:
        _validate_event_binding(event, by_ref)
        if event.kind is HKLegislationEventKind.RECONSTRUCTION:
            if any(basis in reconstructed_basis for basis in event.basis_event_refs):
                _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
            reconstructed_basis.update(event.basis_event_refs)
    _validate_lifecycle_chronology(events)


def _validate_lifecycle_chronology(events: tuple[HKLegislationEvent, ...]) -> None:
    publications = tuple(
        event for event in events if event.kind is HKLegislationEventKind.PUBLICATION
    )
    commencements = tuple(
        event for event in events if event.kind is HKLegislationEventKind.COMMENCEMENT
    )
    if any(
        not any(
            publication.effective_at <= commencement.effective_at for publication in publications
        )
        for commencement in commencements
    ):
        _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)

    status_events = tuple(
        event
        for event in events
        if event.kind
        in {
            HKLegislationEventKind.COMMENCEMENT,
            HKLegislationEventKind.CESSATION,
            HKLegislationEventKind.REVIVAL,
        }
    )
    operative = False
    operative_since: str | None = None
    applicable_cessation: HKLegislationEvent | None = None
    for effective_at in dict.fromkeys(event.effective_at for event in status_events):
        simultaneous = tuple(event for event in status_events if event.effective_at == effective_at)
        if len({event.kind for event in simultaneous}) > 1:
            break
        for event in simultaneous:
            if event.kind is HKLegislationEventKind.COMMENCEMENT:
                if operative or applicable_cessation is not None:
                    _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
                operative = True
                operative_since = event.effective_at
                applicable_cessation = None
            elif event.kind is HKLegislationEventKind.CESSATION:
                if (
                    not operative
                    or operative_since is None
                    or event.effective_at <= operative_since
                ):
                    _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
                operative = False
                applicable_cessation = event
            elif (
                operative
                or applicable_cessation is None
                or event.effective_at <= applicable_cessation.effective_at
                or event.basis_event_refs != (applicable_cessation.event_ref,)
            ):
                _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
            else:
                operative = True
                operative_since = event.effective_at
                applicable_cessation = None


def _timeline_snapshot(value: object) -> HKLegislationEventTimeline:
    if type(value) is not HKLegislationEventTimeline:
        _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
    try:
        header, event_values = _timeline_header(value)
        del value
        primitive_events = tuple(_capture_event_primitives(event) for event in event_values)
        del event_values
        events = tuple(
            sorted(
                (_event_snapshot(event) for event in primitive_events),
                key=lambda event: (event.effective_at, event.event_ref),
            )
        )
        _validate_event_inventory(
            events,
            header.legal_location_id,
            header.official_version_id,
        )
    except HKLegislationEventError:
        raise
    except Exception as error:
        raise HKLegislationEventError(HKLegislationEventErrorCode.TIMELINE_INVALID) from error
    return HKLegislationEventTimeline(
        header.schema_id,
        header.schema_version,
        header.legal_location_id,
        header.official_version_id,
        header.source_facts_complete,
        header.known_stale,
        header.source_contract_review,
        events,
    )


def _timeline_fingerprint(timeline: HKLegislationEventTimeline) -> str:
    document: dict[str, JsonValue] = {
        "schema_id": timeline.schema_id,
        "schema_version": timeline.schema_version,
        "legal_location_id": timeline.legal_location_id,
        "official_version_id": timeline.official_version_id,
        "source_facts_complete": timeline.source_facts_complete,
        "known_stale": timeline.known_stale,
        "source_contract_review": timeline.source_contract_review.value,
        "events": [
            {
                "event_ref": event.event_ref,
                "event_identity": event.event_identity,
                "legal_location_id": event.legal_location_id,
                "official_version_id": event.official_version_id,
                "kind": event.kind.value,
                "source": event.source.value,
                "effective_at": event.effective_at,
                "evidence_fingerprint": event.evidence_fingerprint,
                "basis_event_refs": list(event.basis_event_refs),
                "reconstruction_report_ref": (
                    None
                    if event.reconstruction_report is None
                    else {
                        "ref_type": "RECONSTRUCTION_EXECUTION_REPORT",
                        "ref_id": (event.reconstruction_report.reconstruction_execution_report_id),
                        "fingerprint": event.reconstruction_report.fingerprint,
                    }
                ),
                "reconstruction_authority": (
                    None
                    if event.reconstruction_authority is None
                    else {
                        "accepted_report_id": event.reconstruction_authority.accepted_report_id,
                        "accepted_report_fingerprint": (
                            event.reconstruction_authority.accepted_report_fingerprint
                        ),
                        "reconstruction_plan_id": (
                            event.reconstruction_authority.reconstruction_plan_id
                        ),
                        "reconstruction_plan_fingerprint": (
                            event.reconstruction_authority.reconstruction_plan_fingerprint
                        ),
                        "base_official_version_id": (
                            event.reconstruction_authority.base_official_version_id
                        ),
                        "base_official_version_fingerprint": (
                            event.reconstruction_authority.base_official_version_fingerprint
                        ),
                        "engine_build_id": event.reconstruction_authority.engine_build_id,
                        "engine_build_fingerprint": (
                            event.reconstruction_authority.engine_build_fingerprint
                        ),
                        "expected_alignment_id": (
                            event.reconstruction_authority.expected_alignment_id
                        ),
                        "expected_alignment_fingerprint": (
                            event.reconstruction_authority.expected_alignment_fingerprint
                        ),
                        "affected_location_refs": [
                            {"ref_id": ref_id, "fingerprint": fingerprint}
                            for ref_id, fingerprint in (
                                event.reconstruction_authority.affected_location_refs
                            )
                        ],
                        "reconstructed_artifact_id": (
                            event.reconstruction_authority.reconstructed_artifact_id
                        ),
                        "reconstructed_artifact_fingerprint": (
                            event.reconstruction_authority.reconstructed_artifact_fingerprint
                        ),
                        "canonical_output_fingerprint": (
                            event.reconstruction_authority.canonical_output_fingerprint
                        ),
                        "canonical_output_byte_size": (
                            event.reconstruction_authority.canonical_output_byte_size
                        ),
                    }
                ),
            }
            for event in timeline.events
        ],
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(document))).hexdigest()}"


def _validate_decision_structure(decision: HKLegislationEventDecision) -> None:
    if (
        type(decision.legal_location_id) is not str
        or _LEGAL_LOCATION_ID.fullmatch(decision.legal_location_id) is None
        or type(decision.official_version_id) is not str
        or _OFFICIAL_VERSION_ID.fullmatch(decision.official_version_id) is None
        or type(decision.processing_outcome) is not HKLegislationProcessingOutcome
        or (
            decision.legal_disposition is not None
            and type(decision.legal_disposition) is not HKLegislationDisposition
        )
        or type(decision.coverage_effect) is not HKLegislationCoverageEffect
        or type(decision.source_contract_review) is not HKLegislationSourceContractReview
        or type(decision.reason_code) is not str
        or _CODE.fullmatch(decision.reason_code) is None
        or type(decision.controlling_event_refs) is not tuple
        or type(decision.unresolved_fact_codes) is not tuple
        or type(decision.timeline_fingerprint) is not str
        or _FINGERPRINT.fullmatch(decision.timeline_fingerprint) is None
        or type(decision.decision_fingerprint) is not str
        or (
            decision.decision_fingerprint != ""
            and _FINGERPRINT.fullmatch(decision.decision_fingerprint) is None
        )
    ):
        _fail(HKLegislationEventErrorCode.DECISION_INVALID)
    if (
        any(
            type(item) is not str or _IDENTITY.fullmatch(item) is None
            for item in decision.controlling_event_refs
        )
        or len(set(decision.controlling_event_refs)) != len(decision.controlling_event_refs)
        or any(
            type(item) is not str or _CODE.fullmatch(item) is None
            for item in decision.unresolved_fact_codes
        )
        or len(set(decision.unresolved_fact_codes)) != len(decision.unresolved_fact_codes)
    ):
        _fail(HKLegislationEventErrorCode.DECISION_INVALID)
    if decision.processing_outcome is HKLegislationProcessingOutcome.BLOCK:
        coherent = (
            decision.legal_disposition is None
            and decision.coverage_effect is HKLegislationCoverageEffect.NONE
        )
    elif decision.processing_outcome is HKLegislationProcessingOutcome.QUARANTINE:
        coherent = (
            decision.legal_disposition is HKLegislationDisposition.QUARANTINE
            and decision.coverage_effect is HKLegislationCoverageEffect.NONE
        )
    else:
        known_stale_carry_forward = (
            decision.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT
            and decision.coverage_effect is HKLegislationCoverageEffect.COVERAGE_GAP
            and decision.reason_code == "KNOWN_STALE_ANALYTICAL_CARRY_FORWARD"
            and decision.unresolved_fact_codes
            == ("KNOWN_STALE_WARNING_AND_AUTHORITY_NOTE_REQUIRED",)
        )
        reconstructed_gap = (
            decision.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT
            and decision.coverage_effect is HKLegislationCoverageEffect.COVERAGE_GAP
            and decision.reason_code == "OPERATIVE_CURRENT_TEXT_RECONSTRUCTED"
            and not decision.unresolved_fact_codes
        )
        ordinary_pass = decision.legal_disposition in {
            HKLegislationDisposition.SEARCHABLE_CURRENT,
            HKLegislationDisposition.WAITING_ROOM,
            HKLegislationDisposition.EVIDENCE_ONLY,
            HKLegislationDisposition.HISTORICAL,
        } and (decision.coverage_effect is HKLegislationCoverageEffect.COVERAGE_GAP) == (
            decision.legal_disposition is HKLegislationDisposition.EVIDENCE_ONLY
        )
        coherent = known_stale_carry_forward or reconstructed_gap or ordinary_pass
    if not coherent:
        _fail(HKLegislationEventErrorCode.DECISION_INVALID)


def _decision_fingerprint(decision: HKLegislationEventDecision) -> str:
    document: dict[str, JsonValue] = {
        "legal_location_id": decision.legal_location_id,
        "official_version_id": decision.official_version_id,
        "processing_outcome": decision.processing_outcome.value,
        "legal_disposition": (
            None if decision.legal_disposition is None else decision.legal_disposition.value
        ),
        "coverage_effect": decision.coverage_effect.value,
        "source_contract_review": decision.source_contract_review.value,
        "reason_code": decision.reason_code,
        "controlling_event_refs": list(decision.controlling_event_refs),
        "unresolved_fact_codes": list(decision.unresolved_fact_codes),
        "timeline_fingerprint": decision.timeline_fingerprint,
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(document))).hexdigest()}"


def _issue_decision(decision: HKLegislationEventDecision) -> HKLegislationEventDecision:
    snapshot = _decision_fingerprint(decision)
    object.__setattr__(decision, "decision_fingerprint", snapshot)
    identity = id(decision)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        issued = _DECISION_ISSUANCE.get(identity)
        if issued is not None and issued.reference is reference:
            del _DECISION_ISSUANCE[identity]

    _DECISION_ISSUANCE[identity] = _IssuedDecision(weakref.ref(decision, cleanup), snapshot)
    decision.assert_factory_issued()
    return decision


@dataclass(frozen=True, slots=True)
class _DecisionSpec:
    processing_outcome: HKLegislationProcessingOutcome
    disposition: HKLegislationDisposition | None
    coverage_effect: HKLegislationCoverageEffect
    reason_code: str
    unresolved: tuple[str, ...] = ()


def _decision(
    timeline: HKLegislationEventTimeline,
    spec: _DecisionSpec,
    controlling: tuple[HKLegislationEvent, ...],
) -> HKLegislationEventDecision:
    return _issue_decision(
        HKLegislationEventDecision(
            timeline.legal_location_id,
            timeline.official_version_id,
            spec.processing_outcome,
            spec.disposition,
            spec.coverage_effect,
            timeline.source_contract_review,
            spec.reason_code,
            tuple(event.event_ref for event in controlling),
            spec.unresolved,
            _timeline_fingerprint(timeline),
        )
    )


def _conflicting_events(
    active: tuple[HKLegislationEvent, ...],
) -> tuple[HKLegislationEvent, ...]:
    by_identity: dict[str, list[HKLegislationEvent]] = {}
    for event in active:
        by_identity.setdefault(event.event_identity, []).append(event)
    for facts in by_identity.values():
        if len({(event.kind, event.effective_at) for event in facts}) > 1:
            return tuple(facts)
    status_kinds = {
        HKLegislationEventKind.COMMENCEMENT,
        HKLegislationEventKind.CESSATION,
        HKLegislationEventKind.REVIVAL,
    }
    status_by_time: dict[str, list[HKLegislationEvent]] = {}
    for event in active:
        if event.kind in status_kinds:
            status_by_time.setdefault(event.effective_at, []).append(event)
    for facts in status_by_time.values():
        if len({event.kind for event in facts}) > 1:
            return tuple(facts)
    return ()


def _initial_state_decision(
    snapshot: HKLegislationEventTimeline,
    active: tuple[HKLegislationEvent, ...],
) -> tuple[
    HKLegislationEventDecision | None,
    tuple[HKLegislationEvent, ...],
    tuple[HKLegislationEvent, ...],
]:
    publications = tuple(
        event for event in active if event.kind is HKLegislationEventKind.PUBLICATION
    )
    commencements = tuple(
        event for event in active if event.kind is HKLegislationEventKind.COMMENCEMENT
    )
    if not snapshot.source_facts_complete:
        decision = _decision(
            snapshot,
            _DecisionSpec(
                HKLegislationProcessingOutcome.BLOCK,
                None,
                HKLegislationCoverageEffect.NONE,
                "SOURCE_EVENT_FACTS_INCOMPLETE",
                ("SOURCE_EVENT_FACTS_INCOMPLETE",),
            ),
            (),
        )
    elif conflict := _conflicting_events(active):
        decision = _decision(
            snapshot,
            _DecisionSpec(
                HKLegislationProcessingOutcome.QUARANTINE,
                HKLegislationDisposition.QUARANTINE,
                HKLegislationCoverageEffect.NONE,
                "OFFICIAL_EVENT_CONFLICT",
                ("OFFICIAL_EVENT_CONFLICT",),
            ),
            conflict,
        )
    elif not publications:
        decision = _decision(
            snapshot,
            _DecisionSpec(
                HKLegislationProcessingOutcome.PASS,
                HKLegislationDisposition.WAITING_ROOM,
                HKLegislationCoverageEffect.NONE,
                "PUBLICATION_NOT_PROVED",
                ("PUBLICATION_NOT_PROVED",),
            ),
            (),
        )
    elif not commencements:
        decision = _decision(
            snapshot,
            _DecisionSpec(
                HKLegislationProcessingOutcome.PASS,
                HKLegislationDisposition.WAITING_ROOM,
                HKLegislationCoverageEffect.NONE,
                "COMMENCEMENT_NOT_PROVED",
                ("COMMENCEMENT_NOT_PROVED",),
            ),
            publications,
        )
    else:
        decision = None
    return decision, publications, commencements


def _operative_state_decision(
    snapshot: HKLegislationEventTimeline,
    active: tuple[HKLegislationEvent, ...],
    publications: tuple[HKLegislationEvent, ...],
) -> HKLegislationEventDecision:
    status_events = tuple(
        event
        for event in active
        if event.kind
        in {
            HKLegislationEventKind.COMMENCEMENT,
            HKLegislationEventKind.CESSATION,
            HKLegislationEventKind.REVIVAL,
        }
    )
    if status_events[-1].kind is HKLegislationEventKind.CESSATION:
        return _decision(
            snapshot,
            _DecisionSpec(
                HKLegislationProcessingOutcome.PASS,
                HKLegislationDisposition.HISTORICAL,
                HKLegislationCoverageEffect.NONE,
                "CESSATION_OPERATIVE_AT_CUTOFF",
            ),
            (*publications, *status_events),
        )
    text_events = tuple(
        event
        for event in active
        if event.kind
        in {
            HKLegislationEventKind.AMENDMENT,
            HKLegislationEventKind.CORRECTION,
            HKLegislationEventKind.EDITORIAL,
        }
    )
    reconstructions = tuple(
        event for event in active if event.kind is HKLegislationEventKind.RECONSTRUCTION
    )
    reconstructed = {basis for event in reconstructions for basis in event.basis_event_refs}
    unresolved_events = tuple(
        event for event in text_events if event.event_ref not in reconstructed
    )
    if snapshot.known_stale and not text_events:
        _fail(HKLegislationEventErrorCode.TIMELINE_INVALID)
    if snapshot.known_stale and unresolved_events:
        return _decision(
            snapshot,
            _DecisionSpec(
                HKLegislationProcessingOutcome.PASS,
                HKLegislationDisposition.SEARCHABLE_CURRENT,
                HKLegislationCoverageEffect.COVERAGE_GAP,
                "KNOWN_STALE_ANALYTICAL_CARRY_FORWARD",
                ("KNOWN_STALE_WARNING_AND_AUTHORITY_NOTE_REQUIRED",),
            ),
            (*publications, *status_events, *text_events),
        )
    if unresolved_events:
        return _decision(
            snapshot,
            _DecisionSpec(
                HKLegislationProcessingOutcome.PASS,
                HKLegislationDisposition.EVIDENCE_ONLY,
                HKLegislationCoverageEffect.COVERAGE_GAP,
                "CURRENT_TEXT_RECONSTRUCTION_REQUIRED",
                ("UNRECONSTRUCTED_TEXT_EVENT",),
            ),
            (*publications, *status_events, *text_events),
        )
    if text_events:
        return _decision(
            snapshot,
            _DecisionSpec(
                HKLegislationProcessingOutcome.PASS,
                HKLegislationDisposition.SEARCHABLE_CURRENT,
                (
                    HKLegislationCoverageEffect.COVERAGE_GAP
                    if snapshot.known_stale
                    else HKLegislationCoverageEffect.NONE
                ),
                "OPERATIVE_CURRENT_TEXT_RECONSTRUCTED",
            ),
            (*publications, *status_events, *text_events, *reconstructions),
        )
    return _decision(
        snapshot,
        _DecisionSpec(
            HKLegislationProcessingOutcome.PASS,
            HKLegislationDisposition.SEARCHABLE_CURRENT,
            HKLegislationCoverageEffect.NONE,
            "OPERATIVE_CURRENT_TEXT_PROVED",
        ),
        (*publications, *status_events),
    )


def decide_hk_legislation_state(
    timeline: object,
    cutoff: object,
) -> HKLegislationEventDecision:
    """Merge exact pure event facts at one cutoff without provider or legal-effect inference."""
    try:
        if not _canonical_utc(cutoff):
            _fail(HKLegislationEventErrorCode.CUTOFF_INVALID)
        snapshot = _timeline_snapshot(timeline)
    except HKLegislationEventError:
        raise
    except Exception as error:
        raise HKLegislationEventError(HKLegislationEventErrorCode.TIMELINE_INVALID) from error
    active = tuple(event for event in snapshot.events if event.effective_at <= cutoff)
    initial, publications, _commencements = _initial_state_decision(snapshot, active)
    if initial is not None:
        return initial
    return _operative_state_decision(snapshot, active, publications)
