"""Pure, evidence-bound Hong Kong Case judgment-bundle loading for Plan 4."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Never, Protocol

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_EARLIEST_V1_DATE = date(1997, 7, 1)
_EARLIEST_V1_YEAR = _EARLIEST_V1_DATE.year
_FINGERPRINT_PREFIX = "sha256:"
_FINGERPRINT_HEX_LENGTH = 64
_FIRST_CONTROL_CODEPOINT = 32
_MAX_ARTIFACT_BYTES = 10_000_000
_JUDGMENT_SCHEMA_ID = "asklegal.hk-case-judgment-artifact/v1"
_COURT_IDS = frozenset({"CFA", "CA", "CFI", "CT"})
_ARTIFACT_ROLES = frozenset({"ORIGINAL", "TRANSLATION"})
_LANGUAGES = frozenset({"ENGLISH", "TRADITIONAL_CHINESE"})
_OPINION_ROLES = frozenset({"COURT", "MAJORITY", "CONCURRENCE", "DISSENT", "SEPARATE"})
_CASES_CUTOFF = re.compile(r"^(?P<year>[0-9]{4})-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_CASES_BUNDLE_REF = re.compile(r"^cases/judgment-bundles/sha256/[0-9a-f]{64}\.json$")
_MARKUP_PATTERN = re.compile(r"<\s*/?\s*[a-z][^>]*>", re.IGNORECASE)
_ORDINARY_FAILURES = (Exception,)


class HKCaseEvidenceErrorCode(StrEnum):
    """Closed failures at the source-listing and retained-evidence boundary."""

    ARTIFACT_DOCUMENT_INVALID = "ARTIFACT_DOCUMENT_INVALID"
    ARTIFACT_DOCUMENT_MISMATCH = "ARTIFACT_DOCUMENT_MISMATCH"
    ARTIFACT_FINGERPRINT_MISMATCH = "ARTIFACT_FINGERPRINT_MISMATCH"
    ARTIFACT_LENGTH_MISMATCH = "ARTIFACT_LENGTH_MISMATCH"
    ARTIFACT_ROLE_UNSUPPORTED = "ARTIFACT_ROLE_UNSUPPORTED"
    ACQUISITION_MANIFEST_INVALID = "ACQUISITION_MANIFEST_INVALID"
    BUNDLE_FINGERPRINT_MISMATCH = "BUNDLE_FINGERPRINT_MISMATCH"
    EVIDENCE_MEMBER_CROSS_LISTING = "EVIDENCE_MEMBER_CROSS_LISTING"
    EVIDENCE_MEMBER_DUPLICATE = "EVIDENCE_MEMBER_DUPLICATE"
    EVIDENCE_MEMBER_INVALID = "EVIDENCE_MEMBER_INVALID"
    HTML_OR_SCRIPT_FORBIDDEN = "HTML_OR_SCRIPT_FORBIDDEN"
    LISTING_INVALID = "LISTING_INVALID"
    OPINION_ARTIFACT_MISSING = "OPINION_ARTIFACT_MISSING"
    OUTPUT_INVALID = "OUTPUT_INVALID"


class HKCaseEvidenceError(ValueError):
    """One fail-closed local judgment-bundle loading error."""

    code: HKCaseEvidenceErrorCode

    def __init__(self, code: HKCaseEvidenceErrorCode) -> None:
        """Expose the closed error code without preserving untrusted input."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HKCaseCompleteAcquisitionManifestReference:
    """The narrow complete-only Cases acquisition admission for later local work."""

    cycle_id: str
    manifest_fingerprint: str
    judgment_bundle_refs: tuple[str, ...]


def accept_complete_cases_acquisition_manifest(
    raw: bytes,
) -> HKCaseCompleteAcquisitionManifestReference:
    """Admit only a self-fingerprinted complete Cases manifest; no provider is invoked."""
    try:
        document = _json_object(parse_json_bytes(raw, max_bytes=1_000_000))
        expected = {
            "cycle_id",
            "discrepancy_refs",
            "earliest_decision_date",
            "fingerprint",
            "journal_head_fingerprint",
            "judgment_bundle_refs",
            "observation_cutoff",
            "result",
            "year_dispositions",
        }
        if set(document) != expected:
            _invalid_acquisition_manifest()
        fingerprint = _text(document["fingerprint"])
        unsigned = {key: value for key, value in document.items() if key != "fingerprint"}
        result = _text(document["result"])
        cutoff = _text(document["observation_cutoff"])
        cutoff_match = _CASES_CUTOFF.fullmatch(cutoff)
        if cutoff_match is None:
            _invalid_acquisition_manifest()
        datetime.fromisoformat(cutoff.removesuffix("Z") + "+00:00")
        bundle_refs = _complete_text_list(document["judgment_bundle_refs"])
        _complete_text_list(document["discrepancy_refs"])
        judgment_count = _complete_shards(
            document["year_dispositions"], int(cutoff_match.group("year"))
        )
        if (
            fingerprint != _acquisition_manifest_fingerprint(unsigned)
            or result not in {"COMPLETE", "NO_CHANGE"}
            or not _text(document["cycle_id"])
            or _text(document["earliest_decision_date"]) != "1997-07-01"
            or re.fullmatch(r"sha256:[0-9a-f]{64}", _text(document["journal_head_fingerprint"]))
            is None
            or any(_CASES_BUNDLE_REF.fullmatch(ref) is None for ref in bundle_refs)
            or len(bundle_refs) != judgment_count
        ):
            _invalid_acquisition_manifest()
        return HKCaseCompleteAcquisitionManifestReference(
            cycle_id=_text(document["cycle_id"]),
            manifest_fingerprint=fingerprint,
            judgment_bundle_refs=bundle_refs,
        )
    except KeyError, TypeError, ValueError:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ACQUISITION_MANIFEST_INVALID) from None


