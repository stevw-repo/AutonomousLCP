"""Source-neutral Plan 4 Task 2 proposition-request construction tests."""

from __future__ import annotations

import copy
import gc
import json
import pickle
import weakref
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256

import asklegal_legal_desks.hk_case_proposition as proposition_module
import pytest
from asklegal_contracts import fingerprint
from asklegal_legal_desks.hk_case_coverage_ledger import (
    HKCaseEvidenceRole,
    HKCaseNonPropositionalReason,
    HKCaseOpinionRole,
    HKCasePrimaryUse,
    HKCaseUnitResolution,
)
from asklegal_legal_desks.hk_case_judgment import (
    HKCaseEvidenceMember,
    HKCaseJudgmentBundle,
    load_hk_case_judgment_bundle,
)
from asklegal_legal_desks.hk_case_proposition import (
    HKCaseAdmittedEvidenceLink,
    HKCaseAdmittedProposition,
    HKCaseAdmittedSemanticDecision,
    HKCaseAdmittedUnitResolution,
    HKCasePropositionReadingLedgerEntry,
    HKCasePropositionRequestAuthorities,
    HKCasePropositionRequestError,
    HKCasePropositionRequestErrorCode,
    HKCasePropositionRequestPair,
    admit_hk_case_propositions,
    bind_hk_case_proposition_challenge,
    build_hk_case_proposition_requests,
)
from asklegal_legal_desks.hk_case_semantic_task import (
    HKCaseSemanticTaskOutcome,
    HKCaseSemanticWorkflowComponent,
    evaluate_hk_case_semantic_task_request,
)
from asklegal_legal_desks.model import SemanticTaskProfile


class _Court(StrEnum):
    CFA = "CFA"


class _Role(StrEnum):
    ORIGINAL = "ORIGINAL"
    TRANSLATION = "TRANSLATION"


class _Language(StrEnum):
    ENGLISH = "ENGLISH"
    TRADITIONAL_CHINESE = "TRADITIONAL_CHINESE"


@dataclass(frozen=True, slots=True)
class _Artifact:
    artifact_identity: str
    listing_identity: str
    source_id: str
    role: _Role
    language: _Language
    opinion_or_reasons_identity: str

    def __post_init__(self) -> None:
        if type(self.artifact_identity) is not str or type(self.listing_identity) is not str:
            raise TypeError


@dataclass(frozen=True, slots=True)
class _Listing:
    listing_identity: str
    court_family: _Court
    decision_date: str
    artifacts: tuple[_Artifact, ...]
    opinion_or_reasons_identities: tuple[str, ...]
    case_name: str = "Fixture v Example"
    neutral_citations: tuple[str, ...] = ("2020 HKCFA 1",)
    reported_citations: tuple[str, ...] = ()
    proceeding_numbers: tuple[str, ...] = ("P-1",)

    def __post_init__(self) -> None:
        if (
            type(self.artifacts) is not tuple
            or type(self.opinion_or_reasons_identities) is not tuple
        ):
            raise TypeError


class _Reader:
    def __init__(self, bodies: dict[str, bytes]) -> None:
        self._bodies = bodies

    def read_exact(self, member: HKCaseEvidenceMember) -> bytes:
        return self._bodies[member.reference]


