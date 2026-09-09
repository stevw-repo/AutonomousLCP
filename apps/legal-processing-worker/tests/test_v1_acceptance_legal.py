"""Focused positive two-family Legal acceptance tests."""

from __future__ import annotations

import re
import runpy
import shutil
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol, TypeGuard, TypeIs, runtime_checkable

import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import (
    AuthorityNoteEvidence,
    CorpusRelease,
    RecordTraceabilityLookupInput,
    ReleaseRecordEntry,
    ServingRecord,
    ServingRecordProfile,
    TraceabilityEntry,
    TraceabilityReference,
    TraceabilityScopeShardInput,
    compose_desired_state,
)
from asklegal_evidence_vault import (
    ExactObjectReference,
    LocalImmutableVault,
    RetentionProfile,
    VaultName,
)
from asklegal_legal_desks.hk_case_judgment import accept_complete_cases_acquisition_manifest
from asklegal_legal_desks.hk_legislation_records import (
    canonical_hk_legislation_candidate_set,
)
from asklegal_legal_processing_worker.hk_case_release import (
    HKCasePositiveReleaseRequest,
    HKCaseRecordTraceabilityBinding,
)
from asklegal_legal_processing_worker.hk_legislation_release import (
    HKLegislationReleaseSet,
    HKLegislationScopeReleaseRequest,
    HKLegislationScopeReleaseResult,
    accept_hk_legislation_acquisition_manifest,
    build_hk_legislation_scope_release,
)
from asklegal_legal_processing_worker.v1_acceptance import (
    AcceptanceLegalError,
    LocalAcceptanceInputProducer,
    LocalAcceptanceLegalInputReader,
    LocalReviewArtifactFreezer,
    TwoFamilyAcceptanceInputs,
    TwoFamilyAcceptanceReleases,
    prepare_hk_v1_acceptance_inputs,
    start_hk_v1_acceptance_legal_processing,
)

_ROOT = Path(__file__).parents[3]
_LEGISLATION_HELPERS = runpy.run_path(
    str(_ROOT / "apps/legal-processing-worker/tests/test_hk_legislation_release.py")
)
_CUTOFF = "2026-08-27T00:00:00Z"
_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)


@runtime_checkable
class _PromotionRecordView(Protocol):
    @property
    def record_id(self) -> str: ...

    @property
    def record(self) -> ServingRecord: ...


@runtime_checkable
class _PromotionDesiredStateView(Protocol):
    @property
    def records(self) -> tuple[_PromotionRecordView, ...]: ...


@runtime_checkable
class _PromotionManifestView(Protocol):
    @property
    def desired_state(self) -> _PromotionDesiredStateView: ...


def _is_promotion_manifest_view(
    value: object, expected_type: object
) -> TypeGuard[_PromotionManifestView]:
    if (
        not isinstance(expected_type, type)
        or type(value) is not expected_type
        or not isinstance(value, _PromotionManifestView)
    ):
        return False
    desired_state: object = value.desired_state
    return _is_promotion_desired_state_view(desired_state)


def _is_promotion_desired_state_view(value: object) -> TypeGuard[_PromotionDesiredStateView]:
    if not isinstance(value, _PromotionDesiredStateView):
        return False
    records: object = value.records
    if type(records) is not tuple:
        return False
    return all(_is_promotion_record_view(item) for item in records)


def _is_promotion_record_view(value: object) -> TypeGuard[_PromotionRecordView]:
    if not isinstance(value, _PromotionRecordView):
        return False
    record_id: object = value.record_id
    record: object = value.record
    return type(record_id) is str and type(record) is ServingRecord


def _legislation_request(scope: str) -> HKLegislationScopeReleaseRequest:
    factory = _LEGISLATION_HELPERS.get("_request")
    assert callable(factory)
    value = factory(scope)
    assert type(value) is HKLegislationScopeReleaseRequest
    return replace(
        value,
        allocated_identities=replace(value.allocated_identities, corpus_scope_id=scope),
    )


def _inputs() -> TwoFamilyAcceptanceInputs:
    requests = tuple(
        _legislation_request(scope)
        for scope in (
            "HK-LEG-ORDINANCES",
            "HK-LEG-SUBSIDIARY",
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        )
    )
    previews = tuple(build_hk_legislation_scope_release(request) for request in requests)
    shards = tuple(
        TraceabilityScopeShardInput(
            request.allocated_identities.corpus_scope_id,
            preview.release.release_id,
            "rts_" + digit * 48,
        )
        for request, preview, digit in zip(requests, previews, ("a", "b", "c"), strict=True)
    )
    # Release IDs are derived during mapping; the reader supplies identity inputs,
    # while this test freezer does not inspect the Legislation lookup artifact.
    return TwoFamilyAcceptanceInputs(
        "cyc_" + "1" * 48,
        "sha256:" + "2" * 64,
        _CUTOFF,
        "sha256:" + "3" * 64,
        "sha256:" + "4" * 64,
        HKCasePositiveReleaseRequest(
            _CUTOFF,
            (),
            ("evi_" + "1" * 48,),
            ("val_" + "2" * 48,),
            (
                "hk-v1/legal-processing/zero-record/"
                "HK-CASE-BINDING-POST-1997/sha256/" + "5" * 64 + ".json",
            ),
        ),
        requests,
        "hk-v1-local",
        RecordTraceabilityLookupInput(
            "rtl_" + "6" * 48,
            "sha256:" + "7" * 64,
            "sha256:" + "8" * 64,
        ),
        shards,
        None,
        (),
        RecordTraceabilityLookupInput(
            "rtl_" + "9" * 48,
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
        ),
        (
            TraceabilityScopeShardInput(
                "HK-CASE-BINDING-POST-1997",
                "rel_" + "0" * 48,
                "rts_" + "d" * 48,
            ),
            *shards,
        ),
    )


