"""Source-neutral candidate-to-corpus release mapping proofs."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, fields, replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import (
    AuthorityNoteEvidence,
    CorpusRelease,
    DesiredStateInventory,
    FlattenedRecord,
    RecordTraceabilityLookup,
    RecordTraceabilityLookupInput,
    ReleaseRecordEntry,
    ServingRecord,
    ServingRecordProfile,
    TraceabilityEntry,
    TraceabilityReference,
    TraceabilityScopeShardInput,
    TraceabilityShard,
    serving_payload_fingerprint,
)
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import LocalImmutableVault, VaultName
from asklegal_legal_desks.hk_legislation_events import (
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
    HKLegislationCandidateSet,
    HKLegislationInventoryOutcome,
    HKLegislationServingPayload,
    HKLegislationTraceabilityReference,
    bind_hk_legislation_inventory_decision_authority,
    build_hk_legislation_candidate_set,
    canonical_hk_legislation_candidate_set,
    hk_legislation_candidate_set_from_bytes,
)
from asklegal_legal_processing_worker.hk_legislation_release import (
    _CAPTURE_PROJECTION_FIELDS,
    HKLegislationAcquisitionReleaseInput,
    HKLegislationAllocatedIdentitySet,
    HKLegislationDownstreamPorts,
    HKLegislationRecordAllocation,
    HKLegislationReleaseError,
    HKLegislationReleaseErrorCode,
    HKLegislationReleaseSet,
    HKLegislationReleaseSetRequest,
    HKLegislationScopeReleaseRequest,
    HKLegislationScopeReleaseResult,
    _AllocatedIdentitySetSnapshot,
    _AuthorityNoteEvidenceSnapshot,
    _CorpusReleaseSnapshot,
    _DesiredStateSnapshot,
    _FlattenedRecordSnapshot,
    _HKLegislationTraceabilityReferenceSnapshot,
    _OutcomeSnapshot,
    _RecordTraceabilityLookupSnapshot,
    _ReleaseRecordEntrySnapshot,
    _ReleaseSetSnapshot,
    _ScopeResultSnapshot,
    _ServingRecordProfileSnapshot,
    _ServingRecordSnapshot,
    _TraceabilityEntrySnapshot,
    _TraceabilityReferenceSnapshot,
    _TraceabilityShardSnapshot,
    accept_hk_legislation_acquisition_manifest,
    build_hk_legislation_scope_release,
    freeze_hk_legislation_release_set,
    route_hk_legislation_acquisition_input,
)
from asklegal_legal_processing_worker.v1_pipeline import build_activities

CUTOFF = "2026-08-27T00:00:00Z"
SCOPE = "HK-LEG-ORDINANCES"
LOCATION = "loc_" + "1" * 48
VERSION = "ofv_" + "2" * 48


def _acquisition_manifest(result: str = "COMPLETE", *, extra: bool = False) -> bytes:
    scope_result = "NO_CHANGE" if result == "NO_CHANGE" else "COMPLETE"
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.legislation-acquisition-manifest",
        "schema_version": "1.0.0",
        "cycle_id": "cyc_20260904_legislation",
        "observation_cutoff": "2026-09-04T00:00:00+00:00",
        "scope_dispositions": [
            {
                "scope_id": scope,
                "required_item_count": 1,
                "verified_item_count": 1,
                "retryable_item_count": 0,
                "rejected_item_count": 0,
                "result": scope_result,
            }
            for scope in (
                "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                "HK-LEG-ORDINANCES",
                "HK-LEG-SUBSIDIARY",
            )
        ],
        "verified_item_refs": ["legislation-item/source-00/" + "a" * 64],
        "review_issue_refs": ["hkel-structure/ROOT_LANGUAGE/2"],
        "journal_head_fingerprint": "sha256:" + "b" * 64,
        "source_register_fingerprint": "sha256:" + "c" * 64,
        "source_baseline_fingerprint": "sha256:" + "d" * 64,
        "work_plan_fingerprint": "sha256:" + "e" * 64,
        "result": result,
    }
    fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
    document: dict[str, JsonValue] = {**body, "fingerprint": fingerprint}
    if extra:
        document["unexpected"] = True
    return canonicalize(checked_json_value(document))


def _input(inventory_item_id: str, scope: str = SCOPE) -> HKLegislationCandidateInput:
    decision = decide_hk_legislation_state(
        HKLegislationEventTimeline(
            schema_id="asklegal.hk-legislation-event-timeline",
            schema_version="1.0.0",
            legal_location_id=LOCATION,
            official_version_id=VERSION,
            source_facts_complete=True,
            known_stale=False,
            source_contract_review=HKLegislationSourceContractReview.NOT_REQUIRED,
            events=(
                HKLegislationEvent(
                    "publication",
                    "publication",
                    LOCATION,
                    VERSION,
                    HKLegislationEventKind.PUBLICATION,
                    HKLegislationEventSource.GAZETTE,
                    "2026-08-25T00:00:00Z",
                    "sha256:" + "a" * 64,
                    (),
                    None,
                ),
                HKLegislationEvent(
                    "commencement",
                    "commencement",
                    LOCATION,
                    VERSION,
                    HKLegislationEventKind.COMMENCEMENT,
                    HKLegislationEventSource.GAZETTE,
                    "2026-08-26T00:00:00Z",
                    "sha256:" + "b" * 64,
                    (),
                    None,
                ),
            ),
        ),
        CUTOFF,
    )
    text = "English\n\n中文"
    payload = {
        "authority_note": "None",
        "country": "Hong Kong",
        "jurisdiction": "Hong Kong",
        "source": "HKeL",
        "text": text,
        "type": "Legislation",
    }
    part = BilingualServingPart(
        1,
        1,
        ("node",),
        ("alignment",),
        (),
        ("en",),
        ("zh",),
        (),
        (),
        text,
        "sha256:" + sha256(text.encode()).hexdigest(),
        "sha256:" + sha256(canonicalize(checked_json_value(payload))).hexdigest(),
        PartitionMeasurement(
            1,
            len(canonicalize(checked_json_value(payload))),
            2,
            40_000,
        ),
    )
    raw_partition = BilingualPartitionResult(
        disposition=PartitionDisposition.PASS,
        reason=PartitionReason.PASS_UNSPLIT,
        parts=(part,),
        quarantined_partition_node_ids=(),
        coverage_gap_required=False,
        profile_id="srp_" + "4" * 48,
        profile_fingerprint="sha256:" + "4" * 64,
        en_tree_fingerprint="sha256:" + "5" * 64,
        zh_hant_tree_fingerprint="sha256:" + "6" * 64,
        alignment_map_fingerprint="sha256:" + "7" * 64,
        canonical_bytes=b"",
        fingerprint="",
    )
    canonical = canonicalize(checked_json_value(raw_partition.document()))
    partition = __import__("dataclasses").replace(
        raw_partition,
        canonical_bytes=canonical,
        fingerprint="sha256:" + sha256(canonical).hexdigest(),
    )
    decision_ref = HKLegislationTraceabilityReference(
        "DECISION", "dec_" + "9" * 48, "sha256:" + "9" * 64
    )
    evidence = HKLegislationTraceabilityReference(
        "EVIDENCE", "evi_" + "a" * 48, "sha256:" + "a" * 64
    )
    return HKLegislationCandidateInput(
        inventory_item_id,
        scope,
        "lit_" + "3" * 48,
        (VERSION,),
        (LOCATION,),
        decision,
        partition,
        HKLegislationServingPayload("Hong Kong", "Hong Kong", "Legislation", "HKeL", "None"),
        "art_" + "b" * 48,
        (evidence,),
        HKLegislationAuthorityNoteSeed(
            "sha256:" + __import__("hashlib").sha256(b"None").hexdigest(), decision_ref, ()
        ),
    )


def _candidate_set(scope: str = SCOPE) -> HKLegislationCandidateSet:
    return build_hk_legislation_candidate_set(
        legislation_scope_code=scope,
        observation_cutoff=CUTOFF,
        inputs=(_input("inventory-1", scope),),
    )


def _positive_candidate_set(scope: str = SCOPE) -> HKLegislationCandidateSet:
    item = _input("inventory-positive", scope)
    item = replace(
        item,
        authority_note_evidence=replace(
            item.authority_note_evidence,
            decision_ref=replace(
                item.authority_note_evidence.decision_ref,
                fingerprint=item.event_decision.decision_fingerprint,
            ),
        ),
    )
    bound = replace(
        item,
        decision_authority=bind_hk_legislation_inventory_decision_authority(item),
    )
    return build_hk_legislation_candidate_set(
        legislation_scope_code=scope,
        observation_cutoff=CUTOFF,
        inputs=(bound,),
    )


def test_positive_emitted_record_survives_scope_and_release_set_replay() -> None:
    """Verified drafts and exact allocated identities survive both issuance layers."""
    candidate = _positive_candidate_set()
    candidate = hk_legislation_candidate_set_from_bytes(
        canonical_hk_legislation_candidate_set(candidate)
    )
    allocation = HKLegislationRecordAllocation(
        SCOPE,
        candidate.drafts[0].candidate_key,
        "rec_" + "1" * 48,
        "INITIAL",
        None,
        None,
        None,
    )
    positive = build_hk_legislation_scope_release(
        replace(
            _request(),
            candidate_set=candidate,
            allocated_identities=HKLegislationAllocatedIdentitySet(
                SCOPE,
                (allocation,),
                None,
                None,
            ),
        )
    )
    others = (
        build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY")),
        build_hk_legislation_scope_release(_request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")),
    )
    results = (positive, *others)
    frozen = freeze_hk_legislation_release_set(
        HKLegislationReleaseSetRequest(
            results,
            "hk-v1-local",
            CUTOFF,
            RecordTraceabilityLookupInput(
                "rtl_" + "6" * 48,
                "sha256:" + "7" * 64,
                "sha256:" + "8" * 64,
            ),
            tuple(
                TraceabilityScopeShardInput(
                    result.release.scope_id,
                    result.release.release_id,
                    "rts_" + digit * 48,
                )
                for result, digit in zip(results, ("a", "b", "c"), strict=True)
            ),
        )
    )

    assert [item.record_id for item in frozen.desired_state.records] == ["rec_" + "1" * 48]
    assert frozen.traceability_lookup.total_entry_count == 1


def _request(
    scope: str = SCOPE,
    *,
    allocation: HKLegislationRecordAllocation | None = None,
) -> HKLegislationScopeReleaseRequest:
    candidates = _candidate_set(scope)
    digit = sha256(scope.encode()).hexdigest()[0]
    allocations = () if allocation is None else (allocation,)
    return HKLegislationScopeReleaseRequest(
        candidate_set=candidates,
        allocated_identities=HKLegislationAllocatedIdentitySet(
            "rsc_" + digit * 48, allocations, None, None
        ),
        serving_profile=ServingRecordProfile("srp_" + "4" * 48, "1.0.0", "sha256:" + "3" * 64),
        release_evidence_refs=("evi_" + "4" * 48,),
        release_validation_refs=("val_" + "5" * 48,),
        prior_release=None,
        prior_traceability_entries=None,
        prior_inventory_outcomes=None,
        unchanged=False,
    )


def test_release_rejects_spurious_allocation_for_a_withheld_current_item() -> None:
    """Missing caller allocation cannot become a locally selected record."""
    request = _request()
    allocation = HKLegislationRecordAllocation(
        SCOPE, "candidate_" + "1" * 48, "rec_" + "1" * 48, "INITIAL", None, None, None
    )
    with pytest.raises(HKLegislationReleaseError) as caught:
        build_hk_legislation_scope_release(
            replace(
                request,
                allocated_identities=replace(
                    request.allocated_identities, allocations=(allocation,)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID


def test_scope_release_rejects_same_byte_candidate_scope_subclass_before_replay() -> None:
    """A caller cannot relabel an issued all-withheld candidate before release freeze."""
    request = _request()
    candidates = request.candidate_set

    class SameByteScope(str):
        __slots__ = ()

    object.__setattr__(candidates, "legislation_scope_code", SameByteScope(SCOPE))
    with pytest.raises(HKLegislationReleaseError) as caught:
        build_hk_legislation_scope_release(request)
    assert caught.value.code is HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID


def test_three_scope_freeze_requires_common_cutoff_complete_entries_and_zero_shard() -> None:
    """All three scopes and their exact shard inventory are mandatory."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=(first, second, third),
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=(),
            ),
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE
    assert third.release.scope_id.startswith("rsc_")
    frozen = freeze_hk_legislation_release_set(
        HKLegislationReleaseSetRequest(
            scope_results=(first, second, third),
            target_key="hk-v1-local",
            observation_cutoff=CUTOFF,
            lookup_input=RecordTraceabilityLookupInput(
                "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
            ),
            lookup_shards=tuple(
                TraceabilityScopeShardInput(
                    result.release.scope_id,
                    result.release.release_id,
                    "rts_" + digit * 48,
                )
                for result, digit in zip((first, second, third), ("a", "b", "c"), strict=True)
            ),
        )
    )
    assert frozen.traceability_lookup.total_entry_count == 0
    assert all(shard.entry_count == 0 for shard in frozen.traceability_lookup.shards)