def _fingerprint(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _bundle(
    *,
    majority_text: str | tuple[str, ...] = "Majority paragraph.",
    translation_text: str = "UNRELATED TRANSLATION FIXTURE MARKER",
    neutral_citations: tuple[str, ...] = ("2020 HKCFA 1",),
    reported_citations: tuple[str, ...] = (),
    proceeding_numbers: tuple[str, ...] = ("P-1",),
) -> HKCaseJudgmentBundle:
    artifacts = (
        _Artifact(
            "artifact-dissent",
            "listing-current",
            "HK-CASE-JUDICIARY-JUDGMENT",
            _Role.ORIGINAL,
            _Language.ENGLISH,
            "dissent",
        ),
        _Artifact(
            "artifact-majority",
            "listing-current",
            "HK-CASE-JUDICIARY-JUDGMENT",
            _Role.ORIGINAL,
            _Language.ENGLISH,
            "majority",
        ),
        _Artifact(
            "artifact-translation",
            "listing-current",
            "HK-CASE-JUDICIARY-TRANSLATION",
            _Role.TRANSLATION,
            _Language.TRADITIONAL_CHINESE,
            "majority",
        ),
    )
    listing = _Listing(
        "listing-current",
        _Court.CFA,
        "2020-01-02",
        artifacts,
        ("dissent", "majority"),
        "Fixture v Example",
        neutral_citations,
        reported_citations,
        proceeding_numbers,
    )
    bodies = {
        "evidence/artifact-majority": _body(
            artifacts[1],
            "MAJORITY",
            majority_text,
            ("Judge A", "Judge B"),
        ),
        "evidence/artifact-dissent": _body(artifacts[0], "DISSENT", "Dissent paragraph."),
        "evidence/artifact-translation": _body(artifacts[2], "SEPARATE", translation_text),
    }
    members = tuple(
        HKCaseEvidenceMember(
            item.artifact_identity,
            listing.listing_identity,
            f"evidence/{item.artifact_identity}",
            _fingerprint(bodies[f"evidence/{item.artifact_identity}"]),
            len(bodies[f"evidence/{item.artifact_identity}"]),
        )
        for item in artifacts
    )
    return load_hk_case_judgment_bundle(listing, members, _Reader(bodies))


def _body(
    artifact: _Artifact,
    opinion_role: str,
    paragraph: str | tuple[str, ...],
    judge_names: tuple[str, ...] = ("Judge Example",),
) -> bytes:
    paragraphs = (
        [
            {
                "locator": f"loc-{artifact.artifact_identity}",
                "paragraph_id": f"para-{artifact.artifact_identity}",
                "text": paragraph,
            }
        ]
        if type(paragraph) is str
        else [
            {
                "locator": f"loc-{artifact.artifact_identity}-{index}",
                "paragraph_id": f"para-{artifact.artifact_identity}-{index}",
                "text": text,
            }
            for index, text in enumerate(paragraph, start=1)
        ]
    )
    return json.dumps(
        {
            "artifact_identity": artifact.artifact_identity,
            "court_id": "CFA",
            "decision_date": "2020-01-02",
            "judge_names": list(judge_names),
            "language": artifact.language.value,
            "listing_identity": artifact.listing_identity,
            "opinion_id": artifact.opinion_or_reasons_identity,
            "opinion_role": opinion_role,
            "paragraphs": paragraphs,
            "schema_id": "asklegal.hk-case-judgment-artifact/v1",
            "source_id": artifact.source_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _profile(profile_id: str, task: str, prompt: str) -> SemanticTaskProfile:
    return SemanticTaskProfile(
        profile_id=profile_id,
        task=task,
        provider="LOCAL_FAKE",
        resource_class="local",
        geography_class="local",
        deployment_name="disabled",
        model_id="fake",
        model_version="1",
        api_contract="v1",
        tokenizer="HK_CASE_CODEPOINT_FIXTURE_V1",
        prompt_fingerprint=_fingerprint(prompt.encode()),
        input_schema="case-proposition-input/v1",
        output_schema="case-proposition-output/v1",
        evidence_budget_bytes=100_000,
        max_output_tokens=1000,
        content_filter_policy="strict",
        retry_policy="none",
        data_handling_profile="local",
        evaluator_id="fixture",
        threshold_basis_points=9000,
        expires_at="2030-01-01T00:00:00+00:00",
        stateful_features=False,
        allowed_environments=("LOCAL_SYNTHETIC",),
    )


def _profiles() -> tuple[SemanticTaskProfile, SemanticTaskProfile]:
    return (
        _profile("case_decision_profile", "HK_CASE_PROPOSITION_ANALYSIS", "decision prompt"),
        _profile("case_challenge_profile", "HK_CASE_PROPOSITION_CHALLENGE", "challenge prompt"),
    )


def _profile_fingerprint(profile: SemanticTaskProfile) -> str:
    """Mirror the retained exact profile snapshot, without granting construction defaults."""
    return fingerprint(
        {
            "profile_id": profile.profile_id,
            "task": profile.task,
            "provider": profile.provider,
            "resource_class": profile.resource_class,
            "geography_class": profile.geography_class,
            "deployment_name": profile.deployment_name,
            "model_id": profile.model_id,
            "model_version": profile.model_version,
            "api_contract": profile.api_contract,
            "tokenizer": profile.tokenizer,
            "prompt_fingerprint": profile.prompt_fingerprint,
            "input_schema": profile.input_schema,
            "output_schema": profile.output_schema,
            "evidence_budget_bytes": profile.evidence_budget_bytes,
            "max_output_tokens": profile.max_output_tokens,
            "content_filter_policy": profile.content_filter_policy,
            "retry_policy": profile.retry_policy,
            "data_handling_profile": profile.data_handling_profile,
            "evaluator_id": profile.evaluator_id,
            "threshold_basis_points": profile.threshold_basis_points,
            "expires_at": profile.expires_at,
            "stateful_features": profile.stateful_features,
            "allowed_environments": list(profile.allowed_environments),
        }
    )


def _components(profile: SemanticTaskProfile) -> tuple[HKCaseSemanticWorkflowComponent, ...]:
    return tuple(
        HKCaseSemanticWorkflowComponent(
            role,
            profile.prompt_fingerprint
            if role == "PROMPT"
            else _profile_fingerprint(profile)
            if role == "MODEL_SETTINGS"
            else _fingerprint(f"authority:{profile.profile_id}:{role}".encode()),
        )
        for role in (
            "COVERAGE_LEDGER",
            "MODEL_SETTINGS",
            "OUTPUT_SCHEMA",
            "PARSER_PROFILE",
            "PROCESSING_BUILD",
            "PROMPT",
            "SEGMENTATION_CONTRACT",
            "SOURCE_RULEBOOK",
            "STRUCTURE_CONTRACT",
            "VALIDATOR",
        )
    )


def _authorities(
    bundle: HKCaseJudgmentBundle, profiles: tuple[SemanticTaskProfile, SemanticTaskProfile]
) -> HKCasePropositionRequestAuthorities:
    return HKCasePropositionRequestAuthorities(
        processing_cutoff="2026-08-01",
        source_snapshot_id="source_snapshot_fixture",
        source_snapshot_fingerprint=_fingerprint(b"source-snapshot-fixture"),
        judgment_artifact_fingerprint=bundle.bundle_fingerprint,
        official_version_id="official_version_fixture",
        official_version_fingerprint=_fingerprint(b"official-version-fixture"),
        decision_workflow_components=_components(profiles[0]),
        challenge_workflow_components=_components(profiles[1]),
        output_budget_bytes=4096,
    )


def _build(
    bundle: HKCaseJudgmentBundle, profiles: tuple[SemanticTaskProfile, SemanticTaskProfile]
) -> HKCasePropositionRequestPair:
    return build_hk_case_proposition_requests(bundle, profiles, _authorities(bundle, profiles))


def _admitted(
    pair: HKCasePropositionRequestPair,
    *,
    complete_reading: bool = True,
    propositions: tuple[HKCaseAdmittedProposition, ...] | None = None,
    support_refs: tuple[str, ...] | None = None,
    context_refs: tuple[str, ...] = (),
) -> HKCaseAdmittedSemanticDecision:
    paragraph_texts = {
        f"{opinion['opinion_id']}:{paragraph['paragraph_id']}": paragraph["text"]
        for opinion in json.loads(pair.decision.evidence_bytes)["opinions"]
        for paragraph in opinion["paragraphs"]
    }
    selected_support_refs = (
        support_refs
        if support_refs is not None
        else (next(ref for ref in pair.paragraph_refs if ref.startswith("majority:")),)
    )
    primary_ref = selected_support_refs[0]
    evidence_links = tuple(
        HKCaseAdmittedEvidenceLink(role, primary_ref)
        for role in (
            HKCaseEvidenceRole.ANSWER,
            HKCaseEvidenceRole.APPLICATION,
            HKCaseEvidenceRole.ATTRIBUTION,
            HKCaseEvidenceRole.CONTEXT,
            HKCaseEvidenceRole.ISSUE,
            HKCaseEvidenceRole.QUALIFICATION,
            HKCaseEvidenceRole.QUOTATION,
            HKCaseEvidenceRole.RESULT,
        )
    ) + tuple(HKCaseAdmittedEvidenceLink(HKCaseEvidenceRole.CONTEXT, ref) for ref in context_refs)
    proposition = HKCaseAdmittedProposition(
        proposition_id="proposition_fixture",
        candidate_id="candidate_fixture",
        proposition_text=paragraph_texts[primary_ref],
        text_mode="FAITHFUL_DISTILLATION",
        court_id="CFA",
        opinion_id="majority",
        judge_names=("Judge A", "Judge B"),
        qualification_texts=(paragraph_texts[primary_ref],),
        exception_texts=(paragraph_texts[primary_ref],),
        support_paragraph_refs=selected_support_refs,
        support_fingerprint=fingerprint(
            {
                "support": [
                    {
                        "paragraph_ref": reference,
                        "text_fingerprint": _fingerprint(
                            paragraph_texts[reference].encode("utf-8")
                        ),
                    }
                    for reference in selected_support_refs
                ]
            }
        ),
        authority_role=HKCaseOpinionRole.LEAD,
        legal_issue="Fixture issue",
        material_context=None,
        result_context="Fixture result",
        quotation_paragraph_refs=(primary_ref,),
        evidence_links=evidence_links,
    )
    admitted_propositions = (proposition,) if propositions is None else propositions
    resolutions = tuple(
        HKCaseAdmittedUnitResolution(
            paragraph_ref=reference,
            resolution=HKCaseUnitResolution.RESOLVED,
            primary_use=(
                HKCasePrimaryUse.NON_PROPOSITIONAL
                if not admitted_propositions or reference not in selected_support_refs
                else (
                    HKCasePrimaryUse.CONTEXT_EVIDENCE
                    if reference in context_refs
                    else HKCasePrimaryUse.PROPOSITION_EVIDENCE
                )
            ),
            evidence_roles=(
                ()
                if not admitted_propositions or reference not in selected_support_refs
                else tuple(
                    role
                    for role in HKCaseEvidenceRole
                    if any(
                        link.role is role and link.paragraph_ref == reference
                        for link in evidence_links
                    )
                )
            ),
            non_propositional_reason=(
                HKCaseNonPropositionalReason.NON_MATERIAL_DISCUSSION
                if not admitted_propositions or reference not in selected_support_refs
                else None
            ),
            citation_or_treatment_lead=False,
            screening_handoff_ids=(),
        )
        for reference in pair.paragraph_refs
    )
    return HKCaseAdmittedSemanticDecision(
        request_id=pair.decision.request_id,
        proposal_fingerprint=_proposal_fingerprint(admitted_propositions, resolutions),
        complete_reading=complete_reading,
        challenge_complete=True,
        propositions=admitted_propositions,
        unit_resolutions=resolutions,
    )


def _proposal_fingerprint(
    propositions: tuple[HKCaseAdmittedProposition, ...],
    resolutions: tuple[HKCaseAdmittedUnitResolution, ...],
) -> str:
    return fingerprint(
        {
            "propositions": [
                {
                    "proposition_id": item.proposition_id,
                    "candidate_id": item.candidate_id,
                    "proposition_text": item.proposition_text,
                    "text_mode": item.text_mode,
                    "court_id": item.court_id,
                    "opinion_id": item.opinion_id,
                    "judge_names": list(item.judge_names),
                    "qualification_texts": list(item.qualification_texts),
                    "exception_texts": list(item.exception_texts),
                    "support_paragraph_refs": list(item.support_paragraph_refs),
                    "support_fingerprint": item.support_fingerprint,
                    "authority_role": item.authority_role.value,
                    "legal_issue": item.legal_issue,
                    "material_context": item.material_context,
                    "result_context": item.result_context,
                    "quotation_paragraph_refs": list(item.quotation_paragraph_refs),
                    "evidence_links": [
                        {"role": link.role.value, "paragraph_ref": link.paragraph_ref}
                        for link in item.evidence_links
                    ],
                }
                for item in propositions
            ],
            "unit_resolutions": [
                {
                    "paragraph_ref": item.paragraph_ref,
                    "resolution": item.resolution.value,
                    "primary_use": item.primary_use.value,
                    "evidence_roles": [role.value for role in item.evidence_roles],
                    "non_propositional_reason": (
                        item.non_propositional_reason.value
                        if item.non_propositional_reason is not None
                        else None
                    ),
                    "citation_or_treatment_lead": item.citation_or_treatment_lead,
                    "screening_handoff_ids": list(item.screening_handoff_ids),
                }
                for item in resolutions
            ],
        }
    )


def _as_exact_quotation(item: HKCaseAdmittedProposition) -> HKCaseAdmittedProposition:
    return replace(item, text_mode="EXACT_QUOTATION")


def _move_qualifications_to_exceptions(
    item: HKCaseAdmittedProposition,
) -> HKCaseAdmittedProposition:
    return replace(
        item,
        qualification_texts=(),
        exception_texts=item.qualification_texts + item.exception_texts,
    )


def test_request_pair_is_judgment_only_and_preserves_complete_opinion_attribution() -> None:
    """Including translation or dropping a dissent would corrupt the decision's evidence scope."""
    pair = _build(_bundle(), _profiles())

    assert type(pair) is HKCasePropositionRequestPair
    assert pair.decision.subject_id == "judgment-listing-current"
    assert pair.decision.evidence_bytes == pair.challenge.evidence_bytes
    assert pair.decision.input_fingerprint == pair.challenge.input_fingerprint
    assert pair.paragraph_refs == (
        "dissent:para-artifact-dissent",
        "majority:para-artifact-majority",
    )
    rendered = pair.decision.evidence_bytes.decode("utf-8")
    assert "Dissent paragraph." in rendered
    assert "UNRELATED TRANSLATION FIXTURE MARKER" not in rendered
    result = evaluate_hk_case_semantic_task_request(pair.decision.semantic_task)
    assert result.outcome is HKCaseSemanticTaskOutcome.VALID_REQUEST
    assert result.complete_judgment_assignment is True
    assert result.provider_call_authorized is False
    assert pair.challenge.evidence_bytes == pair.decision.evidence_bytes
    assert pair.challenge.input_fingerprint == pair.decision.input_fingerprint


def test_task3_red_omitted_qualification_or_exception_is_not_admitted() -> None:
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)
    proposition = replace(decision.propositions[0], qualification_texts=("unrelated",))
    with pytest.raises(HKCasePropositionRequestError):
        admit_hk_case_propositions(pair, replace(decision, propositions=(proposition,)))


def test_task3_red_cross_opinion_or_unsupported_paragraph_is_not_admitted() -> None:
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)
    proposition = replace(decision.propositions[0], support_paragraph_refs=("foreign:para",))
    with pytest.raises(HKCasePropositionRequestError):
        admit_hk_case_propositions(pair, replace(decision, propositions=(proposition,)))


def test_task3_red_unsafe_zero_requires_complete_reading_and_challenge() -> None:
    pair = _build(_bundle(), _profiles())
    with pytest.raises(HKCasePropositionRequestError):
        admit_hk_case_propositions(pair, _admitted(pair, complete_reading=False, propositions=()))
    assert admit_hk_case_propositions(pair, _admitted(pair, propositions=())).propositions == ()


def test_task3_red_duplicate_candidate_and_quotation_mismatch_are_not_admitted() -> None:
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)
    duplicate = replace(decision.propositions[0], proposition_id="proposition_second")
    with pytest.raises(HKCasePropositionRequestError):
        admit_hk_case_propositions(
            pair, replace(decision, propositions=(decision.propositions[0], duplicate))
        )


