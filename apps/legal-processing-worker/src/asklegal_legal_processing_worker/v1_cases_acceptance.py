# ruff: noqa: C401, C901, D102, EM101, FBT003, PLR0912, PLR0913, PLR0917, TRY300, TRY301
"""Restart-safe retained Judiciary HTML to source-neutral Case judgments.

This adapter owns the missing cross-application format boundary.  It consumes only
the canonical Cases manifest and the immutable bundle/capture references named by
that manifest.  It performs no source or provider access and deliberately stops
before semantic proposition work.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts import fingerprint as contract_fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import AuthorityNoteEvidence, ServingRecordProfile, TraceabilityReference
from asklegal_evidence_vault import ExactObjectReference, VaultName
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
    accept_complete_cases_acquisition_manifest,
    load_hk_case_judgment_bundle,
)
from asklegal_legal_desks.hk_case_proposition import (
    HKCaseAdmissionTokenCounter,
    HKCaseAdmittedEvidenceLink,
    HKCaseAdmittedProposition,
    HKCaseAdmittedSemanticDecision,
    HKCaseAdmittedUnitResolution,
    HKCasePropositionAdmissionResult,
    HKCasePropositionRequestAuthorities,
    HKCasePropositionRequestPair,
    admit_hk_case_propositions,
    bind_hk_case_proposition_challenge,
    build_hk_case_proposition_requests,
)
from asklegal_management_register_ports import (
    LegalIdentityKind,
    LegalIdentityRegister,
    LegalIdentityRequest,
    SearchRecordIdentityRequest,
)

from .hk_case_release import (
    HKCasePositiveReleaseRequest,
    HKCaseRecordTraceabilityBinding,
    HKCaseReleaseCandidate,
    build_hk_case_corpus_release,
    build_hk_case_record_traceability,
)

if TYPE_CHECKING:
    from asklegal_legal_desks.model import SemanticTaskProfile

_MAX_BUNDLE_BYTES = 2_000_000
_MAX_SOURCE_BYTES = 10_000_000
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_WORK_ID = re.compile(r"^awi_[0-9a-f]{64}$")
_BUNDLE_REF = re.compile(r"^cases/judgment-bundles/sha256/([0-9a-f]{64})\.json$")
_DATE_DMY = re.compile(
    r"(?:Date\s+of\s+Judgment|Judgment\s+Date|Date)\s*:?\s*"
    r"(?P<day>[0-3][0-9])/(?P<month>[01][0-9])/(?P<year>[12][0-9]{3})",
    re.IGNORECASE,
)
_DATE_ISO = re.compile(r"\b(?P<year>[12][0-9]{3})-(?P<month>[01][0-9])-(?P<day>[0-3][0-9])\b")
_CITATION = re.compile(r"\[(?P<year>[12][0-9]{3})\]\s+HK(?:CFA|CA|CFI|CT)\s+[0-9]+")
_PROCEEDING = re.compile(
    r"\b(?:FACV|FACC|CACV|CACC|HCAL|HCA|HCMP|HCCC|CTEA|CTMP)\s*[0-9]+/[0-9]{4}\b",
    re.IGNORECASE,
)
_PARAGRAPH_PREFIX = re.compile(r"^\s*\[(?P<number>[1-9][0-9]*)\]\s*(?P<text>.+?)\s*$", re.DOTALL)
_CORAM = re.compile(r"(?:Coram|Before)\s*:\s*(?P<names>[^\n|]{2,500})", re.IGNORECASE)
_COURTS = (
    (re.compile(r"Court of Final Appeal", re.IGNORECASE), "CFA"),
    (re.compile(r"Court of Appeal(?: of the High Court)?", re.IGNORECASE), "CA"),
    (re.compile(r"Court of First Instance", re.IGNORECASE), "CFI"),
    (re.compile(r"Competition Tribunal", re.IGNORECASE), "CT"),
)
_RELATIONSHIPS = (
    "CORRECTION_ARTIFACT",
    "REISSUE_ARTIFACT",
    "LANGUAGE",
    "TRANSLATION_ARTIFACT",
    "LISTING_ALIAS",
    "PROCEEDING_IDENTITY",
)
_DECISION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "request_id",
        "complete_reading",
        "propositions",
        "unit_resolutions",
        "proposal_fingerprint",
    }
)
_PROPOSITION_FIELDS = frozenset(
    {
        "proposition_id",
        "candidate_id",
        "proposition_text",
        "text_mode",
        "court_id",
        "opinion_id",
        "judge_names",
        "qualification_texts",
        "exception_texts",
        "support_paragraph_refs",
        "support_fingerprint",
        "authority_role",
        "legal_issue",
        "material_context",
        "result_context",
        "quotation_paragraph_refs",
        "evidence_links",
    }
)
_RESOLUTION_FIELDS = frozenset(
    {
        "paragraph_ref",
        "resolution",
        "primary_use",
        "evidence_roles",
        "non_propositional_reason",
        "citation_or_treatment_lead",
        "screening_handoff_ids",
    }
)
_CHALLENGE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "request_id",
        "proposal_fingerprint",
        "challenge_code",
        "supporting_evidence_refs",
        "unresolved_facts",
    }
)
_TREATMENT_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "judicial_decision_id",
        "complete_whole_judgment_reading",
        "examined_paragraph_refs",
        "treatment_lead_refs",
        "unresolved_facts",
    }
)


class CasesAcceptanceError(ValueError):
    """One sanitized retained Cases adapter refusal."""


class CurrentPrimaryVault(Protocol):
    """The exact immutable read surface required by this adapter."""

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None: ...

    def read_exact(self, reference: ExactObjectReference) -> bytes: ...


@dataclass(frozen=True, slots=True)
class VerifiedCaseJudgment:
    """One source-neutral judgment and its immutable source bindings."""

    acquisition_manifest_fingerprint: str
    wrapper_reference: ExactObjectReference
    capture_reference: ExactObjectReference
    normalized_artifact: bytes
    bundle: HKCaseJudgmentBundle


@dataclass(frozen=True, slots=True)
class PreparedCaseSemanticWork:
    """Exact Desk request pair ready for the injected semantic transport."""

    pair: HKCasePropositionRequestPair


@dataclass(frozen=True, slots=True)
class PreparedCaseReleaseComponent:
    """Positive Case release plus exact traceability inputs for retained persistence."""

    request: HKCasePositiveReleaseRequest
    serving_profile: ServingRecordProfile
    bindings: tuple[HKCaseRecordTraceabilityBinding, ...]


@dataclass(frozen=True, slots=True)
class CaseAdmissionTokenCounter:
    """Bind one processing-owned exact counter to one Desk profile snapshot."""

    tokenizer_id: str
    profile_fingerprint: str
    delegate: object

    def count(self, text: str) -> int:
        """Delegate exact counting without importing processing into the Desk."""
        method = getattr(self.delegate, "count", None)
        if not callable(method):
            raise CasesAcceptanceError("CASES_TOKEN_COUNTER_INVALID")
        value = method(text)
        if type(value) is not int or value < 0:
            raise CasesAcceptanceError("CASES_TOKEN_COUNTER_INVALID")
        return value


def case_admission_token_counter(
    work: PreparedCaseSemanticWork,
    counter: object,
) -> CaseAdmissionTokenCounter:
    """Issue the exact Desk counter fingerprint for the selected decision profile."""
    tokenizer = getattr(counter, "tokenizer_id", None)
    if type(tokenizer) is not str or not tokenizer:
        raise CasesAcceptanceError("CASES_TOKEN_COUNTER_INVALID")
    return CaseAdmissionTokenCounter(
        tokenizer,
        contract_fingerprint(
            checked_json_value(
                {
                    "tokenizer": tokenizer,
                    "profile_fingerprint": work.pair.decision.profile_fingerprint,
                }
            )
        ),
        counter,
    )


def parse_case_semantic_decision(
    work: PreparedCaseSemanticWork, raw: bytes
) -> HKCaseAdmittedSemanticDecision:
    """Expose the strict decision parser for sequential decision/challenge execution."""
    return _parse_decision(work.pair, raw)


def prepare_case_semantic_work(
    judgment: VerifiedCaseJudgment,
    profiles: tuple[SemanticTaskProfile, SemanticTaskProfile],
    authorities: HKCasePropositionRequestAuthorities,
) -> PreparedCaseSemanticWork:
    """Compose the existing Desk request builder without invoking a provider."""
    try:
        pair = build_hk_case_proposition_requests(judgment.bundle, profiles, authorities)
    except Exception as error:
        raise CasesAcceptanceError("CASES_SEMANTIC_REQUEST_INVALID") from error
    return PreparedCaseSemanticWork(pair)


def admit_case_semantic_outputs(
    work: PreparedCaseSemanticWork,
    decision_raw: bytes,
    challenge_raw: bytes,
    *,
    counter: HKCaseAdmissionTokenCounter | None = None,
) -> HKCasePropositionAdmissionResult:
    """Strictly parse decision/challenge bytes and feed the existing Desk admission."""
    pair = work.pair
    decision = _parse_decision(pair, decision_raw)
    try:
        challenge_request = bind_hk_case_proposition_challenge(
            pair.challenge,
            decision.proposal_fingerprint,
            pair.decision.authorities,
        )
    except Exception as error:
        raise CasesAcceptanceError("CASES_SEMANTIC_CHALLENGE_BINDING_INVALID") from error
    challenge = _canonical_object(
        challenge_raw,
        _MAX_BUNDLE_BYTES,
        "CASES_SEMANTIC_CHALLENGE_INVALID",
    )
    if frozenset(challenge) != _CHALLENGE_FIELDS:
        raise CasesAcceptanceError("CASES_SEMANTIC_CHALLENGE_INVALID")
    refs = _text_list(challenge.get("supporting_evidence_refs"))
    unresolved = _text_list(challenge.get("unresolved_facts"), allow_empty=True)
    if (
        challenge.get("schema_id") != "asklegal.hk-case-proposition-challenge-output/v1"
        or challenge.get("schema_version") != "1.0.0"
        or challenge.get("request_id") != challenge_request.request_id
        or challenge.get("proposal_fingerprint") != decision.proposal_fingerprint
        or challenge.get("challenge_code") != "PASS"
        or unresolved
        or not set(refs).issubset(set(challenge_request.evidence_refs))
    ):
        raise CasesAcceptanceError("CASES_SEMANTIC_CHALLENGE_INVALID")
    try:
        return admit_hk_case_propositions(
            pair,
            replace(decision, challenge_complete=True),
            counter=counter,
        )
    except Exception as error:
        raise CasesAcceptanceError("CASES_SEMANTIC_ADMISSION_INVALID") from error


def prepare_case_release_component(
    judgment: VerifiedCaseJudgment,
    admission: HKCasePropositionAdmissionResult,
    decision_raw: bytes,
    challenge_raw: bytes,
    treatment_raw: bytes,
    observation_cutoff: str,
    serving_profile: ServingRecordProfile,
    register: LegalIdentityRegister,
) -> PreparedCaseReleaseComponent:
    """Issue stable identities and build one positive Case release from admitted facts."""
    try:
        if admission.request_pair.decision.semantic_task.artifact_fingerprint != (
            judgment.bundle.bundle_fingerprint
        ):
            raise TypeError
        treatment = _canonical_object(
            treatment_raw, _MAX_BUNDLE_BYTES, "CASES_TREATMENT_PROOF_INVALID"
        )
        if frozenset(treatment) != _TREATMENT_FIELDS:
            raise TypeError
        lead_refs = _text_list(treatment.get("treatment_lead_refs"), allow_empty=True)
        expected_leads = tuple(
            sorted(
                item.paragraph_ref
                for item in admission.admitted_decision.unit_resolutions
                if item.citation_or_treatment_lead
            )
        )
        if (
            treatment.get("schema_id") != "asklegal.hk-case-later-treatment-proof/v1"
            or treatment.get("schema_version") != "1.0.0"
            or treatment.get("judicial_decision_id")
            != admission.request_pair.decision.semantic_task.judicial_decision_id
            or treatment.get("complete_whole_judgment_reading") is not True
            or _text_list(treatment.get("examined_paragraph_refs"))
            != tuple(sorted(admission.request_pair.paragraph_refs))
            or lead_refs != expected_leads
            or _text_list(treatment.get("unresolved_facts"), allow_empty=True)
        ):
            raise TypeError
        if lead_refs:
            raise CasesAcceptanceError("CASES_TREATMENT_CANDIDATE_NOT_READY")

        decision_fp = _fingerprint(decision_raw)
        challenge_fp = _fingerprint(challenge_raw)
        treatment_fp = _fingerprint(treatment_raw)
        semantic_task = admission.request_pair.decision.semantic_task
        legal_item = register.issue_identity(
            LegalIdentityRequest(
                LegalIdentityKind.LEGAL_ITEM,
                f"case:{semantic_task.judicial_decision_id}",
            )
        ).identity_id
        official_version = register.issue_identity(
            LegalIdentityRequest(
                LegalIdentityKind.OFFICIAL_VERSION,
                f"case:{semantic_task.official_version_id}",
            )
        ).identity_id
        legal_location = register.issue_identity(
            LegalIdentityRequest(
                LegalIdentityKind.LEGAL_LOCATION,
                f"case:{semantic_task.judicial_decision_id}:judgment",
            )
        ).identity_id
        artifact = register.issue_identity(
            LegalIdentityRequest(
                LegalIdentityKind.ARTIFACT,
                f"case:{judgment.capture_reference.fingerprint}",
            )
        ).identity_id
        evidence_pairs = tuple(
            sorted(
                (
                    register.issue_identity(
                        LegalIdentityRequest(LegalIdentityKind.EVIDENCE, natural_key)
                    ).identity_id,
                    source_fp,
                )
                for natural_key, source_fp in (
                    (
                        f"case-source:{judgment.capture_reference.fingerprint}",
                        judgment.capture_reference.fingerprint,
                    ),
                    (f"case-decision:{decision_fp}", decision_fp),
                    (f"case-challenge:{challenge_fp}", challenge_fp),
                )
            )
        )
        evidence_ids = tuple(identity for identity, _ in evidence_pairs)
        validation = register.issue_identity(
            LegalIdentityRequest(
                LegalIdentityKind.VALIDATION,
                f"case-treatment:{treatment_fp}",
            )
        ).identity_id
        decision_id = register.issue_identity(
            LegalIdentityRequest(
                LegalIdentityKind.DECISION,
                f"case-semantic:{decision_fp}:{challenge_fp}",
            )
        ).identity_id
        proposals = {item.proposition_id: item for item in admission.output_request.propositions}
        candidates: list[HKCaseReleaseCandidate] = []
        bindings: list[HKCaseRecordTraceabilityBinding] = []
        for proposed in admission.output_request.proposed_records:
            issued = register.issue_search_record(
                SearchRecordIdentityRequest(
                    "HK-CASE-BINDING-POST-1997",
                    f"case-proposition:{proposed.proposition_id}",
                    proposed.payload_fingerprint,
                )
            )
            rebound = replace(proposed, record_id=issued.search_record_id)
            candidates.append(HKCaseReleaseCandidate(rebound, artifact, evidence_ids))
            evidence_refs = tuple(
                sorted(
                    (
                        TraceabilityReference("EVIDENCE", identity, source_fp)
                        for identity, source_fp in evidence_pairs
                    ),
                    key=lambda item: (item.ref_type, item.ref_id, item.fingerprint),
                )
            )
            proposition = proposals[proposed.proposition_id]
            decision_ref = TraceabilityReference("DECISION", decision_id, decision_fp)
            bindings.append(
                HKCaseRecordTraceabilityBinding(
                    rebound.record_id,
                    serving_profile.serving_record_profile_id,
                    legal_item,
                    (official_version,),
                    (legal_location,),
                    evidence_refs,
                    AuthorityNoteEvidence(
                        _fingerprint(proposition.authority_note.encode()),
                        decision_ref,
                        evidence_refs,
                    ),
                )
            )
        register.commit()
        request = HKCasePositiveReleaseRequest(
            observation_cutoff,
            tuple(candidates),
            evidence_ids,
            (validation,),
        )
        release = build_hk_case_corpus_release(request)
        build_hk_case_record_traceability(release, serving_profile, tuple(bindings))
        return PreparedCaseReleaseComponent(request, serving_profile, tuple(bindings))
    except CasesAcceptanceError:
        raise
    except Exception as error:
        raise CasesAcceptanceError("CASES_RELEASE_COMPONENT_INVALID") from error


def persist_case_release_component(
    operation_root: Path,
    operation_id: str,
    command_fingerprint: str,
    cases_manifest_fingerprint: str,
    component: PreparedCaseReleaseComponent,
) -> Path:
    """Atomically create-or-match the exact Case input consumed by acceptance."""
    try:
        if (
            not operation_root.is_absolute()
            or operation_root.is_symlink()
            or not operation_id
            or not _FINGERPRINT.fullmatch(command_fingerprint)
            or not _FINGERPRINT.fullmatch(cases_manifest_fingerprint)
        ):
            raise TypeError
        request = component.request
        body = checked_json_value(
            {
                "schema_id": "asklegal.hk-v1-case-release-input/v1",
                "schema_version": "1.0.0",
                "operation_id": operation_id,
                "command_fingerprint": command_fingerprint,
                "observation_cutoff": request.observation_cutoff,
                "cases_manifest_fingerprint": cases_manifest_fingerprint,
                "case_release": {
                    "observation_cutoff": request.observation_cutoff,
                    "candidates": [
                        {
                            "proposed_record": {
                                field: getattr(candidate.proposed_record, field)
                                for field in candidate.proposed_record.__dataclass_fields__
                            },
                            "artifact_ref": candidate.artifact_ref,
                            "evidence_refs": list(candidate.evidence_refs),
                        }
                        for candidate in request.candidates
                    ],
                    "release_evidence_refs": list(request.release_evidence_refs),
                    "release_validation_refs": list(request.release_validation_refs),
                    "zero_record_justification_refs": list(request.zero_record_justification_refs),
                },
                "case_traceability": {
                    "serving_profile": {
                        "serving_record_profile_id": (
                            component.serving_profile.serving_record_profile_id
                        ),
                        "schema_version": component.serving_profile.schema_version,
                        "schema_fingerprint": component.serving_profile.schema_fingerprint,
                    },
                    "bindings": [_binding_document(item) for item in component.bindings],
                },
            }
        )
        if type(body) is not dict:
            raise TypeError
        content = canonicalize(
            checked_json_value(
                {
                    **body,
                    "fingerprint": _fingerprint(canonicalize(body)),
                }
            )
        )
        operation_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        target = operation_root / "case-release-input.json"
        if target.exists():
            if target.read_bytes() != content:
                raise CasesAcceptanceError("CASES_RELEASE_COMPONENT_DRIFT")
            return target
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        if target.read_bytes() != content:
            raise CasesAcceptanceError("CASES_RELEASE_COMPONENT_READBACK_FAILED")
        return target
    except CasesAcceptanceError:
        raise
    except Exception as error:
        raise CasesAcceptanceError("CASES_RELEASE_COMPONENT_INVALID") from error


def combine_case_release_components(
    components: tuple[PreparedCaseReleaseComponent, ...],
) -> PreparedCaseReleaseComponent:
    """Combine independently admitted judgments into one fixed-scope Case input."""
    if not components:
        raise CasesAcceptanceError("CASES_RELEASE_COMPONENT_INVALID")
    profile = components[0].serving_profile
    cutoff = components[0].request.observation_cutoff
    if any(
        item.serving_profile != profile or item.request.observation_cutoff != cutoff
        for item in components
    ):
        raise CasesAcceptanceError("CASES_RELEASE_COMPONENT_INVALID")
    request = HKCasePositiveReleaseRequest(
        cutoff,
        tuple(candidate for item in components for candidate in item.request.candidates),
        tuple(sorted({ref for item in components for ref in item.request.release_evidence_refs})),
        tuple(sorted({ref for item in components for ref in item.request.release_validation_refs})),
    )
    bindings = tuple(binding for item in components for binding in item.bindings)
    try:
        release = build_hk_case_corpus_release(request)
        build_hk_case_record_traceability(release, profile, bindings)
    except Exception as error:
        raise CasesAcceptanceError("CASES_RELEASE_COMPONENT_INVALID") from error
    return PreparedCaseReleaseComponent(request, profile, bindings)


def _reference_document(reference: TraceabilityReference) -> dict[str, str]:
    return {
        "ref_type": reference.ref_type,
        "ref_id": reference.ref_id,
        "fingerprint": reference.fingerprint,
    }


def _binding_document(binding: HKCaseRecordTraceabilityBinding) -> dict[str, JsonValue]:
    authority = binding.authority_note_evidence
    value = checked_json_value(
        {
            "record_id": binding.record_id,
            "serving_profile_id": binding.serving_profile_id,
            "legal_item_id": binding.legal_item_id,
            "official_version_ids": list(binding.official_version_ids),
            "legal_location_ids": list(binding.legal_location_ids),
            "evidence_refs": [_reference_document(item) for item in binding.evidence_refs],
            "authority_note_evidence": {
                "rendered_value_fingerprint": authority.rendered_value_fingerprint,
                "decision_ref": _reference_document(authority.decision_ref),
                "supporting_evidence_refs": [
                    _reference_document(item) for item in authority.supporting_evidence_refs
                ],
            },
            "grouping_ids": list(binding.grouping_ids),
            "display_citation_ids": list(binding.display_citation_ids),
        }
    )
    if type(value) is not dict:
        raise CasesAcceptanceError("CASES_RELEASE_COMPONENT_INVALID")
    return value


def _parse_decision(
    pair: HKCasePropositionRequestPair,
    raw: bytes,
) -> HKCaseAdmittedSemanticDecision:
    document = _canonical_object(raw, _MAX_BUNDLE_BYTES, "CASES_SEMANTIC_DECISION_INVALID")
    if (
        frozenset(document) != _DECISION_FIELDS
        or document.get("schema_id") != "asklegal.hk-case-proposition-decision-output/v1"
        or document.get("schema_version") != "1.0.0"
        or document.get("request_id") != pair.decision.request_id
        or document.get("complete_reading") is not True
    ):
        raise CasesAcceptanceError("CASES_SEMANTIC_DECISION_INVALID")
    raw_propositions = document.get("propositions")
    raw_resolutions = document.get("unit_resolutions")
    if type(raw_propositions) is not list or type(raw_resolutions) is not list:
        raise CasesAcceptanceError("CASES_SEMANTIC_DECISION_INVALID")
    paragraph_texts = _paragraph_texts(pair)
    allowed_refs = set(pair.paragraph_refs)
    propositions: list[HKCaseAdmittedProposition] = []
    try:
        for value in raw_propositions:
            item = _object(value)
            if frozenset(item) != _PROPOSITION_FIELDS:
                raise TypeError
            support_refs = _text_list(item.get("support_paragraph_refs"))
            quotation_refs = _text_list(item.get("quotation_paragraph_refs"))
            if not set(support_refs).issubset(allowed_refs) or not set(quotation_refs).issubset(
                set(support_refs)
            ):
                raise TypeError
            expected_support = contract_fingerprint(
                checked_json_value(
                    {
                        "support": [
                            {
                                "paragraph_ref": reference,
                                "text_fingerprint": _fingerprint(
                                    paragraph_texts[reference].encode()
                                ),
                            }
                            for reference in support_refs
                        ]
                    }
                )
            )
            links_raw = item.get("evidence_links")
            if type(links_raw) is not list:
                raise TypeError
            links: list[HKCaseAdmittedEvidenceLink] = []
            for raw_link in links_raw:
                link = _object(raw_link)
                if frozenset(link) != frozenset({"role", "paragraph_ref"}):
                    raise TypeError
                paragraph_ref = _text(link.get("paragraph_ref"))
                if paragraph_ref not in allowed_refs:
                    raise TypeError
                links.append(
                    HKCaseAdmittedEvidenceLink(
                        HKCaseEvidenceRole(_text(link.get("role"))),
                        paragraph_ref,
                    )
                )
            material_context = item.get("material_context")
            if material_context is not None and type(material_context) is not str:
                raise TypeError
            if item.get("support_fingerprint") != expected_support:
                raise TypeError
            propositions.append(
                HKCaseAdmittedProposition(
                    _text(item.get("proposition_id")),
                    _text(item.get("candidate_id")),
                    _text(item.get("proposition_text")),
                    _text(item.get("text_mode")),
                    _text(item.get("court_id")),
                    _text(item.get("opinion_id")),
                    _text_list(item.get("judge_names")),
                    _text_list(item.get("qualification_texts"), allow_empty=True),
                    _text_list(item.get("exception_texts"), allow_empty=True),
                    support_refs,
                    expected_support,
                    HKCaseOpinionRole(_text(item.get("authority_role"))),
                    _text(item.get("legal_issue")),
                    material_context,
                    _text(item.get("result_context")),
                    quotation_refs,
                    tuple(links),
                )
            )
        resolutions: list[HKCaseAdmittedUnitResolution] = []
        for value in raw_resolutions:
            item = _object(value)
            if frozenset(item) != _RESOLUTION_FIELDS:
                raise TypeError
            paragraph_ref = _text(item.get("paragraph_ref"))
            raw_reason = item.get("non_propositional_reason")
            reason = None if raw_reason is None else HKCaseNonPropositionalReason(_text(raw_reason))
            if paragraph_ref not in allowed_refs:
                raise TypeError
            resolutions.append(
                HKCaseAdmittedUnitResolution(
                    paragraph_ref,
                    HKCaseUnitResolution(_text(item.get("resolution"))),
                    HKCasePrimaryUse(_text(item.get("primary_use"))),
                    tuple(
                        HKCaseEvidenceRole(value)
                        for value in _text_list(item.get("evidence_roles"), allow_empty=True)
                    ),
                    reason,
                    _boolean(item.get("citation_or_treatment_lead")),
                    _text_list(item.get("screening_handoff_ids"), allow_empty=True),
                )
            )
        decision = HKCaseAdmittedSemanticDecision(
            pair.decision.request_id,
            _text(document.get("proposal_fingerprint")),
            True,
            False,
            tuple(propositions),
            tuple(resolutions),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CasesAcceptanceError("CASES_SEMANTIC_DECISION_INVALID") from error
    return decision


def _paragraph_texts(pair: HKCasePropositionRequestPair) -> dict[str, str]:
    try:
        evidence = _canonical_object(
            pair.decision.evidence_bytes,
            _MAX_BUNDLE_BYTES,
            "CASES_SEMANTIC_REQUEST_INVALID",
        )
        opinions = evidence["opinions"]
        if type(opinions) is not list:
            raise TypeError
        result: dict[str, str] = {}
        for raw_opinion in opinions:
            opinion = _object(raw_opinion)
            opinion_id = _text(opinion.get("opinion_id"))
            paragraphs = opinion.get("paragraphs")
            if type(paragraphs) is not list:
                raise TypeError
            for raw_paragraph in paragraphs:
                paragraph = _object(raw_paragraph)
                result[f"{opinion_id}:{_text(paragraph.get('paragraph_id'))}"] = _text(
                    paragraph.get("text")
                )
        if set(result) != set(pair.paragraph_refs):
            raise TypeError
        return result
    except (KeyError, TypeError, ValueError) as error:
        raise CasesAcceptanceError("CASES_SEMANTIC_REQUEST_INVALID") from error


class _Court(StrEnum):
    CFA = "CFA"
    CA = "CA"
    CFI = "CFI"
    CT = "CT"


class _Role(StrEnum):
    ORIGINAL = "ORIGINAL"


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
        if any(
            type(value) is not str or not value
            for value in (
                self.artifact_identity,
                self.listing_identity,
                self.source_id,
                self.opinion_or_reasons_identity,
            )
        ):
            raise TypeError


@dataclass(frozen=True, slots=True)
class _Listing:
    listing_identity: str
    court_family: _Court
    decision_date: str
    artifacts: tuple[_Artifact, ...]
    opinion_or_reasons_identities: tuple[str, ...]
    case_name: str
    neutral_citations: tuple[str, ...]
    reported_citations: tuple[str, ...]
    proceeding_numbers: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.listing_identity
            or not self.case_name
            or not self.artifacts
            or not self.opinion_or_reasons_identities
            or not self.proceeding_numbers
        ):
            raise TypeError


@dataclass(frozen=True, slots=True)
class _ParsedHtml:
    title: str
    headings: tuple[str, ...]
    blocks: tuple[str, ...]
    paragraphs: tuple[tuple[str | None, str], ...]
    language: str


class _JudiciaryHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._suppressed = 0
        self._capture: str | None = None
        self._capture_id: str | None = None
        self._parts: list[str] = []
        self.title = ""
        self.headings: list[str] = []
        self.blocks: list[str] = []
        self.paragraphs: list[tuple[str | None, str]] = []
        self.language = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._suppressed += 1
            return
        if tag == "html":
            self.language = attributes.get("lang") or ""
        if self._suppressed == 0 and tag in {"title", "h1", "h2", "h3", "p", "div", "td"}:
            self._capture = tag
            self._capture_id = attributes.get("id") or attributes.get("name")
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._suppressed:
            self._suppressed -= 1
            return
        if self._suppressed or tag != self._capture:
            return
        text = " ".join("".join(self._parts).split())
        if text:
            self.blocks.append(text)
            if tag == "title":
                self.title = text
            elif tag in {"h1", "h2", "h3"}:
                self.headings.append(text)
            elif tag == "p":
                self.paragraphs.append((self._capture_id, text))
        self._capture = None
        self._capture_id = None
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._suppressed == 0 and self._capture is not None:
            self._parts.append(data)

    def parsed(self) -> _ParsedHtml:
        return _ParsedHtml(
            self.title,
            tuple(self.headings),
            tuple(self.blocks),
            tuple(self.paragraphs),
            self.language,
        )


class _OneArtifactReader:
    def __init__(self, reference: str, content: bytes) -> None:
        self._reference = reference
        self._content = content

    def read_exact(self, member: HKCaseEvidenceMember) -> bytes:
        if member.reference != self._reference:
            raise CasesAcceptanceError("CASES_NORMALIZED_ARTIFACT_DRIFT")
        return self._content


def load_verified_case_judgments(
    manifest: bytes,
    vault: CurrentPrimaryVault,
) -> tuple[VerifiedCaseJudgment, ...]:
    """Read exact wrappers/captures and normalize each admitted Judiciary judgment."""
    try:
        accepted = accept_complete_cases_acquisition_manifest(manifest)
    except Exception as error:
        raise CasesAcceptanceError("CASES_ACQUISITION_MANIFEST_INVALID") from error
    results: list[VerifiedCaseJudgment] = []
    for wrapper_key in accepted.judgment_bundle_refs:
        wrapper_ref, wrapper = _read_current(vault, wrapper_key, "CASES_WRAPPER_NOT_READY")
        match = _BUNDLE_REF.fullmatch(wrapper_key)
        if match is None or sha256(wrapper).hexdigest() != match.group(1):
            raise CasesAcceptanceError("CASES_WRAPPER_DRIFT")
        document = _canonical_object(wrapper, _MAX_BUNDLE_BYTES, "CASES_WRAPPER_INVALID")
        capture, dis_id = _wrapper_capture(document)
        capture_ref, source = _read_current(
            vault, _text(capture.get("object_ref")), "CASES_SOURCE_BODY_NOT_READY"
        )
        body_length = capture.get("body_length")
        fingerprint = _text(capture.get("content_fingerprint"))
        if (
            type(body_length) is not int
            or body_length <= 0
            or len(source) != body_length
            or capture_ref.byte_length != body_length
            or capture_ref.fingerprint != fingerprint
            or _fingerprint(source) != fingerprint
        ):
            raise CasesAcceptanceError("CASES_SOURCE_BODY_DRIFT")
        normalized, listing, artifact = _normalize_judiciary_html(source, dis_id, capture_ref)
        normalized_ref = (
            f"{capture_ref.logical_key}@{capture_ref.version_id}@{_fingerprint(normalized)}"
        )
        member = HKCaseEvidenceMember(
            artifact.artifact_identity,
            listing.listing_identity,
            normalized_ref,
            _fingerprint(normalized),
            len(normalized),
        )
        try:
            bundle = load_hk_case_judgment_bundle(
                listing,
                (member,),
                _OneArtifactReader(normalized_ref, normalized),
            )
        except Exception as error:
            raise CasesAcceptanceError("CASES_NORMALIZED_JUDGMENT_INVALID") from error
        results.append(
            VerifiedCaseJudgment(
                accepted.manifest_fingerprint,
                wrapper_ref,
                capture_ref,
                normalized,
                bundle,
            )
        )
    return tuple(results)


def _read_current(
    vault: CurrentPrimaryVault,
    logical_key: str,
    code: str,
) -> tuple[ExactObjectReference, bytes]:
    try:
        reference = vault.resolve_current(logical_key)
        if reference is None or reference.vault is not VaultName.PRIMARY:
            raise TypeError
        body = vault.read_exact(reference)
    except Exception as error:
        raise CasesAcceptanceError(code) from error
    if (
        type(body) is not bytes
        or len(body) != reference.byte_length
        or _fingerprint(body) != reference.fingerprint
    ):
        raise CasesAcceptanceError(code.replace("NOT_READY", "DRIFT"))
    return reference, body


def _wrapper_capture(document: dict[str, JsonValue]) -> tuple[dict[str, JsonValue], int]:
    if (
        frozenset(document)
        != frozenset({"capture", "judgment_node_key", "occurrences", "schema_id"})
        or document.get("schema_id") != "asklegal.hk-case-judgment-bundle/v1"
    ):
        raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
    capture = _object(document.get("capture"))
    if frozenset(capture) != frozenset(
        {"body_length", "content_fingerprint", "object_ref", "work_item_id"}
    ):
        raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
    fingerprint = _text(capture.get("content_fingerprint"))
    if (
        _FINGERPRINT.fullmatch(fingerprint) is None
        or _WORK_ID.fullmatch(_text(capture.get("work_item_id"))) is None
    ):
        raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
    occurrences = document.get("occurrences")
    if type(occurrences) is not list or not occurrences:
        raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
    dis_ids: set[int] = set()
    for value in occurrences:
        occurrence = _object(value)
        if frozenset(occurrence) != frozenset(
            {
                "dis_id",
                "listing_node_key",
                "occurrence_key",
                "presentation",
                "relationships",
            }
        ):
            raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
        dis_id = occurrence.get("dis_id")
        relationships = occurrence.get("relationships")
        if type(dis_id) is not int or dis_id <= 0 or type(relationships) is not list:
            raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
        kinds: list[str] = []
        for item in relationships:
            relation = _object(item)
            if (
                frozenset(relation)
                != frozenset({"disposition", "kind", "relationship_node_key", "work_item_id"})
                or relation.get("disposition") != "SOURCE_RELATIONSHIP_RETAINED"
            ):
                raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
            kinds.append(_text(relation.get("kind")))
        if tuple(kinds) != _RELATIONSHIPS:
            raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
        dis_ids.add(dis_id)
    if len(dis_ids) != 1:
        raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
    return capture, next(iter(dis_ids))


def _normalize_judiciary_html(
    source: bytes,
    dis_id: int,
    capture: ExactObjectReference,
) -> tuple[bytes, _Listing, _Artifact]:
    if not source or len(source) > _MAX_SOURCE_BYTES:
        raise CasesAcceptanceError("CASES_SOURCE_BODY_INVALID")
    try:
        text = source.decode("utf-8-sig")
        parser = _JudiciaryHtmlParser()
        parser.feed(text)
        parser.close()
        parsed = parser.parsed()
    except (UnicodeDecodeError, ValueError) as error:
        raise CasesAcceptanceError("CASES_SOURCE_BODY_INVALID") from error
    corpus = "\n".join(parsed.blocks)
    name = next((item for item in parsed.headings if " v " in item.casefold()), parsed.title)
    name = _clean_title(name)
    court = next((code for pattern, code in _COURTS if pattern.search(corpus)), None)
    date_match = _DATE_DMY.search(corpus) or _DATE_ISO.search(corpus)
    proceedings = tuple(
        sorted(
            set(match.group(0).upper().replace("  ", " ") for match in _PROCEEDING.finditer(corpus))
        )
    )
    citations = tuple(sorted(set(match.group(0) for match in _CITATION.finditer(corpus))))
    coram = _CORAM.search(corpus)
    paragraph_values: list[tuple[str, str, str]] = []
    for element_id, value in parsed.paragraphs:
        match = _PARAGRAPH_PREFIX.fullmatch(value)
        if match is None:
            continue
        paragraph_id = match.group("number")
        locator = element_id or f"paragraph-{paragraph_id}"
        paragraph_values.append((paragraph_id, locator, match.group("text")))
    if (
        not name
        or " v " not in name.casefold()
        or court is None
        or date_match is None
        or not proceedings
        or not paragraph_values
        or coram is None
        or len({item[0] for item in paragraph_values}) != len(paragraph_values)
        or len({item[1] for item in paragraph_values}) != len(paragraph_values)
    ):
        raise CasesAcceptanceError("CASES_SOURCE_BODY_INVALID")
    decision_date = (
        f"{date_match.group('year')}-{date_match.group('month')}-{date_match.group('day')}"
    )
    language = (
        _Language.TRADITIONAL_CHINESE
        if parsed.language.casefold().startswith("zh")
        else _Language.ENGLISH
    )
    listing_id = f"judiciary-dis-{dis_id}"
    artifact_id = f"judiciary-artifact-{sha256(capture.fingerprint.encode()).hexdigest()[:24]}"
    # The Desk semantic contract admits identifiers with ``[a-z0-9_]`` only.
    opinion_id = f"court_opinion_{dis_id}"
    artifact = _Artifact(
        artifact_id,
        listing_id,
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        _Role.ORIGINAL,
        language,
        opinion_id,
    )
    listing = _Listing(
        listing_id,
        _Court(court),
        decision_date,
        (artifact,),
        (opinion_id,),
        name,
        citations,
        (),
        proceedings,
    )
    judges = tuple(
        sorted(
            set(item.strip() for item in re.split(r"[,;&]", coram.group("names")) if item.strip())
        )
    )
    if not judges:
        raise CasesAcceptanceError("CASES_SOURCE_BODY_INVALID")
    document: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-case-judgment-artifact/v1",
        "artifact_identity": artifact_id,
        "listing_identity": listing_id,
        "source_id": artifact.source_id,
        "court_id": court,
        "decision_date": decision_date,
        "language": language.value,
        "opinion_id": opinion_id,
        "opinion_role": "COURT",
        "judge_names": list(judges),
        "paragraphs": [
            {"paragraph_id": paragraph_id, "locator": locator, "text": value}
            for paragraph_id, locator, value in paragraph_values
        ],
    }
    return canonicalize(checked_json_value(document)), listing, artifact


def _clean_title(value: str) -> str:
    title = " ".join(value.split()).strip(" -|")
    for suffix in (" - Legal Reference System", " | Legal Reference System"):
        title = title.removesuffix(suffix).strip()
    return title


def _canonical_object(raw: bytes, maximum: int, code: str) -> dict[str, JsonValue]:
    try:
        value = parse_json_bytes(raw, max_bytes=maximum)
    except (ContractViolation, ValueError) as error:
        raise CasesAcceptanceError(code) from error
    if type(value) is not dict or canonicalize(value) != raw:
        raise CasesAcceptanceError(code)
    return value


def _object(value: JsonValue | None) -> dict[str, JsonValue]:
    if type(value) is not dict:
        raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
    return value


def _text(value: JsonValue | None) -> str:
    if type(value) is not str or not value:
        raise CasesAcceptanceError("CASES_WRAPPER_INVALID")
    return value


def _text_list(value: JsonValue | None, *, allow_empty: bool = False) -> tuple[str, ...]:
    if (
        type(value) is not list
        or (not allow_empty and not value)
        or any(type(item) is not str or not item for item in value)
    ):
        raise CasesAcceptanceError("CASES_SEMANTIC_OUTPUT_INVALID")
    return tuple(item for item in value if type(item) is str)


def _boolean(value: JsonValue | None) -> bool:
    if type(value) is not bool:
        raise CasesAcceptanceError("CASES_SEMANTIC_OUTPUT_INVALID")
    return value


def _fingerprint(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


__all__ = [
    "CasesAcceptanceError",
    "CurrentPrimaryVault",
    "PreparedCaseSemanticWork",
    "VerifiedCaseJudgment",
    "admit_case_semantic_outputs",
    "load_verified_case_judgments",
    "prepare_case_semantic_work",
]
