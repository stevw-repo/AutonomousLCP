"""Fail-closed Plan 4 Task 5 Cases record-accounting checkpoint tests."""

from __future__ import annotations

import copy
import inspect
import json
import runpy
from collections.abc import Iterator
from dataclasses import dataclass, fields, replace
from dataclasses import field as dataclass_field
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TypeIs

import asklegal_legal_desks.hk_case_records as hk_case_records_module
import pytest
from asklegal_legal_desks.hk_case_authority_graph import (
    HKCaseAuthorityGraph,
    build_hk_case_authority_graph,
    build_hk_case_authority_propositions,
)
from asklegal_legal_desks.hk_case_judgment import HKCaseJudgmentBundle
from asklegal_legal_desks.hk_case_proposition import (
    HKCaseAdmittedSemanticDecision,
    HKCasePropositionAdmissionResult,
    HKCasePropositionRequestPair,
    admit_hk_case_propositions,
)
from asklegal_legal_desks.hk_case_records import (
    HKCaseListingRecordDisposition,
    HKCaseListingWork,
    HKCaseRecordAccountingError,
    HKCaseRecordAccountingErrorCode,
    HKCaseRecordAccountingRequest,
    HKCaseRecordBlockerCode,
    HKCaseReleaseRunKind,
    account_hk_case_records,
    canonical_hk_case_record_accounting_checkpoint,
    replay_hk_case_record_accounting_checkpoint,
)
from asklegal_legal_desks.model import SemanticTaskProfile

_PROPOSITION_HELPERS: object = runpy.run_path(
    str(Path(__file__).with_name("test_hk_case_proposition.py"))
)
_EXPECTED_BLOCKERS = (
    HKCaseRecordBlockerCode.AUTHENTIC_INVENTORY_NOT_ADMITTED,
    HKCaseRecordBlockerCode.CURRENT_AUTHORITY_NOT_ESTABLISHED,
    HKCaseRecordBlockerCode.REGISTER_IDENTITY_ISSUANCE_UNAVAILABLE,
    HKCaseRecordBlockerCode.SEMANTIC_WORKFLOW_NOT_ADMITTED,
)


def _is_object_dictionary(value: object) -> TypeIs[dict[object, object]]:
    return type(value) is dict


def _is_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _helper(name: str) -> object:
    if not _is_object_dictionary(_PROPOSITION_HELPERS) or name not in _PROPOSITION_HELPERS:
        raise TypeError(name)
    return _PROPOSITION_HELPERS[name]


def _bundle(*, majority_text: str = "FULL JUDGMENT FIXTURE MARKER") -> HKCaseJudgmentBundle:
    factory = _helper("_bundle")
    if not callable(factory):
        raise TypeError
    result: object = factory(majority_text=majority_text)
    if type(result) is not HKCaseJudgmentBundle:
        raise TypeError
    return result


def _profiles() -> tuple[SemanticTaskProfile, SemanticTaskProfile]:
    factory = _helper("_profiles")
    if not callable(factory):
        raise TypeError
    result: object = factory()
    if not _is_object_tuple(result) or len(result) != 2:
        raise TypeError
    first, second = result
    if type(first) is not SemanticTaskProfile or type(second) is not SemanticTaskProfile:
        raise TypeError
    return first, second


def _admission(
    *, zero: bool = False
) -> tuple[HKCaseJudgmentBundle, HKCasePropositionAdmissionResult]:
    bundle = _bundle()
    pair_factory = _helper("_build")
    decision_factory = _helper("_admitted")
    if not callable(pair_factory) or not callable(decision_factory):
        raise TypeError
    pair: object = pair_factory(bundle, _profiles())
    if type(pair) is not HKCasePropositionRequestPair:
        raise TypeError
    decision: object = decision_factory(pair, propositions=() if zero else None)
    if type(decision) is not HKCaseAdmittedSemanticDecision:
        raise TypeError
    return bundle, admit_hk_case_propositions(pair, decision)


def _graph(admissions: tuple[HKCasePropositionAdmissionResult, ...]) -> HKCaseAuthorityGraph:
    propositions = tuple(
        proposition
        for admission in admissions
        for proposition in build_hk_case_authority_propositions(admission)
    )
    return build_hk_case_authority_graph(propositions, (), (), "2026-08-25")


class _Court(StrEnum):
    CFA = "CFA"
    CA = "CA"


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class _InventoryEntry:
    listing_identity: str
    court_family: _Court
    decision_date: str
    listing_fact_fingerprint: str

    def __post_init__(self) -> None:
        expected = _fingerprint(
            {
                "court_family": self.court_family.value,
                "decision_date": self.decision_date,
                "listing_identity": self.listing_identity,
            }
        )
        if self.listing_fact_fingerprint != expected:
            raise TypeError

    @classmethod
    def create(cls, listing_identity: str, court_family: _Court) -> _InventoryEntry:
        return cls(
            listing_identity,
            court_family,
            "2020-01-02",
            _fingerprint(
                {
                    "court_family": court_family.value,
                    "decision_date": "2020-01-02",
                    "listing_identity": listing_identity,
                }
            ),
        )


_INVENTORY_AUTHORITY = object()