def test_task3_red_quotation_mismatch_is_not_admitted() -> None:
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)
    mismatch = replace(
        decision.propositions[0], text_mode="EXACT_QUOTATION", proposition_text="forged"
    )
    with pytest.raises(HKCasePropositionRequestError):
        admit_hk_case_propositions(pair, replace(decision, propositions=(mismatch,)))


def test_task3_red_admission_returns_complete_mature_output_projection() -> None:
    pair = _build(_bundle(), _profiles())
    result = admit_hk_case_propositions(pair, _admitted(pair))
    assert result.disposition == "COMPLETE_PROPOSITIONS"
    assert result.output_result.outcome.value == "VALID_OUTPUT"


def test_task3_red_supported_zero_returns_complete_mature_output_projection() -> None:
    pair = _build(_bundle(), _profiles())
    result = admit_hk_case_propositions(pair, _admitted(pair, propositions=()))
    assert result.disposition == "COMPLETE_ZERO_PROPOSITIONS"
    assert result.output_result.outcome.value == "VALID_ZERO_OUTPUT"


def test_task3_output_adapter_maps_every_paragraph_to_one_whole_source_range_and_record() -> None:
    """A subrange or omitted paragraph would make the admitted output untraceable."""
    pair = _build(_bundle(), _profiles())
    result = admit_hk_case_propositions(pair, _admitted(pair))

    request = result.output_request
    assert [unit.source_order for unit in request.source_units] == [1, 2]
    assert len(request.source_ranges) == len(request.source_units)
    assert all(
        source_range.start_byte == 0
        and source_range.end_byte
        == len(
            next(
                unit for unit in request.source_units if unit.unit_id == source_range.unit_id
            ).exact_text.encode("utf-8")
        )
        for source_range in request.source_ranges
    )
    assert request.proposed_records[0].proposition_id == "proposition_fixture"
    assert result.output_result.outcome.value == "VALID_OUTPUT"