def test_release_rejects_subclass_request_and_replay_is_stable() -> None:
    """Exact request classes block subclass bypass while replay is deterministic."""

    class ScopeRequestSubclass(HKLegislationScopeReleaseRequest):
        pass

    request = _request()
    first = build_hk_legislation_scope_release(request)
    repeated = build_hk_legislation_scope_release(request)
    with pytest.raises(HKLegislationReleaseError) as caught:
        build_hk_legislation_scope_release(
            ScopeRequestSubclass(
                request.candidate_set,
                request.allocated_identities,
                request.serving_profile,
                request.release_evidence_refs,
                request.release_validation_refs,
                request.prior_release,
                request.prior_traceability_entries,
                request.prior_inventory_outcomes,
                request.unchanged,
            )
        )
    assert first == repeated
    assert caught.value.code is HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID


def test_release_rejects_forged_candidate_projection_and_cross_scope_allocation() -> None:
    """Only a live complete Desk issuance may reach the corpus mapper."""
    request = _request()
    forged = HKLegislationCandidateSet(
        request.candidate_set.legislation_scope_code,
        request.candidate_set.observation_cutoff,
        request.candidate_set.drafts,
        request.candidate_set.outcomes,
    )
    with pytest.raises(HKLegislationReleaseError) as forged_caught:
        build_hk_legislation_scope_release(replace(request, candidate_set=forged))
    allocation = HKLegislationRecordAllocation(
        "HK-LEG-SUBSIDIARY", "candidate_" + "1" * 48, "rec_" + "1" * 48, "INITIAL", None, None, None
    )
    with pytest.raises(HKLegislationReleaseError) as scope_caught:
        build_hk_legislation_scope_release(
            replace(
                request,
                allocated_identities=replace(
                    request.allocated_identities,
                    allocations=(allocation,),
                ),
            )
        )
    assert forged_caught.value.code is HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID
    assert scope_caught.value.code is HKLegislationReleaseErrorCode.IDENTITY_BINDING_INVALID