@dataclass(frozen=True, slots=True)
class _Inventory:
    court_family: _Court
    earliest_decision_date: str
    observation_cutoff: str
    entries: tuple[_InventoryEntry, ...]
    inventory_fingerprint: str
    _authority: object | None = dataclass_field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        for entry in self.entries:
            entry.__post_init__()
        expected = _fingerprint(
            {
                "court_family": self.court_family.value,
                "earliest_decision_date": self.earliest_decision_date,
                "entries": [entry.listing_fact_fingerprint for entry in self.entries],
                "observation_cutoff": self.observation_cutoff,
            }
        )
        if (
            self.entries != tuple(sorted(self.entries, key=lambda item: item.listing_identity))
            or self.inventory_fingerprint != expected
        ):
            raise TypeError

    def assert_enumerator_issued(self) -> None:
        if self._authority is not _INVENTORY_AUTHORITY:
            raise TypeError

    @classmethod
    def create(cls, court_family: _Court, entries: tuple[_InventoryEntry, ...]) -> _Inventory:
        ordered = tuple(sorted(entries, key=lambda item: item.listing_identity))
        result = cls(
            court_family,
            "1997-07-01",
            "2026-08-25T00:00:00Z",
            ordered,
            _fingerprint(
                {
                    "court_family": court_family.value,
                    "earliest_decision_date": "1997-07-01",
                    "entries": [entry.listing_fact_fingerprint for entry in ordered],
                    "observation_cutoff": "2026-08-25T00:00:00Z",
                }
            ),
        )
        object.__setattr__(result, "_authority", _INVENTORY_AUTHORITY)
        return result


def _structural_inventory(
    *listing_ids: str,
    court_family: _Court = _Court.CFA,
) -> _Inventory:
    return _Inventory.create(
        court_family,
        tuple(_InventoryEntry.create(listing_id, court_family) for listing_id in listing_ids),
    )


