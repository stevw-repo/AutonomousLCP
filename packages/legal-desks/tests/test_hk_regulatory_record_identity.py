"""ADR 0011/0073 HKEX traceability and Search Record identity conformance."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Protocol, TypedDict, Unpack

import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue
from asklegal_legal_desks import (
    HKEX_ENGLISH_RECORD_RULE_ID,
    HKEX_GEM_SCOPE_ID,
    HKEX_MAIN_SCOPE_ID,
    HKEXBranchState,
    HKEXComponentClass,
    HKEXEnglishConstructionRequest,
    HKEXEnglishRecordUnit,
    HKEXEnglishServingProfile,
    HKEXEnglishSourceTree,
    HKEXEnglishSourceUnit,
    HKEXEnglishUnitKind,
    HKEXExistingSearchRecord,
    HKEXRecordChange,
    HKEXRecordIdentityConsequence,
    HKEXRecordIdentityError,
    HKEXRecordIdentityErrorCode,
    HKEXRecordIdentityReason,
    HKEXRecordIdentityRequest,
    HKEXReferencedLocation,
    HKEXSourceContractState,
    HKEXSourceUnitRole,
    HKEXTraceabilityReference,
    HKEXTraceabilityReferenceType,
    construct_hkex_english_request,
    decide_hkex_record_identity,
    hkex_record_identity_request_from_document,
)
from jsonschema import Draft202012Validator

FINGERPRINT = f"sha256:{'a' * 64}"
OTHER_FINGERPRINT = f"sha256:{'9' * 64}"
LEGAL_ITEM_ID = f"lit_{'1' * 48}"
OFFICIAL_VERSION_ID = f"ofv_{'2' * 48}"
LEGAL_LOCATION_ID = f"loc_{'3' * 48}"
FIRST_RECORD_ID = f"rec_{'4' * 48}"
SECOND_RECORD_ID = f"rec_{'5' * 48}"
PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)


class ExactCharacterCounter:
    """Frozen source-neutral exact counter; never a production admission."""

    profile_id = "synthetic-hkex-identity-profile-1"
    profile_fingerprint = FINGERPRINT
    tokenizer_id = "synthetic-codepoint-counter-1"

    def count(self, text: str) -> int:
        """Count the fixture text exactly by Unicode code point."""
        return len(text)


class FrozenFixtureCounter:
    """Counter bound to the explicitly non-admitted frozen fixture profile."""

    def __init__(self, profile_id: str, profile_fingerprint: str, tokenizer_id: str) -> None:
        """Bind the exact declared synthetic profile triplet."""
        self.profile_id = profile_id
        self.profile_fingerprint = profile_fingerprint
        self.tokenizer_id = tokenizer_id

    def count(self, text: str) -> int:
        """Reproduce the fixture's declared code-point measurement."""
        return len(text)


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


class _ConstructionOptions(TypedDict, total=False):
    text: str
    state: HKEXBranchState
    authority_note: str
    reference: HKEXReferencedLocation | None
    scope_id: str


class _RequestOptions(TypedDict, total=False):
    construction: HKEXEnglishConstructionRequest
    current_legal_support: bool
    existing_records: tuple[HKEXExistingSearchRecord, ...]
    predecessor_search_record_ids: tuple[str, ...]
    change: HKEXRecordChange
    evidence_refs: tuple[HKEXTraceabilityReference, ...]
    legal_item_id: str