def test_changed_prior_release_is_blocked_and_initial_has_no_predecessor() -> None:
    """Changed predecessor lineage cannot persist through this corpus API."""
    prior = build_hk_legislation_scope_release(_request()).release
    initial = build_hk_legislation_scope_release(_request())
    unchanged = build_hk_legislation_scope_release(
        replace(
            _request(),
            prior_release=initial.release,
            prior_traceability_entries=initial.traceability_entries,
            prior_inventory_outcomes=initial.inventory_outcomes,
            unchanged=True,
        )
    )
    assert unchanged.release == initial.release
    assert unchanged.reused_prior_release
    with pytest.raises(HKLegislationReleaseError) as caught:
        build_hk_legislation_scope_release(replace(_request(), prior_release=prior))
    assert caught.value.code is HKLegislationReleaseErrorCode.PRIOR_RELEASE_INVALID


def test_release_set_rejects_replaced_scope_result_before_desired_state_selection() -> None:
    """A copied zero-result has no application issuance and cannot be selected."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )
    results = (replace(first), second, third)
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=results,
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=tuple(
                    TraceabilityScopeShardInput(
                        result.release.scope_id,
                        result.release.release_id,
                        "rts_" + digit * 48,
                    )
                    for result, digit in zip(results, ("a", "b", "c"), strict=True)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE


def test_release_set_rejects_same_byte_nested_outcome_subclass_before_comparison() -> None:
    """A live issued outcome cannot retain a callback-capable scalar subtype."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )

    class EqualityTrap(str):
        __slots__ = ()

        compared = False
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            type(self).compared = True
            return super().__eq__(other)

    object.__setattr__(first.inventory_outcomes[0], "outcome_kind", EqualityTrap("QUARANTINE"))
    results = (first, second, third)
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=results,
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=tuple(
                    TraceabilityScopeShardInput(
                        result.release.scope_id,
                        result.release.release_id,
                        "rts_" + digit * 48,
                    )
                    for result, digit in zip(results, ("a", "b", "c"), strict=True)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE
    assert not EqualityTrap.compared


def test_release_set_rejects_replaced_inventory_outcome_container_before_replay() -> None:
    """A copied list cannot replace the exact issued outcome tuple."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )
    object.__setattr__(first, "inventory_outcomes", list(first.inventory_outcomes))
    results = (first, second, third)
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=results,
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=tuple(
                    TraceabilityScopeShardInput(
                        result.release.scope_id,
                        result.release.release_id,
                        "rts_" + digit * 48,
                    )
                    for result, digit in zip(results, ("a", "b", "c"), strict=True)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE


def test_release_set_rejects_same_byte_allocated_scope_subclass_before_comparison() -> None:
    """An allocated scope subtype cannot run code during issued-result replay."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )

    class EqualityTrap(str):
        __slots__ = ()

        compared = False
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            type(self).compared = True
            return super().__eq__(other)

    identities = first.allocated_identities
    if identities is None:
        raise AssertionError
    object.__setattr__(identities, "corpus_scope_id", EqualityTrap(identities.corpus_scope_id))
    results = (first, second, third)
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=results,
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=tuple(
                    TraceabilityScopeShardInput(
                        result.release.scope_id,
                        result.release.release_id,
                        "rts_" + digit * 48,
                    )
                    for result, digit in zip(results, ("a", "b", "c"), strict=True)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE
    assert not EqualityTrap.compared


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lookup_revision_id", "rtl_" + "a" * 48),
        ("lookup_shard_id", "rts_" + "b" * 48),
    ],
)
def test_release_set_rejects_changed_allocated_lookup_fact_before_replay(
    field: str, value: str
) -> None:
    """Every issued lookup fact participates in the live scope projection."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )
    if first.allocated_identities is None:
        raise AssertionError
    object.__setattr__(first.allocated_identities, field, value)
    results = (first, second, third)
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=results,
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=tuple(
                    TraceabilityScopeShardInput(
                        result.release.scope_id,
                        result.release.release_id,
                        "rts_" + digit * 48,
                    )
                    for result, digit in zip(results, ("a", "b", "c"), strict=True)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE


@pytest.mark.parametrize("field", ["lookup_revision_id", "lookup_shard_id"])
def test_release_set_rejects_omitted_allocated_lookup_fact_before_replay(field: str) -> None:
    """Missing slots cannot silently become the retained `None` lookup fact."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )
    if first.allocated_identities is None:
        raise AssertionError
    object.__delattr__(first.allocated_identities, field)
    results = (first, second, third)
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=results,
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=tuple(
                    TraceabilityScopeShardInput(
                        result.release.scope_id,
                        result.release.release_id,
                        "rts_" + digit * 48,
                    )
                    for result, digit in zip(results, ("a", "b", "c"), strict=True)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE


def test_stale_zero_release_fingerprint_cannot_hide_an_inserted_record_or_trace() -> None:
    """An inserted record cannot reach desired state through a stale zero-result."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )
    inserted = ServingRecord(
        "rec_" + "1" * 48,
        "inserted",
        "Hong Kong",
        "Hong Kong",
        "Legislation",
        "HKeL",
        "None",
        "art_" + "b" * 48,
        (),
    )
    object.__setattr__(
        first,
        "release",
        replace(
            first.release,
            records=(ReleaseRecordEntry(inserted, serving_payload_fingerprint(inserted)),),
        ),
    )
    results = (first, second, third)
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=results,
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=tuple(
                    TraceabilityScopeShardInput(
                        result.release.scope_id,
                        result.release.release_id,
                        "rts_" + digit * 48,
                    )
                    for result, digit in zip(results, ("a", "b", "c"), strict=True)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE


def test_profile_subclass_callback_cannot_alter_an_issued_withheld_outcome() -> None:
    """Exact primitive capture rejects a callback-mutated profile/result pair."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )

    class MutatingProfileId(str):
        __slots__ = ()

        def __str__(self) -> str:
            object.__setattr__(first.inventory_outcomes[0], "outcome_kind", "WAITING_ROOM")
            object.__setattr__(
                first.inventory_outcomes[0], "reason_code", "COMMENCEMENT_NOT_PROVED"
            )
            return super().__str__()

    object.__setattr__(
        first.serving_profile,
        "serving_record_profile_id",
        MutatingProfileId(first.serving_profile.serving_record_profile_id),
    )
    assert str(first.serving_profile.serving_record_profile_id).startswith("srp_")
    results = (first, second, third)
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=results,
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=tuple(
                    TraceabilityScopeShardInput(
                        result.release.scope_id,
                        result.release.release_id,
                        "rts_" + digit * 48,
                    )
                    for result, digit in zip(results, ("a", "b", "c"), strict=True)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE


def _inserted_traceability_entry(result: HKLegislationScopeReleaseResult) -> TraceabilityEntry:
    """Make a structurally exact entry solely to exercise live-result rejection."""
    return TraceabilityEntry(
        "rec_" + "9" * 48,
        "sha256:" + "a" * 64,
        result.serving_profile.serving_record_profile_id,
        "lit_" + "b" * 48,
        ("ofv_" + "c" * 48,),
        ("loc_" + "d" * 48,),
        result.release.scope_id,
        result.release.release_id,
        (),
        AuthorityNoteEvidence(
            "sha256:" + "e" * 64,
            TraceabilityReference("decision", "dec_" + "f" * 48, "sha256:" + "1" * 64),
            (),
        ),
    )


def _assert_traceability_evidence_container_rejects_before_iteration(
    evidence_refs: object, *, iteration_state: dict[str, bool] | None = None
) -> None:
    """Exercise one non-tuple nested reference container at the public freeze boundary."""
    first = build_hk_legislation_scope_release(_request("HK-LEG-ORDINANCES"))
    second = build_hk_legislation_scope_release(_request("HK-LEG-SUBSIDIARY"))
    third = build_hk_legislation_scope_release(
        _request("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS")
    )
    entry = _inserted_traceability_entry(first)
    object.__setattr__(entry, "evidence_refs", evidence_refs)
    object.__setattr__(first, "traceability_entries", (entry,))
    results = (first, second, third)
    with pytest.raises(HKLegislationReleaseError) as caught:
        freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results=results,
                target_key="hk-v1-local",
                observation_cutoff=CUTOFF,
                lookup_input=RecordTraceabilityLookupInput(
                    "rtl_" + "6" * 48, "sha256:" + "7" * 64, "sha256:" + "8" * 64
                ),
                lookup_shards=tuple(
                    TraceabilityScopeShardInput(
                        result.release.scope_id,
                        result.release.release_id,
                        "rts_" + digit * 48,
                    )
                    for result, digit in zip(results, ("a", "b", "c"), strict=True)
                ),
            )
        )
    assert caught.value.code is HKLegislationReleaseErrorCode.RELEASE_SET_INCOMPLETE
    if iteration_state is not None:
        assert not iteration_state["called"]