def _acquisition_manifest_fingerprint(unsigned: dict[str, JsonValue]) -> str:
    """Hash the exact canonical JSON representation used by the acquisition worker."""
    encoded = canonicalize(checked_json_value(unsigned))
    return f"sha256:{sha256(encoded).hexdigest()}"


def _invalid_acquisition_manifest() -> Never:
    """Keep malformed acquisition input on the closed evidence error path."""
    raise TypeError


def _complete_text_list(value: JsonValue) -> tuple[str, ...]:
    """Return one duplicate-free exact artifact-reference tuple."""
    values = _json_list(value)
    if any(type(item) is not str or not item for item in values) or len(set(values)) != len(values):
        _invalid_acquisition_manifest()
    return tuple(_text(item) for item in values)


def _complete_shards(value: JsonValue, cutoff_year: int) -> int:
    """Revalidate the complete contiguous 1997-through-cutoff source universe."""
    values = _json_list(value)
    if len(values) != cutoff_year - _EARLIEST_V1_YEAR + 1 or cutoff_year < _EARLIEST_V1_YEAR:
        _invalid_acquisition_manifest()
    expected_fields = {
        "discovered_judgments",
        "final_page",
        "first_in_scope_date",
        "result",
        "retryable_items",
        "verified_judgments",
        "verified_listing_pages",
        "year",
    }
    judgment_count = 0
    for expected_year, shard_value in zip(
        range(_EARLIEST_V1_YEAR, cutoff_year + 1), values, strict=True
    ):
        shard = _json_object(shard_value)
        if set(shard) != expected_fields:
            _invalid_acquisition_manifest()
        year = _exact_manifest_integer(shard["year"])
        final_page = _exact_manifest_integer(shard["final_page"])
        listing_pages = _exact_manifest_integer(shard["verified_listing_pages"])
        discovered = _exact_manifest_integer(shard["discovered_judgments"])
        verified = _exact_manifest_integer(shard["verified_judgments"])
        retryable = _exact_manifest_integer(shard["retryable_items"])
        if (
            year != expected_year
            or _text(shard["first_in_scope_date"])
            != (_EARLIEST_V1_DATE.isoformat() if year == _EARLIEST_V1_YEAR else f"{year:04d}-01-01")
            or _text(shard["result"]) != "COMPLETE"
            or final_page <= 0
            or listing_pages != final_page
            or discovered < 0
            or verified != discovered
            or retryable != 0
        ):
            _invalid_acquisition_manifest()
        judgment_count += verified
    return judgment_count


def _exact_manifest_integer(value: JsonValue) -> int:
    if type(value) is not int:
        _invalid_acquisition_manifest()
    return value


class HKCaseJudgmentDisposition(StrEnum):
    """The only source-neutral judgment-bundle outcomes in this first slice."""

    LOADED = "LOADED"
    OUT_OF_V1_DATE_SCOPE = "OUT_OF_V1_DATE_SCOPE"


@dataclass(frozen=True, slots=True)
class HKCaseEvidenceMember:
    """One explicit immutable byte binding for one declared listing artifact."""

    artifact_identity: str
    listing_identity: str
    reference: str
    fingerprint: str
    byte_length: int

    def __post_init__(self) -> None:
        """Reject malformed or equality-lying evidence mapping leaves at construction."""
        _validate_member(self)


class HKCaseEvidenceReader(Protocol):
    """The only injected source of already retained local artifact bytes."""

    def read_exact(self, member: HKCaseEvidenceMember) -> bytes:
        """Return the exact immutable bytes for one explicitly named member."""
        ...


class _SourceEnum(Protocol):
    """The small source-owned enum projection this desk can safely consume."""

    @property
    def value(self) -> str:
        """Return the exact primitive source enum value."""
        ...


