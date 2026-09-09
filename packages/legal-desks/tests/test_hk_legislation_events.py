"""Pure deterministic Hong Kong legislation event-timeline tests."""

from __future__ import annotations

import socket
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import asklegal_legal_desks.hk_legislation_events as events_module
import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks.hk_legislation_events import (
    HKLegislationAcquiredEventFacts,
    HKLegislationCoverageEffect,
    HKLegislationDisposition,
    HKLegislationEvent,
    HKLegislationEventDecision,
    HKLegislationEventError,
    HKLegislationEventErrorCode,
    HKLegislationEventKind,
    HKLegislationEventSource,
    HKLegislationEventTimeline,
    HKLegislationProcessingOutcome,
    HKLegislationReconstructionAuthority,
    HKLegislationSourceContractReview,
    bind_hk_legislation_acquired_event_facts,
    decide_hk_legislation_state,
)
from asklegal_legal_desks.hk_reconstruction_report import ReconstructionExecutionReport

_CUTOFF = "2026-08-26T00:00:00Z"
_LOCATION = "loc_000000000000000000000000000000000000000000000001"
_VERSION = "ofv_000000000000000000000000000000000000000000000001"
_REPORT_PATH = (
    Path(__file__).resolve().parents[1]
    / "src/asklegal_legal_desks/_hk_legislation_package/expected/reconstruction-report"
    / "HKLEG-RECON-REPORT-FIX-001.json"
)
_REPORT_EVENT_REF = "lse_000000000000000000000000000000000000000000000001"


def _event(
    event_ref: str,
    kind: HKLegislationEventKind,
    *,
    event_identity: str | None = None,
    source: HKLegislationEventSource = HKLegislationEventSource.GAZETTE,
    effective_at: str = "2026-08-25T00:00:00Z",
) -> HKLegislationEvent:
    return HKLegislationEvent(
        event_ref=event_ref,
        event_identity=event_identity or event_ref,
        legal_location_id=_LOCATION,
        official_version_id=_VERSION,
        kind=kind,
        source=source,
        effective_at=effective_at,
        evidence_fingerprint=("sha256:" + ("5" if event_ref == _REPORT_EVENT_REF else "a") * 64),
        basis_event_refs=(),
        reconstruction_report=None,
    )


def _timeline(
    *events: HKLegislationEvent,
    source_facts_complete: bool = True,
    known_stale: bool = False,
    source_contract_review: HKLegislationSourceContractReview = (
        HKLegislationSourceContractReview.NOT_REQUIRED
    ),
) -> HKLegislationEventTimeline:
    return HKLegislationEventTimeline(
        schema_id="asklegal.hk-legislation-event-timeline",
        schema_version="1.0.0",
        legal_location_id=_LOCATION,
        official_version_id=_VERSION,
        source_facts_complete=source_facts_complete,
        known_stale=known_stale,
        source_contract_review=source_contract_review,
        events=events,
    )


def _successful_report() -> ReconstructionExecutionReport:
    document = parse_json_bytes(_REPORT_PATH.read_bytes(), max_bytes=8_000_000)
    raw = canonicalize(checked_json_value(document))
    return ReconstructionExecutionReport(
        "rex_000000000000000000000000000000000000000000000001",
        f"sha256:{sha256(raw).hexdigest()}",
        raw,
    )


def _report_from_document(
    document: dict[str, JsonValue],
    *,
    report_id: str | None = None,
    canonical: bool = True,
    fingerprint: str | None = None,
) -> ReconstructionExecutionReport:
    raw = canonicalize(checked_json_value(document))
    if not canonical:
        raw += b" "
    selected_id = report_id or str(document["reconstruction_execution_report_id"])
    return ReconstructionExecutionReport(
        selected_id,
        fingerprint or f"sha256:{sha256(raw).hexdigest()}",
        raw,
    )


def _json_fingerprint(value: JsonValue) -> str:
    return f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"


def _object(value: JsonValue | None) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _array(value: JsonValue | None) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _refresh_report_success_bindings(document: dict[str, JsonValue]) -> None:
    """Rebuild the Report's internal derived bindings after a hostile substitution."""
    output = _object(document.get("artifact_output"))
    dependency = _object(document.get("dependency_validation"))
    affected = deepcopy(_array(dependency.get("affected_location_refs")))
    output["affected_legal_location_refs"] = affected
    output["affected_location_inventory_fingerprint"] = _json_fingerprint(affected)

    artifact = deepcopy(_object(output.get("reconstructed_consolidation_artifact_ref")))
    member_keys = (
        "manifest_ref",
        "en_final_tree_ref",
        "zh_hant_final_tree_ref",
        "canonical_bilingual_output_ref",
        "bilingual_alignment_map_ref",
        "dependency_closure_proof_ref",
        "source_unit_coverage_proof_ref",
    )
    for key in member_keys:
        _object(output.get(key))["reconstructed_consolidation_artifact_ref"] = deepcopy(artifact)

    language_results = _array(document.get("language_results"))
    for result_value, member_key in zip(
        language_results,
        ("en_final_tree_ref", "zh_hant_final_tree_ref"),
        strict=True,
    ):
        result = _object(result_value)
        member = deepcopy(_object(output.get(member_key)))
        result["final_tree_ref"] = member
        result["final_tree_fingerprint"] = member["fingerprint"]
    bilingual = _object(document.get("bilingual_validation"))
    alignment = deepcopy(_object(output.get("bilingual_alignment_map_ref")))
    bilingual["final_alignment_map_ref"] = alignment
    bilingual["final_alignment_fingerprint"] = alignment["fingerprint"]
    dependency["artifact_dependency_proof_ref"] = deepcopy(
        _object(output.get("dependency_closure_proof_ref"))
    )

    coverage = _object(document.get("coverage_consequence"))
    traceability_binding: dict[str, JsonValue] = {
        "reconstruction_plan_ref": document["reconstruction_plan_ref"],
        "reconstructed_consolidation_artifact_ref": output[
            "reconstructed_consolidation_artifact_ref"
        ],
        "manifest_ref": output["manifest_ref"],
        "affected_legal_location_refs": affected,
        "contracts": document["contracts"],
        "coverage_gap_ref": coverage["coverage_gap_ref"],
    }
    output["traceability_binding_fingerprint"] = _json_fingerprint(traceability_binding)


def _reference_identity(value: JsonValue | None) -> tuple[str, str]:
    assert isinstance(value, dict)
    ref_id = value.get("ref_id")
    fingerprint = value.get("fingerprint")
    assert isinstance(ref_id, str)
    assert isinstance(fingerprint, str)
    return ref_id, fingerprint