def test_traceability_entry_rejects_evidence_refs_list_before_iteration() -> None:
    """A plain list cannot replace the exact typed evidence-reference tuple."""
    _assert_traceability_evidence_container_rejects_before_iteration([])


def test_traceability_entry_rejects_evidence_refs_list_subclass_before_iteration() -> None:
    """A list subclass cannot execute its iterator while capture validates it."""
    iteration_state = {"called": False}

    class IteratingList(list[TraceabilityReference]):
        def __iter__(self) -> Iterator[TraceabilityReference]:
            iteration_state["called"] = True
            return super().__iter__()

    _assert_traceability_evidence_container_rejects_before_iteration(
        IteratingList(), iteration_state=iteration_state
    )


def test_traceability_entry_rejects_evidence_refs_iterator_before_iteration() -> None:
    """A naked iterator cannot execute while an exact tuple is required."""
    iteration_state = {"called": False}

    class IteratingReferenceIterator:
        def __iter__(self) -> IteratingReferenceIterator:
            iteration_state["called"] = True
            return self

        def __next__(self) -> TraceabilityReference:
            raise StopIteration

    _assert_traceability_evidence_container_rejects_before_iteration(
        IteratingReferenceIterator(), iteration_state=iteration_state
    )


def _projection_fields_match(
    public_fields: tuple[str, ...],
    private_fields: tuple[str, ...],
    declared_fields: tuple[str, ...],
) -> bool:
    """Require the exact positional order used by snapshot constructors."""
    return public_fields == declared_fields and private_fields == declared_fields


