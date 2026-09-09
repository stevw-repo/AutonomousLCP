"""One retained-source-to-frozen-review proof for the live Legal boundary."""

from __future__ import annotations

import runpy
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol, TypeGuard, TypeIs, runtime_checkable

import asklegal_legal_processing_worker.v1_acceptance as acceptance_module
import pytest
from asklegal_contracts import canonicalize, fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import compose_desired_state
from asklegal_evidence_vault import (
    ExactObjectReference,
    LocalImmutableVault,
    RetentionProfile,
    VaultName,
)
from asklegal_legal_desks import SemanticTaskProfile
from asklegal_legal_desks.hk_case_semantic_task import HKCaseSemanticWorkflowComponent
from asklegal_legal_processing_worker.v1_acceptance import (
    AcceptanceLegalError,
    LocalAcceptanceInputMaterializer,
    LocalAcceptanceInputProducer,
    LocalAcceptanceLegalInputReader,
    LocalReviewArtifactFreezer,
    TwoFamilyAcceptanceInputs,
    TwoFamilyAcceptanceReleases,
    build_two_family_acceptance_releases,
    preview_generated_family_releases,
)
from asklegal_legal_processing_worker.v1_live_acceptance import (
    LiveAcceptanceComponentPreparer,
)
from asklegal_processing import SemanticTaskRequest

_ROOT = Path(__file__).parents[3]
_ACCEPT = runpy.run_path(str(Path(__file__).with_name("test_v1_acceptance_legal.py")))
_CASE = runpy.run_path(str(Path(__file__).with_name("test_v1_cases_acceptance.py")))
_LEG = runpy.run_path(str(Path(__file__).with_name("test_v1_legislation_acceptance.py")))
_PROP = runpy.run_path(str(_ROOT / "packages/legal-desks/tests/test_hk_case_proposition.py"))
_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_CUTOFF = "2026-09-08T00:00:00Z"


class _Counter:
    tokenizer_id = "HK_CASE_CODEPOINT_FIXTURE_V1"

    def count(self, text: str) -> int:
        return len(text)


@dataclass(frozen=True, slots=True)
class _Profiles:
    profiles: tuple[SemanticTaskProfile, ...]


@runtime_checkable
class _CaseVaultFixture(Protocol):
    bodies: dict[str, bytes]


@runtime_checkable
class _LegislationVaultFixture(Protocol):
    objects: dict[str, tuple[object, bytes]]


def _is_json_list(value: object) -> TypeGuard[list[JsonValue]]:
    if not _is_object_list(value):
        return False
    try:
        checked_json_value(value)
    except ValueError:
        return False
    return True


def _semantic_profile(value: object) -> SemanticTaskProfile:
    assert type(value) is SemanticTaskProfile
    return value


def _workflow_component(value: object) -> HKCaseSemanticWorkflowComponent:
    assert type(value) is HKCaseSemanticWorkflowComponent
    return value


def _acceptance_payload() -> dict[str, JsonValue]:
    factory = _ACCEPT["_payload"]
    assert callable(factory)
    checked = checked_json_value(factory())
    assert type(checked) is dict
    return checked


def _case_inputs() -> tuple[bytes, _CaseVaultFixture]:
    factory = _CASE["_inputs"]
    assert callable(factory)
    raw = factory()
    assert _is_object_tuple(raw)
    assert len(raw) == 2
    manifest, vault = raw
    assert type(manifest) is bytes
    assert isinstance(vault, _CaseVaultFixture)
    return manifest, vault


def _legislation_inputs() -> tuple[bytes, object, _LegislationVaultFixture]:
    factory = _LEG["_fixture"]
    assert callable(factory)
    raw = factory()
    assert _is_object_tuple(raw)
    assert len(raw) == 3
    manifest, verified, vault = raw
    assert type(manifest) is bytes
    assert isinstance(vault, _LegislationVaultFixture)
    return manifest, verified, vault


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return type(value) is list


def _is_object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _is_string_list(value: object) -> TypeIs[list[str]]:
    return _is_object_list(value) and all(type(item) is str for item in value)