@dataclass
class _Reader:
    value: TwoFamilyAcceptanceInputs
    calls: int = 0

    def read_exact(self, operation_id: str) -> TwoFamilyAcceptanceInputs:
        assert operation_id == self.value.operation_id
        self.calls += 1
        return self.value


@dataclass
class _Freezer:
    calls: int = 0

    def freeze_exact(
        self,
        payload: object,
        releases: TwoFamilyAcceptanceReleases,
        inputs: TwoFamilyAcceptanceInputs,
    ) -> ExactObjectReference:
        assert type(payload) is dict
        assert len(releases.legislation_release_set.scope_results) == 3
        assert inputs.operation_id == "cyc_" + "1" * 48
        self.calls += 1
        content = b"exact review package"
        return ExactObjectReference(
            VaultName.PRIMARY,
            "hk-v1/proposals/exact.json",
            "v" + "9" * 64,
            "sha256:" + "9" * 64,
            len(content),
        )


def _payload() -> dict[str, JsonValue]:
    request = {
        "schema_id": "asklegal.hk-v1.acceptance-cycle-request",
        "schema_version": "1.0.0",
        "kind": "BASELINE",
        "cutoff_key": "t1",
        "observation_cutoff": _CUTOFF,
        "cases_manifest_fingerprint": "sha256:" + "3" * 64,
        "legislation_manifest_fingerprint": "sha256:" + "4" * 64,
        "authentic_changed_families": [],
        "cutoff_selection_fingerprint": "sha256:" + "5" * 64,
        "matrix_revision": "hk-v1",
        "matrix_fingerprint": "sha256:" + "6" * 64,
        "families": ["CASES", "LEGISLATION"],
        "scope_ids": list(_SCOPES),
        "command_id": "cmd_" + "1" * 48,
        "operation_id": "cyc_" + "1" * 48,
        "command_fingerprint": "sha256:" + "2" * 64,
    }
    value = checked_json_value(
        {
            "request": request,
            "acquisition": {
                "schema_id": "asklegal.hk-v1.acceptance-acquisition-result",
                "schema_version": "1.0.0",
                "operation_id": request["operation_id"],
                "command_fingerprint": request["command_fingerprint"],
                "observation_cutoff": _CUTOFF,
                "scope_ids": list(_SCOPES),
                "family_manifests": [
                    {
                        "material_family": "CASES",
                        "manifest_fingerprint": request["cases_manifest_fingerprint"],
                        "result": "COMPLETE",
                        "retryable_count": 0,
                        "rejected_count": 0,
                    },
                    {
                        "material_family": "LEGISLATION",
                        "manifest_fingerprint": request["legislation_manifest_fingerprint"],
                        "result": "COMPLETE",
                        "retryable_count": 0,
                        "rejected_count": 0,
                    },
                ],
                "result": "COMPLETE",
            },
        }
    )
    assert type(value) is dict
    return value


def test_positive_activity_runs_both_owning_mappers_and_returns_control_contract() -> None:
    """The Legal-owned activity reports ready only after its proposal freezer succeeds."""
    reader = _Reader(_inputs())
    freezer = _Freezer()

    result = start_hk_v1_acceptance_legal_processing(
        _payload(),
        reader,
        freezer,
    )

    assert result["result"] == "PROPOSAL_READY"
    assert reader.calls == freezer.calls == 1
    assert result["proposal_reference"] == {
        "vault": "PRIMARY",
        "logical_key": "hk-v1/proposals/exact.json",
        "version_id": "v" + "9" * 64,
        "fingerprint": "sha256:" + "9" * 64,
        "byte_length": 20,
    }
    scopes = result["scope_results"]
    assert type(scopes) is list
    assert [item["scope_id"] for item in scopes if type(item) is dict] == list(_SCOPES)
    assert all(item["record_count"] == 0 for item in scopes if type(item) is dict)
    assert type(scopes[0]) is dict
    assert scopes[0]["zero_record_justification_refs"] == [
        "hk-v1/legal-processing/zero-record/HK-CASE-BINDING-POST-1997/sha256/" + "5" * 64 + ".json"
    ]
    for scope in scopes[1:]:
        assert type(scope) is dict
        refs = scope["zero_record_justification_refs"]
        assert type(refs) is list
        assert refs
        assert all(
            type(ref) is str
            and re.fullmatch(r"[a-z][a-z0-9]{2}_[0-9a-f]{48}@sha256:[0-9a-f]{64}", ref)
            for ref in refs
        )


def test_input_drift_returns_not_ready_before_release_or_package_work() -> None:
    """A restart under changed retained authority cannot call the package freezer."""
    inputs = _inputs()
    object.__setattr__(inputs, "command_fingerprint", "sha256:" + "f" * 64)
    reader = _Reader(inputs)
    freezer = _Freezer()

    result = start_hk_v1_acceptance_legal_processing(
        _payload(),
        reader,
        freezer,
    )

    assert result["result"] == "NOT_READY"
    assert result["blocker_codes"] == ["LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT"]
    assert freezer.calls == 0


def test_missing_retained_input_reports_exact_sanitized_blocker(tmp_path: Path) -> None:
    """Operators can distinguish absent preparation from drift without source content."""
    freezer = _Freezer()

    result = start_hk_v1_acceptance_legal_processing(
        _payload(),
        LocalAcceptanceLegalInputReader(tmp_path / "missing"),
        freezer,
    )

    assert result["result"] == "NOT_READY"
    assert result["blocker_codes"] == ["LEGAL_PROCESSING_ACCEPTANCE_INPUT_NOT_READY"]
    assert freezer.calls == 0