def _reconstruction_authority(
    report: ReconstructionExecutionReport,
) -> HKLegislationReconstructionAuthority:
    document = report.document()
    base = _object(document.get("base_validation"))
    bilingual = _object(document.get("bilingual_validation"))
    dependency = _object(document.get("dependency_validation"))
    output = _object(document.get("artifact_output"))
    plan = _reference_identity(document.get("reconstruction_plan_ref"))
    official_version = _reference_identity(base.get("official_version_ref"))
    engine_build = _reference_identity(document.get("engine_build_ref"))
    alignment = _reference_identity(bilingual.get("expected_alignment_map_ref"))
    affected = tuple(
        _reference_identity(value) for value in _array(dependency.get("affected_location_refs"))
    )
    artifact = _reference_identity(output.get("reconstructed_consolidation_artifact_ref"))
    canonical_output = _object(output.get("canonical_bilingual_output_ref"))
    canonical_fingerprint = canonical_output.get("fingerprint")
    canonical_byte_size = canonical_output.get("byte_size")
    assert isinstance(canonical_fingerprint, str)
    assert type(canonical_byte_size) is int
    return HKLegislationReconstructionAuthority(
        accepted_report_id=report.reconstruction_execution_report_id,
        accepted_report_fingerprint=report.fingerprint,
        reconstruction_plan_id=plan[0],
        reconstruction_plan_fingerprint=plan[1],
        base_official_version_id=official_version[0],
        base_official_version_fingerprint=official_version[1],
        engine_build_id=engine_build[0],
        engine_build_fingerprint=engine_build[1],
        expected_alignment_id=alignment[0],
        expected_alignment_fingerprint=alignment[1],
        affected_location_refs=affected,
        reconstructed_artifact_id=artifact[0],
        reconstructed_artifact_fingerprint=artifact[1],
        canonical_output_fingerprint=canonical_fingerprint,
        canonical_output_byte_size=canonical_byte_size,
    )


def _reconstruction_event(
    report: ReconstructionExecutionReport,
    *,
    basis_event_refs: tuple[str, ...] = (_REPORT_EVENT_REF,),
) -> HKLegislationEvent:
    return HKLegislationEvent(
        event_ref="evt-reconstruction",
        event_identity="evt-reconstruction",
        legal_location_id=_LOCATION,
        official_version_id=_VERSION,
        kind=HKLegislationEventKind.RECONSTRUCTION,
        source=HKLegislationEventSource.ACCEPTED_RECONSTRUCTION,
        effective_at="2026-08-25T02:00:00Z",
        evidence_fingerprint=report.fingerprint,
        basis_event_refs=basis_event_refs,
        reconstruction_report=report,
        reconstruction_authority=_reconstruction_authority(report),
    )


def _complete_reconstruction_timeline(
    *,
    source_facts_complete: bool = True,
    known_stale: bool = False,
    source_contract_review: HKLegislationSourceContractReview = (
        HKLegislationSourceContractReview.NOT_REQUIRED
    ),
) -> tuple[HKLegislationEventTimeline, HKLegislationEvent]:
    reconstruction = _reconstruction_event(_successful_report())
    return (
        _timeline(
            _event("evt-publication", HKLegislationEventKind.PUBLICATION),
            _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT),
            _event(
                _REPORT_EVENT_REF,
                HKLegislationEventKind.AMENDMENT,
                effective_at="2026-08-25T01:00:00Z",
            ),
            reconstruction,
            source_facts_complete=source_facts_complete,
            known_stale=known_stale,
            source_contract_review=source_contract_review,
        ),
        reconstruction,
    )


def _reconstruction_timeline_with_header_value(
    field: str,
    value: object,
) -> tuple[HKLegislationEventTimeline, HKLegislationEvent]:
    if field == "source_facts_complete":
        assert type(value) is bool
        return _complete_reconstruction_timeline(source_facts_complete=value)
    if field == "known_stale":
        assert type(value) is bool
        return _complete_reconstruction_timeline(known_stale=value)
    assert type(value) is HKLegislationSourceContractReview
    return _complete_reconstruction_timeline(source_contract_review=value)


def _later_event_repair_scenario(
    mutation: str,
) -> tuple[HKLegislationEventTimeline, HKLegislationEvent, str, object]:
    class EqualityLiar(str):
        __slots__ = ()
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            del other
            return True

    reconstruction = _reconstruction_event(_successful_report())
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    amendment = _event(
        _REPORT_EVENT_REF,
        HKLegislationEventKind.AMENDMENT,
        effective_at="2026-08-25T01:00:00Z",
    )
    commencement = _event(
        "evt-later",
        HKLegislationEventKind.COMMENCEMENT,
        effective_at="2026-08-25T03:00:00Z",
    )
    later = commencement
    field = mutation
    replacement: object
    if mutation == "kind":
        later = replace(commencement, kind=HKLegislationEventKind.CESSATION)
        replacement = HKLegislationEventKind.COMMENCEMENT
    elif mutation == "source":
        later = replace(
            commencement,
            source=HKLegislationEventSource.ACCEPTED_RECONSTRUCTION,
        )
        replacement = HKLegislationEventSource.GAZETTE
    elif mutation == "effective_at":
        later = replace(commencement, effective_at="2026-08-25T03:00:00+00:00")
        replacement = "2026-08-25T03:00:00Z"
    elif mutation == "evidence_fingerprint":
        later = replace(amendment, evidence_fingerprint="sha256:" + "e" * 64)
        replacement = "sha256:" + "5" * 64
    elif mutation == "equality_source":
        field = "source"
        object.__setattr__(
            later,
            field,
            EqualityLiar(HKLegislationEventSource.ACCEPTED_RECONSTRUCTION.value),
        )
        replacement = HKLegislationEventSource.GAZETTE
    else:
        field = "basis_event_refs"
        object.__setattr__(later, field, [])
        replacement = ()
    events = (reconstruction, publication, amendment, later)
    if mutation == "evidence_fingerprint":
        events = (reconstruction, publication, later, commencement)
    return _timeline(*events), later, field, replacement


def test_publication_without_commencement_stays_waiting() -> None:
    decision = decide_hk_legislation_state(
        _timeline(_event("evt-publication", HKLegislationEventKind.PUBLICATION)), _CUTOFF
    )

    assert decision.processing_outcome is HKLegislationProcessingOutcome.PASS
    assert decision.legal_disposition is HKLegislationDisposition.WAITING_ROOM
    assert decision.reason_code == "COMMENCEMENT_NOT_PROVED"