def _is_string_matrix(value: object) -> TypeGuard[list[list[str]]]:
    return _is_object_list(value) and all(_is_string_list(item) for item in value)


class _StrictTypedRunner:
    """Return exact typed model documents and expose replay/no-call behavior."""

    def __init__(self) -> None:
        self.calls = 0
        self.proposal_fingerprint = ""

    def invoke_exact_json(
        self,
        profile: object,
        request: SemanticTaskRequest,
        *,
        output_schema: str,
    ) -> bytes:
        del profile
        self.calls += 1
        if output_schema.endswith("decision-output/v1"):
            evidence = parse_json_bytes(request.evidence_bytes, max_bytes=1_000_000)
            assert type(evidence) is dict
            opinions = evidence["opinions"]
            assert type(opinions) is list
            assert opinions
            opinion = opinions[0]
            assert type(opinion) is dict
            paragraphs = opinion["paragraphs"]
            assert type(paragraphs) is list
            assert paragraphs
            paragraph = paragraphs[0]
            assert type(paragraph) is dict
            paragraph_ref = f"{opinion['opinion_id']}:{paragraph['paragraph_id']}"
            all_refs = [
                f"{item['opinion_id']}:{unit['paragraph_id']}"
                for item in opinions
                if type(item) is dict and _is_json_list(raw_paragraphs := item.get("paragraphs"))
                for unit in raw_paragraphs
                if type(unit) is dict
            ]
            roles = [
                "ANSWER",
                "APPLICATION",
                "ATTRIBUTION",
                "CONTEXT",
                "ISSUE",
                "QUALIFICATION",
                "QUOTATION",
                "RESULT",
            ]
            proposition = checked_json_value(
                {
                    "proposition_id": "proposition_live_fixture",
                    "candidate_id": "candidate_live_fixture",
                    "proposition_text": paragraph["text"],
                    "text_mode": "FAITHFUL_DISTILLATION",
                    "court_id": evidence["court_id"],
                    "opinion_id": opinion["opinion_id"],
                    "judge_names": opinion["judge_names"],
                    "qualification_texts": [paragraph["text"]],
                    "exception_texts": [paragraph["text"]],
                    "support_paragraph_refs": [paragraph_ref],
                    "support_fingerprint": fingerprint(
                        {
                            "support": [
                                {
                                    "paragraph_ref": paragraph_ref,
                                    "text_fingerprint": "sha256:"
                                    + sha256(str(paragraph["text"]).encode()).hexdigest(),
                                }
                            ]
                        }
                    ),
                    "authority_role": opinion["opinion_role"],
                    "legal_issue": "Construction of section 1",
                    "material_context": None,
                    "result_context": "Appeal dismissed",
                    "quotation_paragraph_refs": [paragraph_ref],
                    "evidence_links": [
                        {"role": role, "paragraph_ref": paragraph_ref} for role in roles
                    ],
                }
            )
            assert type(proposition) is dict
            resolutions: list[JsonValue] = [
                checked_json_value(
                    {
                        "paragraph_ref": ref,
                        "resolution": "RESOLVED",
                        "primary_use": (
                            "PROPOSITION_EVIDENCE" if ref == paragraph_ref else "NON_PROPOSITIONAL"
                        ),
                        "evidence_roles": roles if ref == paragraph_ref else [],
                        "non_propositional_reason": (
                            None if ref == paragraph_ref else "NON_MATERIAL_DISCUSSION"
                        ),
                        "citation_or_treatment_lead": False,
                        "screening_handoff_ids": [],
                    }
                )
                for ref in all_refs
            ]
            self.proposal_fingerprint = fingerprint(
                checked_json_value({"propositions": [proposition], "unit_resolutions": resolutions})
            )
            return canonicalize(
                checked_json_value(
                    {
                        "schema_id": output_schema,
                        "schema_version": "1.0.0",
                        "request_id": request.request_id,
                        "complete_reading": True,
                        "proposal_fingerprint": self.proposal_fingerprint,
                        "propositions": [proposition],
                        "unit_resolutions": resolutions,
                    }
                )
            )
        if output_schema.endswith("challenge-output/v1"):
            return canonicalize(
                {
                    "schema_id": output_schema,
                    "schema_version": "1.0.0",
                    "request_id": request.request_id,
                    "proposal_fingerprint": self.proposal_fingerprint,
                    "challenge_code": "PASS",
                    "supporting_evidence_refs": list(request.evidence_refs),
                    "unresolved_facts": [],
                }
            )
        assert output_schema.endswith("later-treatment-proof/v1")
        evidence = parse_json_bytes(request.evidence_bytes, max_bytes=1_000_000)
        assert type(evidence) is dict
        assert type(evidence["opinions"]) is list
        refs = sorted(
            f"{item['opinion_id']}:{unit['paragraph_id']}"
            for item in evidence["opinions"]
            if type(item) is dict and _is_json_list(raw_paragraphs := item.get("paragraphs"))
            for unit in raw_paragraphs
            if type(unit) is dict
        )
        return canonicalize(
            checked_json_value(
                {
                    "schema_id": output_schema,
                    "schema_version": "1.0.0",
                    "judicial_decision_id": request.subject_id,
                    "complete_whole_judgment_reading": True,
                    "examined_paragraph_refs": refs,
                    "treatment_lead_refs": [],
                    "unresolved_facts": [],
                }
            )
        )