def test_projection_coverage_rejects_reordered_declared_field_tuple() -> None:
    """Positional snapshots require the declared field order, not only membership."""
    public_fields = tuple(field.name for field in fields(HKLegislationScopeReleaseResult))
    private_fields = tuple(field.name for field in fields(_ScopeResultSnapshot))
    assert not _projection_fields_match(
        public_fields, private_fields, tuple(reversed(public_fields))
    )


def test_private_exact_projections_cover_every_retained_public_output_field() -> None:
    """A future output field cannot silently bypass issued-state replay."""
    expected_pairs = {
        (HKLegislationScopeReleaseResult, _ScopeResultSnapshot),
        (HKLegislationAllocatedIdentitySet, _AllocatedIdentitySetSnapshot),
        (HKLegislationInventoryOutcome, _OutcomeSnapshot),
        (HKLegislationTraceabilityReference, _HKLegislationTraceabilityReferenceSnapshot),
        (CorpusRelease, _CorpusReleaseSnapshot),
        (ReleaseRecordEntry, _ReleaseRecordEntrySnapshot),
        (ServingRecord, _ServingRecordSnapshot),
        (ServingRecordProfile, _ServingRecordProfileSnapshot),
        (TraceabilityEntry, _TraceabilityEntrySnapshot),
        (TraceabilityReference, _TraceabilityReferenceSnapshot),
        (AuthorityNoteEvidence, _AuthorityNoteEvidenceSnapshot),
        (DesiredStateInventory, _DesiredStateSnapshot),
        (FlattenedRecord, _FlattenedRecordSnapshot),
        (TraceabilityShard, _TraceabilityShardSnapshot),
        (RecordTraceabilityLookup, _RecordTraceabilityLookupSnapshot),
        (HKLegislationReleaseSet, _ReleaseSetSnapshot),
    }
    assert {
        (public, snapshot) for public, snapshot, _ in _CAPTURE_PROJECTION_FIELDS
    } == expected_pairs
    for public, snapshot, declared_fields in _CAPTURE_PROJECTION_FIELDS:
        assert _projection_fields_match(
            tuple(field.name for field in fields(public)),
            tuple(field.name for field in fields(snapshot)),
            declared_fields,
        )