def test_conflicting_gazette_and_publisher_facts_are_quarantined() -> None:
    gazette = _event(
        "evt-gazette",
        HKLegislationEventKind.COMMENCEMENT,
        event_identity="evt-official-status",
    )
    publisher = replace(
        gazette,
        event_ref="evt-publisher",
        event_identity="evt-publisher-status",
        kind=HKLegislationEventKind.CESSATION,
        source=HKLegislationEventSource.PUBLISHER,
        evidence_fingerprint="sha256:" + "b" * 64,
    )

    decision = decide_hk_legislation_state(
        _timeline(
            _event("evt-publication", HKLegislationEventKind.PUBLICATION), gazette, publisher
        ),
        _CUTOFF,
    )

    assert decision.processing_outcome is HKLegislationProcessingOutcome.QUARANTINE
    assert decision.legal_disposition is HKLegislationDisposition.QUARANTINE
    assert decision.reason_code == "OFFICIAL_EVENT_CONFLICT"


def test_same_time_opposed_official_status_facts_conflict_without_shared_identity() -> None:
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    cessation = _event(
        "evt-cessation",
        HKLegislationEventKind.CESSATION,
        source=HKLegislationEventSource.PUBLISHER,
    )

    decision = decide_hk_legislation_state(
        _timeline(
            _event("evt-publication", HKLegislationEventKind.PUBLICATION),
            commencement,
            cessation,
        ),
        _CUTOFF,
    )

    assert decision.legal_disposition is HKLegislationDisposition.QUARANTINE
    assert decision.reason_code == "OFFICIAL_EVENT_CONFLICT"


def test_all_five_accepted_dispositions_remain_distinct() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    cessation = _event(
        "evt-cessation", HKLegislationEventKind.CESSATION, effective_at="2026-08-25T01:00:00Z"
    )
    conflict = replace(
        commencement,
        event_ref="evt-conflict",
        event_identity="evt-conflict",
        kind=HKLegislationEventKind.CESSATION,
        source=HKLegislationEventSource.PUBLISHER,
    )
    decisions = (
        decide_hk_legislation_state(_timeline(publication, commencement), _CUTOFF),
        decide_hk_legislation_state(_timeline(publication), _CUTOFF),
        decide_hk_legislation_state(
            _timeline(
                publication,
                commencement,
                _event("evt-amendment", HKLegislationEventKind.AMENDMENT),
            ),
            _CUTOFF,
        ),
        decide_hk_legislation_state(_timeline(publication, commencement, cessation), _CUTOFF),
        decide_hk_legislation_state(_timeline(publication, commencement, conflict), _CUTOFF),
    )

    assert tuple(decision.legal_disposition for decision in decisions) == (
        HKLegislationDisposition.SEARCHABLE_CURRENT,
        HKLegislationDisposition.WAITING_ROOM,
        HKLegislationDisposition.EVIDENCE_ONLY,
        HKLegislationDisposition.HISTORICAL,
        HKLegislationDisposition.QUARANTINE,
    )


def test_cutoff_orders_cessation_and_later_revival_without_future_inference() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    cessation = _event(
        "evt-cessation", HKLegislationEventKind.CESSATION, effective_at="2026-08-25T01:00:00Z"
    )
    revival = replace(
        _event(
            "evt-revival",
            HKLegislationEventKind.REVIVAL,
            effective_at="2026-08-27T00:00:00Z",
        ),
        basis_event_refs=(cessation.event_ref,),
    )

    before = decide_hk_legislation_state(
        _timeline(publication, commencement, cessation, revival), _CUTOFF
    )
    after = decide_hk_legislation_state(
        _timeline(publication, commencement, cessation, revival),
        "2026-08-28T00:00:00Z",
    )

    assert before.legal_disposition is HKLegislationDisposition.HISTORICAL
    assert before.controlling_event_refs[-1] == cessation.event_ref
    assert after.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT
    assert after.controlling_event_refs[-1] == revival.event_ref


def test_known_stale_amendment_is_warned_searchable_carry_forward() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    amendment = _event(
        "evt-amendment", HKLegislationEventKind.AMENDMENT, effective_at="2026-08-25T01:00:00Z"
    )

    decision = decide_hk_legislation_state(
        _timeline(publication, commencement, amendment, known_stale=True), _CUTOFF
    )

    assert decision.processing_outcome is HKLegislationProcessingOutcome.PASS
    assert decision.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT
    assert decision.coverage_effect is HKLegislationCoverageEffect.COVERAGE_GAP
    assert decision.reason_code == "KNOWN_STALE_ANALYTICAL_CARRY_FORWARD"
    assert decision.unresolved_fact_codes == ("KNOWN_STALE_WARNING_AND_AUTHORITY_NOTE_REQUIRED",)


def test_known_stale_without_an_operative_text_event_fails_closed() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)

    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(
            _timeline(publication, commencement, known_stale=True),
            _CUTOFF,
        )

    assert caught.value.code.value == "HK_LEGISLATION_EVENT_TIMELINE_INVALID"


def test_complete_reconstruction_takes_precedence_over_known_stale_fallback() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    amendment = _event(
        _REPORT_EVENT_REF,
        HKLegislationEventKind.AMENDMENT,
        effective_at="2026-08-25T01:00:00Z",
    )
    reconstruction = _reconstruction_event(_successful_report())

    decision = decide_hk_legislation_state(
        _timeline(
            publication,
            commencement,
            amendment,
            reconstruction,
            known_stale=True,
        ),
        _CUTOFF,
    )

    assert decision.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT
    assert decision.coverage_effect is HKLegislationCoverageEffect.COVERAGE_GAP
    assert decision.reason_code == "OPERATIVE_CURRENT_TEXT_RECONSTRUCTED"


def test_adr0084_report_authorizes_exact_reconstruction_event() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    amendment = _event(
        _REPORT_EVENT_REF,
        HKLegislationEventKind.AMENDMENT,
        effective_at="2026-08-25T01:00:00Z",
    )

    decision = decide_hk_legislation_state(
        _timeline(
            publication,
            commencement,
            amendment,
            _reconstruction_event(_successful_report()),
        ),
        _CUTOFF,
    )

    assert decision.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT
    assert decision.coverage_effect is HKLegislationCoverageEffect.NONE
    assert decision.reason_code == "OPERATIVE_CURRENT_TEXT_RECONSTRUCTED"


