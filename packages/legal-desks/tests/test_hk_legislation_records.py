"""Source-neutral Hong Kong legislation candidate/accounting proofs."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_legal_desks.hk_legislation_events import (
    HKLegislationDisposition,
    HKLegislationEvent,
    HKLegislationEventKind,
    HKLegislationEventSource,
    HKLegislationEventTimeline,
    HKLegislationSourceContractReview,
    decide_hk_legislation_state,
)
from asklegal_legal_desks.hk_legislation_partition import (
    BilingualPartitionResult,
    BilingualServingPart,
    PartitionDisposition,
    PartitionMeasurement,
    PartitionReason,
)
from asklegal_legal_desks.hk_legislation_records import (
    HKLegislationAuthorityNoteSeed,
    HKLegislationCandidateInput,
    HKLegislationInventoryDecisionAuthority,
    HKLegislationRecordError,
    HKLegislationRecordErrorCode,
    HKLegislationServingPayload,
    HKLegislationTraceabilityReference,
    bind_hk_legislation_inventory_decision_authority,
    build_hk_legislation_candidate_set,
    canonical_hk_legislation_candidate_set,
    hk_legislation_candidate_set_from_bytes,
    replay_hk_legislation_candidate_set,
    validate_hk_legislation_partition_for_record_candidate,
)

CUTOFF = "2026-08-27T00:00:00Z"
LOCATION = "loc_" + "1" * 48
VERSION = "ofv_" + "2" * 48
ITEM = "lit_" + "3" * 48
SCOPE = "HK-LEG-ORDINANCES"


def _fp(value: str) -> str:
    return "sha256:" + sha256(value.encode()).hexdigest()


def test_retained_candidate_set_reissues_after_restart_and_rejects_drift() -> None:
    """Canonical retained output does not depend on the old weakref issuance entry."""
    issued = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE,
        observation_cutoff=CUTOFF,
        inputs=(_input("inventory-retained"),),
    )
    content = canonical_hk_legislation_candidate_set(issued)

    restarted = hk_legislation_candidate_set_from_bytes(content)

    assert restarted is not issued
    assert replay_hk_legislation_candidate_set(restarted).outcomes == issued.outcomes
    with pytest.raises(HKLegislationRecordError) as caught:
        hk_legislation_candidate_set_from_bytes(content.replace(b'"scope"', b'"sc0pe"'))
    assert caught.value.code is HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID


def _ref(ref_type: str, prefix: str, digit: str) -> HKLegislationTraceabilityReference:
    return HKLegislationTraceabilityReference(
        ref_type, prefix + "_" + digit * 48, "sha256:" + digit * 64
    )


def _decision(kind: str = "current"):
    events = (
        HKLegislationEvent(
            "event-publication",
            "event-publication",
            LOCATION,
            VERSION,
            HKLegislationEventKind.PUBLICATION,
            HKLegislationEventSource.GAZETTE,
            "2026-08-25T00:00:00Z",
            "sha256:" + "a" * 64,
            (),
            None,
        ),
    )
    if kind == "current":
        events += (
            HKLegislationEvent(
                "event-commencement",
                "event-commencement",
                LOCATION,
                VERSION,
                HKLegislationEventKind.COMMENCEMENT,
                HKLegislationEventSource.GAZETTE,
                "2026-08-26T00:00:00Z",
                "sha256:" + "b" * 64,
                (),
                None,
            ),
        )
    elif kind == "historical":
        events += (
            HKLegislationEvent(
                "event-commencement",
                "event-commencement",
                LOCATION,
                VERSION,
                HKLegislationEventKind.COMMENCEMENT,
                HKLegislationEventSource.GAZETTE,
                "2026-08-26T00:00:00Z",
                "sha256:" + "b" * 64,
                (),
                None,
            ),
            HKLegislationEvent(
                "event-cessation",
                "event-cessation",
                LOCATION,
                VERSION,
                HKLegislationEventKind.CESSATION,
                HKLegislationEventSource.GAZETTE,
                "2026-08-26T12:00:00Z",
                "sha256:" + "c" * 64,
                (),
                None,
            ),
        )
    elif kind == "evidence":
        events += (
            HKLegislationEvent(
                "event-amendment",
                "event-amendment",
                LOCATION,
                VERSION,
                HKLegislationEventKind.AMENDMENT,
                HKLegislationEventSource.GAZETTE,
                "2026-08-26T12:00:00Z",
                "sha256:" + "c" * 64,
                (),
                None,
            ),
            HKLegislationEvent(
                "event-commencement",
                "event-commencement",
                LOCATION,
                VERSION,
                HKLegislationEventKind.COMMENCEMENT,
                HKLegislationEventSource.GAZETTE,
                "2026-08-26T00:00:00Z",
                "sha256:" + "b" * 64,
                (),
                None,
            ),
        )
    return decide_hk_legislation_state(
        HKLegislationEventTimeline(
            schema_id="asklegal.hk-legislation-event-timeline",
            schema_version="1.0.0",
            legal_location_id=LOCATION,
            official_version_id=VERSION,
            source_facts_complete=True,
            known_stale=False,
            source_contract_review=HKLegislationSourceContractReview.NOT_REQUIRED,
            events=events,
        ),
        CUTOFF,
    )


def _partition(
    disposition: PartitionDisposition = PartitionDisposition.PASS,
) -> BilingualPartitionResult:
    text = "[English — Authentic Text]\nText\n\n[繁體中文 — 真確文本]\n文本"
    payload = {
        "authority_note": "None",
        "country": "Hong Kong",
        "jurisdiction": "Hong Kong",
        "source": "HKeL",
        "text": text,
        "type": "Legislation",
    }
    payload_bytes = canonicalize(checked_json_value(payload))
    part = BilingualServingPart(
        1,
        1,
        ("node-1",),
        ("alignment-1",),
        (),
        ("en-unit",),
        ("zh-unit",),
        (),
        (),
        text,
        _fp(text),
        "sha256:" + sha256(payload_bytes).hexdigest(),
        PartitionMeasurement(10, len(payload_bytes), 100, 1000),
    )
    raw = BilingualPartitionResult(
        disposition,
        PartitionReason.PASS_UNSPLIT
        if disposition is PartitionDisposition.PASS
        else PartitionReason.BILINGUAL_ALIGNMENT_MISMATCH,
        (part,) if disposition is PartitionDisposition.PASS else (),
        ("node-1",) if disposition is not PartitionDisposition.PASS else (),
        disposition is not PartitionDisposition.PASS,
        "srp_" + "4" * 48,
        "sha256:" + "4" * 64,
        "sha256:" + "5" * 64,
        "sha256:" + "6" * 64,
        "sha256:" + "7" * 64,
        b"",
        "",
    )
    canonical = canonicalize(checked_json_value(raw.document()))
    return replace(
        raw, canonical_bytes=canonical, fingerprint="sha256:" + sha256(canonical).hexdigest()
    )


def _input(
    item: str, *, state: str = "current", partition: BilingualPartitionResult | None = None
) -> HKLegislationCandidateInput:
    decision = _decision(state)
    note = "None"
    decision_ref = _ref("DECISION", "dec", "9")
    evidence = _ref("EVIDENCE", "evi", "a")
    return HKLegislationCandidateInput(
        item,
        SCOPE,
        ITEM,
        (VERSION,),
        (LOCATION,),
        decision,
        _partition() if partition is None and state == "current" else partition,
        HKLegislationServingPayload("Hong Kong", "Hong Kong", "Legislation", "HKeL", note),
        "art_" + "b" * 48,
        (evidence,),
        HKLegislationAuthorityNoteSeed(_fp(note), decision_ref, ()),
    )


def _coherently_reseal_candidate_payload(
    candidate: HKLegislationCandidateInput,
    *,
    text: str | None = None,
    **serving_payload_changes: str,
) -> HKLegislationCandidateInput:
    """Create an independently resealed caller payload for direct-boundary tests."""
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    part = partition.parts[0]
    rendered_text = part.text if text is None else text
    payload = replace(candidate.serving_payload, **serving_payload_changes)
    metadata = {
        "authority_note": payload.authority_note,
        "country": payload.country,
        "jurisdiction": payload.jurisdiction,
        "source": payload.source,
        "text": rendered_text,
        "type": payload.material_type,
    }
    payload_bytes = canonicalize(checked_json_value(metadata))
    altered_part = replace(
        part,
        text=rendered_text,
        text_fingerprint=_fp(rendered_text),
        serving_payload_fingerprint="sha256:" + sha256(payload_bytes).hexdigest(),
        measurement=replace(part.measurement, metadata_bytes=len(payload_bytes)),
    )
    altered = replace(partition, parts=(altered_part,))
    canonical = canonicalize(checked_json_value(altered.document()))
    return replace(
        candidate,
        serving_payload=payload,
        partition_result=replace(
            altered,
            canonical_bytes=canonical,
            fingerprint="sha256:" + sha256(canonical).hexdigest(),
        ),
    )


def test_searchable_current_without_admitted_binding_authority_is_withheld() -> None:
    result = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE, observation_cutoff=CUTOFF, inputs=(_input("inventory-1"),)
    )
    assert result.drafts == ()
    assert result.outcomes[0].outcome_kind == "QUARANTINE"
    assert result.outcomes[0].reason_code == "BINDING_AUTHORITY_MISSING"


def _authority_bound_input(inventory_item_id: str) -> HKLegislationCandidateInput:
    candidate = _input(inventory_item_id)
    decision_ref = replace(
        candidate.authority_note_evidence.decision_ref,
        fingerprint=candidate.event_decision.decision_fingerprint,
    )
    candidate = replace(
        candidate,
        authority_note_evidence=replace(
            candidate.authority_note_evidence,
            decision_ref=decision_ref,
        ),
    )
    authority = bind_hk_legislation_inventory_decision_authority(candidate)
    return replace(candidate, decision_authority=authority)


def test_desk_bound_searchable_current_emits_exact_partition_draft() -> None:
    candidate = _authority_bound_input("current-bound")

    result = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE,
        observation_cutoff=CUTOFF,
        inputs=(candidate,),
    )

    assert len(result.drafts) == 1
    assert result.outcomes[0].outcome_kind == "EMITTED"
    assert result.outcomes[0].draft_keys == (result.drafts[0].candidate_key,)
    assert result.drafts[0].decision_fingerprint == candidate.event_decision.decision_fingerprint


def test_caller_constructed_or_cross_inventory_authority_cannot_emit() -> None:
    bound = _authority_bound_input("bound-owner")
    authority = bound.decision_authority
    assert authority is not None
    forged = HKLegislationInventoryDecisionAuthority(
        authority.inventory_item_id,
        authority.legislation_scope_code,
        authority.legal_item_id,
        authority.official_version_ids,
        authority.legal_location_ids,
        authority.decision_fingerprint,
        authority.evidence_refs,
    )
    with pytest.raises(HKLegislationRecordError):
        build_hk_legislation_candidate_set(
            legislation_scope_code=SCOPE,
            observation_cutoff=CUTOFF,
            inputs=(replace(bound, decision_authority=forged),),
        )
    with pytest.raises(HKLegislationRecordError):
        build_hk_legislation_candidate_set(
            legislation_scope_code=SCOPE,
            observation_cutoff=CUTOFF,
            inputs=(replace(_input("different-inventory"), decision_authority=authority),),
        )


def test_every_inventory_member_has_exactly_one_of_five_outcomes() -> None:
    result = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE,
        observation_cutoff=CUTOFF,
        inputs=(
            _input("current"),
            _input("waiting", state="waiting"),
            _input("evidence", state="evidence"),
            _input("history", state="historical"),
            _input("quarantine", partition=_partition(PartitionDisposition.QUARANTINE)),
        ),
    )
    assert {outcome.inventory_item_id for outcome in result.outcomes} == {
        "current",
        "waiting",
        "evidence",
        "history",
        "quarantine",
    }
    assert {outcome.outcome_kind for outcome in result.outcomes} == {
        "WAITING_ROOM",
        "EVIDENCE_ONLY",
        "HISTORICAL",
        "QUARANTINE",
    }
    assert (
        next(
            outcome for outcome in result.outcomes if outcome.inventory_item_id == "current"
        ).reason_code
        == "BINDING_AUTHORITY_MISSING"
    )


def test_searchable_current_with_nonpass_partition_is_quarantined_not_emitted() -> None:
    result = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE,
        observation_cutoff=CUTOFF,
        inputs=(_input("quarantine", partition=_partition(PartitionDisposition.QUARANTINE)),),
    )
    assert result.drafts == ()
    assert result.outcomes[0].outcome_kind == "QUARANTINE"


def test_directly_constructed_event_decision_is_rejected() -> None:
    forged = _decision()
    object.__setattr__(forged, "decision_fingerprint", "sha256:" + "0" * 64)
    candidate = replace(_input("forged"), event_decision=forged)
    with pytest.raises(HKLegislationRecordError) as caught:
        build_hk_legislation_candidate_set(
            legislation_scope_code=SCOPE, observation_cutoff=CUTOFF, inputs=(candidate,)
        )
    assert caught.value.code is HKLegislationRecordErrorCode.DECISION_INVALID


def test_exact_input_container_and_subclass_are_rejected() -> None:
    class CandidateInputSubclass(HKLegislationCandidateInput):
        pass

    candidate = _input("exact-class")
    with pytest.raises(HKLegislationRecordError) as list_caught:
        build_hk_legislation_candidate_set(
            legislation_scope_code=SCOPE,
            observation_cutoff=CUTOFF,
            inputs=[candidate],
        )
    with pytest.raises(HKLegislationRecordError) as subclass_caught:
        build_hk_legislation_candidate_set(
            legislation_scope_code=SCOPE,
            observation_cutoff=CUTOFF,
            inputs=(
                CandidateInputSubclass(
                    candidate.inventory_item_id,
                    candidate.legislation_scope_code,
                    candidate.legal_item_id,
                    candidate.official_version_ids,
                    candidate.legal_location_ids,
                    candidate.event_decision,
                    candidate.partition_result,
                    candidate.serving_payload,
                    candidate.artifact_ref,
                    candidate.evidence_refs,
                    candidate.authority_note_evidence,
                ),
            ),
        )
    assert list_caught.value.code is HKLegislationRecordErrorCode.INVENTORY_ACCOUNTING_INVALID
    assert subclass_caught.value.code is HKLegislationRecordErrorCode.INVENTORY_ACCOUNTING_INVALID


def test_replay_is_deterministic_and_returned_candidate_set_is_detached() -> None:
    candidate = _input("replay")
    first = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE, observation_cutoff=CUTOFF, inputs=(candidate,)
    )
    second = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE, observation_cutoff=CUTOFF, inputs=(candidate,)
    )
    object.__setattr__(candidate.serving_payload, "source", "forged")
    object.__setattr__(candidate.evidence_refs[0], "ref_id", "evi_" + "f" * 48)
    assert first == second
    assert first.outcomes[0].supporting_refs[0].ref_id == "evi_" + "a" * 48


@pytest.mark.parametrize("mode", ["permanent", "transient"])
def test_candidate_replay_rejects_same_byte_scope_callback_before_it_can_mutate_outcome(
    mode: str,
) -> None:
    """Replay must not convert a caller-owned scope after issuance validation."""
    issued = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE, observation_cutoff=CUTOFF, inputs=(_input("reentrant"),)
    )
    original_outcomes = issued.outcomes
    original = original_outcomes[0]
    changed = replace(
        original,
        legal_disposition=HKLegislationDisposition.WAITING_ROOM,
        outcome_kind="WAITING_ROOM",
        reason_code="COMMENCEMENT_NOT_PROVED",
    )

    class ReentrantScope(str):
        __slots__ = ()

        def __str__(self) -> str:
            object.__setattr__(issued, "outcomes", (changed,))
            if mode == "transient":
                object.__setattr__(issued, "outcomes", original_outcomes)
            return str.__str__(self)

    object.__setattr__(issued, "legislation_scope_code", ReentrantScope(SCOPE))
    with pytest.raises(HKLegislationRecordError) as caught:
        replay_hk_legislation_candidate_set(issued)
    assert caught.value.code is HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID
    assert issued.outcomes == original_outcomes


def test_self_rehashed_partition_never_authorizes_a_current_record() -> None:
    """A caller-owned partition hash cannot replace missing binding authority."""
    candidate = _input("bound")
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    reconstructed = replace(
        candidate,
        partition_result=replace(partition, canonical_bytes=b"replaced"),
    )
    result = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE,
        observation_cutoff=CUTOFF,
        inputs=(reconstructed,),
    )
    assert result.drafts == ()
    assert result.outcomes[0].reason_code == "BINDING_AUTHORITY_MISSING"


def test_part_total_cannot_create_an_emitted_candidate_without_authority() -> None:
    """Changing a self-rehashed part total cannot create a record candidate."""
    candidate = _input("parts")
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    original = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE, observation_cutoff=CUTOFF, inputs=(candidate,)
    )
    part = partition.parts[0]
    altered_part = replace(part, total_parts=2)
    altered_partition = replace(partition, parts=(altered_part,))
    canonical = canonicalize(checked_json_value(altered_partition.document()))
    altered = replace(
        candidate,
        partition_result=replace(
            altered_partition,
            canonical_bytes=canonical,
            fingerprint="sha256:" + sha256(canonical).hexdigest(),
        ),
    )
    result = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE, observation_cutoff=CUTOFF, inputs=(altered,)
    )
    assert original.drafts == result.drafts == ()


def test_semantic_partition_replay_rejects_an_over_limit_self_rehashed_part() -> None:
    """A recomputed caller hash cannot make a measured over-limit part servable."""
    candidate = _input("limit")
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    part = partition.parts[0]
    over_limit = replace(part, measurement=replace(part.measurement, text_tokens=101))
    changed = replace(partition, parts=(over_limit,))
    canonical = canonicalize(checked_json_value(changed.document()))
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(
            replace(
                candidate,
                partition_result=replace(
                    changed,
                    canonical_bytes=canonical,
                    fingerprint="sha256:" + sha256(canonical).hexdigest(),
                ),
            )
        )
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE


def test_semantic_partition_replay_rejects_resealed_zero_metadata_bytes() -> None:
    """Declared metadata bytes must equal the independently canonicalized payload."""
    candidate = _input("metadata-bytes")
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    part = partition.parts[0]
    payload = {
        "authority_note": "None",
        "country": "Hong Kong",
        "jurisdiction": "Hong Kong",
        "source": "HKeL",
        "text": part.text,
        "type": "Legislation",
    }
    assert len(canonicalize(checked_json_value(payload))) == 198
    altered_part = replace(part, measurement=PartitionMeasurement(0, 0, 1, 1))
    altered = replace(partition, parts=(altered_part,))
    canonical = canonicalize(checked_json_value(altered.document()))
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(
            replace(
                candidate,
                partition_result=replace(
                    altered,
                    canonical_bytes=canonical,
                    fingerprint="sha256:" + sha256(canonical).hexdigest(),
                ),
            )
        )
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE


@pytest.mark.parametrize(
    "field",
    ["country", "jurisdiction", "material_type", "source", "authority_note"],
)
def test_semantic_partition_replay_rejects_each_empty_resealed_serving_field(
    field: str,
) -> None:
    """A coherent caller digest cannot make an empty required metadata field servable."""
    candidate = _coherently_reseal_candidate_payload(_input(f"empty-{field}"), **{field: ""})
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(candidate)
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("country", " Hong Kong"),
        ("jurisdiction", "Hong Kong "),
        ("material_type", " Legislation "),
        ("source", " HKeL "),
        ("authority_note", " None "),
    ],
)
def test_semantic_partition_replay_rejects_trimmed_resealed_serving_field_drift(
    field: str, value: str
) -> None:
    """A caller must not make metadata meaningful by silently trimming it."""
    candidate = _coherently_reseal_candidate_payload(_input(f"trim-{field}"), **{field: value})
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(candidate)
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE


def test_semantic_partition_replay_rejects_trimmed_resealed_part_text() -> None:
    """The emitted final text cannot have caller-provided outer whitespace."""
    candidate = _input("trim-text")
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    altered = _coherently_reseal_candidate_payload(candidate, text=f" {partition.parts[0].text}")
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(altered)
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE


@pytest.mark.parametrize("field", ["source", "authority_note", "text"])
def test_semantic_partition_replay_normalizes_unpaired_surrogate(field: str) -> None:
    """Invalid Unicode must close as the public partition error, never leak contracts."""
    candidate = _input(f"surrogate-{field}")
    if field == "text":
        partition = candidate.partition_result
        assert type(partition) is BilingualPartitionResult
        candidate = replace(
            candidate,
            partition_result=replace(
                partition, parts=(replace(partition.parts[0], text="\ud800"),)
            ),
        )
    else:
        candidate = replace(
            candidate, serving_payload=replace(candidate.serving_payload, **{field: "\ud800"})
        )
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(candidate)
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE


@pytest.mark.parametrize("field", ["profile_id", "partition_node", "en_source_unit"])
def test_semantic_partition_replay_normalizes_outer_partition_surrogates(field: str) -> None:
    """Non-serving partition facts must use the public closed partition error too."""
    candidate = _input(f"outer-surrogate-{field}")
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    part = partition.parts[0]
    if field == "profile_id":
        altered = replace(partition, profile_id="\ud800")
    elif field == "partition_node":
        altered = replace(partition, parts=(replace(part, primary_partition_node_ids=("\ud800",)),))
    else:
        altered = replace(partition, parts=(replace(part, en_primary_source_unit_ids=("\ud800",)),))
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(
            replace(candidate, partition_result=altered)
        )
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE


def test_candidate_replay_normalizes_unpaired_outcome_reference() -> None:
    """Outcome-reference canonicalization cannot leak a contract-owned exception."""
    issued = build_hk_legislation_candidate_set(
        legislation_scope_code=SCOPE, observation_cutoff=CUTOFF, inputs=(_input("outcome-ref"),)
    )
    outcome = issued.outcomes[0]
    object.__setattr__(
        issued,
        "outcomes",
        (
            replace(
                outcome,
                supporting_refs=(replace(outcome.supporting_refs[0], ref_type="\ud800"),),
            ),
        ),
    )
    with pytest.raises(HKLegislationRecordError) as caught:
        replay_hk_legislation_candidate_set(issued)
    assert caught.value.code is HKLegislationRecordErrorCode.CANDIDATE_ISSUANCE_INVALID


def test_semantic_partition_replay_rejects_a_resealed_payload_fingerprint_lie() -> None:
    """A well-shaped caller payload fingerprint cannot replace six-field proof."""
    candidate = _input("payload-lie")
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    part = partition.parts[0]
    altered = replace(
        partition, parts=(replace(part, serving_payload_fingerprint="sha256:" + "f" * 64),)
    )
    canonical = canonicalize(checked_json_value(altered.document()))
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(
            replace(
                candidate,
                partition_result=replace(
                    altered,
                    canonical_bytes=canonical,
                    fingerprint="sha256:" + sha256(canonical).hexdigest(),
                ),
            )
        )
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE


def test_semantic_partition_replay_rejects_a_resealed_profile_string_subclass() -> None:
    """A profile ID subclass cannot enter the future positive partition guard."""

    class ProfileIdSubclass(str):
        __slots__ = ()

    candidate = _input("profile-subclass")
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    altered = replace(partition, profile_id=ProfileIdSubclass(partition.profile_id))
    canonical = canonicalize(checked_json_value(altered.document()))
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(
            replace(
                candidate,
                partition_result=replace(
                    altered,
                    canonical_bytes=canonical,
                    fingerprint="sha256:" + sha256(canonical).hexdigest(),
                ),
            )
        )
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE


def test_semantic_partition_replay_rejects_a_resealed_profile_fingerprint_subclass() -> None:
    """A profile fingerprint subclass cannot enter the future positive guard."""

    class ProfileFingerprintSubclass(str):
        __slots__ = ()

    candidate = _input("profile-fingerprint-subclass")
    partition = candidate.partition_result
    assert type(partition) is BilingualPartitionResult
    altered = replace(
        partition,
        profile_fingerprint=ProfileFingerprintSubclass(partition.profile_fingerprint),
    )
    canonical = canonicalize(checked_json_value(altered.document()))
    with pytest.raises(HKLegislationRecordError) as caught:
        validate_hk_legislation_partition_for_record_candidate(
            replace(
                candidate,
                partition_result=replace(
                    altered,
                    canonical_bytes=canonical,
                    fingerprint="sha256:" + sha256(canonical).hexdigest(),
                ),
            )
        )
    assert caught.value.code is HKLegislationRecordErrorCode.PARTITION_NOT_SERVABLE