def test_task3_output_adapter_preserves_exact_role_to_paragraph_and_quotation_authority() -> None:
    """Changing a role's paragraph would allow a quotation or limit to lose its source authority."""
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)
    result = admit_hk_case_propositions(pair, decision)

    proposition = result.output_request.propositions[0]
    range_by_id = {item.range_id: item for item in result.output_request.source_ranges}
    unit_by_id = {item.unit_id: item for item in result.output_request.source_units}
    paragraph_by_range = {
        range_id: unit_by_id[source_range.unit_id].exact_text
        for range_id, source_range in range_by_id.items()
    }
    assert {link.role for link in proposition.evidence_links} == (
        set(HKCaseEvidenceRole) - {HKCaseEvidenceRole.SUPPLEMENTARY}
    )
    assert {link.role: paragraph_by_range[link.range_id] for link in proposition.evidence_links}[
        HKCaseEvidenceRole.QUOTATION
    ] == proposition.quotations[0].exact_text
    assert proposition.quotations[0].exact_text == "Majority paragraph."


def test_task3_output_adapter_derives_codepoint_profile_from_retained_bytes() -> None:
    """A display-only tokenizer label cannot validate with a different counter."""
    profiles = _profiles()
    pair = _build(_bundle(), profiles)
    result = admit_hk_case_propositions(pair, _admitted(pair))

    assert result.output_request.tokenizer_profile_fingerprint == fingerprint(
        {
            "tokenizer": "HK_CASE_CODEPOINT_FIXTURE_V1",
            "profile_fingerprint": _profile_fingerprint(profiles[0]),
        }
    )
    assert result.output_result.measured_text_token_counts == (
        len(result.output_request.proposed_records[0].text),
    )


def test_task3_admission_direct_replace_replays_ledger_and_output_evaluators() -> None:
    """Replacing a retained output request without a matching evaluated result must fail closed."""
    pair = _build(_bundle(), _profiles())
    result = admit_hk_case_propositions(pair, _admitted(pair))

    with pytest.raises(HKCasePropositionRequestError):
        replace(result, output_request=replace(result.output_request, max_payload_bytes=1))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("court_id", "CFI"),
        ("judge_names", ("Invented Judge",)),
        ("support_fingerprint", "sha256:" + "e" * 64),
        ("proposition_text", ""),
        ("legal_issue", ""),
        ("result_context", ""),
        ("candidate_id", "BAD ID"),
        ("proposition_id", "BAD ID"),
    ],
)
def test_task3_admission_rejects_source_drift_and_malformed_proposition_identity(
    field: str, value: object
) -> None:
    """Changing a source-bound or identity leaf must never retain COMPLETE_PROPOSITIONS."""
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)

    with pytest.raises(HKCasePropositionRequestError):
        _admit_replaced_proposition(pair, decision, field, value)


def _admit_replaced_proposition(
    pair: HKCasePropositionRequestPair,
    decision: HKCaseAdmittedSemanticDecision,
    field: str,
    value: object,
) -> None:
    proposition = replace(decision.propositions[0], **{field: value})
    admit_hk_case_propositions(
        pair,
        replace(
            decision,
            propositions=(proposition,),
            proposal_fingerprint=_proposal_fingerprint((proposition,), decision.unit_resolutions),
        ),
    )


def test_task3_admission_binds_the_exact_proposal_fingerprint() -> None:
    """A display-only proposal digest would let different parsed output share one admission."""
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)

    with pytest.raises(HKCasePropositionRequestError):
        admit_hk_case_propositions(
            pair, replace(decision, proposal_fingerprint="sha256:" + "b" * 64)
        )

    result = admit_hk_case_propositions(pair, decision)
    assert result.proposal_fingerprint == decision.proposal_fingerprint
    with pytest.raises(HKCasePropositionRequestError):
        replace(result, proposal_fingerprint="sha256:" + "b" * 64)