class _SourceArtifact(Protocol):
    """A source-owned locator projection that avoids a legal-desk connector dependency."""

    @property
    def artifact_identity(self) -> str:
        """Return the source artifact identity."""
        ...

    @property
    def listing_identity(self) -> str:
        """Return the owning source listing identity."""
        ...

    @property
    def source_id(self) -> str:
        """Return the source role that owns this artifact."""
        ...

    @property
    def role(self) -> _SourceEnum:
        """Return the source-owned original or translation role."""
        ...

    @property
    def language(self) -> _SourceEnum:
        """Return the source-owned language identity."""
        ...

    @property
    def opinion_or_reasons_identity(self) -> str:
        """Return the separately accounted opinion or reasons identity."""
        ...

    def __post_init__(self) -> None:
        """Revalidate the original source object before this desk consumes it."""
        ...


class _SourceListing(Protocol):
    """The bounded Plan 2 listing projection consumed by this pure legal desk."""

    @property
    def listing_identity(self) -> str:
        """Return the source listing identity."""
        ...

    @property
    def court_family(self) -> _SourceEnum:
        """Return the source-owned issuing-court partition."""
        ...

    @property
    def decision_date(self) -> str:
        """Return the original decision date."""
        ...

    @property
    def case_name(self) -> str:
        """Return the exact source-provided case name."""
        ...

    @property
    def artifacts(self) -> tuple[_SourceArtifact, ...]:
        """Return every separately declared source artifact."""
        ...

    @property
    def opinion_or_reasons_identities(self) -> tuple[str, ...]:
        """Return the complete source-owned opinion/reasons inventory."""
        ...

    @property
    def neutral_citations(self) -> tuple[str, ...]:
        """Return exact source-provided neutral citations."""
        ...

    @property
    def reported_citations(self) -> tuple[str, ...]:
        """Return exact source-provided reported citations."""
        ...

    @property
    def proceeding_numbers(self) -> tuple[str, ...]:
        """Return exact source-provided proceeding-number authorities."""
        ...

    def __post_init__(self) -> None:
        """Revalidate the original source object before this desk consumes it."""
        ...


@dataclass(frozen=True, slots=True)
class HKCaseJudgmentParagraph:
    """One preserved, ordered paragraph with its exact publisher locator."""

    paragraph_id: str
    locator: str
    text: str

    def __post_init__(self) -> None:
        """Revalidate exact inert paragraph facts on every reconstruction."""
        try:
            _validate_output_paragraph(self)
        except TypeError, ValueError:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.OUTPUT_INVALID) from None


@dataclass(frozen=True, slots=True)
class HKCaseJudgmentOpinion:
    """One distinct original-language judicial opinion, never a ledger opinion."""

    opinion_id: str
    judge_names: tuple[str, ...]
    opinion_role: str
    language: str
    paragraphs: tuple[HKCaseJudgmentParagraph, ...]
    evidence_ref: str
    evidence_fingerprint: str
    evidence_byte_length: int
    content_fingerprint: str

    def __post_init__(self) -> None:
        """Revalidate one exact original opinion and its retained-byte authority."""
        try:
            _validate_output_opinion(self)
        except TypeError, ValueError:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.OUTPUT_INVALID) from None


@dataclass(frozen=True, slots=True)
class HKCaseJudgment:
    """One judgment assembled from every declared original opinion artifact."""

    judgment_id: str
    case_name: str
    court_id: str
    decision_date: str
    neutral_citations: tuple[str, ...]
    reported_citations: tuple[str, ...]
    proceeding_numbers: tuple[str, ...]
    opinions: tuple[HKCaseJudgmentOpinion, ...]

    def __post_init__(self) -> None:
        """Revalidate judgment identity, scope, date, and distinct original opinions."""
        try:
            _validate_output_judgment(self)
        except TypeError, ValueError:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.OUTPUT_INVALID) from None


@dataclass(frozen=True, slots=True)
class HKCaseJudgmentTranslation:
    """One linked translation retained separately from the original authority."""

    translation_id: str
    opinion_id: str
    language: str
    paragraphs: tuple[HKCaseJudgmentParagraph, ...]
    evidence_ref: str
    evidence_fingerprint: str
    evidence_byte_length: int
    content_fingerprint: str

    def __post_init__(self) -> None:
        """Revalidate separately retained translated content and exact byte authority."""
        try:
            _validate_output_translation(self)
        except TypeError, ValueError:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.OUTPUT_INVALID) from None


