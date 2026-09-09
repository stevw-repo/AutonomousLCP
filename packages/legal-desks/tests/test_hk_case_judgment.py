# ruff: noqa: PLR0913
"""Source-neutral judgment-bundle boundary tests for Plan 4 Task 1."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import copy, deepcopy
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from typing import TypeIs

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_legal_desks.hk_case_judgment import (
    HKCaseEvidenceError,
    HKCaseEvidenceErrorCode,
    HKCaseEvidenceMember,
    HKCaseJudgmentDisposition,
    HKCaseJudgmentParagraph,
    accept_complete_cases_acquisition_manifest,
    load_hk_case_judgment_bundle,
)


class ScriptedCourtFamily(StrEnum):
    """The frozen four-family source-shaped V1 court partition."""

    CFA = "CFA"
    CA = "CA"
    CFI = "CFI"
    CT = "CT"


class ScriptedArtifactRole(StrEnum):
    """The source-shaped original/translation artifact partition."""

    ORIGINAL = "ORIGINAL"
    TRANSLATION = "TRANSLATION"


class ScriptedLanguage(StrEnum):
    """The source-shaped publisher language classification."""

    ENGLISH = "ENGLISH"
    TRADITIONAL_CHINESE = "TRADITIONAL_CHINESE"


@dataclass(frozen=True, slots=True)
class ScriptedArtifact:
    """A local Plan 2-shaped artifact fact with source-side replay validation."""

    artifact_identity: str
    listing_identity: str
    source_id: str
    role: ScriptedArtifactRole
    language: ScriptedLanguage
    opinion_or_reasons_identity: str
    official_locator: str

    def __post_init__(self) -> None:
        """Reject malformed source facts before the legal-desk boundary observes them."""
        if (
            any(
                type(value) is not str or not value
                for value in (
                    self.artifact_identity,
                    self.listing_identity,
                    self.source_id,
                    self.opinion_or_reasons_identity,
                    self.official_locator,
                )
            )
            or type(self.role) is not ScriptedArtifactRole
            or type(self.language) is not ScriptedLanguage
        ):
            raise TypeError


@dataclass(frozen=True, slots=True)
class ScriptedListing:
    """A local Plan 2-shaped listing fact used without importing a connector into this package."""

    listing_identity: str
    court_family: ScriptedCourtFamily
    decision_date: str
    artifacts: tuple[ScriptedArtifact, ...]
    opinion_or_reasons_identities: tuple[str, ...]
    case_name: str = "Fixture v Example"
    neutral_citations: tuple[str, ...] = ("2020 HKCFA 1",)
    reported_citations: tuple[str, ...] = ()
    proceeding_numbers: tuple[str, ...] = ("P-1",)

    def __post_init__(self) -> None:
        """Preserve exact type, date, artifact, and opinion-accounting source invariants."""
        if (
            type(self.listing_identity) is not str
            or not self.listing_identity
            or type(self.court_family) is not ScriptedCourtFamily
            or len(self.decision_date) != len("2000-01-01")
            or type(self.artifacts) is not tuple
            or not self.artifacts
            or type(self.opinion_or_reasons_identities) is not tuple
            or not self.opinion_or_reasons_identities
        ):
            raise TypeError


class RuntimeErrorListing:
    """A structurally complete listing whose replay hook fails ordinarily."""

    listing_identity = "listing-runtime"
    case_name = "Runtime v Example"
    court_family = ScriptedCourtFamily.CFA
    decision_date = "2020-01-02"
    artifacts: tuple[ScriptedArtifact, ...] = ()
    opinion_or_reasons_identities = ("majority",)
    neutral_citations = ("2020 HKCFA 1",)
    reported_citations: tuple[str, ...] = ()
    proceeding_numbers: tuple[str, ...] = ("P-1",)

    def __post_init__(self) -> None:
        """Reproduce an ordinary source-listing replay failure."""
        raise RuntimeError


class BaseExceptionListing(RuntimeErrorListing):
    """A hostile listing proving process-control exceptions remain observable."""

    def __post_init__(self) -> None:
        """Raise outside the ordinary exception family normalized by this boundary."""
        raise KeyboardInterrupt


class RuntimeErrorArtifact:
    """A structurally complete artifact whose source property fails ordinarily."""

    artifact_identity = "artifact-runtime"
    listing_identity = "listing-runtime-artifact"
    role = ScriptedArtifactRole.ORIGINAL
    language = ScriptedLanguage.ENGLISH
    opinion_or_reasons_identity = "majority"

    @property
    def source_id(self) -> str:
        """Reproduce an ordinary source-artifact property failure."""
        raise RuntimeError

    def __post_init__(self) -> None:
        """Allow replay to reach the hostile source property."""


class RuntimeErrorArtifactListing:
    """A source-shaped listing containing the hostile structural artifact."""

    listing_identity = "listing-runtime-artifact"
    case_name = "Runtime Artifact v Example"
    court_family = ScriptedCourtFamily.CFA
    decision_date = "2020-01-02"
    opinion_or_reasons_identities = ("majority",)
    neutral_citations = ("2020 HKCFA 1",)
    reported_citations: tuple[str, ...] = ()
    proceeding_numbers: tuple[str, ...] = ("P-1",)

    @property
    def artifacts(self) -> tuple[RuntimeErrorArtifact, ...]:
        """Expose a read-only structural artifact tuple for protocol covariance."""
        return (RuntimeErrorArtifact(),)

    def __post_init__(self) -> None:
        """Keep the outer listing valid so nested normalization is exercised."""
        for artifact in self.artifacts:
            artifact.__post_init__()
        if (
            tuple(sorted(item.artifact_identity for item in self.artifacts))
            != tuple(item.artifact_identity for item in self.artifacts)
            or tuple(sorted(self.opinion_or_reasons_identities))
            != self.opinion_or_reasons_identities
        ):
            raise TypeError


class _LyingArtifactIdentity(str):
    """A string lookalike that must not impersonate an exact evidence identity."""

    __slots__ = ()

    def __hash__(self) -> int:
        return hash("artifact-majority")

    def __eq__(self, other: object) -> bool:
        return other == "artifact-majority" or super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class ScriptedEvidenceReader:
    """A local exact-byte reader that exposes observable evidence access."""

    def __init__(self, bodies: dict[str, bytes]) -> None:
        """Store exact local fixture bytes without any transport behavior."""
        self._bodies = bodies
        self.calls: list[HKCaseEvidenceMember] = []

    def read_exact(self, member: HKCaseEvidenceMember) -> bytes:
        """Return the exact scripted member body."""
        self.calls.append(member)
        return self._bodies[member.reference]


class MutatingEvidenceReader:
    """A hostile reader that rewrites its caller-owned member before returning changed bytes."""

    def __init__(self, changed_body: bytes) -> None:
        """Retain one changed but otherwise valid artifact body."""
        self.changed_body = changed_body

    def read_exact(self, member: HKCaseEvidenceMember) -> bytes:
        """Attempt to replace the authoritative reference, length, digest, and bytes."""
        object.__setattr__(member, "reference", "evidence/reader-forged")
        object.__setattr__(member, "fingerprint", _fingerprint(self.changed_body))
        object.__setattr__(member, "byte_length", len(self.changed_body))
        return self.changed_body


def test_pre_cutoff_listing_is_explicitly_out_of_scope_before_evidence_access() -> None:
    """Moving the cutoff branch after a read would touch excluded judgment evidence."""
    listing, bodies = _listing(decision_date="1997-06-30")
    reader = ScriptedEvidenceReader(bodies)

    result = load_hk_case_judgment_bundle(listing, _members(listing, bodies), reader)

    assert result.disposition is HKCaseJudgmentDisposition.OUT_OF_V1_DATE_SCOPE
    assert result.judgment is None
    assert reader.calls == []


@pytest.mark.parametrize("court_family", tuple(ScriptedCourtFamily))
def test_all_and_only_v1_court_families_can_produce_a_judgment_bundle(
    court_family: ScriptedCourtFamily,
) -> None:
    """Dropping or broadening one binding-court partition must change the result."""
    listing, bodies = _listing(court_family=court_family, decision_date="1997-07-01")

    result = load_hk_case_judgment_bundle(
        listing, _members(listing, bodies), ScriptedEvidenceReader(bodies)
    )

    assert result.disposition is HKCaseJudgmentDisposition.LOADED
    assert result.judgment is not None
    assert result.judgment.court_id == court_family.value
    assert result.judgment.decision_date == "1997-07-01"


def test_bundle_requires_every_declared_opinion_artifact_before_any_read() -> None:
    """Treating a missing dissent artifact as a complete judgment would hide evidence loss."""
    listing, bodies = _listing(opinions=("majority", "dissent"))
    members = tuple(
        item for item in _members(listing, bodies) if item.artifact_identity != "artifact-dissent"
    )
    reader = ScriptedEvidenceReader(bodies)

    with pytest.raises(HKCaseEvidenceError) as raised:
        load_hk_case_judgment_bundle(listing, members, reader)

    assert raised.value.code is HKCaseEvidenceErrorCode.OPINION_ARTIFACT_MISSING
    assert reader.calls == []


def test_bundle_keeps_each_declared_opinion_separate() -> None:
    """Collapsing a dissent into a majority judgment would corrupt authority attribution."""
    listing, bodies = _listing(opinions=("majority", "dissent"))

    result = load_hk_case_judgment_bundle(
        listing, _members(listing, bodies), ScriptedEvidenceReader(bodies)
    )

    assert result.judgment is not None
    assert tuple(item.opinion_id for item in result.judgment.opinions) == ("dissent", "majority")
    assert tuple(item.opinion_role for item in result.judgment.opinions) == ("DISSENT", "MAJORITY")


def test_duplicate_evidence_member_cannot_satisfy_multiple_declared_artifacts() -> None:
    """Deduplicating a caller-supplied duplicate would make the mapping ambiguous."""
    listing, bodies = _listing()
    member = _members(listing, bodies)[0]
    reader = ScriptedEvidenceReader(bodies)

    with pytest.raises(HKCaseEvidenceError) as raised:
        load_hk_case_judgment_bundle(listing, (member, member), reader)

    assert raised.value.code is HKCaseEvidenceErrorCode.EVIDENCE_MEMBER_DUPLICATE
    assert reader.calls == []


def test_cross_listing_evidence_member_is_rejected_before_read() -> None:
    """Using bytes retained for another listing would destroy item-specific provenance."""
    listing, bodies = _listing()
    member = _members(listing, bodies)[0]
    foreign = replace(member, listing_identity="listing-foreign")
    reader = ScriptedEvidenceReader(bodies)

    with pytest.raises(HKCaseEvidenceError) as raised:
        load_hk_case_judgment_bundle(listing, (foreign,), reader)

    assert raised.value.code is HKCaseEvidenceErrorCode.EVIDENCE_MEMBER_CROSS_LISTING
    assert reader.calls == []


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"not a judgment document", HKCaseEvidenceErrorCode.ARTIFACT_DOCUMENT_INVALID),
        (
            b"<html><script>not a judgment</script></html>",
            HKCaseEvidenceErrorCode.HTML_OR_SCRIPT_FORBIDDEN,
        ),
    ],
)
def test_raw_or_html_artifact_bytes_are_not_parsed_as_judgments(
    body: bytes, code: HKCaseEvidenceErrorCode
) -> None:
    """Accepting unstructured or active bytes as judgment evidence would be unsafe."""
    listing, bodies = _listing()
    member = _members(listing, bodies)[0]
    reader = ScriptedEvidenceReader({member.reference: body})
    forged = replace(member, fingerprint=_fingerprint(body), byte_length=len(body))

    with pytest.raises(HKCaseEvidenceError) as raised:
        load_hk_case_judgment_bundle(listing, (forged,), reader)

    assert raised.value.code is code


def test_mutated_source_listing_is_revalidated_before_evidence_access() -> None:
    """Trusting construction-time validation would let post-issuance source mutation through."""
    listing, bodies = _listing()
    object.__setattr__(listing.artifacts[0], "official_locator", 123)
    reader = ScriptedEvidenceReader(bodies)

    with pytest.raises(HKCaseEvidenceError) as raised:
        load_hk_case_judgment_bundle(listing, _members(listing, bodies), reader)

    assert raised.value.code is HKCaseEvidenceErrorCode.LISTING_INVALID
    assert reader.calls == []


def test_equality_lying_artifact_identity_is_rejected_before_mapping() -> None:
    """Equality-based member lookup would let an impostor artifact select real bytes."""
    listing, bodies = _listing()
    member = _members(listing, bodies)[0]
    object.__setattr__(member, "artifact_identity", _LyingArtifactIdentity("impostor"))
    reader = ScriptedEvidenceReader(bodies)

    with pytest.raises(HKCaseEvidenceError) as raised:
        load_hk_case_judgment_bundle(listing, (member,), reader)

    assert raised.value.code is HKCaseEvidenceErrorCode.EVIDENCE_MEMBER_INVALID
    assert reader.calls == []


def test_replay_rebuilds_an_equal_bundle_from_the_same_exact_bytes() -> None:
    """Depending on process-local issuance would make durable replay change a judgment bundle."""
    listing, bodies = _listing(opinions=("majority", "dissent"))
    reader = ScriptedEvidenceReader(bodies)
    members = _members(listing, bodies)

    first = load_hk_case_judgment_bundle(listing, members, reader)
    replay = load_hk_case_judgment_bundle(listing, members, reader)

    assert replay == first
    assert replay.bundle_fingerprint == first.bundle_fingerprint
    assert (
        tuple(item.reference for item in reader.calls)
        == tuple(item.reference for item in members) * 2
    )


def test_reader_mutation_cannot_replace_the_authoritative_member_or_body() -> None:
    """Passing caller authority into the reader would let it bless different retained bytes."""
    listing, bodies = _listing()
    members = _members(listing, bodies)
    original = members[0]
    changed = _changed_paragraph_body(
        bodies[original.reference], "X" * len("The exact scripted judgment paragraph.")
    )

    with pytest.raises(HKCaseEvidenceError) as raised:
        load_hk_case_judgment_bundle(listing, members, MutatingEvidenceReader(changed))

    assert raised.value.code is HKCaseEvidenceErrorCode.ARTIFACT_FINGERPRINT_MISMATCH
    assert original.reference == "evidence/artifact-majority"
    assert original.fingerprint == _fingerprint(bodies[original.reference])
    assert original.byte_length == len(bodies[original.reference])


def test_rich_listing_separates_original_opinions_from_translation_identities() -> None:
    """Requiring a translation identity as an original opinion would reject valid source facts."""
    listing, bodies = _listing(with_translation=True)

    result = load_hk_case_judgment_bundle(
        listing, _members(listing, bodies), ScriptedEvidenceReader(bodies)
    )

    assert result.judgment is not None
    assert tuple(item.opinion_id for item in result.judgment.opinions) == ("majority",)
    assert len(result.translations) == 1
    translation = result.translations[0]
    assert translation.translation_id == "artifact-translation-zh"
    assert translation.opinion_id == "translation-zh"
    assert translation.language == "ZH_HANT"
    assert translation.evidence_ref == "evidence/artifact-translation-zh"
    assert translation.evidence_fingerprint == _fingerprint(
        bodies["evidence/artifact-translation-zh"]
    )
    assert translation.evidence_byte_length == len(bodies["evidence/artifact-translation-zh"])
    assert translation.content_fingerprint.startswith("sha256:")
    assert translation.paragraphs[0].text == "The exact scripted judgment paragraph."


def test_linked_translation_may_share_the_original_opinion_identity() -> None:
    """The live source contract accounts opinion identities as a set across artifact roles."""
    listing, bodies = _listing(with_translation=True, translation_opinion_id="majority")

    result = load_hk_case_judgment_bundle(
        listing, _members(listing, bodies), ScriptedEvidenceReader(bodies)
    )

    assert result.judgment is not None
    assert tuple(item.opinion_id for item in result.judgment.opinions) == ("majority",)
    assert tuple(item.opinion_id for item in result.translations) == ("majority",)


def test_changed_valid_translation_bytes_change_bundle_identity() -> None:
    """Omitting translated content from the bundle digest would hide retained-byte drift."""
    listing, bodies = _listing(with_translation=True)
    members = _members(listing, bodies)
    first = load_hk_case_judgment_bundle(listing, members, ScriptedEvidenceReader(bodies))
    translation_ref = "evidence/artifact-translation-zh"
    changed_body = _changed_paragraph_body(bodies[translation_ref], "不同但有效的譯文。")
    changed_bodies = {**bodies, translation_ref: changed_body}
    changed = load_hk_case_judgment_bundle(
        listing,
        _members(listing, changed_bodies),
        ScriptedEvidenceReader(changed_bodies),
    )

    assert (
        first.translations[0].evidence_fingerprint != changed.translations[0].evidence_fingerprint
    )
    assert first.translations[0].paragraphs != changed.translations[0].paragraphs
    assert first.bundle_fingerprint != changed.bundle_fingerprint


@pytest.mark.parametrize("markup", ["<p>html</p>", "<ScRiPt>alert(1)</sCrIpT>"])
def test_json_escaped_decoded_markup_is_rejected_recursively(markup: str) -> None:
    """Inspecting only raw bytes would miss markup represented through JSON escapes."""
    listing, bodies = _listing()
    member = _members(listing, bodies)[0]
    changed = _changed_paragraph_body(bodies[member.reference], markup).replace(b"<", b"\\u003c")
    changed_member = replace(
        member,
        fingerprint=_fingerprint(changed),
        byte_length=len(changed),
    )

    with pytest.raises(HKCaseEvidenceError) as raised:
        load_hk_case_judgment_bundle(
            listing,
            (changed_member,),
            ScriptedEvidenceReader({member.reference: changed}),
        )

    assert raised.value.code is HKCaseEvidenceErrorCode.HTML_OR_SCRIPT_FORBIDDEN


def test_output_dataclasses_revalidate_nested_exact_facts_on_reconstruction() -> None:
    """A reconstructed bundle must not trust mutated nested output values."""
    listing, bodies = _listing(with_translation=True)
    result = load_hk_case_judgment_bundle(
        listing, _members(listing, bodies), ScriptedEvidenceReader(bodies)
    )
    assert result.judgment is not None

    with pytest.raises(HKCaseEvidenceError) as paragraph:
        HKCaseJudgmentParagraph(paragraph_id="", locator="para-1", text="Valid text")
    assert paragraph.value.code is HKCaseEvidenceErrorCode.OUTPUT_INVALID

    with pytest.raises(HKCaseEvidenceError) as opinion:
        replace(result.judgment.opinions[0], opinion_role="UNKNOWN")
    assert opinion.value.code is HKCaseEvidenceErrorCode.OUTPUT_INVALID

    with pytest.raises(HKCaseEvidenceError) as judgment:
        replace(result.judgment, opinions=())
    assert judgment.value.code is HKCaseEvidenceErrorCode.OUTPUT_INVALID

    with pytest.raises(HKCaseEvidenceError) as translation:
        replace(result.translations[0], content_fingerprint=f"sha256:{'0' * 64}")
    assert translation.value.code is HKCaseEvidenceErrorCode.OUTPUT_INVALID


def test_bundle_rejects_stale_or_copied_cached_fingerprint() -> None:
    """Bundle construction and copying must recompute coherence and the displayed digest."""
    listing, bodies = _listing()
    result = load_hk_case_judgment_bundle(
        listing, _members(listing, bodies), ScriptedEvidenceReader(bodies)
    )

    with pytest.raises(HKCaseEvidenceError) as stale:
        replace(result, bundle_fingerprint=f"sha256:{'0' * 64}")
    assert stale.value.code is HKCaseEvidenceErrorCode.BUNDLE_FINGERPRINT_MISMATCH

    object.__setattr__(result, "bundle_fingerprint", f"sha256:{'0' * 64}")
    with pytest.raises(HKCaseEvidenceError) as copied:
        copy(result)
    assert copied.value.code is HKCaseEvidenceErrorCode.BUNDLE_FINGERPRINT_MISMATCH


@pytest.mark.parametrize("listing", [RuntimeErrorListing(), RuntimeErrorArtifactListing()])
def test_ordinary_structural_listing_or_artifact_failure_is_closed(
    listing: RuntimeErrorListing | RuntimeErrorArtifactListing,
) -> None:
    """Ordinary source replay/property failures must not leak implementation exceptions."""
    reader = ScriptedEvidenceReader({})

    with pytest.raises(HKCaseEvidenceError) as raised:
        load_hk_case_judgment_bundle(listing, (), reader)

    assert raised.value.code is HKCaseEvidenceErrorCode.LISTING_INVALID
    assert reader.calls == []


def test_source_boundary_does_not_swallow_base_exceptions() -> None:
    """Process-control exceptions must survive ordinary structural normalization."""
    with pytest.raises(KeyboardInterrupt):
        load_hk_case_judgment_bundle(BaseExceptionListing(), (), ScriptedEvidenceReader({}))


def test_citation_inventories_preserve_zero_multiple_category_and_order() -> None:
    listing, bodies = _listing(
        neutral_citations=("N-1", "N-2"),
        reported_citations=("R-1", "R-2"),
        proceeding_numbers=("P-1", "P-2"),
    )
    bundle = load_hk_case_judgment_bundle(
        listing, _members(listing, bodies), ScriptedEvidenceReader(bodies)
    )
    assert bundle.judgment is not None
    assert bundle.judgment.neutral_citations == ("N-1", "N-2")
    assert bundle.judgment.reported_citations == ("R-1", "R-2")
    assert bundle.judgment.proceeding_numbers == ("P-1", "P-2")
    for kwargs in (
        {"neutral_citations": ("N-1", "N-1")},
        {"reported_citations": ("R-2", "R-1")},
        {"proceeding_numbers": ()},
        {"neutral_citations": ["N-1"]},
        {"reported_citations": "R-1"},
        {"proceeding_numbers": (_LyingArtifactIdentity("P-1"),)},
    ):
        with pytest.raises(HKCaseEvidenceError):
            replace(bundle.judgment, **kwargs)
    zero, zero_bodies = _listing(neutral_citations=(), reported_citations=())
    assert load_hk_case_judgment_bundle(
        zero, _members(zero, zero_bodies), ScriptedEvidenceReader(zero_bodies)
    ).judgment


def _listing(
    *,
    court_family: ScriptedCourtFamily = ScriptedCourtFamily.CFA,
    decision_date: str = "2020-01-02",
    opinions: tuple[str, ...] = ("majority",),
    with_translation: bool = False,
    translation_opinion_id: str = "translation-zh",
    neutral_citations: tuple[str, ...] = ("2020 HKCFA 1",),
    reported_citations: tuple[str, ...] = (),
    proceeding_numbers: tuple[str, ...] = ("P-1",),
) -> tuple[ScriptedListing, dict[str, bytes]]:
    """Build a complete scripted Plan 2 listing and its local immutable bytes."""
    originals = tuple(_artifact("listing-current", opinion) for opinion in opinions)
    translation = (
        (
            _artifact(
                "listing-current",
                translation_opinion_id,
                role=ScriptedArtifactRole.TRANSLATION,
                language=ScriptedLanguage.TRADITIONAL_CHINESE,
                artifact_identity="artifact-translation-zh",
            ),
        )
        if with_translation
        else ()
    )
    artifacts = (*originals, *translation)
    sorted_artifacts = tuple(sorted(artifacts, key=lambda item: item.artifact_identity))
    listing = ScriptedListing(
        listing_identity="listing-current",
        court_family=court_family,
        decision_date=decision_date,
        opinion_or_reasons_identities=tuple(
            sorted({*opinions, *((translation_opinion_id,) if with_translation else ())})
        ),
        artifacts=sorted_artifacts,
        neutral_citations=neutral_citations,
        reported_citations=reported_citations,
        proceeding_numbers=proceeding_numbers,
    )
    bodies = {
        f"evidence/{artifact.artifact_identity}": _artifact_document(
            artifact,
            court_family,
            decision_date,
            _opinion_role(artifact.opinion_or_reasons_identity),
        )
        for artifact in sorted_artifacts
    }
    return listing, bodies


def _artifact(
    listing_identity: str,
    opinion_id: str,
    *,
    role: ScriptedArtifactRole = ScriptedArtifactRole.ORIGINAL,
    language: ScriptedLanguage = ScriptedLanguage.ENGLISH,
    artifact_identity: str | None = None,
) -> ScriptedArtifact:
    """Build one source-shaped original judgment artifact locator."""
    return ScriptedArtifact(
        artifact_identity=artifact_identity or f"artifact-{opinion_id}",
        listing_identity=listing_identity,
        source_id=(
            "HK-CASE-JUDICIARY-JUDGMENT"
            if role is ScriptedArtifactRole.ORIGINAL
            else "HK-CASE-JUDICIARY-TRANSLATION"
        ),
        role=role,
        language=language,
        opinion_or_reasons_identity=opinion_id,
        official_locator=f"/judgments/{opinion_id}.json",
    )


def _artifact_document(
    artifact: ScriptedArtifact,
    court_family: ScriptedCourtFamily,
    decision_date: str,
    opinion_role: str,
) -> bytes:
    """Return independently shaped immutable fixture bytes for one opinion artifact."""
    document = {
        "artifact_identity": artifact.artifact_identity,
        "court_id": court_family.value,
        "decision_date": decision_date,
        "judge_names": ["Judge Example"],
        "language": artifact.language.value,
        "listing_identity": artifact.listing_identity,
        "opinion_id": artifact.opinion_or_reasons_identity,
        "opinion_role": opinion_role,
        "paragraphs": [
            {
                "locator": f"para-{artifact.opinion_or_reasons_identity}-1",
                "paragraph_id": f"paragraph-{artifact.opinion_or_reasons_identity}-1",
                "text": "The exact scripted judgment paragraph.",
            }
        ],
        "schema_id": "asklegal.hk-case-judgment-artifact/v1",
        "source_id": artifact.source_id,
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _members(
    listing: ScriptedListing, bodies: dict[str, bytes]
) -> tuple[HKCaseEvidenceMember, ...]:
    """Bind each declared locator to one retained immutable evidence member."""
    return tuple(
        HKCaseEvidenceMember(
            artifact_identity=artifact.artifact_identity,
            listing_identity=listing.listing_identity,
            reference=f"evidence/{artifact.artifact_identity}",
            fingerprint=_fingerprint(bodies[f"evidence/{artifact.artifact_identity}"]),
            byte_length=len(bodies[f"evidence/{artifact.artifact_identity}"]),
        )
        for artifact in listing.artifacts
    )


def _fingerprint(body: bytes) -> str:
    """Compute the fixture's independent SHA-256 retained-byte binding."""
    return f"sha256:{sha256(body).hexdigest()}"