def _inventory(
    *listing_ids: str,
    court_family: _Court = _Court.CFA,
) -> bytes:
    inventory = _structural_inventory(*listing_ids, court_family=court_family)
    facts: dict[str, object] = {
        "schema_id": "asklegal.hk-judiciary-accounting-projection/v1",
        "source_inventory_fingerprint": inventory.inventory_fingerprint,
        "court_family": inventory.court_family.value,
        "earliest_decision_date": inventory.earliest_decision_date,
        "observation_cutoff": inventory.observation_cutoff,
        "entries": [
            {
                "listing_identity": entry.listing_identity,
                "court_family": entry.court_family.value,
                "decision_date": entry.decision_date,
                "listing_fact_fingerprint": entry.listing_fact_fingerprint,
            }
            for entry in inventory.entries
        ],
    }
    facts["projection_fingerprint"] = _fingerprint(facts)
    return json.dumps(facts, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _request(
    *,
    run_kind: HKCaseReleaseRunKind = HKCaseReleaseRunKind.INITIAL,
    prior_release_id: str | None = None,
) -> HKCaseRecordAccountingRequest:
    return HKCaseRecordAccountingRequest(
        scope_id="hk_cases_cfa_2020",
        court_family="CFA",
        calendar_year=2020,
        observation_cutoff="2026-08-25T00:00:00Z",
        run_kind=run_kind,
        prior_release_id=prior_release_id,
    )


def _complete_checkpoint(*, zero: bool = False):
    bundle, admission = _admission(zero=zero)
    return account_hk_case_records(
        _request(),
        _inventory("listing-current"),
        (HKCaseListingWork("listing-current", bundle, admission, ()),),
        _graph((admission,)),
    )


def _account_inventory_object(projection: object) -> object:
    return _invoke_account(account_hk_case_records, projection)


def _invoke_account(entrypoint: object, projection: object) -> object:
    if not callable(entrypoint):
        raise TypeError
    return entrypoint(_request(), projection, (), _graph(()))


def test_task5_rejects_permanent_bundle_replacement_during_task1_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 1 replay cannot replace submitted bundle A with coherent bundle B."""
    submitted = _bundle(majority_text="SUBMITTED BUNDLE A")
    replacement = _bundle(majority_text="REPLACEMENT BUNDLE B")
    submitted_fingerprint = submitted.bundle_fingerprint
    replacement_fingerprint = replacement.bundle_fingerprint
    original_post_init = HKCaseJudgmentBundle.__post_init__

    def replace_during_replay(bundle: HKCaseJudgmentBundle) -> None:
        if bundle is submitted:
            for field in fields(HKCaseJudgmentBundle):
                object.__setattr__(bundle, field.name, getattr(replacement, field.name))
        original_post_init(bundle)

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", replace_during_replay)

    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", submitted, None, ("gap:semantic",)),),
            _graph(()),
        )

    assert submitted_fingerprint != replacement_fingerprint
    assert submitted.bundle_fingerprint == replacement_fingerprint
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_uses_precaptured_request_when_task1_replay_mutates_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reentrant replay cannot rewrite the submitted year, scope, or cutoff."""
    request = _request()
    bundle = _bundle()
    original_post_init = HKCaseJudgmentBundle.__post_init__

    def mutate_request(submitted: HKCaseJudgmentBundle) -> None:
        object.__setattr__(request, "calendar_year", 2021)
        object.__setattr__(request, "scope_id", "hk_cases_cfa_2021")
        object.__setattr__(request, "observation_cutoff", "2026-08-26T00:00:00Z")
        original_post_init(submitted)

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", mutate_request)
    result = account_hk_case_records(
        request,
        _inventory("listing-current"),
        (HKCaseListingWork("listing-current", bundle, None, ("gap:semantic",)),),
        _graph(()),
    )

    assert request.calendar_year == 2021
    assert result.calendar_year == 2020
    assert result.scope_id == "hk_cases_cfa_2020"
    assert result.observation_cutoff == "2026-08-25T00:00:00Z"
    assert result.listing_count == 1


def test_task5_rejects_listing_tuple_mutation_during_task1_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-checking caller facts rejects replacement of a precaptured work row."""
    bundle = _bundle()
    work = HKCaseListingWork("listing-current", bundle, None, ("gap:semantic",))
    original_post_init = HKCaseJudgmentBundle.__post_init__

    def mutate_work(submitted: HKCaseJudgmentBundle) -> None:
        object.__setattr__(work, "listing_id", "listing-mutated")
        object.__setattr__(work, "blocking_refs", ("gap:mutated",))
        original_post_init(submitted)

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", mutate_work)
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(_request(), _inventory("listing-current"), (work,), _graph(()))

    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_captures_later_row_before_nested_task3_behavior_can_mutate_it() -> None:
    """Row 1 nested behavior cannot replace row 2 before its first snapshot."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    original_pair = admission.request_pair
    later = HKCaseListingWork("listing-later", None, None, ("gap:A",))

    class _ReentrantPair:
        judgment_fingerprint = original_pair.judgment_fingerprint

        @property
        def decision(self) -> object:
            object.__setattr__(later, "blocking_refs", ("gap:B",))
            object.__setattr__(admission, "request_pair", original_pair)
            return original_pair.decision

    object.__setattr__(admission, "request_pair", _ReentrantPair())

    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current", "listing-later"),
            (
                HKCaseListingWork("listing-current", bundle, admission, ()),
                later,
            ),
            graph,
        )

    assert later.blocking_refs == ("gap:A",)
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_rejects_later_row_mutation_from_nested_task3_fingerprint_property() -> None:
    """A second nested pair field cannot rewrite a later uncaptured row."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    original_pair = admission.request_pair
    later = HKCaseListingWork("listing-later", None, None, ("gap:A",))

    class _ReentrantPair:
        decision = original_pair.decision

        @property
        def judgment_fingerprint(self) -> object:
            object.__setattr__(later, "blocking_refs", ("gap:B",))
            object.__setattr__(admission, "request_pair", original_pair)
            return original_pair.judgment_fingerprint

    object.__setattr__(admission, "request_pair", _ReentrantPair())

    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current", "listing-later"),
            (
                HKCaseListingWork("listing-current", bundle, admission, ()),
                later,
            ),
            graph,
        )

    assert later.blocking_refs == ("gap:A",)
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_two_row_transient_replay_mutation_uses_precaptured_later_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A-to-B-to-A replay cannot change the detached later-row accounting."""
    bundle = _bundle()
    later = HKCaseListingWork("listing-later", None, None, ("gap:A",))
    original_post_init = HKCaseJudgmentBundle.__post_init__

    def mutate_and_restore(submitted: HKCaseJudgmentBundle) -> None:
        object.__setattr__(later, "blocking_refs", ("gap:B",))
        original_post_init(submitted)
        object.__setattr__(later, "blocking_refs", ("gap:A",))

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", mutate_and_restore)
    result = account_hk_case_records(
        _request(),
        _inventory("listing-current", "listing-later"),
        (
            HKCaseListingWork("listing-current", bundle, None, ("gap:semantic",)),
            later,
        ),
        _graph(()),
    )

    assert result.listing_accounting[1].blocking_refs == ("gap:A",)