def test_preseeded_components_cannot_replace_family_acquisition_evidence(tmp_path: Path) -> None:
    """A manual payload cannot turn locally preseeded components into legal success."""
    inputs = _inputs()
    prepared = tmp_path / "prepared"
    retained = tmp_path / "retained"
    _write_retained_inputs(prepared, inputs)
    operation = inputs.operation_id
    prepared_operation = prepared / operation
    legal = parse_json_bytes(
        prepared_operation.joinpath("legal-input.json").read_bytes(), max_bytes=1_000_000
    )
    assert type(legal) is dict
    legal.pop("fingerprint")
    policy_facts: dict[str, JsonValue] = {
        "title": "Exact retained HK V1 proposal",
        "base_serving_state_fingerprint": "sha256:" + "1" * 64,
        "task7_proposal": {},
        "coverage_status": {},
        "promotion_manifest": {},
        "readiness": {},
        "estimated_cost_microunits": 0,
        "review_statement": "Exact retained inputs pending package validation.",
    }
    artifacts: list[JsonValue] = []
    for path in sorted(prepared_operation.glob("legislation/*/candidate-set.json")):
        relative = path.relative_to(prepared_operation)
        content = path.read_bytes()
        artifacts.append(
            {
                "path": relative.as_posix(),
                "fingerprint": "sha256:" + sha256(content).hexdigest(),
                "byte_length": len(content),
            }
        )
    common: dict[str, JsonValue] = {
        "schema_version": "1.0.0",
        "operation_id": operation,
        "command_fingerprint": inputs.command_fingerprint,
        "observation_cutoff": inputs.observation_cutoff,
    }
    components: dict[str, JsonValue] = {
        "case-release-input.json": {
            **common,
            "schema_id": "asklegal.hk-v1-case-release-input/v1",
            "cases_manifest_fingerprint": inputs.cases_manifest_fingerprint,
            "case_release": legal["case_release"],
            "case_traceability": legal["case_traceability"],
        },
        "legislation-release-input.json": {
            **common,
            "schema_id": "asklegal.hk-v1-legislation-release-input/v1",
            "legislation_manifest_fingerprint": inputs.legislation_manifest_fingerprint,
            "legislation_scopes": legal["legislation_scopes"],
            "legislation_target_key": legal["legislation_target_key"],
            "legislation_lookup_input": legal["legislation_lookup_input"],
            "legislation_lookup_shards": legal["legislation_lookup_shards"],
            "artifacts": artifacts,
        },
        "package-traceability-input.json": {
            **common,
            "schema_id": "asklegal.hk-v1-package-traceability-input/v1",
            "package_lookup_input": legal["package_lookup_input"],
            "package_lookup_shards": legal["package_lookup_shards"],
        },
        "package-policy-facts.json": {
            **common,
            "schema_id": "asklegal.hk-v1-package-policy-facts/v1",
            **policy_facts,
        },
    }
    for name, body in components.items():
        checked = checked_json_value(body)
        assert type(checked) is dict
        prepared_operation.joinpath(name).write_bytes(
            canonicalize(
                {
                    **checked,
                    "fingerprint": "sha256:" + sha256(canonicalize(checked)).hexdigest(),
                }
            )
        )
    producer = LocalAcceptanceInputProducer(prepared, retained / ".staged")
    with pytest.raises(
        AcceptanceLegalError,
        match="LEGAL_PROCESSING_ACCEPTANCE_ACQUISITION_EVIDENCE_NOT_READY",
    ):
        producer.produce_exact(_payload())
    assert not (retained / ".staged" / operation).exists()


def test_missing_producer_inputs_return_exact_not_ready(tmp_path: Path) -> None:
    """Absent processed outputs are visible and cannot reach release creation."""
    result = prepare_hk_v1_acceptance_inputs(
        _payload(),
        LocalAcceptanceInputProducer(tmp_path / "processed", tmp_path / "staged"),
    )

    assert result["result"] == "NOT_READY"
    assert result["blocker_codes"] == ["LEGAL_PROCESSING_ACCEPTANCE_ACQUISITION_EVIDENCE_NOT_READY"]