def test_task3_admission_result_replays_every_public_proposition_fact() -> None:
    """A rebuilt public result must not describe facts different from its ledger/output request."""
    pair = _build(_bundle(), _profiles())
    result = admit_hk_case_propositions(pair, _admitted(pair))

    with pytest.raises(HKCasePropositionRequestError):
        replace(
            result,
            propositions=(replace(result.propositions[0], proposition_text="Invented legal rule"),),
        )


@pytest.mark.parametrize(
    "replacement",
    [
        _as_exact_quotation,
        _move_qualifications_to_exceptions,
    ],
)
def test_task3_result_rejects_coordinated_rebuild_of_unmerged_proposition_facts(
    replacement: Callable[[HKCaseAdmittedProposition], HKCaseAdmittedProposition],
) -> None:
    """Text mode and qualification partition remain authority facts after output rendering."""
    pair = _build(_bundle(), _profiles())
    result = admit_hk_case_propositions(pair, _admitted(pair))
    proposition = replacement(result.propositions[0])

    with pytest.raises(HKCasePropositionRequestError):
        replace(
            result,
            propositions=(proposition,),
            proposal_fingerprint=_proposal_fingerprint(
                (proposition,), result.admitted_decision.unit_resolutions
            ),
        )


def test_task3_result_retains_the_exact_task2_pair_and_admitted_decision() -> None:
    """A ledger/output replay must not float free of its decision and challenge authority."""
    profiles = _profiles()
    pair = _build(_bundle(), profiles)
    result = admit_hk_case_propositions(pair, _admitted(pair))
    changed_pair = _build(
        _bundle(),
        (replace(profiles[0], prompt_fingerprint="sha256:" + "a" * 64), profiles[1]),
    )

    with pytest.raises(HKCasePropositionRequestError):
        replace(result, request_pair=changed_pair)


def test_task3_red_result_rejects_a_fully_resealed_text_mode_or_partition_rewrite() -> None:
    """A result reconstruction cannot self-authorize a different semantic decision."""
    pair = _build(_bundle(), _profiles())
    original = _admitted(pair)
    faithful = replace(
        original.propositions[0],
        proposition_text="The court's faithfully distilled answer differs from its source wording.",
    )
    decision = replace(
        original,
        propositions=(faithful,),
        proposal_fingerprint=_proposal_fingerprint((faithful,), original.unit_resolutions),
    )
    result = admit_hk_case_propositions(pair, decision)
    forged_items = (
        replace(faithful, text_mode="EXACT_QUOTATION"),
        replace(
            faithful,
            qualification_texts=(),
            exception_texts=faithful.qualification_texts + faithful.exception_texts,
        ),
    )

    for forged in forged_items:
        forged_decision = replace(
            decision,
            propositions=(forged,),
            proposal_fingerprint=_proposal_fingerprint((forged,), decision.unit_resolutions),
        )
        projection = proposition_module.canonical_hk_case_proposition_admission_projection(
            pair, forged_decision
        )
        if forged.text_mode == "EXACT_QUOTATION":
            with pytest.raises(HKCasePropositionRequestError):
                proposition_module.replay_hk_case_proposition_admission_projection(
                    pair, forged_decision
                )
        with pytest.raises(HKCasePropositionRequestError):
            replace(
                result,
                propositions=(forged,),
                proposal_fingerprint=forged_decision.proposal_fingerprint,
                admitted_decision=forged_decision,
                admission_projection=projection,
                admission_fingerprint=_fingerprint(projection),
            )


def test_task3_red_replaced_or_mutated_issuance_cannot_reseal_a_partition() -> None:
    """A copied witness cannot turn source-supported exceptions into a new historical result."""
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)
    result = admit_hk_case_propositions(pair, decision)
    forged = replace(
        decision.propositions[0],
        qualification_texts=(),
        exception_texts=(
            decision.propositions[0].qualification_texts + decision.propositions[0].exception_texts
        ),
    )
    forged_decision = replace(
        decision,
        propositions=(forged,),
        proposal_fingerprint=_proposal_fingerprint((forged,), decision.unit_resolutions),
    )
    projection = proposition_module.canonical_hk_case_proposition_admission_projection(
        pair, forged_decision
    )
    copied_witness = replace(result.issuance, projection=projection)

    with pytest.raises(HKCasePropositionRequestError):
        replace(
            result,
            propositions=(forged,),
            proposal_fingerprint=forged_decision.proposal_fingerprint,
            admitted_decision=forged_decision,
            admission_projection=projection,
            admission_fingerprint=_fingerprint(projection),
            issuance=copied_witness,
        )

    object.__setattr__(result.issuance, "projection", projection)
    with pytest.raises(HKCasePropositionRequestError):
        replace(
            result,
            propositions=(forged,),
            proposal_fingerprint=forged_decision.proposal_fingerprint,
            admitted_decision=forged_decision,
            admission_projection=projection,
            admission_fingerprint=_fingerprint(projection),
        )


def test_task3_red_issuance_is_not_copyable_or_serializable() -> None:
    """Process-local issuance is intentionally not a durable result-reconstruction format."""
    pair = _build(_bundle(), _profiles())
    result = admit_hk_case_propositions(pair, _admitted(pair))

    with pytest.raises(TypeError):
        pickle.dumps(result)
    with pytest.raises(TypeError):
        pickle.dumps(result.issuance)
    with pytest.raises(TypeError):
        copy.copy(result.issuance)
    with pytest.raises(TypeError):
        copy.deepcopy(result.issuance)
    with pytest.raises(HKCasePropositionRequestError):
        replace(result)


def test_task3_issuance_registry_does_not_keep_discarded_results_alive() -> None:
    """The process-local witness registry releases its entry when the issued result is discarded."""

    def issue() -> weakref.ReferenceType[object]:
        pair = _build(_bundle(), _profiles())
        result = admit_hk_case_propositions(pair, _admitted(pair))
        return weakref.ref(result.issuance)

    witness = issue()
    gc.collect()

    assert witness() is None


def test_task3_red_result_rejects_a_fully_resealed_pair_workflow_replacement() -> None:
    """A result cannot switch to a different Task2 decision/challenge pair after admission."""
    profiles = _profiles()
    pair = _build(_bundle(), profiles)
    decision = _admitted(pair)
    result = admit_hk_case_propositions(pair, decision)
    changed_pair = _build(
        _bundle(),
        (replace(profiles[0], prompt_fingerprint="sha256:" + "c" * 64), profiles[1]),
    )
    projection = proposition_module.canonical_hk_case_proposition_admission_projection(
        changed_pair, decision
    )

    with pytest.raises(HKCasePropositionRequestError):
        proposition_module.replay_hk_case_proposition_admission_projection(changed_pair, decision)

    with pytest.raises(HKCasePropositionRequestError):
        replace(
            result,
            request_pair=changed_pair,
            admission_projection=projection,
            admission_fingerprint=_fingerprint(projection),
        )