@pytest.mark.parametrize(
    "reference_path",
    [
        ("event_chain_validation", "event_refs", 0),
        ("base_validation", "official_version_ref"),
        ("engine_build_ref",),
        ("bilingual_validation", "expected_alignment_map_ref"),
    ],
)
def test_reconstruction_report_reference_fingerprints_bind_to_retained_event_authority(
    reference_path: tuple[str | int, ...],
) -> None:
    """Resealing one report reference cannot replace the authority the event retained."""
    original = _successful_report()
    reconstruction = _reconstruction_event(original)
    document = original.document()
    if reference_path == ("event_chain_validation", "event_refs", 0):
        validation = document["event_chain_validation"]
        assert isinstance(validation, dict)
        refs = validation["event_refs"]
        assert isinstance(refs, list)
        target = refs[0]
    elif reference_path == ("base_validation", "official_version_ref"):
        base = document["base_validation"]
        assert isinstance(base, dict)
        target = base["official_version_ref"]
    elif reference_path == ("engine_build_ref",):
        target = document["engine_build_ref"]
    else:
        bilingual = document["bilingual_validation"]
        assert isinstance(bilingual, dict)
        target = bilingual["expected_alignment_map_ref"]
    assert isinstance(target, dict)
    target["fingerprint"] = "sha256:" + "f" * 64
    forged = _report_from_document(document)
    amendment = _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT)

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                _event("evt-publication", HKLegislationEventKind.PUBLICATION),
                _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT),
                amendment,
                replace(
                    reconstruction,
                    reconstruction_report=forged,
                    evidence_fingerprint=forged.fingerprint,
                ),
            ),
            _CUTOFF,
        )


def test_reconstruction_event_fingerprint_must_equal_its_retained_report() -> None:
    """A reconstruction source fact cannot cite bytes other than the report it carries."""
    report = _successful_report()
    amendment = _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT)

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                amendment,
                replace(
                    _reconstruction_event(report),
                    evidence_fingerprint="sha256:" + "e" * 64,
                ),
            ),
            _CUTOFF,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_official_version_id", "ofv_" + "2" * 48),
        ("base_official_version_fingerprint", "sha256:" + "f" * 64),
        ("accepted_report_id", "rex_" + "2" * 48),
        ("accepted_report_fingerprint", "sha256:" + "f" * 64),
        ("reconstruction_plan_id", "rpl_" + "2" * 48),
        ("reconstruction_plan_fingerprint", "sha256:" + "f" * 64),
        ("engine_build_id", "eng_" + "2" * 48),
        ("engine_build_fingerprint", "sha256:" + "f" * 64),
        ("expected_alignment_id", "art_" + "2" * 48),
        ("expected_alignment_fingerprint", "sha256:" + "f" * 64),
        (
            "affected_location_refs",
            ((_LOCATION, "sha256:" + "f" * 64),),
        ),
        ("reconstructed_artifact_id", "rca_" + "2" * 48),
        ("reconstructed_artifact_fingerprint", "sha256:" + "f" * 64),
        ("canonical_output_fingerprint", "sha256:" + "f" * 64),
        ("canonical_output_byte_size", 1),
    ],
)
def test_reconstruction_authority_snapshot_rejects_every_substituted_fact(
    field: str,
    value: object,
) -> None:
    reconstruction = _reconstruction_event(_successful_report())
    authority = reconstruction.reconstruction_authority
    assert isinstance(authority, HKLegislationReconstructionAuthority)
    forged = replace(reconstruction, reconstruction_authority=replace(authority, **{field: value}))

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
                forged,
            ),
            _CUTOFF,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "report_id",
        "plan_id",
        "plan_fingerprint",
        "affected_location_fingerprint",
        "artifact_id",
        "artifact_fingerprint",
        "canonical_output_fingerprint",
        "canonical_output_byte_size",
    ],
)
def test_reconstruction_authority_rejects_internally_coherent_report_substitution(
    mutation: str,
) -> None:
    original = _successful_report()
    reconstruction = _reconstruction_event(original)
    document = original.document()
    report_id: str | None = None
    if mutation == "report_id":
        report_id = "rex_" + "2" * 48
        document["reconstruction_execution_report_id"] = report_id
    elif mutation in {"plan_id", "plan_fingerprint"}:
        plan = _object(document.get("reconstruction_plan_ref"))
        if mutation == "plan_id":
            plan["ref_id"] = "rpl_" + "2" * 48
        else:
            plan["fingerprint"] = "sha256:" + "2" * 64
    elif mutation == "affected_location_fingerprint":
        dependency = _object(document.get("dependency_validation"))
        affected = _array(dependency.get("affected_location_refs"))
        _object(affected[0])["fingerprint"] = "sha256:" + "2" * 64
    elif mutation in {"artifact_id", "artifact_fingerprint"}:
        output = _object(document.get("artifact_output"))
        artifact = _object(output.get("reconstructed_consolidation_artifact_ref"))
        if mutation == "artifact_id":
            artifact["ref_id"] = "rca_" + "2" * 48
        else:
            artifact["fingerprint"] = "sha256:" + "2" * 64
    elif mutation == "canonical_output_fingerprint":
        output = _object(document.get("artifact_output"))
        canonical_output = _object(output.get("canonical_bilingual_output_ref"))
        canonical_output["fingerprint"] = "sha256:" + "2" * 64
    else:
        output = _object(document.get("artifact_output"))
        canonical_output = _object(output.get("canonical_bilingual_output_ref"))
        canonical_output["byte_size"] = 1
    _refresh_report_success_bindings(document)
    forged = _report_from_document(document, report_id=report_id)

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
                replace(
                    reconstruction,
                    reconstruction_report=forged,
                    evidence_fingerprint=forged.fingerprint,
                ),
            ),
            _CUTOFF,
        )


@pytest.mark.parametrize("mutation", ["reorder", "missing", "duplicate"])
def test_reconstruction_authority_binds_complete_ordered_affected_location_inventory(
    mutation: str,
) -> None:
    original = _successful_report()
    reconstruction = _reconstruction_event(original)
    document = original.document()
    dependency = _object(document.get("dependency_validation"))
    affected = _array(dependency.get("affected_location_refs"))
    if mutation == "reorder":
        affected.reverse()
    elif mutation == "missing":
        affected.pop()
    else:
        affected.append(deepcopy(affected[0]))
    _refresh_report_success_bindings(document)
    forged = _report_from_document(document)

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
                replace(
                    reconstruction,
                    reconstruction_report=forged,
                    evidence_fingerprint=forged.fingerprint,
                ),
            ),
            _CUTOFF,
        )


@pytest.mark.parametrize("mutation", ["reorder", "missing", "duplicate"])
def test_reconstruction_authority_snapshot_rejects_affected_inventory_aliases(
    mutation: str,
) -> None:
    reconstruction = _reconstruction_event(_successful_report())
    authority = reconstruction.reconstruction_authority
    assert isinstance(authority, HKLegislationReconstructionAuthority)
    affected = list(authority.affected_location_refs)
    if mutation == "reorder":
        affected.reverse()
    elif mutation == "missing":
        affected.pop()
    else:
        affected.append(affected[0])
    forged = replace(
        reconstruction,
        reconstruction_authority=replace(
            authority,
            affected_location_refs=tuple(affected),
        ),
    )

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
                forged,
            ),
            _CUTOFF,
        )