def test_task5_validates_detached_task1_a_before_live_replay_can_substitute_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid submitted A cannot borrow a transient valid Task 1 replay as B."""
    submitted = _bundle(majority_text="INVALID SUBMITTED A")
    replacement = _bundle(majority_text="VALID TRANSIENT B")
    object.__setattr__(submitted, "bundle_fingerprint", "sha256:" + "0" * 64)
    submitted_fields = tuple(
        (field.name, getattr(submitted, field.name)) for field in fields(HKCaseJudgmentBundle)
    )
    original_post_init = HKCaseJudgmentBundle.__post_init__

    def validate_b_then_restore_a(bundle: HKCaseJudgmentBundle) -> None:
        if bundle is submitted:
            for field in fields(HKCaseJudgmentBundle):
                object.__setattr__(bundle, field.name, getattr(replacement, field.name))
            original_post_init(bundle)
            for name, value in submitted_fields:
                object.__setattr__(bundle, name, value)
        else:
            original_post_init(bundle)

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", validate_b_then_restore_a)
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", submitted, None, ("gap:semantic",)),),
            _graph(()),
        )

    assert submitted.bundle_fingerprint == "sha256:" + "0" * 64
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_validates_detached_task3_a_before_live_replay_can_substitute_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid submitted A cannot borrow a transient valid Task 3 replay as B."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    valid_fingerprint = admission.admission_fingerprint
    invalid_fingerprint = "sha256:" + "0" * 64
    object.__setattr__(admission, "admission_fingerprint", invalid_fingerprint)
    original_post_init = HKCasePropositionAdmissionResult.__post_init__

    def validate_b_then_restore_a(result: HKCasePropositionAdmissionResult) -> None:
        if result is admission:
            object.__setattr__(result, "admission_fingerprint", valid_fingerprint)
            original_post_init(result)
            object.__setattr__(result, "admission_fingerprint", invalid_fingerprint)
        else:
            original_post_init(result)

    monkeypatch.setattr(
        HKCasePropositionAdmissionResult,
        "__post_init__",
        validate_b_then_restore_a,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert admission.admission_fingerprint == invalid_fingerprint
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_validates_detached_task4_a_before_live_replay_can_substitute_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid submitted graph A cannot borrow a transient issued replay as B."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    invalid_edges = ("edge-invalid-a",)
    object.__setattr__(graph, "quarantined_edge_ids", invalid_edges)
    original_replay = hk_case_records_module.replay_hk_case_authority_graph

    def validate_b_then_restore_a(submitted: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
        object.__setattr__(submitted, "quarantined_edge_ids", ())
        try:
            return original_replay(submitted)
        finally:
            object.__setattr__(submitted, "quarantined_edge_ids", invalid_edges)

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_authority_graph",
        validate_b_then_restore_a,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert graph.quarantined_edge_ids == invalid_edges
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID


def test_task5_rejects_same_byte_nonissued_graph_witness_before_live_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching graph bytes cannot replace the captured factory-issued witness."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    issued = graph.issuance
    if issued is None:
        raise TypeError
    forged = type(issued)(issued.kind, issued.projection)
    object.__setattr__(graph, "issuance", forged)
    original_replay = hk_case_records_module.replay_hk_case_authority_graph

    def borrow_issued_then_restore(submitted: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
        object.__setattr__(submitted, "issuance", issued)
        try:
            return original_replay(submitted)
        finally:
            object.__setattr__(submitted, "issuance", forged)

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_authority_graph",
        borrow_issued_then_restore,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert graph.issuance is forged
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID


def test_task5_rejects_same_byte_nonissued_selection_witness_before_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching selection bytes cannot replace its captured factory witness."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    selection = graph.selections[0]
    issued = selection.issuance
    if issued is None:
        raise TypeError
    forged = type(issued)(issued.kind, issued.projection)
    object.__setattr__(selection, "issuance", forged)
    original_replay = hk_case_records_module.replay_hk_case_authority_graph

    def borrow_issued_then_restore(submitted: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
        object.__setattr__(selection, "issuance", issued)
        try:
            return original_replay(submitted)
        finally:
            object.__setattr__(selection, "issuance", forged)

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_authority_graph",
        borrow_issued_then_restore,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert selection.issuance is forged
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID


def test_task5_rejects_same_byte_nonissued_admission_witness_before_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching Task 3 bytes cannot replace its captured factory witness."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    issued = admission.issuance
    forged = type(issued)(issued.projection)
    object.__setattr__(admission, "issuance", forged)
    original_post_init = HKCasePropositionAdmissionResult.__post_init__

    def borrow_issued_then_restore(result: HKCasePropositionAdmissionResult) -> None:
        if result is admission:
            object.__setattr__(result, "issuance", issued)
            try:
                original_post_init(result)
            finally:
                object.__setattr__(result, "issuance", forged)
        else:
            original_post_init(result)

    monkeypatch.setattr(
        HKCasePropositionAdmissionResult,
        "__post_init__",
        borrow_issued_then_restore,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert admission.issuance is forged
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_rejects_cross_row_admission_witness_alias_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One process-local Task 3 witness tree cannot back two work rows."""
    bundle, admission = _admission()
    graph = _graph((admission,))

    def validation_must_not_run(self: HKCasePropositionAdmissionResult) -> None:
        del self
        raise KeyboardInterrupt

    monkeypatch.setattr(
        HKCasePropositionAdmissionResult,
        "__post_init__",
        validation_must_not_run,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current", "listing-later"),
            (
                HKCaseListingWork("listing-current", bundle, admission, ()),
                HKCaseListingWork("listing-later", None, admission, ()),
            ),
            graph,
        )

    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_preserves_baseexception_from_captured_witness_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process control from owner-side witness validation remains visible."""

    def interrupt(_: object, __: str, ___: bytes) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        hk_case_records_module,
        "_AUTHORITY_OUTPUT_ISSUANCE_VALIDATOR",
        interrupt,
    )
    with pytest.raises(KeyboardInterrupt):
        account_hk_case_records(_request(), _inventory(), (), _graph(()))


def test_task5_rejects_permanent_equal_admission_result_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A byte-equal non-issued result cannot replace captured admission A."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    work = HKCaseListingWork("listing-current", bundle, admission, ())
    clone = object.__new__(HKCasePropositionAdmissionResult)
    for item in fields(HKCasePropositionAdmissionResult):
        object.__setattr__(clone, item.name, object.__getattribute__(admission, item.name))
    original = hk_case_records_module.replay_hk_case_proposition_admission_projection

    def replace_then_replay(
        pair: HKCasePropositionRequestPair,
        decision: HKCaseAdmittedSemanticDecision,
    ) -> bytes:
        object.__setattr__(work, "admission", clone)
        return original(pair, decision)

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_proposition_admission_projection",
        replace_then_replay,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(_request(), _inventory("listing-current"), (work,), graph)

    assert work.admission is clone
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_rejects_permanent_equal_issued_selection_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A separately issued equal selection cannot replace captured selection A."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    replacement = _graph((admission,)).selections[0]
    original = hk_case_records_module.replay_hk_case_proposition_admission_projection

    def replace_then_replay(
        pair: HKCasePropositionRequestPair,
        decision: HKCaseAdmittedSemanticDecision,
    ) -> bytes:
        object.__setattr__(graph, "selections", (replacement,))
        return original(pair, decision)

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_proposition_admission_projection",
        replace_then_replay,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert graph.selections[0] is replacement
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID


def test_task5_validates_detached_task4_selection_before_transient_restoration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A captured invalid authority-note fact cannot borrow a valid live replay."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    selection = graph.selections[0]
    object.__setattr__(selection, "authority_note_required", True)
    original_replay = hk_case_records_module.replay_hk_case_authority_graph

    def validate_b_then_restore_a(submitted: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
        object.__setattr__(selection, "authority_note_required", False)
        try:
            return original_replay(submitted)
        finally:
            object.__setattr__(selection, "authority_note_required", True)

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_authority_graph",
        validate_b_then_restore_a,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert selection.authority_note_required is True
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("selection", "proposition_id", "proposition_forged"),
        ("selection_issuance", "projection", b"forged-selection-projection"),
        ("graph_issuance", "projection", b"forged-graph-projection"),
    ],
)
def test_task5_rejects_invalid_detached_task4_inventory_before_live_replay(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    field: str,
    value: object,
) -> None:
    """Detached proposition and issuance facts must fail before provenance replay."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    selection = graph.selections[0]
    targets: dict[str, object] = {
        "selection": selection,
        "selection_issuance": selection.issuance,
        "graph_issuance": graph.issuance,
    }
    object.__setattr__(targets[target], field, value)

    def replay_must_not_run(_: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_authority_graph",
        replay_must_not_run,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert rejected.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID


def test_task5_rejects_permanent_task4_drift_after_live_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid detached A rejects when provenance replay permanently leaves graph B."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    original_replay = hk_case_records_module.replay_hk_case_authority_graph

    def replay_then_drift(submitted: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
        replayed = original_replay(submitted)
        object.__setattr__(submitted, "quarantined_edge_ids", ("edge-drift-b",))
        return replayed

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_authority_graph",
        replay_then_drift,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert graph.quarantined_edge_ids == ("edge-drift-b",)
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID


def test_task5_rejects_repeated_task4_selection_alias_before_live_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One selection object cannot occupy two graph inventory positions."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    selection = graph.selections[0]
    object.__setattr__(graph, "selections", (selection, selection))

    def replay_must_not_run(_: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_authority_graph",
        replay_must_not_run,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, admission, ()),),
            graph,
        )

    assert rejected.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID


def test_task5_rejects_cross_row_bundle_alias_before_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One live Task 1 object cannot stand behind two submitted work rows."""
    shared = _bundle()

    def replay_must_not_run(self: HKCaseJudgmentBundle) -> None:
        del self
        raise KeyboardInterrupt

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", replay_must_not_run)
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current", "listing-later"),
            (
                HKCaseListingWork("listing-current", shared, None, ("gap:semantic",)),
                HKCaseListingWork("listing-later", shared, None, ("gap:semantic",)),
            ),
            _graph(()),
        )

    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_rejects_nested_sequence_and_equality_traps_without_dispatch() -> None:
    """Non-exact containers reject before iteration or equality can run callbacks."""
    bundle, admission = _admission()
    graph = _graph((admission,))
    later = HKCaseListingWork("listing-later", None, None, ("gap:A",))

    class _TrapTuple(tuple[object, ...]):
        __slots__ = ()

        def __hash__(self) -> int:
            return 1

        def __iter__(self) -> Iterator[object]:
            object.__setattr__(later, "blocking_refs", ("gap:iterated",))
            raise KeyboardInterrupt

        def __eq__(self, other: object) -> bool:
            del other
            object.__setattr__(later, "blocking_refs", ("gap:compared",))
            raise KeyboardInterrupt

    object.__setattr__(admission, "propositions", _TrapTuple(admission.propositions))

    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(
            _request(),
            _inventory("listing-current", "listing-later"),
            (
                HKCaseListingWork("listing-current", bundle, admission, ()),
                later,
            ),
            graph,
        )

    assert later.blocking_refs == ("gap:A",)
    assert rejected.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_transient_bundle_a_b_a_cannot_influence_detached_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient valid B is harmless because accounting uses only precaptured A."""
    submitted = _bundle(majority_text="SUBMITTED BUNDLE A")
    replacement = _bundle(majority_text="TRANSIENT BUNDLE B")
    original_fields = tuple(
        (field.name, getattr(submitted, field.name)) for field in fields(HKCaseJudgmentBundle)
    )
    original_post_init = HKCaseJudgmentBundle.__post_init__

    def change_and_restore(bundle: HKCaseJudgmentBundle) -> None:
        if bundle is submitted:
            for field in fields(HKCaseJudgmentBundle):
                object.__setattr__(bundle, field.name, getattr(replacement, field.name))
            original_post_init(bundle)
            for name, value in original_fields:
                object.__setattr__(bundle, name, value)
        else:
            original_post_init(bundle)

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", change_and_restore)
    result = account_hk_case_records(
        _request(),
        _inventory("listing-current"),
        (HKCaseListingWork("listing-current", submitted, None, ("gap:semantic",)),),
        _graph(()),
    )

    assert result.listing_accounting[0].bundle_fingerprint == submitted.bundle_fingerprint
    assert b"TRANSIENT BUNDLE B" not in canonical_hk_case_record_accounting_checkpoint(result)