def test_task3_proposal_identity_binds_every_unit_resolution_fact() -> None:
    """A proposition digest cannot survive changed coverage/use accounting."""
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)
    changed_resolution = replace(decision.unit_resolutions[0], citation_or_treatment_lead=True)
    changed_resolutions = (changed_resolution, *decision.unit_resolutions[1:])

    assert decision.proposal_fingerprint != _proposal_fingerprint(
        decision.propositions, changed_resolutions
    )
    with pytest.raises(HKCasePropositionRequestError):
        replace(decision, unit_resolutions=changed_resolutions)


def test_task3_result_rejects_mutated_challenge_workflow_authority() -> None:
    """The challenge's retained workflow facts remain part of result replay, not display data."""
    pair = _build(_bundle(), _profiles())
    result = admit_hk_case_propositions(pair, _admitted(pair))
    object.__setattr__(
        result.request_pair.challenge.authorities.challenge_workflow_components[0],
        "fingerprint",
        "sha256:" + "b" * 64,
    )

    with pytest.raises(HKCasePropositionRequestError):
        replace(result)


def test_task3_result_normalizes_malformed_projection_and_preserves_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad retained projection bytes close locally while process control remains observable."""
    pair = _build(_bundle(), _profiles())
    result = admit_hk_case_propositions(pair, _admitted(pair))
    malformed = b"not-a-canonical-admission-projection"

    with pytest.raises(HKCasePropositionRequestError):
        replace(
            result,
            admission_projection=malformed,
            admission_fingerprint=_fingerprint(malformed),
        )

    def interrupt(_: HKCasePropositionRequestPair, __: HKCaseAdmittedSemanticDecision) -> bytes:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        proposition_module, "canonical_hk_case_proposition_admission_projection", interrupt
    )
    with pytest.raises(KeyboardInterrupt):
        replace(result)


def test_task3_admission_normalizes_malformed_nested_links() -> None:
    """Ordinary hostile nested objects must close at the proposition boundary, not escape raw."""
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)
    object.__setattr__(decision.propositions[0], "evidence_links", (object(),))

    with pytest.raises(HKCasePropositionRequestError):
        admit_hk_case_propositions(pair, decision)


def test_task3_admission_preserves_process_control_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordinary-error normalizer must not swallow cancellation or process control."""
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)

    def interrupt(_: HKCaseAdmittedSemanticDecision) -> HKCaseAdmittedSemanticDecision:
        raise KeyboardInterrupt

    monkeypatch.setattr(proposition_module, "_admitted_decision_snapshot", interrupt)
    with pytest.raises(KeyboardInterrupt):
        admit_hk_case_propositions(pair, decision)


def test_task3_zero_rejects_evidence_roles_on_non_propositional_units() -> None:
    """A zero result cannot retain ANSWER evidence while declaring the unit non-propositional."""
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair, propositions=())
    majority = replace(decision.unit_resolutions[1], evidence_roles=(HKCaseEvidenceRole.ANSWER,))

    with pytest.raises(HKCasePropositionRequestError):
        admit_hk_case_propositions(
            pair, replace(decision, unit_resolutions=(decision.unit_resolutions[0], majority))
        )


def test_task3_proposition_allows_absent_qualification_and_exception_text() -> None:
    """A proposition with no qualification or exception must not invent either section."""
    pair = _build(_bundle(), _profiles())
    decision = _admitted(pair)
    proposition = replace(decision.propositions[0], qualification_texts=(), exception_texts=())
    admitted = replace(
        decision,
        propositions=(proposition,),
        proposal_fingerprint=_proposal_fingerprint((proposition,), decision.unit_resolutions),
    )

    result = admit_hk_case_propositions(pair, admitted)

    assert result.output_request.propositions[0].qualifications is None


def test_task3_admission_preserves_context_units_and_multi_range_roles() -> None:
    """Context evidence and repeated roles may bind several exact ranges without becoming zero."""
    pair = _build(
        _bundle(majority_text=("Majority answer.", "Majority context.")),
        _profiles(),
    )
    answer_ref = "majority:para-artifact-majority-1"
    context_ref = "majority:para-artifact-majority-2"
    decision = _admitted(
        pair,
        support_refs=(answer_ref, context_ref),
        context_refs=(context_ref,),
    )

    result = admit_hk_case_propositions(pair, decision)

    units = {item.unit_id: item for item in result.ledger_request.units}
    assert units["unit_697af72e4b0e726c4637b684b631a57bf9d1044948e958d4"].primary_uses == (
        HKCasePrimaryUse.CONTEXT_EVIDENCE,
    )
    context_links = tuple(
        item.range_id
        for item in result.output_request.propositions[0].evidence_links
        if item.role is HKCaseEvidenceRole.CONTEXT
    )
    assert len(context_links) == 2
    assert len(set(context_links)) == 2


def test_task3_rejects_a_profile_tokenizer_the_local_counter_does_not_implement() -> None:
    """A profile label cannot authorize measurements by a different counter algorithm."""
    decision_profile, challenge_profile = _profiles()
    unsupported = replace(decision_profile, tokenizer="ARBITRARY_PROVIDER_TOKENIZER")
    profiles = (unsupported, challenge_profile)
    pair = _build(_bundle(), profiles)

    with pytest.raises(HKCasePropositionRequestError):
        admit_hk_case_propositions(pair, _admitted(pair))


def test_pair_binds_distinct_exact_profiles_without_changing_the_evidence_input() -> None:
    """Swapping a challenge profile or prompt must not leave a valid independent challenge."""
    pair = _build(_bundle(), _profiles())

    assert pair.decision.profile_id == "case_decision_profile"
    assert pair.challenge.profile_id == "case_challenge_profile"
    assert pair.decision.profile_fingerprint != pair.challenge.profile_fingerprint
    assert pair.decision.input_fingerprint == pair.challenge.input_fingerprint


def test_profile_swap_and_duplicate_profile_are_rejected_before_request_construction() -> None:
    """Accepting a wrong or shared profile would defeat the independent challenge boundary."""
    decision, challenge = _profiles()

    for profiles in (
        (challenge, decision),
        (decision, replace(decision, task="HK_CASE_PROPOSITION_CHALLENGE")),
    ):
        with pytest.raises(HKCasePropositionRequestError) as raised:
            _build(_bundle(), profiles)
        assert raised.value.code is HKCasePropositionRequestErrorCode.PROFILE_BINDING_INVALID