def _changed_paragraph_body(body: bytes, text: str) -> bytes:
    """Change only one valid fixture paragraph while retaining the exact document shape."""
    old = b'"text":"The exact scripted judgment paragraph."'
    replacement = b'"text":' + json.dumps(text, ensure_ascii=False).encode()
    assert body.count(old) == 1
    return body.replace(old, replacement)


def _opinion_role(opinion_id: str) -> str:
    """Return one literal fixture role without coupling expected results to production logic."""
    return {"majority": "MAJORITY", "dissent": "DISSENT", "translation-zh": "SEPARATE"}[opinion_id]


def test_only_a_fingerprinted_complete_cases_manifest_is_admitted_for_later_processing() -> None:
    """Changing result or a covered field must withhold Case processing input."""
    body = {
        "cycle_id": "cyc_cases_1",
        "discrepancy_refs": ["差異/一"],
        "earliest_decision_date": "1997-07-01",
        "journal_head_fingerprint": "sha256:" + "b" * 64,
        "judgment_bundle_refs": ["cases/judgment-bundles/sha256/" + "1" * 64 + ".json"],
        "observation_cutoff": "1997-12-31T00:00:00Z",
        "result": "COMPLETE",
        "year_dispositions": [
            {
                "discovered_judgments": 1,
                "final_page": 1,
                "first_in_scope_date": "1997-07-01",
                "result": "COMPLETE",
                "retryable_items": 0,
                "verified_judgments": 1,
                "verified_listing_pages": 1,
                "year": 1997,
            }
        ],
    }
    body["fingerprint"] = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
    raw = canonicalize(checked_json_value(body))

    accepted = accept_complete_cases_acquisition_manifest(raw)

    assert accepted.cycle_id == "cyc_cases_1"
    assert accepted.manifest_fingerprint == body["fingerprint"]
    body["result"] = "INCOMPLETE_RETRYABLE"
    with pytest.raises(HKCaseEvidenceError) as caught:
        accept_complete_cases_acquisition_manifest(
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        )
    assert caught.value.code is HKCaseEvidenceErrorCode.ACQUISITION_MANIFEST_INVALID