def test_acquisition_manifest_gate_emits_exact_three_complete_scope_inputs() -> None:
    """Only the closed complete family manifest can begin release processing."""
    accepted = accept_hk_legislation_acquisition_manifest(_acquisition_manifest())

    assert type(accepted) is HKLegislationAcquisitionReleaseInput
    assert accepted.changed is True
    assert accepted.source_baseline_fingerprint == "sha256:" + "d" * 64
    assert tuple(scope.scope_id for scope in accepted.scope_inputs) == (
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
    )


def test_no_change_manifest_causes_zero_at_four_distinct_downstream_boundaries() -> None:
    """A proved no-change cycle cannot start model, embedding, proposal, or Pinecone work."""
    accepted = accept_hk_legislation_acquisition_manifest(_acquisition_manifest("NO_CHANGE"))

    class ExplodingModelWork:
        @staticmethod
        def enqueue(value: HKLegislationAcquisitionReleaseInput) -> None:
            del value
            message = "no-change reached model boundary"
            raise AssertionError(message)

    class ExplodingEmbeddingWork:
        @staticmethod
        def enqueue(value: HKLegislationAcquisitionReleaseInput) -> None:
            del value
            message = "no-change reached embedding boundary"
            raise AssertionError(message)

    class ExplodingProposalWork:
        @staticmethod
        def enqueue(value: HKLegislationAcquisitionReleaseInput) -> None:
            del value
            message = "no-change reached proposal boundary"
            raise AssertionError(message)

    class ExplodingPineconeWork:
        @staticmethod
        def enqueue(value: HKLegislationAcquisitionReleaseInput) -> None:
            del value
            message = "no-change reached Pinecone boundary"
            raise AssertionError(message)

    assert accepted.changed is False
    assert (
        route_hk_legislation_acquisition_input(
            accepted,
            HKLegislationDownstreamPorts(
                ExplodingModelWork(),
                ExplodingEmbeddingWork(),
                ExplodingProposalWork(),
                ExplodingPineconeWork(),
            ),
        )
        is False
    )