def _construction(
    **options: Unpack[_ConstructionOptions],
) -> HKEXEnglishConstructionRequest:
    text = options.get("text", "2.01 An issuer must comply with the Listing Rules.")
    state = options.get("state", HKEXBranchState.CURRENT)
    authority_note = options.get("authority_note", "None")
    reference = options.get("reference")
    scope_id = options.get("scope_id", HKEX_MAIN_SCOPE_ID)
    context_text = "Rule 2 — General obligations"
    source_units = (
        HKEXEnglishSourceUnit(
            source_unit_id="context",
            parent_source_unit_id=None,
            child_source_unit_ids=("rule-a",),
            source_order=0,
            kind=HKEXEnglishUnitKind.HEADING,
            role=HKEXSourceUnitRole.CONTEXT_ONLY,
            text=context_text,
            source_range="artifact#heading",
            required_context_unit_ids=(),
            meaning_bearing=True,
            content_fingerprint=_raw_fingerprint(context_text),
        ),
        HKEXEnglishSourceUnit(
            source_unit_id="rule-a",
            parent_source_unit_id="context",
            child_source_unit_ids=(),
            source_order=1,
            kind=HKEXEnglishUnitKind.BODY_TEXT,
            role=HKEXSourceUnitRole.PRIMARY,
            text=text,
            source_range="artifact#rule-2.01",
            required_context_unit_ids=("context",),
            meaning_bearing=True,
            content_fingerprint=_raw_fingerprint(text),
        ),
    )
    tree = HKEXEnglishSourceTree(
        tree_id="tree-main-2.01",
        component_id="component-main-2.01",
        scope_id=scope_id,
        branch_id="branch-main-2.01",
        branch_state=state,
        component_class=HKEXComponentClass.ORDINARY_RULE,
        component_label="Main Board Listing Rules",
        location_label="Rule 2.01",
        official_heading="General obligations",
        root_source_unit_id="context",
        source_units=source_units,
        root_record_unit_ids=("record-root",),
        record_units=(
            HKEXEnglishRecordUnit(
                record_unit_id="record-root",
                primary_source_unit_ids=("rule-a",),
                dependency_source_unit_ids=("context",),
                referenced_locations=(() if reference is None else (reference,)),
                child_record_unit_ids=(),
                source_contract_state=HKEXSourceContractState.SUPPORTED,
                indivisible=True,
            ),
        ),
        source_rule_id=HKEX_ENGLISH_RECORD_RULE_ID,
        source_artifact_fingerprints=(FINGERPRINT,),
    )
    profile = HKEXEnglishServingProfile(
        profile_id=ExactCharacterCounter.profile_id,
        profile_fingerprint=ExactCharacterCounter.profile_fingerprint,
        tokenizer_id=ExactCharacterCounter.tokenizer_id,
        max_text_tokens=100_000,
        max_metadata_bytes=100_000,
        country="Hong Kong",
        jurisdiction="Hong Kong",
        material_type="regulatory_material",
        source="Hong Kong Exchanges and Clearing Limited",
        authority_note=authority_note,
    )
    effective_context = (
        "Applies to synthetic pre-2026 issuers"
        if state is HKEXBranchState.TRANSITIONAL_CURRENT
        else None
    )
    return HKEXEnglishConstructionRequest(tree, profile, effective_context)


def _ref(
    ref_type: HKEXTraceabilityReferenceType,
    digit: str,
) -> HKEXTraceabilityReference:
    return HKEXTraceabilityReference(
        ref_type,
        f"evd_{digit * 48}",
        f"sha256:{digit * 64}",
    )


def _request(**options: Unpack[_RequestOptions]) -> HKEXRecordIdentityRequest:
    construction = options.get("construction", _construction())
    return HKEXRecordIdentityRequest(
        decision_id="hkex-record-identity-decision-001",
        construction=construction,
        root_record_unit_id="record-root",
        part_number=1,
        legal_item_id=options.get("legal_item_id", LEGAL_ITEM_ID),
        official_version_ids=(OFFICIAL_VERSION_ID,),
        legal_location_ids=(LEGAL_LOCATION_ID,),
        evidence_refs=options.get(
            "evidence_refs",
            (_ref(HKEXTraceabilityReferenceType.SOURCE_SNAPSHOT, "6"),),
        ),
        authority_note_decision_ref=_ref(HKEXTraceabilityReferenceType.DECISION, "7"),
        authority_note_supporting_refs=(),
        current_legal_support=options.get("current_legal_support", True),
        existing_records=options.get("existing_records", ()),
        predecessor_search_record_ids=options.get("predecessor_search_record_ids", ()),
        change=options.get("change", HKEXRecordChange.INITIAL),
        decision_evidence_fingerprint=FINGERPRINT,
        legal_desk_actor="synthetic-hk-regulatory-legal-desk",
    )


def _payload(construction: HKEXEnglishConstructionRequest) -> str:
    coverage = construct_hkex_english_request(construction, ExactCharacterCounter())
    return coverage.record_results[0].parts[0].serving_payload_fingerprint


def _existing(
    record_id: str,
    payload: str,
    *,
    selected: bool,
    scope_id: str = HKEX_MAIN_SCOPE_ID,
    legal_item_id: str = LEGAL_ITEM_ID,
) -> HKEXExistingSearchRecord:
    return HKEXExistingSearchRecord(
        record_id,
        payload,
        scope_id,
        legal_item_id,
        selected,
    )