@dataclass(frozen=True, slots=True)
class HKCaseJudgmentBundle:
    """A replayable source-neutral bundle, never a complete Case release."""

    listing_id: str
    disposition: HKCaseJudgmentDisposition
    judgment: HKCaseJudgment | None
    translations: tuple[HKCaseJudgmentTranslation, ...]
    bundle_fingerprint: str

    def __post_init__(self) -> None:
        """Recompute nested coherence and the displayed bundle fingerprint."""
        try:
            _validate_output_bundle(self)
        except TypeError, ValueError:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.OUTPUT_INVALID) from None
        if self.bundle_fingerprint != _bundle_fingerprint_values(
            self.listing_id,
            self.disposition,
            self.judgment,
            self.translations,
        ):
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.BUNDLE_FINGERPRINT_MISMATCH)

    def __copy__(self) -> HKCaseJudgmentBundle:
        """Reconstruct and revalidate a shallow copy instead of copying cached authority."""
        return type(self)(
            listing_id=self.listing_id,
            disposition=self.disposition,
            judgment=self.judgment,
            translations=self.translations,
            bundle_fingerprint=self.bundle_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class _ArtifactFact:
    """The validated source-facing fields required from one locator."""

    artifact_identity: str
    listing_identity: str
    source_id: str
    role: str
    language: str
    opinion_id: str


def load_hk_case_judgment_bundle(
    listing: _SourceListing,
    evidence_members: tuple[HKCaseEvidenceMember, ...],
    reader: HKCaseEvidenceReader,
) -> HKCaseJudgmentBundle:
    """Load one exact local bundle without source, provider, network, or clock access."""
    facts = _listing_facts(listing)
    listing_id, court_id, decision_date, case_name, artifacts, original_opinion_ids = facts[:6]
    neutral_citations, reported_citations, proceeding_numbers = facts[6:]
    if date.fromisoformat(decision_date) < _EARLIEST_V1_DATE:
        return _out_of_scope_bundle(listing_id)

    members = _member_map(listing_id, evidence_members)
    if set(members) != {item.artifact_identity for item in artifacts}:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.OPINION_ARTIFACT_MISSING)

    opinions: list[HKCaseJudgmentOpinion] = []
    translations: list[HKCaseJudgmentTranslation] = []
    loaded_original_ids: set[str] = set()
    for artifact in artifacts:
        member = members[artifact.artifact_identity]
        body = _read_exact(reader, member)
        document = _artifact_document(body, artifact, court_id, decision_date)
        if artifact.role == "ORIGINAL":
            opinion = _opinion_from_document(document, artifact, member)
            if opinion.opinion_id in loaded_original_ids:
                raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_MISMATCH)
            loaded_original_ids.add(opinion.opinion_id)
            opinions.append(opinion)
        elif artifact.role == "TRANSLATION":
            translations.append(_translation_from_document(document, artifact, member))
        else:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_ROLE_UNSUPPORTED)

    if loaded_original_ids != set(original_opinion_ids):
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.OPINION_ARTIFACT_MISSING)
    judgment = HKCaseJudgment(
        judgment_id=f"judgment-{listing_id}",
        case_name=case_name,
        court_id=court_id,
        decision_date=decision_date,
        neutral_citations=neutral_citations,
        reported_citations=reported_citations,
        proceeding_numbers=proceeding_numbers,
        opinions=tuple(opinions),
    )
    frozen_translations = tuple(translations)
    return HKCaseJudgmentBundle(
        listing_id=listing_id,
        disposition=HKCaseJudgmentDisposition.LOADED,
        judgment=judgment,
        translations=frozen_translations,
        bundle_fingerprint=_bundle_fingerprint_values(
            listing_id,
            HKCaseJudgmentDisposition.LOADED,
            judgment,
            frozen_translations,
        ),
    )


def _out_of_scope_bundle(listing_id: str) -> HKCaseJudgmentBundle:
    """Return the explicit pre-handover disposition without reading retained evidence."""
    return HKCaseJudgmentBundle(
        listing_id=listing_id,
        disposition=HKCaseJudgmentDisposition.OUT_OF_V1_DATE_SCOPE,
        judgment=None,
        translations=(),
        bundle_fingerprint=_bundle_fingerprint_values(
            listing_id,
            HKCaseJudgmentDisposition.OUT_OF_V1_DATE_SCOPE,
            None,
            (),
        ),
    )