def test_complete_manifest_reaches_the_changed_work_boundary() -> None:
    """Changed input crosses four distinct local boundaries in canonical order."""
    accepted = accept_hk_legislation_acquisition_manifest(_acquisition_manifest())
    calls: list[str] = []

    class ChangedWork:
        def __init__(self, name: str) -> None:
            self.name = name

        def enqueue(self, value: HKLegislationAcquisitionReleaseInput) -> None:
            assert value is accepted
            calls.append(self.name)

    assert (
        route_hk_legislation_acquisition_input(
            accepted,
            HKLegislationDownstreamPorts(
                ChangedWork("model"),
                ChangedWork("embedding"),
                ChangedWork("proposal"),
                ChangedWork("pinecone"),
            ),
        )
        is True
    )
    assert calls == ["model", "embedding", "proposal", "pinecone"]


def test_changed_route_stops_at_an_exploding_downstream_boundary() -> None:
    """A failed earlier local stage cannot be skipped to a later boundary."""
    accepted = accept_hk_legislation_acquisition_manifest(_acquisition_manifest())

    class ExplodingChangedWork:
        @staticmethod
        def enqueue(value: HKLegislationAcquisitionReleaseInput) -> None:
            del value
            message = "changed work boundary reached"
            raise AssertionError(message)

    with pytest.raises(AssertionError, match="changed work boundary reached"):
        route_hk_legislation_acquisition_input(
            accepted,
            HKLegislationDownstreamPorts(
                ExplodingChangedWork(),
                ExplodingChangedWork(),
                ExplodingChangedWork(),
                ExplodingChangedWork(),
            ),
        )