def test_unseen_initial_payload_requires_register_id_and_complete_traceability_seed() -> None:
    request = _request()
    result = decide_hkex_record_identity(request, ExactCharacterCounter())

    assert result.consequence is HKEXRecordIdentityConsequence.REQUIRE_NEW_INITIAL
    assert result.reason is HKEXRecordIdentityReason.UNSEEN_INITIAL_PAYLOAD_REQUIRES_ID
    assert result.selected_search_record_id is None
    assert result.register_allocation_required
    assert result.selection_event_required
    assert result.identity_decision_complete
    assert not result.search_record_authorized
    assert not result.serving_ready
    seed = result.traceability_seed
    assert seed is not None
    assert seed.serving_payload_fingerprint == result.candidate_serving_payload_fingerprint
    assert seed.legal_item_id == LEGAL_ITEM_ID
    assert seed.official_version_ids == (OFFICIAL_VERSION_ID,)
    assert seed.legal_location_ids == (LEGAL_LOCATION_ID,)
    assert tuple(item.source_unit_id for item in seed.primary_source_units) == ("rule-a",)
    assert tuple(item.source_unit_id for item in seed.dependency_source_units) == ("context",)
    assert seed.primary_source_units[0].source_range == "artifact#rule-2.01"
    assert seed.authority_note_fingerprint == _raw_fingerprint("None")
    assert seed.identity_decision_evidence_fingerprint == FINGERPRINT
    assert seed.legal_desk_actor == "synthetic-hk-regulatory-legal-desk"
    assert hkex_record_identity_request_from_document(request.document()) == request


@pytest.mark.parametrize(
    "change",
    [HKEXRecordChange.SIX_FIELD_UNCHANGED, HKEXRecordChange.TRACEABILITY_ONLY],
)
def test_exact_current_payload_preserves_selected_record(
    change: HKEXRecordChange,
) -> None:
    construction = _construction()
    existing = _existing(FIRST_RECORD_ID, _payload(construction), selected=True)
    result = decide_hkex_record_identity(
        _request(
            construction=construction,
            existing_records=(existing,),
            predecessor_search_record_ids=(FIRST_RECORD_ID,),
            change=change,
        ),
        ExactCharacterCounter(),
    )

    assert result.consequence is HKEXRecordIdentityConsequence.PRESERVE_SELECTED
    assert result.reason is HKEXRecordIdentityReason.EXACT_SELECTED_PAYLOAD_PRESERVED
    assert result.selected_search_record_id == FIRST_RECORD_ID
    assert not result.register_allocation_required
    assert not result.selection_event_required


def test_exact_older_payload_is_reselected_without_backward_lineage() -> None:
    construction = _construction()
    exact_older = _existing(FIRST_RECORD_ID, _payload(construction), selected=False)
    current = _existing(SECOND_RECORD_ID, OTHER_FINGERPRINT, selected=True)
    result = decide_hkex_record_identity(
        _request(
            construction=construction,
            existing_records=(exact_older, current),
            predecessor_search_record_ids=(SECOND_RECORD_ID,),
            change=HKEXRecordChange.REINSTATEMENT,
        ),
        ExactCharacterCounter(),
    )

    assert result.consequence is HKEXRecordIdentityConsequence.RESELECT_PRESERVED
    assert result.reason is HKEXRecordIdentityReason.EXACT_PRESERVED_PAYLOAD_RESELECTED
    assert result.selected_search_record_id == FIRST_RECORD_ID
    assert result.predecessor_search_record_ids == ()
    assert result.selection_event_required
    assert not result.register_allocation_required


@pytest.mark.parametrize(
    "change",
    [
        HKEXRecordChange.PRIMARY_TEXT_CHANGED,
        HKEXRecordChange.APPLICABILITY_CONTEXT_CHANGED,
        HKEXRecordChange.GOVERNING_CONTEXT_CHANGED,
        HKEXRecordChange.REFERENCED_LOCATION_CHANGED,
        HKEXRecordChange.STRUCTURED_PROJECTION_CHANGED,
        HKEXRecordChange.PARTITION_CHANGED,
        HKEXRecordChange.AUTHORITY_NOTE_CHANGED,
    ],
)
def test_unseen_payload_change_requires_forward_successor_without_issuing_id(
    change: HKEXRecordChange,
) -> None:
    construction = _construction(text="2.01 Changed exact source wording.")
    current = _existing(FIRST_RECORD_ID, OTHER_FINGERPRINT, selected=True)
    result = decide_hkex_record_identity(
        _request(
            construction=construction,
            existing_records=(current,),
            predecessor_search_record_ids=(FIRST_RECORD_ID,),
            change=change,
        ),
        ExactCharacterCounter(),
    )

    assert result.consequence is (HKEXRecordIdentityConsequence.REQUIRE_NEW_FORWARD_SUCCESSOR)
    assert result.reason is (HKEXRecordIdentityReason.UNSEEN_CHANGED_PAYLOAD_REQUIRES_SUCCESSOR)
    assert result.selected_search_record_id is None
    assert result.predecessor_search_record_ids == (FIRST_RECORD_ID,)
    assert result.register_allocation_required