def _update_manifest(body: dict[str, object], **values: object) -> None:
    body.update(values)


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return type(value) is list


def _is_object_dict(value: object) -> TypeIs[dict[str, object]]:
    return type(value) is dict


def _update_first_manifest_shard(body: dict[str, object], **values: object) -> None:
    shards = body["year_dispositions"]
    assert _is_object_list(shards)
    assert shards
    assert _is_object_dict(shards[0])
    shards[0].update(values)


_HOSTILE_MANIFEST_MUTATIONS: tuple[Callable[[dict[str, object]], None], ...] = (
    lambda body: _update_manifest(body, observation_cutoff="1998-12-31T00:00:00Z"),
    lambda body: _update_first_manifest_shard(body, first_in_scope_date="1997-01-01"),
    lambda body: _update_first_manifest_shard(body, final_page=0),
    lambda body: _update_first_manifest_shard(body, verified_listing_pages=2),
    lambda body: _update_manifest(body, judgment_bundle_refs=[]),
    lambda body: _update_first_manifest_shard(body, retryable_items=1),
    lambda body: _update_first_manifest_shard(body, extra="hostile"),
    lambda body: _update_first_manifest_shard(body, final_page=True),
)


@pytest.mark.parametrize("mutation", _HOSTILE_MANIFEST_MUTATIONS)
def test_cases_manifest_rejects_hostile_complete_shapes_even_when_resigned(
    mutation: Callable[[dict[str, object]], None],
) -> None:
    """A matching digest cannot bless an incomplete or type-confused universe."""
    body = {
        "cycle_id": "cyc_cases_hostile",
        "discrepancy_refs": [],
        "earliest_decision_date": "1997-07-01",
        "journal_head_fingerprint": "sha256:" + "b" * 64,
        "judgment_bundle_refs": ["cases/judgment-bundles/sha256/" + "1" * 64 + ".json"],
        "observation_cutoff": "1997-12-31T00:00:00Z",
        "result": "COMPLETE",
        "year_dispositions": [
            {
                "discovered_judgments": 1,
                "final_page": 1,
                "first_in_scope_date": "1997-07-01",
                "result": "COMPLETE",
                "retryable_items": 0,
                "verified_judgments": 1,
                "verified_listing_pages": 1,
                "year": 1997,
            }
        ],
    }
    hostile: dict[str, object] = {key: deepcopy(value) for key, value in body.items()}
    mutation(hostile)
    hostile["fingerprint"] = (
        "sha256:" + sha256(canonicalize(checked_json_value(hostile))).hexdigest()
    )

    with pytest.raises(HKCaseEvidenceError) as caught:
        accept_complete_cases_acquisition_manifest(canonicalize(checked_json_value(hostile)))

    assert caught.value.code is HKCaseEvidenceErrorCode.ACQUISITION_MANIFEST_INVALID


def test_cases_manifest_unicode_refs_and_complete_no_change_use_rfc8785() -> None:
    """Non-ASCII source refs must round-trip under the repository canonicalizer."""
    body = {
        "cycle_id": "cyc_cases_unicode",
        "discrepancy_refs": ["差異/法院"],
        "earliest_decision_date": "1997-07-01",
        "journal_head_fingerprint": "sha256:" + "b" * 64,
        "judgment_bundle_refs": [],
        "observation_cutoff": "1997-12-31T00:00:00Z",
        "result": "NO_CHANGE",
        "year_dispositions": [
            {
                "discovered_judgments": 0,
                "final_page": 1,
                "first_in_scope_date": "1997-07-01",
                "result": "COMPLETE",
                "retryable_items": 0,
                "verified_judgments": 0,
                "verified_listing_pages": 1,
                "year": 1997,
            }
        ],
    }
    body["fingerprint"] = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()

    accepted = accept_complete_cases_acquisition_manifest(canonicalize(checked_json_value(body)))

    assert accepted.cycle_id == "cyc_cases_unicode"