def test_family_evidence_replays_journals_and_vault_before_semantic_not_ready(
    tmp_path: Path,
) -> None:
    """The live wrapper path retains verified source objects before mapper output exists."""
    payload = _payload()
    request = payload["request"]
    assert type(request) is dict
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    retention = RetentionProfile("source-v1", "2099-01-01T00:00:00Z")
    journal_root = tmp_path / "due-cycle"
    children: list[dict[str, JsonValue]] = []
    for index, family in enumerate(("CASES", "LEGISLATION"), start=1):
        cycle_id = f"cyc_{family.lower()}_source"
        object_body = f"verified {family} source".encode()
        object_receipt = vault.conditional_create(
            f"source/{family.lower()}/{index}", object_body, retention
        )
        entry_body: dict[str, JsonValue] = {
            "schema_id": "asklegal.acquisition-journal-entry",
            "schema_version": "1.0.0",
            "sequence": 1,
            "previous_entry_fingerprint": "sha256:" + "0" * 64,
            "work_item": {"work_item_id": f"awi_{index:064x}"},
            "transition": "CAPTURED_VERIFIED",
            "payload": {
                "object_ref": object_receipt.reference.logical_key,
                "content_fingerprint": "sha256:" + sha256(object_body).hexdigest(),
                "body_length": len(object_body),
                "read_back_verified": True,
            },
        }
        entry_fingerprint = "sha256:" + sha256(canonicalize(entry_body)).hexdigest()
        entries = journal_root / "acquisition-journals" / cycle_id / "entries"
        entries.mkdir(parents=True)
        entries.joinpath("00000000000000000001.json").write_bytes(
            canonicalize({**entry_body, "fingerprint": entry_fingerprint})
        )
        manifest_field = (
            "cases_manifest_fingerprint"
            if family == "CASES"
            else "legislation_manifest_fingerprint"
        )
        if family == "CASES":
            manifest_body: dict[str, JsonValue] = {
                "cycle_id": cycle_id,
                "discrepancy_refs": [],
                "earliest_decision_date": "1997-07-01",
                "journal_head_fingerprint": entry_fingerprint,
                "judgment_bundle_refs": [],
                "observation_cutoff": request["observation_cutoff"],
                "result": "COMPLETE",
                "year_dispositions": [
                    {
                        "discovered_judgments": 0,
                        "final_page": 1,
                        "first_in_scope_date": (
                            "1997-07-01" if year == 1997 else f"{year:04d}-01-01"
                        ),
                        "result": "COMPLETE",
                        "retryable_items": 0,
                        "verified_judgments": 0,
                        "verified_listing_pages": 1,
                        "year": year,
                    }
                    for year in range(1997, int(_CUTOFF[:4]) + 1)
                ],
            }
        else:
            manifest_body = {
                "schema_id": "asklegal.legislation-acquisition-manifest",
                "schema_version": "1.0.0",
                "cycle_id": cycle_id,
                "observation_cutoff": _CUTOFF.removesuffix("Z") + "+00:00",
                "scope_dispositions": [
                    {
                        "scope_id": scope,
                        "required_item_count": 1,
                        "verified_item_count": 1,
                        "retryable_item_count": 0,
                        "rejected_item_count": 0,
                        "result": "COMPLETE",
                    }
                    for scope in _SCOPES[1:]
                ],
                "verified_item_refs": ["legislation-item/stable-key/" + "c" * 64],
                "review_issue_refs": [],
                "journal_head_fingerprint": entry_fingerprint,
                "source_register_fingerprint": "sha256:" + "d" * 64,
                "source_baseline_fingerprint": "sha256:" + "e" * 64,
                "work_plan_fingerprint": "sha256:" + "f" * 64,
                "result": "COMPLETE",
            }
        manifest = canonicalize(
            {
                **manifest_body,
                "fingerprint": "sha256:" + sha256(canonicalize(manifest_body)).hexdigest(),
            }
        )
        manifest_document = parse_json_bytes(manifest, max_bytes=len(manifest))
        assert type(manifest_document) is dict
        if family == "CASES":
            accept_complete_cases_acquisition_manifest(manifest)
        else:
            accept_hk_legislation_acquisition_manifest(manifest)
        request[manifest_field] = manifest_document["fingerprint"]
        acquisition = payload["acquisition"]
        assert type(acquisition) is dict
        family_manifests = acquisition["family_manifests"]
        assert type(family_manifests) is list
        family_manifest = family_manifests[index - 1]
        assert type(family_manifest) is dict
        family_manifest["manifest_fingerprint"] = request[manifest_field]
        manifest_receipt = vault.conditional_create(
            f"due/family-manifests/{family.casefold()}", manifest, retention
        )
        children.append(
            {
                "source_family": family,
                "cycle_id": cycle_id,
                "journal_ref": f"acquisition-journals/{cycle_id}",
                "manifest_fingerprint": request[manifest_field],
                "journal_head_fingerprint": entry_fingerprint,
                "result": "COMPLETE",
                "manifest_reference": {
                    "vault": "PRIMARY",
                    "logical_key": manifest_receipt.reference.logical_key,
                    "version_id": manifest_receipt.reference.version_id,
                    "fingerprint": manifest_receipt.reference.fingerprint,
                    "byte_length": manifest_receipt.reference.byte_length,
                },
            }
        )
    root_cycle = "cyc_due_source"
    root_plan = "sha256:" + "d" * 64
    evidence = canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-v1.scheduled-family-acquisitions",
                "schema_version": "1.0.0",
                "root_instruction": {
                    "cycle_id": root_cycle,
                    "cycle_kind": "DAILY_CURRENT_LAW",
                    "scheduled_at": _CUTOFF,
                    "observation_cutoff": request["observation_cutoff"],
                    "matrix_revision": request["matrix_revision"],
                    "matrix_fingerprint": request["matrix_fingerprint"],
                },
                "root_plan_fingerprint": root_plan,
                "children": children,
            }
        )
    )
    receipt = vault.conditional_create("due/family-evidence", evidence, retention)
    payload["family_acquisition_evidence"] = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1.acceptance-family-acquisition-evidence",
            "schema_version": "1.0.0",
            "root_cycle_id": root_cycle,
            "root_plan_fingerprint": root_plan,
            "evidence_reference": {
                "vault": "PRIMARY",
                "logical_key": receipt.reference.logical_key,
                "version_id": receipt.reference.version_id,
                "fingerprint": receipt.reference.fingerprint,
                "byte_length": receipt.reference.byte_length,
            },
            "children": children,
        }
    )
    processed = tmp_path / "processed"

    result = prepare_hk_v1_acceptance_inputs(
        payload,
        LocalAcceptanceInputProducer(
            processed,
            tmp_path / "staged",
            journal_root,
            vault,
        ),
    )

    assert result["result"] == "NOT_READY"
    assert result["blocker_codes"] == ["LEGAL_PROCESSING_ACCEPTANCE_SEMANTIC_OUTPUT_NOT_READY"]
    checkpoint = parse_json_bytes(
        processed.joinpath(
            _string(request["operation_id"]), "verified-acquisition-inputs.json"
        ).read_bytes(),
        max_bytes=1_000_000,
    )
    assert type(checkpoint) is dict
    assert _source_families(checkpoint) == [
        "CASES",
        "LEGISLATION",
    ]