def test_registered_legal_activity_consumes_canonical_manifest_at_own_boundary(
    tmp_path: Path,
) -> None:
    """The legal worker's production entry parses and routes acquisition-owned bytes."""

    class Credential:
        @staticmethod
        def reveal() -> bytes:
            return b"unused"

    @dataclass(frozen=True)
    class Infrastructure:
        primary_vault: LocalImmutableVault
        model_provider_credential: Credential
        model_egress_proxy_credential: Credential

    infrastructure = Infrastructure(
        LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY),
        Credential(),
        Credential(),
    )
    activities = build_activities(
        infrastructure,
        {"ASKLEGAL_HK_V1_LEGISLATION_SPOOL_ROOT": str(tmp_path / "spool")},
    )

    result = activities.accept_legislation_manifest(
        ActivityContext("test", 1), _acquisition_manifest()
    )

    assert result == {
        "accepted": True,
        "changed": True,
        "manifest_fingerprint": accept_hk_legislation_acquisition_manifest(
            _acquisition_manifest()
        ).acquisition_manifest_fingerprint,
    }
    assert activities.legislation_dispatch_stages == (
        "model",
        "embedding",
        "proposal",
        "pinecone",
    )


def test_registered_legal_activity_records_zero_local_dispatches_for_no_change(
    tmp_path: Path,
) -> None:
    """The normal local service composition preserves the no-change zero-effect gate."""

    class Credential:
        @staticmethod
        def reveal() -> bytes:
            return b"unused"

    @dataclass(frozen=True)
    class Infrastructure:
        primary_vault: LocalImmutableVault
        model_provider_credential: Credential
        model_egress_proxy_credential: Credential

    infrastructure = Infrastructure(
        LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY),
        Credential(),
        Credential(),
    )
    activities = build_activities(
        infrastructure,
        {"ASKLEGAL_HK_V1_LEGISLATION_SPOOL_ROOT": str(tmp_path / "spool")},
    )

    result = activities.accept_legislation_manifest(
        ActivityContext("test", 1), _acquisition_manifest("NO_CHANGE")
    )

    assert type(result) is dict
    assert result["changed"] is False
    assert activities.legislation_dispatch_stages == ()


def test_acquisition_manifest_gate_rejects_extra_fields_and_incomplete_scope() -> None:
    """The cross-application JSON boundary stays closed and complete-only."""
    with pytest.raises(HKLegislationReleaseError):
        accept_hk_legislation_acquisition_manifest(_acquisition_manifest(extra=True))

    raw = _acquisition_manifest().replace(b'"verified_item_count":1', b'"verified_item_count":0', 1)
    with pytest.raises(HKLegislationReleaseError):
        accept_hk_legislation_acquisition_manifest(raw)