def test_mutating_the_bundle_after_construction_cannot_change_detached_request_bytes() -> None:
    """Retaining a caller-owned judgment graph would make request replay time-of-check dependent."""
    bundle = _bundle()
    pair = _build(bundle, _profiles())
    assert bundle.judgment is not None
    object.__setattr__(bundle.judgment.opinions[0].paragraphs[0], "text", "forged")

    assert b"forged" not in pair.decision.evidence_bytes
    assert pair.decision.input_fingerprint == pair.challenge.input_fingerprint


def test_pair_rejects_incomplete_or_duplicate_reading_ledger_on_reconstruction() -> None:
    """A supported zero or proposition output needs a one-for-one complete reading ledger."""
    pair = _build(_bundle(), _profiles())

    with pytest.raises(HKCasePropositionRequestError) as incomplete:
        replace(pair, reading_ledger=pair.reading_ledger[:-1])
    assert incomplete.value.code is HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID
    with pytest.raises(HKCasePropositionRequestError) as duplicate:
        replace(pair, paragraph_refs=(pair.paragraph_refs[0],) * len(pair.paragraph_refs))
    assert duplicate.value.code is HKCasePropositionRequestErrorCode.READING_LEDGER_INVALID


def test_replay_is_byte_identical_and_translation_drift_does_not_enter_judgment_only_pair() -> None:
    """Translation drift cannot alter request evidence but remains part of its source snapshot."""
    first = _build(_bundle(), _profiles())
    replay = _build(_bundle(), _profiles())
    changed = _build(_bundle(translation_text="different translation"), _profiles())

    assert replay == first
    assert replay.decision.evidence_bytes == first.decision.evidence_bytes
    assert changed.decision.evidence_bytes != first.decision.evidence_bytes
    assert changed.decision.input_fingerprint != first.decision.input_fingerprint
    assert changed.judgment_fingerprint != first.judgment_fingerprint
    assert changed.decision.request_id != first.decision.request_id


def test_original_judgment_drift_changes_the_replay_fingerprint() -> None:
    """An original-paragraph change cannot reuse an earlier evidence binding."""
    first = _build(_bundle(), _profiles())
    changed = _build(_bundle(majority_text="Changed majority paragraph."), _profiles())

    assert changed.judgment_fingerprint != first.judgment_fingerprint
    assert changed.decision.input_fingerprint != first.decision.input_fingerprint


def test_challenge_preparation_requires_a_validated_proposal_before_full_judgment_challenge() -> (
    None
):
    """A pre-decision template cannot claim the proposal binding ADR 0066 requires."""
    pair = _build(_bundle(), _profiles())

    challenge = bind_hk_case_proposition_challenge(
        pair.challenge,
        "sha256:" + "a" * 64,
        pair.challenge.authorities,
    )

    result = evaluate_hk_case_semantic_task_request(challenge.semantic_task)
    assert challenge.semantic_task.request_kind.value == "FULL_JUDGMENT_CHALLENGE"
    assert challenge.semantic_task.validated_proposal_fingerprint == "sha256:" + "a" * 64
    assert result.outcome is HKCaseSemanticTaskOutcome.VALID_REQUEST
    assert result.provider_call_authorized is False


def test_challenge_identity_binds_the_actual_validated_proposal() -> None:
    """Distinct validated proposals cannot share a full-judgment challenge replay identity."""
    pair = _build(_bundle(), _profiles())
    first = bind_hk_case_proposition_challenge(
        pair.challenge, "sha256:" + "a" * 64, pair.challenge.authorities
    )
    second = bind_hk_case_proposition_challenge(
        pair.challenge, "sha256:" + "b" * 64, pair.challenge.authorities
    )
    assert first.request_id != second.request_id
    assert first.semantic_task.attempt_id != second.semantic_task.attempt_id
    replay = bind_hk_case_proposition_challenge(
        pair.challenge, "sha256:" + "a" * 64, pair.challenge.authorities
    )
    assert replay.semantic_task.attempt_id == first.semantic_task.attempt_id


def test_authority_mutation_is_not_a_display_only_replacement() -> None:
    """Cutoff, role fingerprints and output budget all participate in the request identity."""
    pair = _build(_bundle(), _profiles())
    for authorities in (
        replace(pair.decision.authorities, processing_cutoff="2026-08-02"),
        replace(pair.decision.authorities, output_budget_bytes=1),
        replace(
            pair.decision.authorities,
            decision_workflow_components=(
                replace(
                    pair.decision.authorities.decision_workflow_components[0],
                    fingerprint="sha256:" + "f" * 64,
                ),
                *pair.decision.authorities.decision_workflow_components[1:],
            ),
        ),
    ):
        with pytest.raises(HKCasePropositionRequestError):
            replace(pair.decision, authorities=authorities)


def test_processing_cutoff_is_inclusive_of_decision_day_but_never_before_it() -> None:
    """Processing provenance may be contemporaneous, but cannot predate the judgment."""
    bundle = _bundle()
    profiles = _profiles()
    same_day = replace(_authorities(bundle, profiles), processing_cutoff="2020-01-02")
    assert _build(bundle, profiles).decision.authorities.processing_cutoff == "2026-08-01"
    assert build_hk_case_proposition_requests(bundle, profiles, same_day).decision.request_id
    before = replace(same_day, processing_cutoff="2020-01-01")
    with pytest.raises(HKCasePropositionRequestError):
        build_hk_case_proposition_requests(bundle, profiles, before)


def test_explicit_source_snapshot_and_official_version_are_evidence_bound() -> None:
    """The source snapshot is a supplied authority, not the bundle digest in disguise."""
    bundle = _bundle()
    profiles = _profiles()
    first = build_hk_case_proposition_requests(bundle, profiles, _authorities(bundle, profiles))
    distinct = replace(
        _authorities(bundle, profiles),
        source_snapshot_id="source_snapshot_distinct",
        source_snapshot_fingerprint="sha256:" + "c" * 64,
        official_version_id="official_version_distinct",
        official_version_fingerprint="sha256:" + "d" * 64,
    )
    changed = build_hk_case_proposition_requests(bundle, profiles, distinct)
    assert changed.decision.request_id != first.decision.request_id
    assert changed.decision.semantic_task.source_snapshot_fingerprint == "sha256:" + "c" * 64
    with pytest.raises(HKCasePropositionRequestError):
        replace(first.decision, authorities=distinct)