def _reseal(document: dict[str, JsonValue]) -> bytes:
    body = dict(document)
    body.pop("fingerprint", None)
    return canonicalize({**body, "fingerprint": "sha256:" + sha256(canonicalize(body)).hexdigest()})


def _journal(
    root: Path,
    vault: LocalImmutableVault,
    cycle_id: str,
    objects: dict[str, bytes],
    retention: RetentionProfile,
) -> str:
    entries = root / "acquisition-journals" / cycle_id / "entries"
    entries.mkdir(parents=True)
    previous = "sha256:" + "0" * 64
    for sequence, (key, body) in enumerate(sorted(objects.items()), start=1):
        receipt = vault.conditional_create(key, body, retention)
        unsigned: dict[str, JsonValue] = {
            "schema_id": "asklegal.acquisition-journal-entry",
            "schema_version": "1.0.0",
            "sequence": sequence,
            "previous_entry_fingerprint": previous,
            "work_item": {"work_item_id": f"awi_{sequence:064x}"},
            "transition": "CAPTURED_VERIFIED",
            "payload": {
                "object_ref": key,
                "content_fingerprint": receipt.reference.fingerprint,
                "body_length": len(body),
                "read_back_verified": True,
            },
        }
        previous = "sha256:" + sha256(canonicalize(unsigned)).hexdigest()
        entries.joinpath(f"{sequence:020d}.json").write_bytes(
            canonicalize({**unsigned, "fingerprint": previous})
        )
    return previous


def _profiles_and_policy(path: Path) -> _Profiles:
    profile_factory = _PROP["_profiles"]
    component_factory = _PROP["_components"]
    assert callable(profile_factory)
    assert callable(component_factory)
    raw_profiles = profile_factory()
    assert _is_object_tuple(raw_profiles)
    assert len(raw_profiles) == 2
    decision = _semantic_profile(raw_profiles[0])
    challenge = _semantic_profile(raw_profiles[1])
    decision = replace(decision, output_schema="asklegal.hk-case-proposition-decision-output/v1")
    challenge = replace(challenge, output_schema="asklegal.hk-case-proposition-challenge-output/v1")
    treatment = replace(
        decision,
        profile_id="case_treatment_profile",
        task="HK_LATER_TREATMENT_DISCOVERY",
        output_schema="asklegal.hk-case-later-treatment-proof/v1",
    )

    def components(profile: SemanticTaskProfile) -> tuple[HKCaseSemanticWorkflowComponent, ...]:
        raw = component_factory(profile)
        assert _is_object_tuple(raw)
        return tuple(_workflow_component(item) for item in raw)

    path.write_bytes(
        canonicalize(
            {
                "schema_id": "asklegal.hk-v1-case-processing-policy/v1",
                "schema_version": "1.0.0",
                "source_snapshot_id": "source_snapshot_live_fixture",
                "output_budget_bytes": 24_000,
                "decision_workflow_components": [
                    {
                        "component_role": item.component_role,
                        "fingerprint": item.fingerprint,
                    }
                    for item in components(decision)
                ],
                "challenge_workflow_components": [
                    {
                        "component_role": item.component_role,
                        "fingerprint": item.fingerprint,
                    }
                    for item in components(challenge)
                ],
                "serving_profile": {
                    "serving_record_profile_id": "srp_" + "5" * 48,
                    "schema_version": "1.0.0",
                    "schema_fingerprint": "sha256:" + "3" * 64,
                },
            }
        )
    )
    return _Profiles((decision, challenge, treatment))