@pytest.mark.parametrize(
    "projection",
    [
        bytearray(_inventory()),
        b'{"schema_id":"a","schema_id":"b"}',
        _inventory("listing-b", "listing-a"),
    ],
)
def test_task5_rejects_malformed_or_non_exact_inventory_projection(
    projection: object,
) -> None:
    """Only exact canonical bytes with closed, internally bound facts are accepted."""
    if type(projection) is bytes and b"listing-b" in projection:
        document = json.loads(projection)
        document["entries"] = list(reversed(document["entries"]))
        projection = json.dumps(
            document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        _account_inventory_object(projection)

    assert rejected.value.code is HKCaseRecordAccountingErrorCode.INVENTORY_INVALID


def test_task5_rejects_forged_inventory_projection_fingerprint() -> None:
    projection = _inventory("listing-current")
    document = json.loads(projection)
    document["projection_fingerprint"] = "sha256:" + "f" * 64
    forged = json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()

    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(_request(), forged, (), _graph(()))

    assert rejected.value.code is HKCaseRecordAccountingErrorCode.INVENTORY_INVALID


def test_task5_rejects_request_subclasses_before_projection_parsing() -> None:
    """Only the exact request type can cross the pure byte boundary."""

    class _RequestSubclass(HKCaseRecordAccountingRequest):
        pass

    request = _RequestSubclass(
        "hk_cases_cfa_2020",
        "CFA",
        2020,
        "2026-08-25T00:00:00Z",
        HKCaseReleaseRunKind.INITIAL,
        None,
    )
    with pytest.raises(HKCaseRecordAccountingError) as rejected:
        account_hk_case_records(request, _inventory(), (), _graph(()))

    assert rejected.value.code is HKCaseRecordAccountingErrorCode.REQUEST_INVALID


def test_task5_accounts_each_scoped_inventory_listing_exactly_once() -> None:
    """Dropping or duplicating a scoped row must break exact listing accounting."""
    bundle, admission = _admission()

    result = account_hk_case_records(
        _request(),
        _inventory("listing-current", "listing-blocked"),
        (
            HKCaseListingWork("listing-blocked", None, None, ("gap:artifact",)),
            HKCaseListingWork("listing-current", bundle, admission, ()),
        ),
        _graph((admission,)),
    )

    assert result.listing_count == result.disposition_count == 2
    assert tuple(row.listing_id for row in result.listing_accounting) == (
        "listing-blocked",
        "listing-current",
    )
    assert tuple(row.disposition for row in result.listing_accounting) == (
        HKCaseListingRecordDisposition.JUDGMENT_BUNDLE_BLOCKED,
        HKCaseListingRecordDisposition.AUTHORITY_QUARANTINED,
    )
    assert result.blocked_listing_ids == ("listing-blocked",)
    assert result.quarantine_listing_ids == ("listing-current",)
    assert result.blockers == _EXPECTED_BLOCKERS
    assert result.listing_accounting[1].evidence_refs


def test_task5_rejects_missing_duplicate_and_extraneous_listing_work() -> None:
    """Missing, duplicate, and foreign listing work remain distinct closed failures."""
    inventory = _inventory("listing-current")
    graph = _graph(())
    with pytest.raises(HKCaseRecordAccountingError) as missing:
        account_hk_case_records(_request(), inventory, (), graph)
    assert missing.value.code is HKCaseRecordAccountingErrorCode.LISTING_ACCOUNTING_INCOMPLETE

    blocked = HKCaseListingWork("listing-current", None, None, ("gap:artifact",))
    with pytest.raises(HKCaseRecordAccountingError) as duplicate:
        account_hk_case_records(_request(), inventory, (blocked, blocked), graph)
    assert duplicate.value.code is HKCaseRecordAccountingErrorCode.LISTING_ACCOUNTING_DUPLICATE

    with pytest.raises(HKCaseRecordAccountingError) as extra:
        account_hk_case_records(
            _request(),
            inventory,
            (blocked, HKCaseListingWork("listing-extra", None, None, ("gap:extra",))),
            graph,
        )
    assert extra.value.code is HKCaseRecordAccountingErrorCode.LISTING_ACCOUNTING_EXTRANEOUS


def test_task5_initial_predecessor_is_optional_and_changed_requires_one() -> None:
    """Initial and changed attempts preserve opposite predecessor requirements."""
    assert _request().prior_release_id is None
    with pytest.raises(HKCaseRecordAccountingError) as initial:
        _request(prior_release_id="rel_prior")
    assert initial.value.code is HKCaseRecordAccountingErrorCode.REQUEST_INVALID

    with pytest.raises(HKCaseRecordAccountingError) as changed:
        _request(run_kind=HKCaseReleaseRunKind.CHANGED)
    assert changed.value.code is HKCaseRecordAccountingErrorCode.REQUEST_INVALID

    changed_request = _request(run_kind=HKCaseReleaseRunKind.CHANGED, prior_release_id="rel_prior")
    assert changed_request.prior_release_id == "rel_prior"


def test_task5_complete_zero_is_only_a_listing_disposition() -> None:
    """A valid zero judgment never becomes an empty complete release."""
    result = _complete_checkpoint(zero=True)

    assert result.zero_proposition_count == 1
    assert result.quarantine_listing_ids == ()
    assert result.listing_accounting[0].disposition is (
        HKCaseListingRecordDisposition.COMPLETE_ZERO_PROPOSITIONS
    )
    assert result.blockers == _EXPECTED_BLOCKERS
    assert not any(name in {"release", "records", "ready"} for name in result.__slots__)


def test_task5_missing_semantic_admission_preserves_evidence_and_blocks_listing() -> None:
    """Missing Task 3 authority must preserve evidence while withholding the listing."""
    bundle = _bundle()

    result = account_hk_case_records(
        _request(),
        _inventory("listing-current"),
        (HKCaseListingWork("listing-current", bundle, None, ("gap:semantic",)),),
        _graph(()),
    )

    row = result.listing_accounting[0]
    assert row.disposition is HKCaseListingRecordDisposition.PROPOSITION_ADMISSION_BLOCKED
    assert row.evidence_refs == (
        "evidence/artifact-dissent",
        "evidence/artifact-majority",
        "evidence/artifact-translation",
    )
    assert row.blocking_refs == ("gap:semantic",)
    assert result.blocked_listing_ids == ("listing-current",)


def test_task5_changed_attempt_preserves_predecessor_but_still_cannot_release() -> None:
    """A predecessor reference cannot unlock the unavailable changed-release path."""
    result = account_hk_case_records(
        _request(run_kind=HKCaseReleaseRunKind.CHANGED, prior_release_id="rel_prior"),
        _inventory("listing-current"),
        (HKCaseListingWork("listing-current", None, None, ("gap:artifact",)),),
        _graph(()),
    )

    assert result.run_kind is HKCaseReleaseRunKind.CHANGED
    assert result.prior_release_id == "rel_prior"
    assert result.blockers == _EXPECTED_BLOCKERS


def test_task5_task4_quarantine_never_becomes_a_record_candidate() -> None:
    """Task 4 quarantine cannot acquire a record or release surface."""
    result = _complete_checkpoint()
    row = result.listing_accounting[0]

    assert row.proposition_ids == ("proposition_fixture",)
    assert row.quarantined_proposition_ids == row.proposition_ids
    assert row.disposition is HKCaseListingRecordDisposition.AUTHORITY_QUARANTINED
    forbidden = {
        "record",
        "records",
        "record_id",
        "release",
        "release_id",
        "traceability_entries",
        "ready",
    }
    assert forbidden.isdisjoint(field.name for field in fields(type(result)))
    assert forbidden.isdisjoint(field.name for field in fields(type(row)))


def test_task5_rejects_reconstructed_task3_output() -> None:
    """Caller reconstruction cannot replace Task 3 issuance."""
    _, admission = _admission()
    with pytest.raises(TypeError, match="HK_CASE_PROPOSITION_ADMISSION_NOT_SERIALIZABLE"):
        copy.copy(admission)


def test_task5_separates_scope_work_proposition_and_graph_failures() -> None:
    """Distinct trust-boundary defects must retain their exact closed codes."""
    with pytest.raises(HKCaseRecordAccountingError) as scope:
        account_hk_case_records(
            _request(),
            _inventory("listing-current", court_family=_Court.CA),
            (HKCaseListingWork("listing-current", None, None, ("gap:artifact",)),),
            _graph(()),
        )
    assert scope.value.code is HKCaseRecordAccountingErrorCode.INVENTORY_SCOPE_MISMATCH

    bundle, admission = _admission()
    work = (HKCaseListingWork("listing-current", bundle, admission, ()),)
    with pytest.raises(HKCaseRecordAccountingError) as propositions:
        account_hk_case_records(_request(), _inventory("listing-current"), work, _graph(()))
    assert propositions.value.code is (
        HKCaseRecordAccountingErrorCode.PROPOSITION_ACCOUNTING_INCOMPLETE
    )

    graph = _graph((admission,))
    object.__setattr__(graph, "selections", ())
    with pytest.raises(HKCaseRecordAccountingError) as graph_error:
        account_hk_case_records(_request(), _inventory("listing-current"), work, graph)
    assert graph_error.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID

    _, changed_admission = _admission()
    object.__setattr__(changed_admission, "admission_fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(HKCaseRecordAccountingError) as work_error:
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, changed_admission, ()),),
            _graph(()),
        )
    assert work_error.value.code is HKCaseRecordAccountingErrorCode.LISTING_WORK_INVALID