def _listing_facts(
    listing: _SourceListing,
) -> tuple[
    str,
    str,
    str,
    str,
    tuple[_ArtifactFact, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    """Revalidate a Plan 2 source object and project only the exact needed facts."""
    try:
        return _checked_listing_facts(listing)
    except HKCaseEvidenceError:
        raise
    except _ORDINARY_FAILURES:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.LISTING_INVALID) from None


def _checked_listing_facts(
    listing: _SourceListing,
) -> tuple[
    str,
    str,
    str,
    str,
    tuple[_ArtifactFact, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    """Project fully replayed listing facts while ordinary failures remain internal."""
    listing.__post_init__()
    listing_id = _text(listing.listing_identity)
    court_id = _enum_value(listing.court_family, _COURT_IDS)
    decision_date = _iso_date(listing.decision_date)
    case_name = _text(listing.case_name)
    raw_artifacts = listing.artifacts
    raw_opinion_ids = listing.opinion_or_reasons_identities
    neutral_citations = listing.neutral_citations
    reported_citations = listing.reported_citations
    proceeding_numbers = listing.proceeding_numbers
    if type(raw_artifacts) is not tuple or not raw_artifacts:
        raise TypeError
    if type(raw_opinion_ids) is not tuple or not raw_opinion_ids:
        raise TypeError
    neutral = _citation_inventory(neutral_citations, required=False)
    reported = _citation_inventory(reported_citations, required=False)
    proceedings = _citation_inventory(proceeding_numbers, required=True)
    opinion_ids = tuple(_text(value) for value in raw_opinion_ids)
    if len(set(opinion_ids)) != len(opinion_ids) or tuple(sorted(opinion_ids)) != opinion_ids:
        raise ValueError
    artifacts = tuple(_artifact_fact(value, listing_id) for value in raw_artifacts)
    identities = tuple(item.artifact_identity for item in artifacts)
    if len(set(identities)) != len(identities) or tuple(sorted(identities)) != identities:
        raise ValueError
    artifact_opinion_ids = {item.opinion_id for item in artifacts}
    if artifact_opinion_ids != set(opinion_ids):
        raise ValueError
    original_ids = tuple(item.opinion_id for item in artifacts if item.role == "ORIGINAL")
    if not original_ids or len(set(original_ids)) != len(original_ids):
        raise ValueError
    original_opinion_ids = tuple(sorted(original_ids))
    return (
        listing_id,
        court_id,
        decision_date,
        case_name,
        artifacts,
        original_opinion_ids,
        neutral,
        reported,
        proceedings,
    )


def _artifact_fact(value: _SourceArtifact, expected_listing_id: str) -> _ArtifactFact:
    """Revalidate one source locator without making legal desks depend on connectors."""
    try:
        value.__post_init__()
        artifact_identity = _text(value.artifact_identity)
        listing_identity = _text(value.listing_identity)
        source_id = _text(value.source_id)
        role = _enum_value(value.role, _ARTIFACT_ROLES)
        language = _enum_value(value.language, _LANGUAGES)
        opinion_id = _text(value.opinion_or_reasons_identity)
    except _ORDINARY_FAILURES:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.LISTING_INVALID) from None
    if listing_identity != expected_listing_id:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.LISTING_INVALID)
    return _ArtifactFact(
        artifact_identity=artifact_identity,
        listing_identity=listing_identity,
        source_id=source_id,
        role=role,
        language=language,
        opinion_id=opinion_id,
    )


def _member_map(
    listing_id: str, evidence_members: tuple[HKCaseEvidenceMember, ...]
) -> dict[str, HKCaseEvidenceMember]:
    """Validate exact one-to-one source-artifact to retained-byte bindings before any read."""
    if type(evidence_members) is not tuple:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.EVIDENCE_MEMBER_INVALID)
    members: dict[str, HKCaseEvidenceMember] = {}
    for supplied in evidence_members:
        if type(supplied) is not HKCaseEvidenceMember:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.EVIDENCE_MEMBER_INVALID)
        try:
            member = _member_snapshot(supplied)
        except TypeError, ValueError:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.EVIDENCE_MEMBER_INVALID) from None
        if member.listing_identity != listing_id:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.EVIDENCE_MEMBER_CROSS_LISTING)
        if member.artifact_identity in members:
            raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.EVIDENCE_MEMBER_DUPLICATE)
        members[member.artifact_identity] = member
    return members


def _member_snapshot(member: HKCaseEvidenceMember) -> HKCaseEvidenceMember:
    """Rebuild one detached exact primitive member authority from caller-owned state."""
    return HKCaseEvidenceMember(
        artifact_identity=_text(member.artifact_identity),
        listing_identity=_text(member.listing_identity),
        reference=_text(member.reference),
        fingerprint=_fingerprint(member.fingerprint),
        byte_length=_positive_length(member.byte_length),
    )


def _validate_member(member: HKCaseEvidenceMember) -> None:
    """Apply exact primitive validation independently on construction and every replay."""
    _text(member.artifact_identity)
    _text(member.listing_identity)
    _text(member.reference)
    _fingerprint(member.fingerprint)
    _positive_length(member.byte_length)


def _read_exact(reader: HKCaseEvidenceReader, member: HKCaseEvidenceMember) -> bytes:
    """Read and bind one declared immutable member without broad exception leakage."""
    disposable = _member_snapshot(member)
    try:
        body = reader.read_exact(disposable)
    except Exception as error:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_INVALID) from error
    if type(body) is not bytes:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_INVALID)
    if len(body) != member.byte_length:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_LENGTH_MISMATCH)
    if _body_fingerprint(body) != member.fingerprint:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_FINGERPRINT_MISMATCH)
    return body


def _artifact_document(
    body: bytes, artifact: _ArtifactFact, court_id: str, decision_date: str
) -> dict[str, JsonValue]:
    """Decode one inert exact JSON artifact and bind its publisher-facing facts."""
    lowered = body.lower()
    if b"<html" in lowered or b"<script" in lowered:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.HTML_OR_SCRIPT_FORBIDDEN)
    try:
        document = _json_object(parse_json_bytes(body, max_bytes=_MAX_ARTIFACT_BYTES))
    except ContractViolation, TypeError:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_INVALID) from None
    if _contains_decoded_markup(document):
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.HTML_OR_SCRIPT_FORBIDDEN)
    if type(document) is not dict or set(document) != {
        "artifact_identity",
        "court_id",
        "decision_date",
        "judge_names",
        "language",
        "listing_identity",
        "opinion_id",
        "opinion_role",
        "paragraphs",
        "schema_id",
        "source_id",
    }:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_INVALID)
    try:
        matches = (
            _text(document["schema_id"]) != _JUDGMENT_SCHEMA_ID
            or _text(document["artifact_identity"]) != artifact.artifact_identity
            or _text(document["listing_identity"]) != artifact.listing_identity
            or _text(document["source_id"]) != artifact.source_id
            or _enum_text(document["language"], _LANGUAGES) != artifact.language
            or _text(document["court_id"]) != court_id
            or _iso_date(document["decision_date"]) != decision_date
            or _text(document["opinion_id"]) != artifact.opinion_id
        )
    except KeyError, TypeError, ValueError:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_MISMATCH) from None
    if matches:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_MISMATCH)
    return document