def test_reconstruction_authority_is_required_and_forbidden_on_ordinary_events() -> None:
    reconstruction = _reconstruction_event(_successful_report())
    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
                replace(reconstruction, reconstruction_authority=None),
            ),
            _CUTOFF,
        )

    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                replace(
                    publication,
                    reconstruction_authority=reconstruction.reconstruction_authority,
                )
            ),
            _CUTOFF,
        )


def test_malformed_reconstruction_authority_fault_is_normalized() -> None:
    reconstruction = _reconstruction_event(_successful_report())
    authority = reconstruction.reconstruction_authority
    assert isinstance(authority, HKLegislationReconstructionAuthority)
    object.__delattr__(authority, "engine_build_id")

    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(
            _timeline(
                _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
                reconstruction,
            ),
            _CUTOFF,
        )

    assert caught.value.code is HKLegislationEventErrorCode.EVENT_INVALID


def test_reconstruction_authority_rejects_equality_liar_primitives() -> None:
    class EqualityLiar(str):
        __slots__ = ()
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            del other
            return True

    reconstruction = _reconstruction_event(_successful_report())
    authority = reconstruction.reconstruction_authority
    assert isinstance(authority, HKLegislationReconstructionAuthority)
    forged = replace(
        reconstruction,
        reconstruction_authority=replace(
            authority,
            accepted_report_id=EqualityLiar(authority.accepted_report_id),
        ),
    )

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
                forged,
            ),
            _CUTOFF,
        )


def test_reconstruction_authority_is_snapshotted_before_report_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _successful_report()
    reconstruction = _reconstruction_event(report)
    authority = reconstruction.reconstruction_authority
    assert isinstance(authority, HKLegislationReconstructionAuthority)
    timeline = _timeline(
        _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
        reconstruction,
    )
    expected = decide_hk_legislation_state(timeline, _CUTOFF)
    real_validator = events_module.validate_reconstruction_execution_report

    def mutate_during_validation(
        package_root: Path,
        candidate: object,
    ) -> ReconstructionExecutionReport:
        object.__setattr__(authority, "accepted_report_id", "rex_" + "2" * 48)
        return real_validator(package_root, candidate)

    monkeypatch.setattr(
        events_module,
        "validate_reconstruction_execution_report",
        mutate_during_validation,
    )

    decision = decide_hk_legislation_state(timeline, _CUTOFF)

    assert decision == expected
    decision.assert_factory_issued()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", HKLegislationEventKind.EDITORIAL),
        ("source", HKLegislationEventSource.PUBLISHER),
        ("effective_at", "2026-08-25T02:00:00+00:00"),
        ("evidence_fingerprint", "sha256:" + "e" * 64),
    ],
)
def test_event_primitives_are_snapshotted_before_reentrant_report_validation(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    expected_timeline, _expected_reconstruction = _complete_reconstruction_timeline()
    expected = decide_hk_legislation_state(expected_timeline, _CUTOFF)
    timeline, reconstruction = _complete_reconstruction_timeline()
    real_validator = events_module.validate_reconstruction_execution_report

    def mutate_during_validation(
        package_root: Path,
        candidate: object,
    ) -> ReconstructionExecutionReport:
        object.__setattr__(reconstruction, field, value)
        return real_validator(package_root, candidate)

    monkeypatch.setattr(
        events_module,
        "validate_reconstruction_execution_report",
        mutate_during_validation,
    )

    decision = decide_hk_legislation_state(timeline, _CUTOFF)

    assert decision == expected
    decision.assert_factory_issued()


@pytest.mark.parametrize(
    ("field", "initial", "replacement"),
    [
        ("source_facts_complete", False, True),
        ("known_stale", True, False),
        (
            "source_contract_review",
            HKLegislationSourceContractReview.REQUIRED,
            HKLegislationSourceContractReview.NOT_REQUIRED,
        ),
    ],
)
def test_timeline_header_is_snapshotted_before_reentrant_event_validation(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    initial: object,
    replacement: object,
) -> None:
    expected_timeline, _expected_reconstruction = _reconstruction_timeline_with_header_value(
        field, initial
    )
    expected = decide_hk_legislation_state(expected_timeline, _CUTOFF)
    timeline, _reconstruction = _reconstruction_timeline_with_header_value(field, initial)
    real_validator = events_module.validate_reconstruction_execution_report

    def mutate_during_validation(
        package_root: Path,
        candidate: object,
    ) -> ReconstructionExecutionReport:
        object.__setattr__(timeline, field, replacement)
        return real_validator(package_root, candidate)

    monkeypatch.setattr(
        events_module,
        "validate_reconstruction_execution_report",
        mutate_during_validation,
    )

    decision = decide_hk_legislation_state(timeline, _CUTOFF)

    assert decision == expected
    decision.assert_factory_issued()


def test_timeline_equality_liar_and_sequence_mutation_cannot_change_captured_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EqualityLiar(str):
        __slots__ = ()
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            del other
            return True

    expected_timeline, _expected_reconstruction = _complete_reconstruction_timeline(
        source_contract_review=HKLegislationSourceContractReview.REQUIRED,
    )
    expected = decide_hk_legislation_state(expected_timeline, _CUTOFF)
    timeline, reconstruction = _complete_reconstruction_timeline(
        source_contract_review=HKLegislationSourceContractReview.REQUIRED,
    )
    real_validator = events_module.validate_reconstruction_execution_report

    def mutate_during_validation(
        package_root: Path,
        candidate: object,
    ) -> ReconstructionExecutionReport:
        object.__setattr__(
            timeline,
            "source_contract_review",
            EqualityLiar(HKLegislationSourceContractReview.NOT_REQUIRED.value),
        )
        object.__setattr__(timeline, "events", list(timeline.events))
        object.__setattr__(
            reconstruction, "basis_event_refs", list(reconstruction.basis_event_refs)
        )
        return real_validator(package_root, candidate)

    monkeypatch.setattr(
        events_module,
        "validate_reconstruction_execution_report",
        mutate_during_validation,
    )

    decision = decide_hk_legislation_state(timeline, _CUTOFF)

    assert decision == expected
    decision.assert_factory_issued()


@pytest.mark.parametrize(
    "mutation",
    [
        "kind",
        "source",
        "effective_at",
        "evidence_fingerprint",
        "equality_source",
        "basis_sequence",
    ],
)
def test_first_report_validation_cannot_repair_a_later_event(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    timeline, later, field, replacement = _later_event_repair_scenario(mutation)
    real_validator = events_module.validate_reconstruction_execution_report

    def repair_during_validation(
        package_root: Path,
        candidate: object,
    ) -> ReconstructionExecutionReport:
        object.__setattr__(later, field, replacement)
        return real_validator(package_root, candidate)

    monkeypatch.setattr(
        events_module,
        "validate_reconstruction_execution_report",
        repair_during_validation,
    )

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(timeline, _CUTOFF)


def test_two_phase_event_capture_preserves_report_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline, _reconstruction = _complete_reconstruction_timeline()

    def interrupt(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise KeyboardInterrupt

    monkeypatch.setattr(events_module, "validate_reconstruction_execution_report", interrupt)

    with pytest.raises(KeyboardInterrupt):
        decide_hk_legislation_state(timeline, _CUTOFF)


def test_reconstruction_validation_preserves_process_control_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise KeyboardInterrupt

    monkeypatch.setattr(events_module, "validate_reconstruction_execution_report", interrupt)
    with pytest.raises(KeyboardInterrupt):
        decide_hk_legislation_state(
            _timeline(
                _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
                _reconstruction_event(_successful_report()),
            ),
            _CUTOFF,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("legal_location_id", "location-invalid"),
        ("official_version_id", "version-invalid"),
    ],
)
def test_timeline_and_events_require_exact_location_and_version_id_families(
    field: str, value: str
) -> None:
    """Generic display identities cannot stand in for loc_/ofv_ authority identities."""
    timeline = _timeline(_event("evt-publication", HKLegislationEventKind.PUBLICATION))
    events = tuple(replace(event, **{field: value}) for event in timeline.events)

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(replace(timeline, events=events, **{field: value}), _CUTOFF)


def test_cross_version_reconstruction_report_never_authorizes_current_text() -> None:
    other_version = "ofv_000000000000000000000000000000000000000000000002"
    publication = replace(
        _event("evt-publication", HKLegislationEventKind.PUBLICATION),
        official_version_id=other_version,
    )
    commencement = replace(
        _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT),
        official_version_id=other_version,
    )
    amendment = replace(
        _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
        official_version_id=other_version,
    )
    reconstruction = replace(
        _reconstruction_event(_successful_report()),
        official_version_id=other_version,
    )
    timeline = replace(
        _timeline(publication, commencement, amendment, reconstruction),
        official_version_id=other_version,
    )

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(timeline, _CUTOFF)


@pytest.mark.parametrize("report_case", ["same", "competing"])
def test_one_text_event_cannot_have_two_reconstruction_results(report_case: str) -> None:
    report = _successful_report()
    if report_case == "competing":
        document = report.document()
        competing_id = "rex_000000000000000000000000000000000000000000000002"
        document["reconstruction_execution_report_id"] = competing_id
        second_report = _report_from_document(document, report_id=competing_id)
    else:
        second_report = report
    first = _reconstruction_event(report)
    second = replace(
        _reconstruction_event(second_report),
        event_ref="evt-reconstruction-2",
        event_identity="evt-reconstruction-2",
    )

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                _event("evt-publication", HKLegislationEventKind.PUBLICATION),
                _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT),
                _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
                first,
                second,
            ),
            _CUTOFF,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "artifact_record_output",
        "source_contract_review",
        "base_validation",
        "bilingual_validation",
        "coverage_disposition",
        "report_contract",
    ],
)
def test_forged_report_contract_never_authorizes_searchable_current(mutation: str) -> None:
    document = _successful_report().document()
    if mutation == "artifact_record_output":
        artifact = document["artifact_output"]
        assert isinstance(artifact, dict)
        artifact["record_output"] = "FORGED"
    elif mutation == "source_contract_review":
        document["source_contract_review_required"] = True
    elif mutation == "base_validation":
        base = document["base_validation"]
        assert isinstance(base, dict)
        base["complete"] = False
    elif mutation == "bilingual_validation":
        bilingual = document["bilingual_validation"]
        assert isinstance(bilingual, dict)
        bilingual["complete"] = False
    elif mutation == "coverage_disposition":
        coverage = document["coverage_consequence"]
        assert isinstance(coverage, dict)
        coverage["disposition"] = "EXECUTION_FAILED"
    else:
        contracts = document["contracts"]
        assert isinstance(contracts, dict)
        report_contract = contracts["report"]
        assert isinstance(report_contract, dict)
        report_contract["contract_id"] = "asklegal.forged-report"
    report = _report_from_document(document)
    amendment = _event(
        _REPORT_EVENT_REF,
        HKLegislationEventKind.AMENDMENT,
        effective_at="2026-08-25T01:00:00Z",
    )

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(
                _event("evt-publication", HKLegislationEventKind.PUBLICATION),
                _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT),
                amendment,
                _reconstruction_event(report),
            ),
            _CUTOFF,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("processing_outcome", "BLOCK"),
        ("reason_codes", ["RECONSTRUCTION_FINAL_TREE_MISMATCH"]),
        ("selection_consequence", "FALLBACK"),
        ("external_effects", "NETWORK"),
    ],
)
def test_reconstruction_rejects_non_success_report_dimensions(
    field: str,
    value: JsonValue,
) -> None:
    document = _successful_report().document()
    document[field] = value
    report = _report_from_document(document)
    amendment = _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT)

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(amendment, _reconstruction_event(report)),
            _CUTOFF,
        )