def test_local_retained_reader_reissues_legislation_candidates_after_restart(
    tmp_path: Path,
) -> None:
    """A new reader rebuilds exact Desk issuance without the producer's weakrefs."""
    inputs = _inputs()
    root = tmp_path / "acceptance-inputs"
    _write_retained_inputs(root, inputs)

    first = LocalAcceptanceLegalInputReader(root).read_exact(inputs.operation_id)
    restarted = LocalAcceptanceLegalInputReader(root).read_exact(inputs.operation_id)

    assert first is not restarted
    assert build_hk_legislation_scope_release(first.legislation_scope_requests[0]).release == (
        build_hk_legislation_scope_release(restarted.legislation_scope_requests[0]).release
    )
    candidate_path = root / inputs.operation_id / "legislation/HK-LEG-ORDINANCES/candidate-set.json"
    candidate_path.write_bytes(candidate_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT"):
        LocalAcceptanceLegalInputReader(root).read_exact(inputs.operation_id)


def test_update_reuses_verified_unchanged_legislation_releases_after_restart(
    tmp_path: Path,
) -> None:
    """UPDATE can replay an exact prior release without converting it to new work."""
    inputs = _inputs()
    prior = tuple(
        build_hk_legislation_scope_release(request) for request in inputs.legislation_scope_requests
    )
    updated = replace(
        inputs,
        legislation_scope_requests=tuple(
            replace(
                request,
                prior_release=result.release,
                prior_traceability_entries=result.traceability_entries,
                prior_inventory_outcomes=result.inventory_outcomes,
                unchanged=True,
            )
            for request, result in zip(inputs.legislation_scope_requests, prior, strict=True)
        ),
    )
    root = tmp_path / "acceptance-inputs"
    _write_retained_inputs(root, updated)

    restarted = LocalAcceptanceLegalInputReader(root).read_exact(updated.operation_id)
    replayed = tuple(
        build_hk_legislation_scope_release(request)
        for request in restarted.legislation_scope_requests
    )

    assert tuple(item.release for item in replayed) == tuple(item.release for item in prior)
    assert all(item.reused_prior_release for item in replayed)


def test_local_freezer_validates_then_atomically_reads_back_review_and_vault(
    tmp_path: Path,
) -> None:
    """A complete frozen bundle is committed manifest-last and remains resumable."""
    operation_id = "cyc_" + "1" * 48
    staged = tmp_path / "staged"
    source = _ROOT / "apps/review-api/tests/fixtures/hk_v1_review"
    shutil.copytree(source, staged / operation_id)
    releases = _fixture_releases(source)
    inputs = _fixture_inputs(source, releases)
    _write_package_policy(staged / operation_id, source, operation_id, inputs, releases)
    review_root = tmp_path / "review"
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    freezer = LocalReviewArtifactFreezer(
        staged,
        review_root,
        vault,
        RetentionProfile("proposal-v1", "2036-01-01T00:00:00Z"),
    )
    payload = _payload()
    request = payload["request"]
    assert type(request) is dict
    request["observation_cutoff"] = "2026-08-16T00:00:00Z"
    acquisition = payload["acquisition"]
    assert type(acquisition) is dict
    acquisition["observation_cutoff"] = "2026-08-16T00:00:00Z"

    first = freezer.freeze_exact(payload, releases, inputs)
    second = freezer.freeze_exact(payload, releases, inputs)

    assert first == second
    assert (
        vault.read_exact(first)
        == review_root.joinpath("current", "hk-v1-review-package.json").read_bytes()
    )


def _fixture_releases(source: Path) -> TwoFamilyAcceptanceReleases:
    promotion_helpers = runpy.run_path(
        str(_ROOT / "apps/promotion-worker/tests/test_m6_promotion.py")
    )
    manifest_factory = promotion_helpers["task8_v1_manifest_fixture"]
    manifest_type = promotion_helpers["PromotionManifest"]
    assert callable(manifest_factory)
    manifest = manifest_factory()
    assert _is_promotion_manifest_view(manifest, manifest_type)
    source_records = {item.record_id: item.record for item in manifest.desired_state.records}
    release_document = parse_json_bytes(
        source.joinpath("corpus-releases/releases.json").read_bytes(), max_bytes=1_000_000
    )
    desired_document = parse_json_bytes(
        source.joinpath("desired-state-inventories/inventories.json").read_bytes(),
        max_bytes=1_000_000,
    )
    assert type(release_document) is dict
    assert type(release_document["releases"]) is list
    assert type(desired_document) is dict
    assert type(desired_document["records"]) is list
    desired = {
        item["record_id"]: item
        for item in desired_document["records"]
        if type(item) is dict and type(item.get("record_id")) is str
    }
    by_scope: dict[str, CorpusRelease] = {}
    for item in release_document["releases"]:
        assert type(item) is dict
        record_ids = item["record_ids"]
        assert type(record_ids) is list
        entries: list[ReleaseRecordEntry] = []
        for record_id in record_ids:
            assert type(record_id) is str
            record = desired[record_id]
            serving = source_records[record_id]
            entries.append(
                ReleaseRecordEntry(
                    serving,
                    _string(record["serving_payload_fingerprint"]),
                )
            )
        scope = _string(item["scope_id"])
        zero_refs = () if entries else ("evi_" + "f" * 48,)
        by_scope[scope] = CorpusRelease(
            _string(item["release_id"]),
            scope,
            _string(item["observation_cutoff"]),
            tuple(entries),
            _strings(item["evidence_refs"]),
            _strings(item["validation_refs"]),
            (),
            zero_refs,
            "sha256:" + "e" * 64,
            "sha256:" + "d" * 64,
        )
    legislation_results = tuple(
        type("ScopeResult", (), {"legislation_scope_code": scope, "release": by_scope[scope]})()
        for scope in (
            "HK-LEG-ORDINANCES",
            "HK-LEG-SUBSIDIARY",
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        )
    )
    legislation = object.__new__(HKLegislationReleaseSet)
    object.__setattr__(legislation, "scope_results", legislation_results)
    return TwoFamilyAcceptanceReleases(
        by_scope["HK-CASE-BINDING-POST-1997"],
        legislation,
    )


def _fixture_inputs(
    source: Path, releases: TwoFamilyAcceptanceReleases
) -> TwoFamilyAcceptanceInputs:
    lookup = parse_json_bytes(
        source.joinpath("record-traceability/lookup.json").read_bytes(), max_bytes=1_000_000
    )
    desired = parse_json_bytes(
        source.joinpath("desired-state-inventories/inventories.json").read_bytes(),
        max_bytes=1_000_000,
    )
    assert type(lookup) is dict
    assert type(desired) is dict
    raw_profiles = lookup["serving_record_profiles"]
    raw_shards = lookup["shards"]
    assert type(raw_profiles) is list
    assert type(raw_shards) is list
    profiles = {
        _string(item["serving_record_profile_id"]): ServingRecordProfile(
            _string(item["serving_record_profile_id"]),
            _string(item["schema_version"]),
            _string(item["schema_fingerprint"]),
        )
        for item in raw_profiles
        if type(item) is dict
    }
    entries: dict[str, list[TraceabilityEntry]] = {scope: [] for scope in _SCOPES}
    shard_inputs: list[TraceabilityScopeShardInput] = []
    for raw in raw_shards:
        assert type(raw) is dict
        scope = _string(raw["release_scope_id"])
        content = source.joinpath("record-traceability", _string(raw["path"])).read_bytes()
        if content:
            for line in content.rstrip(b"\n").split(b"\n"):
                document = parse_json_bytes(line, max_bytes=1_000_000)
                assert type(document) is dict
                entries[scope].append(_traceability_entry(document))
        shard_inputs.append(
            TraceabilityScopeShardInput(
                scope,
                _string(raw["corpus_release_id"]),
                _string(raw["lookup_shard_id"]),
            )
        )
    case_entry = entries[_SCOPES[0]][0]
    case_profile = profiles[case_entry.serving_record_profile_id]
    case_binding = HKCaseRecordTraceabilityBinding(
        case_entry.search_record_id,
        case_entry.serving_record_profile_id,
        case_entry.legal_item_id,
        case_entry.official_version_ids,
        case_entry.legal_location_ids,
        case_entry.evidence_refs,
        case_entry.authority_note_evidence,
        case_entry.grouping_ids,
        case_entry.display_citation_ids,
    )
    results: list[HKLegislationScopeReleaseResult] = []
    by_scope = _release_inventory_for_test(releases)
    for scope in (
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    ):
        scoped_entries = tuple(entries[scope])
        profile = (
            profiles[scoped_entries[0].serving_record_profile_id]
            if scoped_entries
            else next(iter(profiles.values()))
        )
        results.append(
            HKLegislationScopeReleaseResult(
                scope,
                by_scope[scope],
                scoped_entries,
                (),
                profile,
                reused_prior_release=False,
            )
        )
    object.__setattr__(releases.legislation_release_set, "scope_results", tuple(results))
    return TwoFamilyAcceptanceInputs(
        "cyc_" + "1" * 48,
        "sha256:" + "2" * 64,
        "2026-08-16T00:00:00Z",
        "sha256:" + "3" * 64,
        "sha256:" + "4" * 64,
        HKCasePositiveReleaseRequest("2026-08-16T00:00:00Z", (), (), (), ()),
        (),
        "hk-v1-local",
        RecordTraceabilityLookupInput(
            "rtl_" + "1" * 48,
            "sha256:" + "1" * 64,
            "sha256:" + "1" * 64,
        ),
        (),
        case_profile,
        (case_binding,),
        RecordTraceabilityLookupInput(
            _string(lookup["lookup_revision_id"]),
            _string(lookup["manifest_schema_fingerprint"]),
            _string(lookup["entry_schema_fingerprint"]),
        ),
        tuple(shard_inputs),
    )


def _release_inventory_for_test(
    releases: TwoFamilyAcceptanceReleases,
) -> dict[str, CorpusRelease]:
    return {
        _SCOPES[0]: releases.case_release,
        **{
            item.legislation_scope_code: item.release
            for item in releases.legislation_release_set.scope_results
        },
    }


def _traceability_entry(document: dict[str, JsonValue]) -> TraceabilityEntry:
    authority = document["authority_note_evidence"]
    assert type(authority) is dict
    evidence = document["evidence_refs"]
    supporting = authority["supporting_evidence_refs"]
    assert type(evidence) is list
    assert type(supporting) is list
    return TraceabilityEntry(
        _string(document["search_record_id"]),
        _string(document["serving_payload_fingerprint"]),
        _string(document["serving_record_profile_id"]),
        _string(document["legal_item_id"]),
        _strings(document["official_version_ids"]),
        _strings(document["legal_location_ids"]),
        _string(document["release_scope_id"]),
        _string(document["corpus_release_id"]),
        tuple(_traceability_ref(item) for item in evidence),
        AuthorityNoteEvidence(
            _string(authority["rendered_value_fingerprint"]),
            _traceability_ref(authority["decision_ref"]),
            tuple(_traceability_ref(item) for item in supporting),
        ),
        _strings(document["grouping_ids"]),
        _strings(document["display_citation_ids"]),
    )


def _traceability_ref(value: JsonValue) -> TraceabilityReference:
    assert type(value) is dict
    return TraceabilityReference(
        _string(value["ref_type"]),
        _string(value["ref_id"]),
        _string(value["fingerprint"]),
    )


def _write_package_policy(
    root: Path,
    source: Path,
    operation_id: str,
    inputs: TwoFamilyAcceptanceInputs,
    releases: TwoFamilyAcceptanceReleases,
) -> None:
    def document(path: str) -> dict[str, JsonValue]:
        value = parse_json_bytes(source.joinpath(path).read_bytes(), max_bytes=1_000_000)
        assert type(value) is dict
        return value

    package = document("hk-v1-review-package.json")
    readiness = document("hk-v1-review-readiness.json")
    promotion = document("promotion-manifest/promotion-manifest.json")
    by_scope = _release_inventory_for_test(releases)
    desired = compose_desired_state(
        _SCOPES,
        tuple(by_scope[scope] for scope in _SCOPES),
        target_key=inputs.legislation_target_key,
        observation_cutoff=inputs.observation_cutoff,
    )
    promotion["desired_state_fingerprint"] = desired.inventory_fingerprint
    actions = promotion["actions"]
    assert type(actions) is list
    for action in actions:
        assert type(action) is dict
        raw_refs = action["input_refs"]
        assert type(raw_refs) is list
        for reference in raw_refs:
            if type(reference) is dict and reference.get("ref_type") == "DESIRED_STATE_INVENTORY":
                reference["fingerprint"] = desired.inventory_fingerprint
    predicates = promotion["validity_predicates"]
    assert _is_string_matrix(predicates)
    evidence_fingerprints = {
        "model_evaluation_fingerprint": "sha256:" + "1" * 64,
        "retrieval_evaluation_fingerprint": "sha256:" + "2" * 64,
        "native_backup_fingerprint": "sha256:" + "3" * 64,
        "recovery_backup_fingerprint": "sha256:" + "4" * 64,
    }
    predicates.extend(
        [contract, "1.0.0", evidence_fingerprints[field]]
        for contract, field in (
            ("HK_V1_MODEL_EVALUATION", "model_evaluation_fingerprint"),
            ("HK_V1_RETRIEVAL_EVALUATION", "retrieval_evaluation_fingerprint"),
            ("HK_V1_NATIVE_BACKUP", "native_backup_fingerprint"),
            ("HK_V1_RECOVERY_BACKUP", "recovery_backup_fingerprint"),
        )
    )
    predicates.sort()
    cost = document("cost-and-capacity/admission.json")
    report = document("review-report/report.json")
    body = {
        "schema_id": "asklegal.hk-v1-package-policy-input/v1",
        "schema_version": "1.0.0",
        "operation_id": operation_id,
        "observation_cutoff": package["observation_cutoff"],
        "title": package["title"],
        "base_serving_state_fingerprint": package["base_serving_state_fingerprint"],
        "task7_proposal": document("hk-v1-two-family-proposal.json"),
        "coverage_status": document("coverage-status/coverage.json"),
        "promotion_manifest": promotion,
        "readiness": {
            "limitations": readiness["limitations"],
            "model_evaluation_ref": readiness["model_evaluation_ref"],
            "retrieval_evaluation_ref": readiness["retrieval_evaluation_ref"],
            "model_profile_fingerprint": readiness["model_profile_fingerprint"],
            "embedding_profile_fingerprint": readiness["embedding_profile_fingerprint"],
            "serving_profile_fingerprint": readiness["serving_profile_fingerprint"],
            "target_namespace": readiness["target_namespace"],
            "backup_profile_fingerprint": readiness["backup_profile_fingerprint"],
            "target_name": readiness["target_name"],
            "native_backup_ref": readiness["native_backup_ref"],
            "recovery_backup_ref": readiness["recovery_backup_ref"],
            "rollback_state_id": readiness["rollback_state_id"],
            **evidence_fingerprints,
        },
        "estimated_cost_microunits": cost["estimated_cost_microunits"],
        "review_statement": report["statement"],
    }
    checked = checked_json_value(body)
    assert type(checked) is dict
    root.joinpath("package-policy.json").write_bytes(
        canonicalize(
            {
                **checked,
                "fingerprint": "sha256:" + sha256(canonicalize(checked)).hexdigest(),
            }
        )
    )


def _write_retained_inputs(root: Path, inputs: TwoFamilyAcceptanceInputs) -> None:
    operation_root = root / inputs.operation_id
    scopes: list[JsonValue] = []
    for request in inputs.legislation_scope_requests:
        scope = request.candidate_set.legislation_scope_code
        relative = f"legislation/{scope}/candidate-set.json"
        content = canonical_hk_legislation_candidate_set(request.candidate_set)
        path = operation_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        scopes.append(
            checked_json_value(
                {
                    "scope_id": scope,
                    "candidate_set_path": relative,
                    "candidate_set_fingerprint": "sha256:" + sha256(content).hexdigest(),
                    "allocated_identities": {
                        "corpus_scope_id": request.allocated_identities.corpus_scope_id,
                        "allocations": [
                            {
                                "legislation_scope_code": item.legislation_scope_code,
                                "candidate_key": item.candidate_key,
                                "search_record_id": item.search_record_id,
                                "continuity": item.continuity,
                                "predecessor_record_id": item.predecessor_record_id,
                                "predecessor_payload_fingerprint": (
                                    item.predecessor_payload_fingerprint
                                ),
                                "predecessor_record_fact": (
                                    None
                                    if item.predecessor_record_fact is None
                                    else {
                                        "corpus_scope_id": (
                                            item.predecessor_record_fact.corpus_scope_id
                                        ),
                                        "record": _serving_record_document(
                                            item.predecessor_record_fact.record
                                        ),
                                    }
                                ),
                            }
                            for item in request.allocated_identities.allocations
                        ],
                        "lookup_revision_id": request.allocated_identities.lookup_revision_id,
                        "lookup_shard_id": request.allocated_identities.lookup_shard_id,
                    },
                    "serving_profile": {
                        "serving_record_profile_id": (
                            request.serving_profile.serving_record_profile_id
                        ),
                        "schema_version": request.serving_profile.schema_version,
                        "schema_fingerprint": request.serving_profile.schema_fingerprint,
                    },
                    "release_evidence_refs": list(request.release_evidence_refs),
                    "release_validation_refs": list(request.release_validation_refs),
                    "prior_release": (
                        None
                        if request.prior_release is None
                        else _release_document(request.prior_release)
                    ),
                    "prior_traceability_entries": (
                        None
                        if request.prior_traceability_entries is None
                        else [
                            _traceability_document(item)
                            for item in request.prior_traceability_entries
                        ]
                    ),
                    "prior_inventory_outcomes": (
                        None
                        if request.prior_inventory_outcomes is None
                        else [
                            {
                                "inventory_item_id": item.inventory_item_id,
                                "legal_disposition": item.legal_disposition.value,
                                "outcome_kind": item.outcome_kind,
                                "reason_code": item.reason_code,
                                "draft_keys": list(item.draft_keys),
                                "supporting_refs": [
                                    {
                                        "ref_type": ref.ref_type,
                                        "ref_id": ref.ref_id,
                                        "fingerprint": ref.fingerprint,
                                    }
                                    for ref in item.supporting_refs
                                ],
                            }
                            for item in request.prior_inventory_outcomes
                        ]
                    ),
                    "unchanged": request.unchanged,
                }
            )
        )
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1-retained-acceptance-input/v1",
        "schema_version": "1.0.0",
        "operation_id": inputs.operation_id,
        "command_fingerprint": inputs.command_fingerprint,
        "observation_cutoff": inputs.observation_cutoff,
        "cases_manifest_fingerprint": inputs.cases_manifest_fingerprint,
        "legislation_manifest_fingerprint": inputs.legislation_manifest_fingerprint,
        "case_release": {
            "observation_cutoff": inputs.case_request.observation_cutoff,
            "candidates": [],
            "release_evidence_refs": list(inputs.case_request.release_evidence_refs),
            "release_validation_refs": list(inputs.case_request.release_validation_refs),
            "zero_record_justification_refs": list(
                inputs.case_request.zero_record_justification_refs
            ),
        },
        "legislation_scopes": scopes,
        "legislation_target_key": inputs.legislation_target_key,
        "legislation_lookup_input": {
            "lookup_revision_id": inputs.legislation_lookup_input.lookup_revision_id,
            "manifest_schema_fingerprint": (
                inputs.legislation_lookup_input.manifest_schema_fingerprint
            ),
            "entry_schema_fingerprint": inputs.legislation_lookup_input.entry_schema_fingerprint,
        },
        "legislation_lookup_shards": [
            {
                "release_scope_id": item.release_scope_id,
                "corpus_release_id": item.corpus_release_id,
                "lookup_shard_id": item.lookup_shard_id,
            }
            for item in inputs.legislation_lookup_shards
        ],
        "case_traceability": {"serving_profile": None, "bindings": []},
        "package_lookup_input": {
            "lookup_revision_id": inputs.package_lookup_input.lookup_revision_id,
            "manifest_schema_fingerprint": (
                inputs.package_lookup_input.manifest_schema_fingerprint
            ),
            "entry_schema_fingerprint": inputs.package_lookup_input.entry_schema_fingerprint,
        },
        "package_lookup_shards": [
            {
                "release_scope_id": item.release_scope_id,
                "corpus_release_id": item.corpus_release_id,
                "lookup_shard_id": item.lookup_shard_id,
            }
            for item in inputs.package_lookup_shards
        ],
    }
    checked = checked_json_value(body)
    assert type(checked) is dict
    content = canonicalize(
        {**checked, "fingerprint": "sha256:" + sha256(canonicalize(checked)).hexdigest()}
    )
    operation_root.mkdir(parents=True, exist_ok=True)
    operation_root.joinpath("legal-input.json").write_bytes(content)