def _opinion_from_document(
    document: dict[str, JsonValue], artifact: _ArtifactFact, member: HKCaseEvidenceMember
) -> HKCaseJudgmentOpinion:
    """Create one separately attributable original opinion from one validated artifact."""
    try:
        role = _enum_text(document["opinion_role"], _OPINION_ROLES)
        judge_names = _text_tuple(document["judge_names"])
        paragraphs = _paragraphs(document["paragraphs"])
    except KeyError, TypeError, ValueError:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_INVALID) from None
    content_fingerprint = _paragraphs_fingerprint(paragraphs)
    return HKCaseJudgmentOpinion(
        opinion_id=artifact.opinion_id,
        judge_names=judge_names,
        opinion_role=role,
        language=_language_code(artifact.language),
        paragraphs=paragraphs,
        evidence_ref=member.reference,
        evidence_fingerprint=member.fingerprint,
        evidence_byte_length=member.byte_length,
        content_fingerprint=content_fingerprint,
    )


def _translation_from_document(
    document: dict[str, JsonValue],
    artifact: _ArtifactFact,
    member: HKCaseEvidenceMember,
) -> HKCaseJudgmentTranslation:
    """Preserve parsed translated content separately with its exact retained-byte binding."""
    try:
        paragraphs = _paragraphs(document["paragraphs"])
    except KeyError, TypeError, ValueError:
        raise HKCaseEvidenceError(HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_INVALID) from None
    return HKCaseJudgmentTranslation(
        translation_id=artifact.artifact_identity,
        opinion_id=artifact.opinion_id,
        language=_language_code(artifact.language),
        paragraphs=paragraphs,
        evidence_ref=member.reference,
        evidence_fingerprint=member.fingerprint,
        evidence_byte_length=member.byte_length,
        content_fingerprint=_paragraphs_fingerprint(paragraphs),
    )


def _paragraphs(value: JsonValue) -> tuple[HKCaseJudgmentParagraph, ...]:
    """Strictly preserve non-empty paragraph identities, locators, and text."""
    values = _json_list(value)
    if not values:
        raise ValueError
    paragraphs: list[HKCaseJudgmentParagraph] = []
    for raw_item in values:
        item = _json_object(raw_item)
        if set(item) != {"paragraph_id", "locator", "text"}:
            raise ValueError
        paragraph = HKCaseJudgmentParagraph(
            paragraph_id=_text(item["paragraph_id"]),
            locator=_text(item["locator"]),
            text=_text(item["text"]),
        )
        paragraphs.append(paragraph)
    identifiers = tuple(item.paragraph_id for item in paragraphs)
    locators = tuple(item.locator for item in paragraphs)
    if len(set(identifiers)) != len(identifiers) or len(set(locators)) != len(locators):
        raise ValueError
    return tuple(paragraphs)