@pytest.mark.parametrize("invalid", ["report_id", "plan_id", "plan_fingerprint"])
def test_reconstruction_rejects_malformed_report_and_plan_references(invalid: str) -> None:
    document = _successful_report().document()
    if invalid == "report_id":
        document["reconstruction_execution_report_id"] = "rex_invalid"
    else:
        plan_ref = document["reconstruction_plan_ref"]
        assert isinstance(plan_ref, dict)
        plan_ref["ref_id" if invalid == "plan_id" else "fingerprint"] = "invalid"
    report = _report_from_document(document)
    amendment = _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT)

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(amendment, _reconstruction_event(report)),
            _CUTOFF,
        )


def test_reconstruction_rejects_fingerprint_and_canonical_readback_drift() -> None:
    report = _successful_report()
    bad_fingerprint = ReconstructionExecutionReport(
        report.reconstruction_execution_report_id,
        "sha256:" + "0" * 64,
        report.canonical_bytes,
    )
    noncanonical = _report_from_document(report.document(), canonical=False)
    amendment = _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT)

    for invalid in (bad_fingerprint, noncanonical):
        with pytest.raises(HKLegislationEventError):
            decide_hk_legislation_state(
                _timeline(amendment, _reconstruction_event(invalid)),
                _CUTOFF,
            )