def _serving_record_document(record: ServingRecord) -> dict[str, JsonValue]:
    return {
        "record_id": record.record_id,
        "text": record.text,
        "country": record.country,
        "jurisdiction": record.jurisdiction,
        "material_type": record.material_type,
        "source": record.source,
        "authority_note": record.authority_note,
        "artifact_ref": record.artifact_ref,
        "evidence_refs": list(record.evidence_refs),
    }


def _release_document(release: CorpusRelease) -> dict[str, object]:
    return {
        "release_id": release.release_id,
        "scope_id": release.scope_id,
        "observation_cutoff": release.observation_cutoff,
        "records": [
            {
                "record": _serving_record_document(item.record),
                "serving_payload_fingerprint": item.serving_payload_fingerprint,
            }
            for item in release.records
        ],
        "evidence_refs": list(release.evidence_refs),
        "validation_refs": list(release.validation_refs),
        "withholding_refs": list(release.withholding_refs),
        "zero_record_justification_refs": list(release.zero_record_justification_refs),
        "records_fingerprint": release.records_fingerprint,
        "release_fingerprint": release.release_fingerprint,
    }


def _traceability_document(entry: TraceabilityEntry) -> dict[str, object]:
    def reference(item: TraceabilityReference) -> dict[str, object]:
        return {
            "ref_type": item.ref_type,
            "ref_id": item.ref_id,
            "fingerprint": item.fingerprint,
        }

    return {
        "search_record_id": entry.search_record_id,
        "serving_payload_fingerprint": entry.serving_payload_fingerprint,
        "serving_record_profile_id": entry.serving_record_profile_id,
        "legal_item_id": entry.legal_item_id,
        "official_version_ids": list(entry.official_version_ids),
        "legal_location_ids": list(entry.legal_location_ids),
        "release_scope_id": entry.release_scope_id,
        "corpus_release_id": entry.corpus_release_id,
        "evidence_refs": [reference(item) for item in entry.evidence_refs],
        "authority_note_evidence": {
            "rendered_value_fingerprint": (
                entry.authority_note_evidence.rendered_value_fingerprint
            ),
            "decision_ref": reference(entry.authority_note_evidence.decision_ref),
            "supporting_evidence_refs": [
                reference(item) for item in entry.authority_note_evidence.supporting_evidence_refs
            ],
        },
        "grouping_ids": list(entry.grouping_ids),
        "display_citation_ids": list(entry.display_citation_ids),
    }


def _string(value: object) -> str:
    assert type(value) is str
    return value


def _strings(value: object) -> tuple[str, ...]:
    assert _is_string_list(value)
    return tuple(value)


def _is_string_list(value: object) -> TypeIs[list[str]]:
    return _is_object_list(value) and all(type(item) is str for item in value)


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return type(value) is list


def _is_json_object_list(value: object) -> TypeGuard[list[dict[str, JsonValue]]]:
    return _is_object_list(value) and all(type(item) is dict for item in value)


def _is_string_matrix(value: object) -> TypeGuard[list[list[str]]]:
    return _is_object_list(value) and all(_is_string_list(item) for item in value)


def _source_families(checkpoint: dict[str, JsonValue]) -> list[JsonValue]:
    families = checkpoint["families"]
    assert _is_json_object_list(families)
    return [item["source_family"] for item in families]