def _bundle_fingerprint_values(
    listing_id: str,
    disposition: HKCaseJudgmentDisposition,
    judgment: HKCaseJudgment | None,
    translations: tuple[HKCaseJudgmentTranslation, ...],
) -> str:
    """Derive a replay-stable digest from exact output facts rather than cached state."""
    payload = {
        "disposition": disposition.value,
        "judgment": None
        if judgment is None
        else {
            "court_id": judgment.court_id,
            "case_name": judgment.case_name,
            "neutral_citations": list(judgment.neutral_citations),
            "reported_citations": list(judgment.reported_citations),
            "proceeding_numbers": list(judgment.proceeding_numbers),
            "decision_date": judgment.decision_date,
            "judgment_id": judgment.judgment_id,
            "opinions": [
                {
                    "content_fingerprint": opinion.content_fingerprint,
                    "evidence_byte_length": opinion.evidence_byte_length,
                    "evidence_fingerprint": opinion.evidence_fingerprint,
                    "evidence_ref": opinion.evidence_ref,
                    "judge_names": list(opinion.judge_names),
                    "language": opinion.language,
                    "opinion_id": opinion.opinion_id,
                    "opinion_role": opinion.opinion_role,
                    "paragraphs": [
                        {
                            "locator": paragraph.locator,
                            "paragraph_id": paragraph.paragraph_id,
                            "text": paragraph.text,
                        }
                        for paragraph in opinion.paragraphs
                    ],
                }
                for opinion in judgment.opinions
            ],
        },
        "listing_id": listing_id,
        "translations": [
            {
                "content_fingerprint": item.content_fingerprint,
                "evidence_byte_length": item.evidence_byte_length,
                "evidence_fingerprint": item.evidence_fingerprint,
                "evidence_ref": item.evidence_ref,
                "language": item.language,
                "opinion_id": item.opinion_id,
                "paragraphs": [
                    {
                        "locator": paragraph.locator,
                        "paragraph_id": paragraph.paragraph_id,
                        "text": paragraph.text,
                    }
                    for paragraph in item.paragraphs
                ],
                "translation_id": item.translation_id,
            }
            for item in translations
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return _body_fingerprint(raw)


def _body_fingerprint(body: bytes) -> str:
    """Return the exact SHA-256 representation used by immutable evidence members."""
    return f"{_FINGERPRINT_PREFIX}{sha256(body).hexdigest()}"


def _paragraphs_fingerprint(paragraphs: tuple[HKCaseJudgmentParagraph, ...]) -> str:
    """Bind parsed paragraph identities, locators, order, and inert text exactly."""
    raw = json.dumps(
        [
            {
                "locator": item.locator,
                "paragraph_id": item.paragraph_id,
                "text": item.text,
            }
            for item in paragraphs
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return _body_fingerprint(raw)


def _contains_decoded_markup(value: JsonValue) -> bool:
    """Reject markup after strict JSON decoding, including escaped and mixed-case forms."""
    if isinstance(value, str):
        return _MARKUP_PATTERN.search(value) is not None
    if isinstance(value, list):
        return any(_contains_decoded_markup(item) for item in value)
    if isinstance(value, dict):
        return any(
            _MARKUP_PATTERN.search(key) is not None or _contains_decoded_markup(item)
            for key, item in value.items()
        )
    return False


def _text(value: object) -> str:
    """Return one bounded exact text value without accepting subclasses or blank leaves."""
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(ord(char) < _FIRST_CONTROL_CODEPOINT for char in value)
        or _MARKUP_PATTERN.search(value) is not None
    ):
        raise ValueError
    return value


def _positive_length(value: object) -> int:
    """Return one exact positive byte length without accepting bool or subclasses."""
    if type(value) is not int or value < 1:
        raise ValueError
    return value


def _output_text_tuple(value: tuple[str, ...]) -> tuple[str, ...]:
    """Revalidate an immutable, non-empty, duplicate-free output text sequence."""
    if type(value) is not tuple or not value:
        raise TypeError
    result = tuple(_text(item) for item in value)
    if len(set(result)) != len(result):
        raise ValueError
    return result


def _validate_output_paragraph(value: HKCaseJudgmentParagraph) -> None:
    """Validate one reconstructed paragraph without trusting cached dataclass state."""
    _text(value.paragraph_id)
    _text(value.locator)
    _text(value.text)


def _validate_output_opinion(value: HKCaseJudgmentOpinion) -> None:
    """Validate one reconstructed original opinion and its exact evidence binding."""
    _text(value.opinion_id)
    _output_text_tuple(value.judge_names)
    _enum_text(value.opinion_role, _OPINION_ROLES)
    _enum_text(value.language, frozenset({"EN", "ZH_HANT"}))
    _output_paragraphs(value.paragraphs)
    _text(value.evidence_ref)
    _fingerprint(value.evidence_fingerprint)
    _positive_length(value.evidence_byte_length)
    _fingerprint(value.content_fingerprint)
    if value.content_fingerprint != _paragraphs_fingerprint(value.paragraphs):
        raise ValueError


def _validate_output_judgment(value: HKCaseJudgment) -> None:
    """Validate reconstructed judgment facts and non-colliding original opinions."""
    _text(value.judgment_id)
    _text(value.case_name)
    _enum_text(value.court_id, _COURT_IDS)
    _citation_inventory(value.neutral_citations, required=False)
    _citation_inventory(value.reported_citations, required=False)
    _citation_inventory(value.proceeding_numbers, required=True)
    _iso_date(value.decision_date)
    if type(value.opinions) is not tuple or not value.opinions:
        raise TypeError
    for opinion in value.opinions:
        if type(opinion) is not HKCaseJudgmentOpinion:
            raise TypeError
        opinion.__post_init__()
    identities = tuple(item.opinion_id for item in value.opinions)
    evidence_refs = tuple(item.evidence_ref for item in value.opinions)
    if len(set(identities)) != len(identities) or len(set(evidence_refs)) != len(evidence_refs):
        raise ValueError


def _citation_inventory(value: tuple[object, ...], *, required: bool) -> tuple[str, ...]:
    """Validate one exact sorted source citation/proceeding inventory."""
    if type(value) is not tuple:
        raise TypeError
    result = tuple(_text(item) for item in value)
    if (
        (required and not result)
        or len(set(result)) != len(result)
        or tuple(sorted(result)) != result
    ):
        raise ValueError
    return result


def _validate_output_translation(value: HKCaseJudgmentTranslation) -> None:
    """Validate one reconstructed translation and its exact evidence/content binding."""
    _text(value.translation_id)
    _text(value.opinion_id)
    _enum_text(value.language, frozenset({"EN", "ZH_HANT"}))
    _output_paragraphs(value.paragraphs)
    _text(value.evidence_ref)
    _fingerprint(value.evidence_fingerprint)
    _positive_length(value.evidence_byte_length)
    _fingerprint(value.content_fingerprint)
    if value.content_fingerprint != _paragraphs_fingerprint(value.paragraphs):
        raise ValueError


def _validate_output_bundle(value: HKCaseJudgmentBundle) -> None:
    """Validate disposition coherence and every nested output before digest replay."""
    _text(value.listing_id)
    if type(value.disposition) is not HKCaseJudgmentDisposition:
        raise TypeError
    translation_refs = _validate_output_translations(value.translations)
    if value.disposition is HKCaseJudgmentDisposition.OUT_OF_V1_DATE_SCOPE:
        if value.judgment is not None or value.translations:
            raise ValueError
    else:
        if type(value.judgment) is not HKCaseJudgment:
            raise TypeError
        value.judgment.__post_init__()
        if (
            value.judgment.judgment_id != f"judgment-{value.listing_id}"
            or date.fromisoformat(value.judgment.decision_date) < _EARLIEST_V1_DATE
        ):
            raise ValueError
        original_refs = tuple(item.evidence_ref for item in value.judgment.opinions)
        if set(original_refs).intersection(translation_refs):
            raise ValueError
    _fingerprint(value.bundle_fingerprint)


def _validate_output_translations(
    value: tuple[HKCaseJudgmentTranslation, ...],
) -> tuple[str, ...]:
    """Validate exact translation instances and return their distinct evidence references."""
    if type(value) is not tuple:
        raise TypeError
    for translation in value:
        if type(translation) is not HKCaseJudgmentTranslation:
            raise TypeError
        translation.__post_init__()
    translation_ids = tuple(item.translation_id for item in value)
    translation_refs = tuple(item.evidence_ref for item in value)
    if len(set(translation_ids)) != len(translation_ids) or len(set(translation_refs)) != len(
        translation_refs
    ):
        raise ValueError
    return translation_refs


def _output_paragraphs(
    value: tuple[HKCaseJudgmentParagraph, ...],
) -> tuple[HKCaseJudgmentParagraph, ...]:
    """Revalidate exact paragraph instances and distinct immutable identities."""
    if type(value) is not tuple or not value:
        raise TypeError
    paragraphs: list[HKCaseJudgmentParagraph] = []
    for paragraph in value:
        if type(paragraph) is not HKCaseJudgmentParagraph:
            raise TypeError
        paragraph.__post_init__()
        paragraphs.append(paragraph)
    identifiers = tuple(item.paragraph_id for item in paragraphs)
    locators = tuple(item.locator for item in paragraphs)
    if len(set(identifiers)) != len(identifiers) or len(set(locators)) != len(locators):
        raise ValueError
    return tuple(paragraphs)


def _text_tuple(value: JsonValue) -> tuple[str, ...]:
    """Validate a non-empty, ordered, duplicate-free exact text tuple from artifact JSON."""
    values = _json_list(value)
    if not values:
        raise ValueError
    result = tuple(_text(item) for item in values)
    if len(set(result)) != len(result):
        raise ValueError
    return result


def _enum_value(value: _SourceEnum, allowed: frozenset[str]) -> str:
    """Extract an exact source enum's primitive value without trusting enum equality."""
    return _enum_text(value.value, allowed)


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    """Return one strict JSON object from the repository's typed JSON boundary."""
    if not isinstance(value, dict):
        raise TypeError
    return value


def _json_list(value: JsonValue) -> list[JsonValue]:
    """Return one strict JSON array from the repository's typed JSON boundary."""
    if not isinstance(value, list):
        raise TypeError
    return value


def _enum_text(value: object, allowed: frozenset[str]) -> str:
    """Validate one exact primitive enum text against a closed source-owned universe."""
    text = _text(value)
    if text not in allowed:
        raise ValueError
    return text


def _iso_date(value: object) -> str:
    """Validate a canonical ISO decision date without accepting datetime lookalikes."""
    text = _text(value)
    if date.fromisoformat(text).isoformat() != text:
        raise ValueError
    return text


def _fingerprint(value: object) -> str:
    """Validate one exact SHA-256 retained-byte digest."""
    text = _text(value)
    if (
        not text.startswith(_FINGERPRINT_PREFIX)
        or len(text) != len(_FINGERPRINT_PREFIX) + _FINGERPRINT_HEX_LENGTH
        or any(
            character not in "0123456789abcdef" for character in text[len(_FINGERPRINT_PREFIX) :]
        )
    ):
        raise ValueError
    return text


def _language_code(language: str) -> str:
    """Map the closed source language identity into the local judgment representation."""
    return "EN" if language == "ENGLISH" else "ZH_HANT"