def test_reconstruction_rejects_report_basis_and_affected_location_mismatch() -> None:
    report = _successful_report()
    other = _event("evt-other-amendment", HKLegislationEventKind.AMENDMENT)
    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(other, _reconstruction_event(report, basis_event_refs=(other.event_ref,))),
            _CUTOFF,
        )

    document = report.document()
    dependency = document["dependency_validation"]
    artifact = document["artifact_output"]
    assert isinstance(dependency, dict)
    assert isinstance(artifact, dict)
    other_location: dict[str, JsonValue] = {
        "ref_type": "LEGAL_LOCATION",
        "ref_id": "loc_000000000000000000000000000000000000000000000099",
        "fingerprint": "sha256:" + "9" * 64,
    }
    dependency["affected_location_refs"] = [other_location]
    artifact["affected_legal_location_refs"] = [other_location]
    mismatched = _report_from_document(document)
    amendment = _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT)
    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(
            _timeline(amendment, _reconstruction_event(mismatched)),
            _CUTOFF,
        )


def test_commencement_before_publication_fails_closed() -> None:
    publication = _event(
        "evt-publication",
        HKLegislationEventKind.PUBLICATION,
        effective_at="2026-08-25T01:00:00Z",
    )
    commencement = _event(
        "evt-commencement",
        HKLegislationEventKind.COMMENCEMENT,
        effective_at="2026-08-25T00:00:00Z",
    )

    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(_timeline(publication, commencement), _CUTOFF)

    assert caught.value.code.value == "HK_LEGISLATION_EVENT_TIMELINE_INVALID"


def test_cessation_before_commencement_fails_closed() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    cessation = _event(
        "evt-cessation",
        HKLegislationEventKind.CESSATION,
        effective_at="2026-08-25T01:00:00Z",
    )
    commencement = _event(
        "evt-commencement",
        HKLegislationEventKind.COMMENCEMENT,
        effective_at="2026-08-25T02:00:00Z",
    )

    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(_timeline(publication, cessation, commencement), _CUTOFF)

    assert caught.value.code.value == "HK_LEGISLATION_EVENT_TIMELINE_INVALID"


def test_repeated_commencement_while_operative_fails_closed() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    first = _event("evt-commencement-1", HKLegislationEventKind.COMMENCEMENT)
    repeated = _event(
        "evt-commencement-2",
        HKLegislationEventKind.COMMENCEMENT,
        effective_at="2026-08-25T01:00:00Z",
    )

    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(_timeline(publication, first, repeated), _CUTOFF)

    assert caught.value.code.value == "HK_LEGISLATION_EVENT_TIMELINE_INVALID"


def test_commencement_cannot_restore_state_after_cessation() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    cessation = _event(
        "evt-cessation",
        HKLegislationEventKind.CESSATION,
        effective_at="2026-08-25T01:00:00Z",
    )
    recommencement = _event(
        "evt-recommencement",
        HKLegislationEventKind.COMMENCEMENT,
        effective_at="2026-08-25T02:00:00Z",
    )

    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(
            _timeline(publication, commencement, cessation, recommencement),
            _CUTOFF,
        )

    assert caught.value.code.value == "HK_LEGISLATION_EVENT_TIMELINE_INVALID"


def test_publication_and_commencement_may_share_the_same_effective_time() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)

    decision = decide_hk_legislation_state(_timeline(commencement, publication), _CUTOFF)

    assert decision.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT


def test_same_time_cessation_and_commencement_never_return_current() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    cessation = _event("evt-cessation", HKLegislationEventKind.CESSATION)

    decision = decide_hk_legislation_state(_timeline(publication, commencement, cessation), _CUTOFF)

    assert decision.processing_outcome is HKLegislationProcessingOutcome.QUARANTINE
    assert decision.legal_disposition is HKLegislationDisposition.QUARANTINE
    assert decision.reason_code == "OFFICIAL_EVENT_CONFLICT"


def test_later_status_conflict_cannot_hide_an_earlier_invalid_sequence() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    invalid_cessation = _event(
        "evt-invalid-cessation",
        HKLegislationEventKind.CESSATION,
        effective_at="2026-08-25T01:00:00Z",
    )
    future_commencement = _event(
        "evt-future-commencement",
        HKLegislationEventKind.COMMENCEMENT,
        effective_at="2026-08-27T00:00:00Z",
    )
    future_cessation = _event(
        "evt-future-cessation",
        HKLegislationEventKind.CESSATION,
        source=HKLegislationEventSource.PUBLISHER,
        effective_at="2026-08-27T00:00:00Z",
    )

    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(
            _timeline(
                publication,
                invalid_cessation,
                future_commencement,
                future_cessation,
            ),
            _CUTOFF,
        )

    assert caught.value.code.value == "HK_LEGISLATION_EVENT_TIMELINE_INVALID"


@pytest.mark.parametrize(
    ("kind", "source"),
    [
        (HKLegislationEventKind.PUBLICATION, HKLegislationEventSource.ACCEPTED_RECONSTRUCTION),
        (HKLegislationEventKind.RECONSTRUCTION, HKLegislationEventSource.PUBLISHER),
        (HKLegislationEventKind.EDITORIAL, HKLegislationEventSource.GAZETTE),
        (HKLegislationEventKind.AMENDMENT, HKLegislationEventSource.EDITORIAL_RECORD),
    ],
)
def test_event_source_roles_cannot_be_relabelled(
    kind: HKLegislationEventKind,
    source: HKLegislationEventSource,
) -> None:
    event = _event("evt-source-mismatch", kind, source=source)
    if kind is HKLegislationEventKind.RECONSTRUCTION:
        event = replace(_reconstruction_event(_successful_report()), source=source)
        timeline = _timeline(
            _event(_REPORT_EVENT_REF, HKLegislationEventKind.AMENDMENT),
            event,
        )
    else:
        timeline = _timeline(event)

    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(timeline, _CUTOFF)

    assert caught.value.code.value == "HK_LEGISLATION_EVENT_INVALID"


def test_event_identity_must_be_globally_unique() -> None:
    publication = _event(
        "evt-publication",
        HKLegislationEventKind.PUBLICATION,
        event_identity="evt-shared-identity",
    )
    commencement = _event(
        "evt-commencement",
        HKLegislationEventKind.PUBLICATION,
        event_identity="evt-shared-identity",
    )

    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(_timeline(publication, commencement), _CUTOFF)

    assert caught.value.code.value == "HK_LEGISLATION_EVENT_TIMELINE_INVALID"


def test_correction_requires_an_exact_accepted_reconstruction_binding() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    correction = _event(
        _REPORT_EVENT_REF,
        HKLegislationEventKind.CORRECTION,
        effective_at="2026-08-25T01:00:00Z",
    )
    reconstruction = _reconstruction_event(_successful_report())

    decision = decide_hk_legislation_state(
        _timeline(publication, commencement, correction, reconstruction), _CUTOFF
    )

    assert decision.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT
    assert decision.reason_code == "OPERATIVE_CURRENT_TEXT_RECONSTRUCTED"
    assert decision.controlling_event_refs[-2:] == (correction.event_ref, reconstruction.event_ref)