def _retained_payload(
    tmp_path: Path,
) -> tuple[dict[str, JsonValue], LocalImmutableVault, Path]:
    payload = _acceptance_payload()
    request = payload["request"]
    acquisition = payload["acquisition"]
    assert type(request) is dict
    assert type(acquisition) is dict
    operation = "op_acceptance_fixture"
    request["operation_id"] = operation
    request["command_fingerprint"] = "sha256:" + "9" * 64
    request["observation_cutoff"] = _CUTOFF
    acquisition["operation_id"] = operation
    acquisition["command_fingerprint"] = request["command_fingerprint"]
    acquisition["observation_cutoff"] = _CUTOFF
    retention = RetentionProfile("source-v1", "2099-01-01T00:00:00Z")
    vault = LocalImmutableVault((tmp_path / "primary").resolve(), VaultName.PRIMARY)
    journal_root = (tmp_path / "journals").resolve()
    case_manifest, case_vault = _case_inputs()
    case_document = parse_json_bytes(case_manifest, max_bytes=1_000_000)
    assert type(case_document) is dict
    case_document["observation_cutoff"] = _CUTOFF
    year_dispositions = case_document["year_dispositions"]
    assert type(year_dispositions) is list
    case_document["year_dispositions"] = [
        *year_dispositions,
        *[
            {
                "discovered_judgments": 0,
                "final_page": 1,
                "first_in_scope_date": f"{year:04d}-01-01",
                "result": "COMPLETE",
                "retryable_items": 0,
                "verified_judgments": 0,
                "verified_listing_pages": 1,
                "year": year,
            }
            for year in range(1998, 2027)
        ],
    ]
    case_document["journal_head_fingerprint"] = _journal(
        journal_root, vault, str(case_document["cycle_id"]), case_vault.bodies, retention
    )
    case_manifest = _reseal(case_document)
    leg_manifest, _verified, leg_vault = _legislation_inputs()
    leg_document = parse_json_bytes(leg_manifest, max_bytes=1_000_000)
    assert type(leg_document) is dict
    leg_objects = {key: body for key, (_ref, body) in leg_vault.objects.items()}
    leg_document["journal_head_fingerprint"] = _journal(
        journal_root, vault, str(leg_document["cycle_id"]), leg_objects, retention
    )
    leg_manifest = _reseal(leg_document)
    children: list[dict[str, JsonValue]] = []
    family_manifests = acquisition["family_manifests"]
    assert _is_json_list(family_manifests)
    for index, (family, manifest, document) in enumerate(
        (("CASES", case_manifest, case_document), ("LEGISLATION", leg_manifest, leg_document))
    ):
        parsed = parse_json_bytes(manifest, max_bytes=1_000_000)
        assert type(parsed) is dict
        manifest_fingerprint = str(parsed["fingerprint"])
        field = (
            "cases_manifest_fingerprint"
            if family == "CASES"
            else "legislation_manifest_fingerprint"
        )
        request[field] = manifest_fingerprint
        row = family_manifests[index]
        assert type(row) is dict
        row["manifest_fingerprint"] = manifest_fingerprint
        receipt = vault.conditional_create(
            f"due/family-manifests/{family.casefold()}", manifest, retention
        )
        children.append(
            {
                "source_family": family,
                "cycle_id": document["cycle_id"],
                "journal_ref": f"acquisition-journals/{document['cycle_id']}",
                "manifest_fingerprint": manifest_fingerprint,
                "journal_head_fingerprint": parsed["journal_head_fingerprint"],
                "result": "COMPLETE",
                "manifest_reference": {
                    "vault": "PRIMARY",
                    "logical_key": receipt.reference.logical_key,
                    "version_id": receipt.reference.version_id,
                    "fingerprint": receipt.reference.fingerprint,
                    "byte_length": receipt.reference.byte_length,
                },
            }
        )
    root_cycle = "cyc_due_composed"
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
                    "observation_cutoff": _CUTOFF,
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
    return payload, vault, journal_root