def test_task5_checkpoint_direct_replace_copy_and_replay_are_coherent() -> None:
    """Every reconstruction path reruns the exact checkpoint invariants."""
    result = _complete_checkpoint()

    assert replace(result) == result
    assert copy.copy(result) == result
    assert copy.deepcopy(result) == result
    assert replay_hk_case_record_accounting_checkpoint(result) is result

    object.__setattr__(result, "listing_count", 2)
    with pytest.raises(HKCaseRecordAccountingError) as mutated:
        replay_hk_case_record_accounting_checkpoint(result)
    assert mutated.value.code is HKCaseRecordAccountingErrorCode.CHECKPOINT_INVALID


def test_task5_equivalent_path_distinct_inputs_are_deterministic() -> None:
    """Fresh equivalent Task 1-4 objects must freeze identical negative bytes."""
    first = _complete_checkpoint()
    second = _complete_checkpoint()

    assert first.checkpoint_fingerprint == second.checkpoint_fingerprint
    assert canonical_hk_case_record_accounting_checkpoint(first) == (
        canonical_hk_case_record_accounting_checkpoint(second)
    )


def test_task5_checkpoint_contains_no_full_judgment_text_or_bytes() -> None:
    """Evidence text can be inspected upstream but cannot survive the checkpoint."""
    result = _complete_checkpoint()
    encoded = canonical_hk_case_record_accounting_checkpoint(result)

    assert b"FULL JUDGMENT FIXTURE MARKER" not in encoded
    assert b"paragraph" not in encoded.lower()
    assert b'"text"' not in encoded.lower()
    assert all(
        field.name not in {"judgment", "opinion", "paragraphs", "text", "bytes"}
        for field in fields(type(result))
    )
    assert all(
        field.name not in {"judgment", "opinion", "paragraphs", "text", "bytes"}
        for field in fields(type(result.listing_accounting[0]))
    )
    json.loads(encoded)