def test_payload_change_claim_cannot_create_churn_when_exact_bytes_are_unchanged() -> None:
    construction = _construction()
    current = _existing(FIRST_RECORD_ID, _payload(construction), selected=True)
    result = decide_hkex_record_identity(
        _request(
            construction=construction,
            existing_records=(current,),
            predecessor_search_record_ids=(FIRST_RECORD_ID,),
            change=HKEXRecordChange.AUTHORITY_NOTE_CHANGED,
        ),
        ExactCharacterCounter(),
    )

    assert result.consequence is HKEXRecordIdentityConsequence.BLOCK
    assert result.reason is (HKEXRecordIdentityReason.DECLARED_CHANGE_CONFLICTS_WITH_PAYLOAD)
    assert not result.identity_decision_complete


def test_unchanged_or_reinstated_claim_requires_exact_preserved_payload() -> None:
    construction = _construction()
    current = _existing(FIRST_RECORD_ID, OTHER_FINGERPRINT, selected=True)
    result = decide_hkex_record_identity(
        _request(
            construction=construction,
            existing_records=(current,),
            predecessor_search_record_ids=(FIRST_RECORD_ID,),
            change=HKEXRecordChange.SIX_FIELD_UNCHANGED,
        ),
        ExactCharacterCounter(),
    )

    assert result.consequence is HKEXRecordIdentityConsequence.BLOCK
    assert result.reason is (HKEXRecordIdentityReason.REQUIRED_EXACT_PRESERVED_PAYLOAD_MISSING)


def test_missing_current_support_blocks_selection_but_preserves_traceability() -> None:
    result = decide_hkex_record_identity(
        _request(current_legal_support=False), ExactCharacterCounter()
    )

    assert result.consequence is HKEXRecordIdentityConsequence.BLOCK
    assert result.reason is HKEXRecordIdentityReason.CURRENT_LEGAL_SUPPORT_NOT_PROVED
    assert result.traceability_seed is not None
    assert not result.identity_decision_complete


@pytest.mark.parametrize(
    "state",
    [
        HKEXBranchState.FUTURE_FIXED_DATE,
        HKEXBranchState.SUPERSEDED,
        HKEXBranchState.UNKNOWN,
    ],
)
def test_noncurrent_construction_never_reaches_identity_selection(
    state: HKEXBranchState,
) -> None:
    result = decide_hkex_record_identity(
        _request(construction=_construction(state=state)), ExactCharacterCounter()
    )

    assert result.consequence is HKEXRecordIdentityConsequence.BLOCK
    assert result.reason is (HKEXRecordIdentityReason.CONSTRUCTION_NOT_CURRENT_CANDIDATE)
    assert result.traceability_seed is None


def test_reference_locator_and_authority_note_are_bound_without_target_text_copy() -> None:
    construction = _construction(
        reference=HKEXReferencedLocation("Rule 10.01", "Definitions"),
        authority_note="Subject to the synthetic transition note.",
    )
    result = decide_hkex_record_identity(
        _request(construction=construction), ExactCharacterCounter()
    )
    seed = result.traceability_seed

    assert seed is not None
    assert seed.referenced_locations == (HKEXReferencedLocation("Rule 10.01", "Definitions"),)
    assert seed.authority_note_fingerprint == _raw_fingerprint(
        "Subject to the synthetic transition note."
    )
    assert "target rule text" not in construction.tree.source_units[1].text


def test_duplicate_exact_payload_or_cross_scope_prior_identity_fails_closed() -> None:
    construction = _construction()
    payload = _payload(construction)
    first = _existing(FIRST_RECORD_ID, payload, selected=True)
    second = _existing(SECOND_RECORD_ID, payload, selected=False)
    with pytest.raises(HKEXRecordIdentityError) as duplicate:
        decide_hkex_record_identity(
            _request(
                construction=construction,
                existing_records=(first, second),
                predecessor_search_record_ids=(FIRST_RECORD_ID,),
                change=HKEXRecordChange.SIX_FIELD_UNCHANGED,
            ),
            ExactCharacterCounter(),
        )
    assert duplicate.value.code is HKEXRecordIdentityErrorCode.IDENTITY

    cross_scope = _existing(
        FIRST_RECORD_ID,
        payload,
        selected=True,
        scope_id=HKEX_GEM_SCOPE_ID,
    )
    with pytest.raises(HKEXRecordIdentityError) as scope:
        _request(
            construction=construction,
            existing_records=(cross_scope,),
            predecessor_search_record_ids=(FIRST_RECORD_ID,),
            change=HKEXRecordChange.SIX_FIELD_UNCHANGED,
        )
    assert scope.value.code is HKEXRecordIdentityErrorCode.IDENTITY