def _write_package_facts(root: Path, operation_root: Path) -> None:
    source = _ROOT / "apps/review-api/tests/fixtures/hk_v1_review"
    root.mkdir(parents=True)
    for relative in (
        "hk-v1-review-package.json",
        "hk-v1-review-readiness.json",
        "hk-v1-two-family-proposal.json",
        "coverage-status/coverage.json",
        "promotion-manifest/promotion-manifest.json",
        "cost-and-capacity/admission.json",
        "review-report/report.json",
        "record-traceability/lookup.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        document = parse_json_bytes((source / relative).read_bytes(), max_bytes=1_000_000)
        assert type(document) is dict
        if "observation_cutoff" in document:
            document["observation_cutoff"] = _CUTOFF
        if relative == "hk-v1-two-family-proposal.json":
            document = parse_json_bytes(_reseal(document), max_bytes=1_000_000)
            assert type(document) is dict
        if relative == "coverage-status/coverage.json":
            scopes = document["scopes"]
            assert type(scopes) is list
            for scope in scopes:
                assert type(scope) is dict
                scope["last_verified_at"] = _CUTOFF
            cycle = document["source_cycle"]
            assert type(cycle) is dict
            cycle["observation_cutoff"] = _CUTOFF
        target.write_bytes(canonicalize(document))
    releases = preview_generated_family_releases(operation_root)
    by_scope = {
        releases.case_release.scope_id: releases.case_release,
        **{
            result.legislation_scope_code: result.release
            for result in releases.legislation_release_set.scope_results
        },
    }
    desired = compose_desired_state(
        _SCOPES,
        tuple(by_scope[scope] for scope in _SCOPES),
        target_key="hk-v1-local",
        observation_cutoff=_CUTOFF,
    )
    coverage = (root / "coverage-status/coverage.json").read_bytes()
    promotion_path = root / "promotion-manifest/promotion-manifest.json"
    promotion = parse_json_bytes(promotion_path.read_bytes(), max_bytes=1_000_000)
    assert type(promotion) is dict
    assert type(promotion["actions"]) is list
    promotion["desired_state_fingerprint"] = desired.inventory_fingerprint
    promotion["coverage_fingerprint"] = "sha256:" + sha256(coverage).hexdigest()
    promotion["valid_from"] = _CUTOFF
    promotion["valid_until"] = "2026-09-09T00:00:00Z"
    promotion["freeze_date"] = "20260908"
    for action in promotion["actions"]:
        assert type(action) is dict
        assert type(action["input_refs"]) is list
        action["deadline"] = promotion["valid_until"]
        for reference in action["input_refs"]:
            if type(reference) is dict and reference.get("ref_type") == "DESIRED_STATE_INVENTORY":
                reference["fingerprint"] = desired.inventory_fingerprint
    predicates = promotion["validity_predicates"]
    assert _is_string_matrix(predicates)
    retained_bodies: dict[str, bytes] = {}
    for relative in (
        "evaluation/model.json",
        "evaluation/retrieval.json",
        "backup/native.json",
        "backup/recovery.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        retained_bodies[relative] = canonicalize({"retained": relative})
        target.write_bytes(retained_bodies[relative])
    predicates.extend(
        [contract, "1.0.0", "sha256:" + sha256(retained_bodies[relative]).hexdigest()]
        for contract, relative in (
            ("HK_V1_MODEL_EVALUATION", "evaluation/model.json"),
            ("HK_V1_RETRIEVAL_EVALUATION", "evaluation/retrieval.json"),
            ("HK_V1_NATIVE_BACKUP", "backup/native.json"),
            ("HK_V1_RECOVERY_BACKUP", "backup/recovery.json"),
        )
    )
    predicates.sort()
    promotion_path.write_bytes(canonicalize(promotion))


@dataclass(frozen=True, slots=True)
class _FreezeContext:
    freezer: LocalReviewArtifactFreezer
    payload: dict[str, JsonValue]
    releases: TwoFamilyAcceptanceReleases
    inputs: TwoFamilyAcceptanceInputs
    review: Path


def _freeze_after_interruption(
    context: _FreezeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ExactObjectReference, ExactObjectReference]:
    original_store = acceptance_module.__dict__["_atomic_store"]
    writes = 0
    interruption_code = "TEST_GENERATION_INTERRUPTED"

    def interrupted_store(path: Path, content: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes == 3:
            raise AcceptanceLegalError(interruption_code)
        original_store(path, content)

    monkeypatch.setattr(acceptance_module, "_atomic_store", interrupted_store)
    with pytest.raises(AcceptanceLegalError, match=interruption_code):
        context.freezer.freeze_exact(context.payload, context.releases, context.inputs)
    assert not (context.review / "current").exists()
    monkeypatch.setattr(acceptance_module, "_atomic_store", original_store)
    return context.freezer.freeze_exact(
        context.payload, context.releases, context.inputs
    ), context.freezer.freeze_exact(context.payload, context.releases, context.inputs)


def test_retained_acquisition_to_eleven_member_freeze_is_restart_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exact source refs and strict fake outputs reach one read-back-verified proposal."""
    payload, vault, journals = _retained_payload(tmp_path)
    operation = "op_acceptance_fixture"
    processed = (tmp_path / "processed").resolve()
    staged = (tmp_path / "staged").resolve()
    retained = (tmp_path / "retained").resolve()
    state = (tmp_path / "state").resolve()
    facts = (tmp_path / "facts").resolve()
    policy = (tmp_path / "case-policy.json").resolve()
    profiles = _profiles_and_policy(policy)
    runner = _StrictTypedRunner()
    preparer = LiveAcceptanceComponentPreparer(
        vault, profiles, _Counter(), runner, policy, state, processed, facts
    )
    producer = LocalAcceptanceInputProducer(processed, staged, journals, vault, preparer)

    with pytest.raises(AcceptanceLegalError, match="LEGAL_PROCESSING_PACKAGE_FACTS_NOT_READY"):
        producer.produce_exact(payload)
    assert runner.calls == 3
    _write_package_facts(facts, processed / operation)

    producer.produce_exact(payload)
    producer.produce_exact(payload)
    assert runner.calls == 3
    materializer = LocalAcceptanceInputMaterializer(staged, retained)
    materializer.materialize_exact(payload)
    materializer.materialize_exact(payload)
    inputs = LocalAcceptanceLegalInputReader(retained).read_exact(operation)
    releases = build_two_family_acceptance_releases(inputs)
    review = (tmp_path / "review").resolve()
    freezer = LocalReviewArtifactFreezer(
        retained,
        review,
        vault,
        RetentionProfile("proposal-v1", "2099-01-01T00:00:00Z"),
    )
    first, second = _freeze_after_interruption(
        _FreezeContext(freezer, payload, releases, inputs, review), monkeypatch
    )

    assert first == second
    assert len(list((review / "current").rglob("*.json"))) == 14
    assert vault.read_exact(first) == (review / "current/hk-v1-review-package.json").read_bytes()

    materialization = staged / operation / "acceptance-materialization.json"
    drifted = parse_json_bytes(materialization.read_bytes(), max_bytes=16_777_216)
    assert type(drifted) is dict
    drifted["command_fingerprint"] = "sha256:" + "8" * 64
    materialization.write_bytes(canonicalize(drifted))
    before = runner.calls
    with pytest.raises(
        AcceptanceLegalError, match="LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_DRIFT"
    ):
        materializer.materialize_exact(payload)
    assert runner.calls == before