def test_task5_output_is_detached_from_later_full_judgment_mutation() -> None:
    """Later mutation of caller-held evidence cannot rewrite checkpoint bytes."""
    bundle, admission = _admission()
    result = account_hk_case_records(
        _request(),
        _inventory("listing-current"),
        (HKCaseListingWork("listing-current", bundle, admission, ()),),
        _graph((admission,)),
    )
    before = canonical_hk_case_record_accounting_checkpoint(result)
    if bundle.judgment is None:
        raise TypeError
    paragraph = bundle.judgment.opinions[0].paragraphs[0]

    object.__setattr__(paragraph, "text", "CHANGED FULL JUDGMENT TEXT")

    assert canonical_hk_case_record_accounting_checkpoint(result) == before
    assert b"CHANGED FULL JUDGMENT TEXT" not in before


def test_task5_api_accepts_no_caller_identity_or_readiness_authority() -> None:
    """No caller parameter can manufacture register issuance or readiness."""
    parameters = inspect.signature(account_hk_case_records).parameters
    forbidden = {"identities", "issued", "record_id", "release_id", "ready", "admitted"}

    assert forbidden.isdisjoint(parameters)
    assert forbidden.isdisjoint(field.name for field in fields(HKCaseRecordAccountingRequest))


def test_task5_normalizes_ordinary_errors_but_leaves_baseexception_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Data failures close while process-control exceptions remain observable."""
    with pytest.raises(HKCaseRecordAccountingError) as ordinary:
        account_hk_case_records(_request(), b"not-json", (), _graph(()))
    assert ordinary.value.code is HKCaseRecordAccountingErrorCode.INVENTORY_INVALID

    bundle = _bundle()

    def interrupt_replay(self: HKCaseJudgmentBundle) -> None:
        del self
        raise KeyboardInterrupt

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", interrupt_replay)
    with pytest.raises(KeyboardInterrupt):
        account_hk_case_records(
            _request(),
            _inventory("listing-current"),
            (HKCaseListingWork("listing-current", bundle, None, ("gap:semantic",)),),
            _graph(()),
        )


def test_task5_graph_replay_normalizes_exception_but_preserves_baseexception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live graph provenance closes ordinary errors and exposes process control."""
    graph = _graph(())

    def fail_ordinary(_: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
        raise ValueError

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_authority_graph",
        fail_ordinary,
    )
    with pytest.raises(HKCaseRecordAccountingError) as ordinary:
        account_hk_case_records(_request(), _inventory(), (), graph)
    assert ordinary.value.code is HKCaseRecordAccountingErrorCode.AUTHORITY_GRAPH_INVALID

    def interrupt(_: HKCaseAuthorityGraph) -> HKCaseAuthorityGraph:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        hk_case_records_module,
        "replay_hk_case_authority_graph",
        interrupt,
    )
    with pytest.raises(KeyboardInterrupt):
        account_hk_case_records(_request(), _inventory(), (), graph)
