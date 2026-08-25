"""Source-neutral HKEX component continuity and identity conformance."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue
from asklegal_legal_desks import (
    HKEX_COMPONENT_CONTINUITY_RULE_ID,
    HKEX_GEM_SCOPE_ID,
    HKEX_MAIN_SCOPE_ID,
    HKEXComponentContinuityRequest,
    HKEXComponentLineageType,
    HKEXContinuityError,
    HKEXContinuityErrorCode,
    HKEXContinuityEvent,
    HKEXContinuityReason,
    HKEXContinuitySupport,
    HKEXExistingComponentIdentity,
    HKEXIdentityConsequence,
    HKEXObservedComponentCandidate,
    HKEXProcessingOutcome,
    decide_hkex_component_continuity,
    hkex_component_continuity_request_from_document,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)

FINGERPRINT = f"sha256:{'b' * 64}"


def _predecessor(
    component_id: str = "component-main-old",
    scope_id: str = HKEX_MAIN_SCOPE_ID,
) -> HKEXExistingComponentIdentity:
    return HKEXExistingComponentIdentity(
        component_id=component_id,
        scope_id=scope_id,
        legal_location_id=f"location-{component_id}",
        aliases=(f"old-alias-{component_id}",),
        evidence_refs=(f"evidence-{component_id}",),
    )


def _candidate(
    candidate_id: str = "candidate-main-current",
    scope_id: str = HKEX_MAIN_SCOPE_ID,
) -> HKEXObservedComponentCandidate:
    return HKEXObservedComponentCandidate(
        candidate_id=candidate_id,
        scope_id=scope_id,
        observed_locator=f"locator-{candidate_id}",
        aliases=(f"current-alias-{candidate_id}",),
        evidence_refs=(f"evidence-{candidate_id}",),
    )


def _request(**changes: object) -> HKEXComponentContinuityRequest:
    request = HKEXComponentContinuityRequest(
        decision_id="continuity-decision-001",
        cutoff="2026-08-24T00:00:00+08:00",
        event=HKEXContinuityEvent.UNCHANGED,
        support=HKEXContinuitySupport.PROVED,
        predecessors=(_predecessor(),),
        candidates=(_candidate(),),
        source_rule_id=HKEX_COMPONENT_CONTINUITY_RULE_ID,
        evidence_refs=("evidence-complete-current", "evidence-predecessor"),
        evidence_fingerprint=FINGERPRINT,
        legal_desk_actor="synthetic-hk-regulatory-legal-desk",
    )
    return replace(request, **changes)


@pytest.mark.parametrize(
    ("event", "consequence", "lineage", "reason"),
    [
        (
            HKEXContinuityEvent.UNCHANGED,
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.NONE,
            HKEXContinuityReason.EXACT_NO_CHANGE,
        ),
        (
            HKEXContinuityEvent.URL_MOVED,
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.NONE,
            HKEXContinuityReason.PRESENTATION_ALIAS_CHANGED,
        ),
        (
            HKEXContinuityEvent.RENAMED,
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.RENAME,
            HKEXContinuityReason.SAME_COMPONENT_RENAMED,
        ),
        (
            HKEXContinuityEvent.RENUMBERED,
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.RENUMBER,
            HKEXContinuityReason.SAME_LOCATION_RENUMBERED,
        ),
        (
            HKEXContinuityEvent.STRUCTURALLY_MOVED,
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.STRUCTURAL_MOVE,
            HKEXContinuityReason.SAME_COMPONENT_STRUCTURALLY_MOVED,
        ),
        (
            HKEXContinuityEvent.TEXT_CORRECTED,
            HKEXIdentityConsequence.PRESERVE_EXISTING,
            HKEXComponentLineageType.CORRECTION,
            HKEXContinuityReason.SAME_COMPONENT_TEXT_CORRECTED,
        ),
        (
            HKEXContinuityEvent.REPLACED,
            HKEXIdentityConsequence.REQUIRE_NEW_ONE_TO_ONE,
            HKEXComponentLineageType.REPLACEMENT,
            HKEXContinuityReason.DISTINCT_REPLACEMENT_REQUIRES_NEW_ID,
        ),
        (
            HKEXContinuityEvent.REAPPEARED,
            HKEXIdentityConsequence.RESELECT_EXISTING,
            HKEXComponentLineageType.REINSTATEMENT,
            HKEXContinuityReason.REAPPEARANCE_RESELECTS_PROVED_ID,
        ),
    ],
)
def test_one_to_one_events_have_exact_identity_consequences(
    event: HKEXContinuityEvent,
    consequence: HKEXIdentityConsequence,
    lineage: HKEXComponentLineageType,
    reason: HKEXContinuityReason,
) -> None:
    result = decide_hkex_component_continuity(_request(event=event))

    assert result.identity_consequence is consequence
    assert result.lineage_type is lineage
    assert result.reason is reason
    assert result.processing_outcome is HKEXProcessingOutcome.PASS
    assert result.continuity_decision_complete
    assert not result.search_record_authorized
    assert not result.serving_ready


def test_split_and_merge_require_new_register_ids_and_typed_forward_lineage() -> None:
    split = decide_hkex_component_continuity(
        _request(
            event=HKEXContinuityEvent.SPLIT,
            candidates=(_candidate("candidate-split-a"), _candidate("candidate-split-b")),
        )
    )
    merge = decide_hkex_component_continuity(
        _request(
            event=HKEXContinuityEvent.MERGED,
            predecessors=(_predecessor("component-a"), _predecessor("component-b")),
        )
    )

    assert split.identity_consequence is HKEXIdentityConsequence.REQUIRE_NEW_ONE_TO_MANY
    assert split.lineage_type is HKEXComponentLineageType.SPLIT
    assert split.ended_component_ids == ("component-main-old",)
    assert split.candidate_ids_requiring_allocation == (
        "candidate-split-a",
        "candidate-split-b",
    )
    assert merge.identity_consequence is HKEXIdentityConsequence.REQUIRE_NEW_MANY_TO_ONE
    assert merge.lineage_type is HKEXComponentLineageType.MERGE
    assert merge.ended_component_ids == ("component-a", "component-b")
    assert not split.inventory_admission_ready
    assert not merge.inventory_admission_ready


def test_board_transfer_never_reuses_cross_board_component_identity() -> None:
    result = decide_hkex_component_continuity(
        _request(
            event=HKEXContinuityEvent.BOARD_TRANSFERRED,
            candidates=(_candidate(scope_id=HKEX_GEM_SCOPE_ID),),
        )
    )

    assert result.identity_consequence is HKEXIdentityConsequence.REQUIRE_NEW_ONE_TO_ONE
    assert result.lineage_type is HKEXComponentLineageType.TRANSFER
    assert result.preserved_component_ids == ()
    assert result.ended_component_ids == ("component-main-old",)


def test_official_withdrawal_and_disappearance_are_not_collapsed() -> None:
    withdrawn = decide_hkex_component_continuity(
        _request(event=HKEXContinuityEvent.OFFICIALLY_WITHDRAWN, candidates=())
    )
    disappeared = decide_hkex_component_continuity(
        _request(event=HKEXContinuityEvent.DISAPPEARED, candidates=())
    )

    assert withdrawn.identity_consequence is HKEXIdentityConsequence.PRESERVE_HISTORICAL
    assert withdrawn.lineage_type is HKEXComponentLineageType.WITHDRAWAL
    assert withdrawn.processing_outcome is HKEXProcessingOutcome.PASS
    assert disappeared.identity_consequence is HKEXIdentityConsequence.QUARANTINE
    assert disappeared.reason is HKEXContinuityReason.DISAPPEARANCE_PROVES_NO_RETIREMENT
    assert disappeared.preserved_component_ids == ("component-main-old",)
    assert not disappeared.continuity_decision_complete


def test_new_component_requires_allocation_without_invented_predecessor() -> None:
    result = decide_hkex_component_continuity(
        _request(event=HKEXContinuityEvent.NEW_COMPONENT, predecessors=())
    )

    assert result.identity_consequence is HKEXIdentityConsequence.REQUIRE_NEW_UNRELATED
    assert result.lineage_type is HKEXComponentLineageType.NONE
    assert result.preserved_component_ids == ()
    assert result.ended_component_ids == ()
    assert result.candidate_ids_requiring_allocation == ("candidate-main-current",)


@pytest.mark.parametrize(
    "support",
    [
        HKEXContinuitySupport.AMBIGUOUS,
        HKEXContinuitySupport.SIMILARITY_OR_ALIAS_ONLY,
        HKEXContinuitySupport.MISSING_OR_CONFLICTING,
    ],
)
def test_similarity_alias_or_ambiguous_evidence_never_resolves_identity(
    support: HKEXContinuitySupport,
) -> None:
    result = decide_hkex_component_continuity(
        _request(event=HKEXContinuityEvent.RENUMBERED, support=support)
    )

    assert result.identity_consequence is HKEXIdentityConsequence.QUARANTINE
    assert result.processing_outcome is HKEXProcessingOutcome.QUARANTINE
    assert result.reason is HKEXContinuityReason.CONTINUITY_EVIDENCE_UNRESOLVED
    assert result.preserved_component_ids == ("component-main-old",)


def test_wrong_cardinality_duplicate_identity_and_silent_board_change_fail_closed() -> None:
    with pytest.raises(HKEXContinuityError) as split:
        _request(event=HKEXContinuityEvent.SPLIT)
    assert split.value.code is HKEXContinuityErrorCode.CONTRACT

    with pytest.raises(HKEXContinuityError) as duplicate:
        _request(
            event=HKEXContinuityEvent.MERGED,
            predecessors=(_predecessor(), _predecessor()),
        )
    assert duplicate.value.code is HKEXContinuityErrorCode.CONTRACT

    with pytest.raises(HKEXContinuityError) as board:
        _request(candidates=(_candidate(scope_id=HKEX_GEM_SCOPE_ID),))
    assert board.value.code is HKEXContinuityErrorCode.CONTRACT


def test_invalid_fingerprint_and_empty_alias_evidence_fail_closed() -> None:
    with pytest.raises(HKEXContinuityError) as fingerprint:
        _request(evidence_fingerprint="sha256:bad")
    assert fingerprint.value.code is HKEXContinuityErrorCode.EVIDENCE

    with pytest.raises(HKEXContinuityError) as aliases:
        replace(_predecessor(), aliases=())
    assert aliases.value.code is HKEXContinuityErrorCode.EVIDENCE


def test_frozen_component_continuity_fixture_reproduces_exact_results() -> None:
    fixture = _json_object(
        parse_json_bytes(
            (PACKAGE_ROOT / "fixtures/deterministic/HKREG-CONTINUITY-FIX-001.json").read_bytes(),
            max_bytes=2_000_000,
        )
    )
    expected = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "expected/component-continuity/HKREG-CONTINUITY-FIX-001.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    request_schema = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "contracts/schemas/hkex-component-continuity-request.schema.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    result_schema = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "contracts/schemas/hkex-component-continuity-result.schema.json"
            ).read_bytes(),
            max_bytes=2_000_000,
        )
    )
    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator.check_schema(result_schema)
    base = _json_object(fixture["base_request"])
    cases = _json_array(fixture["cases"])
    expected_cases = _json_array(expected["cases"])
    assert len(cases) == 15
    assert len(expected_cases) == len(cases)

    actual: list[dict[str, object]] = []
    for raw_case in cases:
        case = _json_object(raw_case)
        case_id = _json_text(case["case_id"])
        request_document = {**base, **_json_object(case["overrides"])}
        decision = decide_hkex_component_continuity(
            hkex_component_continuity_request_from_document(request_document)
        )
        actual.append(decision.document(case_id=case_id))

    assert actual == [_json_object(item) for item in expected_cases]


def test_component_continuity_parser_rejects_extra_fields() -> None:
    fixture = _json_object(
        parse_json_bytes(
            (PACKAGE_ROOT / "fixtures/deterministic/HKREG-CONTINUITY-FIX-001.json").read_bytes(),
            max_bytes=2_000_000,
        )
    )
    with pytest.raises(HKEXContinuityError):
        hkex_component_continuity_request_from_document(
            {**_json_object(fixture["base_request"]), "extra": "forbidden"}
        )


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    result: dict[str, JsonValue] = {}
    for key, item in value.items():
        assert isinstance(key, str)
        result[key] = item
    return result


def _json_array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _json_text(value: JsonValue) -> str:
    assert isinstance(value, str)
    assert value
    return value