@pytest.mark.parametrize(
    ("neutral", "reported", "proceedings", "expected"),
    [
        (("N-1", "N-2"), ("R-1",), ("P-1",), "N-1"),
        ((), ("R-1", "R-2"), ("P-1",), "R-1"),
        ((), (), ("P-1", "P-2"), "P-1"),
    ],
)
def test_citation_precedence_is_retained_and_replay_bound(
    neutral: tuple[str, ...],
    reported: tuple[str, ...],
    proceedings: tuple[str, ...],
    expected: str,
) -> None:
    bundle = _bundle(
        neutral_citations=neutral, reported_citations=reported, proceeding_numbers=proceedings
    )
    pair = _build(bundle, _profiles())
    assert pair.decision.semantic_task.citation == expected
    assert expected.encode() in pair.decision.evidence_bytes
    assert _build(bundle, _profiles()).decision.request_id == pair.decision.request_id


def test_empty_citation_inventory_fails_at_task2_not_task1() -> None:
    bundle = _bundle(neutral_citations=(), reported_citations=(), proceeding_numbers=("P-1",))
    assert _build(bundle, _profiles()).decision.semantic_task.citation == "P-1"


def test_authorities_and_components_are_detached_from_caller_mutation() -> None:
    """Returned authority facts never alias the caller-owned authority graph."""
    bundle = _bundle()
    profiles = _profiles()
    authorities = _authorities(bundle, profiles)
    pair = build_hk_case_proposition_requests(bundle, profiles, authorities)
    object.__setattr__(authorities, "processing_cutoff", "2099-01-01")
    object.__setattr__(
        authorities.decision_workflow_components[0], "fingerprint", "sha256:" + "f" * 64
    )
    assert pair.decision.authorities.processing_cutoff == "2026-08-01"
    assert pair.decision.semantic_task.cutoff == "2026-08-01"
    assert (
        pair.decision.authorities.decision_workflow_components[0].fingerprint
        != "sha256:" + "f" * 64
    )
    assert (
        pair.decision.semantic_task.artifact_fingerprint
        == authorities.judgment_artifact_fingerprint
    )
    assert (
        len(
            {
                pair.decision.semantic_task.artifact_fingerprint,
                pair.decision.semantic_task.source_snapshot_fingerprint,
                pair.decision.authorities.official_version_fingerprint,
            }
        )
        == 3
    )


def test_profile_snapshot_precedes_caller_replayable_bundle_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bundle hook cannot alter the already-retained profile/workflow binding."""
    bundle = _bundle()
    profiles = _profiles()
    original = HKCaseJudgmentBundle.__post_init__

    def mutate_bundle(_: HKCaseJudgmentBundle) -> None:
        object.__setattr__(profiles[0], "prompt_fingerprint", "sha256:" + "e" * 64)
        original(_)

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", mutate_bundle)
    pair = build_hk_case_proposition_requests(bundle, profiles, _authorities(bundle, profiles))
    assert pair.decision.semantic_task.workflow_components[5].fingerprint != "sha256:" + "e" * 64


def test_embedded_task_and_reconstructed_fields_are_bound_to_the_retained_snapshots() -> None:
    """Swapping a semantic task or coordinating displayed replacements must not survive replay."""
    pair = _build(_bundle(), _profiles())
    challenge = bind_hk_case_proposition_challenge(
        pair.challenge, "sha256:" + "a" * 64, pair.challenge.authorities
    )

    with pytest.raises(HKCasePropositionRequestError):
        replace(pair.decision, semantic_task=challenge.semantic_task)
    with pytest.raises(HKCasePropositionRequestError):
        replace(pair.decision, request_id="request_forged")
    with pytest.raises(HKCasePropositionRequestError):
        replace(pair.decision, subject_id="judgment-foreign")
    forged_ledger = (
        HKCasePropositionReadingLedgerEntry(
            pair.reading_ledger[0].paragraph_ref,
            pair.reading_ledger[0].evidence_ref,
            "sha256:" + "0" * 64,
        ),
        *pair.reading_ledger[1:],
    )
    with pytest.raises(HKCasePropositionRequestError):
        replace(pair, reading_ledger=forged_ledger)
    assert len(pair.decision.semantic_task.opinions[1].judge_ids) == 2


def test_profile_evidence_budget_blocks_construction_before_any_request() -> None:
    """An evidence payload above an admitted profile budget cannot become a request."""
    decision, challenge = _profiles()
    with pytest.raises(HKCasePropositionRequestError) as raised:
        _build(
            _bundle(),
            (decision, replace(challenge, evidence_budget_bytes=1)),
        )
    assert raised.value.code is HKCasePropositionRequestErrorCode.PROFILE_BINDING_INVALID


class _EqualityLiar(str):
    """A profile or bundle leaf that must not pass by claimed equality."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0


def test_subclassed_profile_or_bundle_leaf_is_rejected_before_request_construction() -> None:
    """Permitting equality-liar leaves would let a profile or evidence identity change unseen."""
    decision, challenge = _profiles()
    object.__setattr__(decision, "profile_id", _EqualityLiar("case_decision_profile"))
    with pytest.raises(HKCasePropositionRequestError) as profile_error:
        _build(_bundle(), (decision, challenge))
    assert profile_error.value.code is HKCasePropositionRequestErrorCode.PROFILE_BINDING_INVALID

    bundle = _bundle()
    assert bundle.judgment is not None
    object.__setattr__(bundle.judgment.opinions[0].paragraphs[0], "text", _EqualityLiar("forged"))
    with pytest.raises(HKCasePropositionRequestError) as bundle_error:
        _build(bundle, _profiles())
    assert bundle_error.value.code is HKCasePropositionRequestErrorCode.BUNDLE_INVALID


def test_ordinary_bundle_replay_failure_is_closed_but_base_exception_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal faults must not leak while process-control exceptions stay observable."""
    bundle = _bundle()

    def ordinary(_: HKCaseJudgmentBundle) -> None:
        raise RuntimeError

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", ordinary)
    with pytest.raises(HKCasePropositionRequestError) as ordinary_error:
        _build(bundle, _profiles())
    assert ordinary_error.value.code is HKCasePropositionRequestErrorCode.BUNDLE_INVALID

    def process_control(_: HKCaseJudgmentBundle) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(HKCaseJudgmentBundle, "__post_init__", process_control)
    with pytest.raises(KeyboardInterrupt):
        _build(bundle, _profiles())