def test_identity_and_traceability_inputs_are_sorted_complete_and_register_shaped() -> None:
    with pytest.raises(HKEXRecordIdentityError) as initial_with_prior:
        _request(existing_records=(_existing(FIRST_RECORD_ID, FINGERPRINT, selected=True),))
    assert initial_with_prior.value.code is HKEXRecordIdentityErrorCode.IDENTITY

    with pytest.raises(HKEXRecordIdentityError) as unissued:
        _request(legal_item_id="component-derived-id")
    assert unissued.value.code is HKEXRecordIdentityErrorCode.IDENTITY

    later = _ref(HKEXTraceabilityReferenceType.SOURCE_SNAPSHOT, "8")
    earlier = _ref(HKEXTraceabilityReferenceType.ARTIFACT, "9")
    with pytest.raises(HKEXRecordIdentityError) as unsorted:
        _request(evidence_refs=(later, earlier))
    assert unsorted.value.code is HKEXRecordIdentityErrorCode.EVIDENCE


def test_request_decoder_rejects_extra_missing_and_mistyped_fields() -> None:
    document = _request().document()
    document["extra"] = True
    with pytest.raises(HKEXRecordIdentityError) as extra:
        hkex_record_identity_request_from_document(document)
    assert extra.value.code is HKEXRecordIdentityErrorCode.CONTRACT

    document = _request().document()
    document.pop("change")
    with pytest.raises(HKEXRecordIdentityError) as missing:
        hkex_record_identity_request_from_document(document)
    assert missing.value.code is HKEXRecordIdentityErrorCode.CONTRACT

    document = _request().document()
    document["part_number"] = True
    with pytest.raises(HKEXRecordIdentityError) as mistyped:
        hkex_record_identity_request_from_document(document)
    assert mistyped.value.code is HKEXRecordIdentityErrorCode.CONTRACT


def test_frozen_record_identity_fixture_reproduces_all_exact_results() -> None:
    fixture = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "fixtures/deterministic/HKREG-RECORD-IDENTITY-FIX-001.json"
            ).read_bytes(),
            max_bytes=4_000_000,
        )
    )
    expected = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "expected/record-identity/HKREG-RECORD-IDENTITY-FIX-001.json"
            ).read_bytes(),
            max_bytes=4_000_000,
        )
    )
    request_schema = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "contracts/schemas/hkex-record-identity-request.schema.json"
            ).read_bytes(),
            max_bytes=4_000_000,
        )
    )
    result_schema = _json_object(
        parse_json_bytes(
            (
                PACKAGE_ROOT / "contracts/schemas/hkex-record-identity-result.schema.json"
            ).read_bytes(),
            max_bytes=4_000_000,
        )
    )
    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator.check_schema(result_schema)
    request_validator = _validator(request_schema)
    result_validator = _validator(result_schema)
    tokenizer = _json_object(fixture["synthetic_tokenizer"])
    assert tokenizer["admitted_for_real_records"] is False
    counter = FrozenFixtureCounter(
        _json_text(tokenizer["profile_id"]),
        _json_text(tokenizer["profile_fingerprint"]),
        _json_text(tokenizer["tokenizer_id"]),
    )
    fixture_cases = _json_array(fixture["cases"])
    expected_cases = _json_array(expected["cases"])
    assert len(fixture_cases) == 8
    actual: list[dict[str, object]] = []
    for raw_case in fixture_cases:
        case = _json_object(raw_case)
        request_document = _json_object(case["request"])
        request_validator.validate(request_document)
        request = hkex_record_identity_request_from_document(request_document)
        assert request.document() == request_document
        result_document = decide_hkex_record_identity(request, counter).document(
            case_id=_json_text(case["case_id"])
        )
        result_validator.validate(result_document)
        actual.append(result_document)

    assert actual == [_json_object(item) for item in expected_cases]


def _raw_fingerprint(value: str) -> str:
    return f"sha256:{sha256(value.encode()).hexdigest()}"


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


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)