def test_unbound_reconstruction_result_is_a_closed_input_failure() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    reconstruction = _reconstruction_event(
        _successful_report(),
        basis_event_refs=(),
    )

    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(_timeline(publication, commencement, reconstruction), _CUTOFF)


def test_incomplete_source_processing_never_becomes_a_legal_state_decision() -> None:
    decision = decide_hk_legislation_state(
        _timeline(
            _event("evt-publication", HKLegislationEventKind.PUBLICATION),
            source_facts_complete=False,
            source_contract_review=HKLegislationSourceContractReview.REQUIRED,
        ),
        _CUTOFF,
    )

    assert decision.processing_outcome is HKLegislationProcessingOutcome.BLOCK
    assert decision.legal_disposition is None
    assert decision.coverage_effect is HKLegislationCoverageEffect.NONE
    assert decision.source_contract_review is HKLegislationSourceContractReview.REQUIRED
    assert decision.reason_code == "SOURCE_EVENT_FACTS_INCOMPLETE"


def test_source_contract_review_is_separate_from_an_operative_legal_state() -> None:
    decision = decide_hk_legislation_state(
        _timeline(
            _event("evt-publication", HKLegislationEventKind.PUBLICATION),
            _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT),
            source_contract_review=HKLegislationSourceContractReview.REQUIRED,
        ),
        _CUTOFF,
    )

    assert decision.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT
    assert decision.source_contract_review is HKLegislationSourceContractReview.REQUIRED


def test_equality_liar_subclass_and_raw_mutation_fail_closed() -> None:
    class EqualityLiar(str):
        __slots__ = ()
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            return True

    timeline = _timeline(_event("evt-publication", HKLegislationEventKind.PUBLICATION))
    object.__setattr__(timeline, "schema_id", EqualityLiar(timeline.schema_id))
    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(timeline, _CUTOFF)

    timeline = _timeline(_event("evt-publication", HKLegislationEventKind.PUBLICATION))
    object.__setattr__(timeline, "events", list(timeline.events))
    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(timeline, _CUTOFF)

    timeline = _timeline(_event("evt-publication", HKLegislationEventKind.PUBLICATION))
    object.__delattr__(timeline, "events")
    with pytest.raises(HKLegislationEventError):
        decide_hk_legislation_state(timeline, _CUTOFF)


def test_decision_is_detached_and_exact_replay_is_deterministic() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)
    timeline = _timeline(publication, commencement)
    first = decide_hk_legislation_state(timeline, _CUTOFF)
    replay = decide_hk_legislation_state(timeline, _CUTOFF)

    assert replay == first
    object.__setattr__(publication, "kind", HKLegislationEventKind.CESSATION)
    assert first.legal_disposition is HKLegislationDisposition.SEARCHABLE_CURRENT
    assert first.controlling_event_refs == ("evt-publication", "evt-commencement")


def test_reordered_equivalent_timeline_has_one_canonical_replay_result() -> None:
    publication = _event("evt-publication", HKLegislationEventKind.PUBLICATION)
    commencement = _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT)

    first = decide_hk_legislation_state(_timeline(publication, commencement), _CUTOFF)
    reordered = decide_hk_legislation_state(_timeline(commencement, publication), _CUTOFF)

    assert reordered == first


def test_decision_direct_construction_replacement_and_mutation_are_not_factory_issued() -> None:
    issued = decide_hk_legislation_state(
        _timeline(
            _event("evt-publication", HKLegislationEventKind.PUBLICATION),
            _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT),
        ),
        _CUTOFF,
    )
    issued.assert_factory_issued()
    direct = HKLegislationEventDecision(
        issued.legal_location_id,
        issued.official_version_id,
        issued.processing_outcome,
        issued.legal_disposition,
        issued.coverage_effect,
        issued.source_contract_review,
        issued.reason_code,
        issued.controlling_event_refs,
        issued.unresolved_fact_codes,
        issued.timeline_fingerprint,
    )
    with pytest.raises(HKLegislationEventError):
        direct.assert_factory_issued()
    replaced = replace(issued, reason_code="FORGED_REASON")
    with pytest.raises(HKLegislationEventError):
        replaced.assert_factory_issued()
    object.__setattr__(issued, "legal_disposition", HKLegislationDisposition.HISTORICAL)
    with pytest.raises(HKLegislationEventError):
        issued.assert_factory_issued()


def test_invalid_calendar_cutoff_is_closed_before_event_evaluation() -> None:
    with pytest.raises(HKLegislationEventError) as caught:
        decide_hk_legislation_state(
            _timeline(_event("evt-publication", HKLegislationEventKind.PUBLICATION)),
            "2026-99-99T99:99:99Z",
        )

    assert caught.value.code.value == "HK_LEGISLATION_EVENT_CUTOFF_INVALID"


def test_no_provider_or_network_capability_is_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_socket(*_args: object, **_kwargs: object) -> socket.socket:
        message = "network forbidden"
        raise AssertionError(message)

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    decision = decide_hk_legislation_state(
        _timeline(
            _event("evt-publication", HKLegislationEventKind.PUBLICATION),
            _event("evt-commencement", HKLegislationEventKind.COMMENCEMENT),
        ),
        _CUTOFF,
    )
    assert decision.processing_outcome is HKLegislationProcessingOutcome.PASS


def test_process_control_base_exception_is_not_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InterruptingDateTime:
        @classmethod
        def strptime(cls, value: str, date_format: str) -> InterruptingDateTime:
            del cls, value, date_format
            raise KeyboardInterrupt

    monkeypatch.setattr(events_module, "datetime", InterruptingDateTime)
    with pytest.raises(KeyboardInterrupt):
        decide_hk_legislation_state(
            _timeline(_event("evt-publication", HKLegislationEventKind.PUBLICATION)), _CUTOFF
        )


def test_acquired_event_facts_bind_evidence_without_inferring_legal_effect() -> None:
    """Acquisition refs cross into the Desk before any event or disposition decision."""
    facts = bind_hk_legislation_acquired_event_facts(
        ("legislation-item/gld-event/" + "a" * 64,),
        ("hkel-structure/ROOT_LANGUAGE/2",),
    )

    assert type(facts) is HKLegislationAcquiredEventFacts
    assert facts.verified_item_refs == ("legislation-item/gld-event/" + "a" * 64,)
    assert not hasattr(facts, "legal_disposition")
    assert not hasattr(facts, "effective_at")


def test_acquired_event_facts_reject_duplicate_or_unsorted_refs() -> None:
    """The source-fact boundary is canonical and cannot hide duplicate evidence."""
    with pytest.raises(HKLegislationEventError):
        bind_hk_legislation_acquired_event_facts(("ref/b", "ref/a"), ())
    with pytest.raises(HKLegislationEventError):
        bind_hk_legislation_acquired_event_facts(("ref/a", "ref/a"), ())
