"""Deterministic Hong Kong Case correction and workflow-admission conformance."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

HK_CASE_ADMISSION_RULE_ID = "HKCASE-PROP-ADMISSION-CONFORMANCE-001"
HK_CASE_ADMISSION_CONTRACT_VERSION = "1.0.0"

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_IDENTITY_PATTERN = r"[a-z][a-z0-9_]{2,95}"
_CODE_PATTERN = r"[A-Z][A-Z0-9_]{2,95}"
_MIN_LINEAGE_BRANCHES = 2


class HKCaseAdmissionErrorCode(StrEnum):
    """Closed malformed admission-conformance request failures."""

    CONTRACT = "HK_CASE_ADMISSION_CONTRACT_INVALID"
    FINGERPRINT = "HK_CASE_ADMISSION_FINGERPRINT_INVALID"
    IDENTITY = "HK_CASE_ADMISSION_IDENTITY_INVALID"


class HKCaseAdmissionError(ValueError):
    """One fail-closed malformed admission-conformance request."""

    code: HKCaseAdmissionErrorCode

    def __init__(self, code: HKCaseAdmissionErrorCode) -> None:
        """Create one stable failure."""
        self.code = code
        super().__init__(code.value)


class HKCaseAdmissionAssertion(StrEnum):
    """Fact dimensions in the final deterministic checkpoint."""

    CATALOGUE_COMPLETENESS = "CATALOGUE_COMPLETENESS"
    CORRECTION = "CORRECTION"
    DETERMINISTIC_REPRODUCIBILITY = "DETERMINISTIC_REPRODUCIBILITY"
    EVALUATION_PACKET = "EVALUATION_PACKET"
    FORBIDDEN_SIDE_EFFECTS = "FORBIDDEN_SIDE_EFFECTS"
    SEALED_PACKAGE_INTEGRITY = "SEALED_PACKAGE_INTEGRITY"
    WORKFLOW_IDENTITY = "WORKFLOW_IDENTITY"


class HKCaseCorrectionKind(StrEnum):
    """Closed correction and reprocessing histories."""

    COMPONENT_CHANGE = "COMPONENT_CHANGE"
    GENUINELY_NEW_PROPOSITION = "GENUINELY_NEW_PROPOSITION"
    MERGE_CORRECTION = "MERGE_CORRECTION"
    OFFICIAL_CORRECTION = "OFFICIAL_CORRECTION"
    PARTIAL_OFFICIAL_CORRECTION = "PARTIAL_OFFICIAL_CORRECTION"
    REPROCESSING_UNCHANGED = "REPROCESSING_UNCHANGED"
    SPLIT_CORRECTION = "SPLIT_CORRECTION"


class HKCaseLineageRelation(StrEnum):
    """Permitted forward processing-correction lineage relations."""

    FORWARD_SUCCESSOR = "FORWARD_SUCCESSOR"
    MERGED_FROM = "MERGED_FROM"
    SPLIT_FROM = "SPLIT_FROM"


class HKCaseCatalogueCompletenessMethod(StrEnum):
    """How the submitted catalogue inventory was constructed."""

    COUNT = "COUNT"
    EXPLICIT = "EXPLICIT"
    GLOB = "GLOB"


class HKCaseForbiddenCapability(StrEnum):
    """Capabilities forbidden to the deterministic fixture runner."""

    AZURE = "AZURE"
    CREDENTIAL = "CREDENTIAL"
    EMBEDDING = "EMBEDDING"
    MODEL = "MODEL"
    NETWORK = "NETWORK"
    PINECONE = "PINECONE"
    PRODUCTION_STORE = "PRODUCTION_STORE"
    ROUTING = "ROUTING"
    SOURCE = "SOURCE"
    UNDECLARED_FILE = "UNDECLARED_FILE"


class HKCaseAdmissionOutcome(StrEnum):
    """Exact deterministic checkpoint conclusions."""

    ELIGIBLE_FOR_WORKFLOW_ADMISSION = "ELIGIBLE_FOR_WORKFLOW_ADMISSION"
    FORBIDDEN_SIDE_EFFECT = "FORBIDDEN_SIDE_EFFECT"
    INVALID = "INVALID"
    NOT_ADMITTED = "NOT_ADMITTED"
    VALIDATED = "VALIDATED"


class HKCaseAdmissionReason(StrEnum):
    """Closed deterministic reasons."""

    CATALOGUE_COMPLETE = "CATALOGUE_COMPLETE"
    CATALOGUE_INCOMPLETE = "CATALOGUE_INCOMPLETE"
    CORRECTION_HISTORY_VALID = "CORRECTION_HISTORY_VALID"
    CORRECTION_INVARIANT_INVALID = "CORRECTION_INVARIANT_INVALID"
    DETERMINISTIC_ARTIFACT_DRIFT = "DETERMINISTIC_ARTIFACT_DRIFT"
    DETERMINISTIC_REPRODUCIBLE = "DETERMINISTIC_REPRODUCIBLE"
    FORBIDDEN_SIDE_EFFECT_ATTEMPT = "FORBIDDEN_SIDE_EFFECT_ATTEMPT"
    PACKAGE_SHAPE_INVALID = "PACKAGE_SHAPE_INVALID"
    PACKET_LEAKAGE = "PACKET_LEAKAGE"
    PACKET_NON_LEAKING = "PACKET_NON_LEAKING"
    SEALED_PACKAGE_INVALID = "SEALED_PACKAGE_INVALID"
    SEALED_PACKAGE_VALID = "SEALED_PACKAGE_VALID"
    SIDE_EFFECT_MUTATION_DETECTED = "SIDE_EFFECT_MUTATION_DETECTED"
    WORKFLOW_IDENTITY_MATCH = "WORKFLOW_IDENTITY_MATCH"
    WORKFLOW_IDENTITY_MISMATCH = "WORKFLOW_IDENTITY_MISMATCH"


@dataclass(frozen=True, slots=True)
class HKCaseCorrectionProposition:
    """One immutable proposition result in a correction comparison."""

    proposition_id: str
    text_fingerprint: str
    support_fingerprint: str
    attribution_fingerprint: str
    payload_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseCorrectionRecord:
    """One register-supplied record state; this evaluator allocates no identity."""

    record_id: str
    proposition_ids: tuple[str, ...]
    payload_fingerprint: str
    embedding_fingerprint: str
    selected: bool


@dataclass(frozen=True, slots=True)
class HKCaseCorrectionLineage:
    """One explicit forward record-lineage edge."""

    relation: HKCaseLineageRelation
    predecessor_record_ids: tuple[str, ...]
    successor_record_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseResultAffectingChange:
    """One changed result-affecting component fingerprint."""

    component_role: str
    prior_fingerprint: str
    current_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseCorrectionFacts:
    """Complete immutable before/after facts for one correction assertion."""

    kind: HKCaseCorrectionKind
    prior_official_version_id: str
    current_official_version_id: str
    prior_ledger_fingerprint: str
    current_ledger_fingerprint: str
    prior_result_id: str
    current_result_id: str
    prior_admission_id: str
    current_admission_id: str
    prior_propositions: tuple[HKCaseCorrectionProposition, ...]
    current_propositions: tuple[HKCaseCorrectionProposition, ...]
    prior_records: tuple[HKCaseCorrectionRecord, ...]
    current_records: tuple[HKCaseCorrectionRecord, ...]
    affected_prior_proposition_ids: tuple[str, ...]
    unaffected_reused_proposition_ids: tuple[str, ...]
    introduced_proposition_ids: tuple[str, ...]
    deselected_prior_record_ids: tuple[str, ...]
    lineages: tuple[HKCaseCorrectionLineage, ...]
    component_changes: tuple[HKCaseResultAffectingChange, ...]
    processing_history_appended: bool
    ledger_history_appended: bool
    impact_declaration_fingerprint: str | None
    prior_ledger_mutated: bool
    prior_admission_mutated: bool


@dataclass(frozen=True, slots=True)
class HKCasePairMembership:
    """One explicit positive or near-miss pair role."""

    pair_id: str
    case_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKCaseCatalogueFacts:
    """Submitted exact frozen catalogue, coverage-cell, and pair inventory."""

    completeness_method: HKCaseCatalogueCompletenessMethod
    case_ids: tuple[str, ...]
    coverage_cell_ids: tuple[str, ...]
    pair_memberships: tuple[HKCasePairMembership, ...]


@dataclass(frozen=True, slots=True)
class HKCaseEvaluationPacketFacts:
    """One evaluated workflow packet and its admitted input boundary."""

    admitted_evidence_refs: tuple[str, ...]
    packet_evidence_refs: tuple[str, ...]
    admitted_task_contract_fingerprint: str
    packet_task_contract_fingerprint: str
    packet_metadata_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseExternalEvaluationArtifact:
    """One registered or observed protected external artifact."""

    role: str
    object_ref: str
    content_fingerprint: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class HKCaseSealedPackageFacts:
    """Registered and independently observed sealed-package inventories."""

    registered_artifacts: tuple[HKCaseExternalEvaluationArtifact, ...]
    observed_artifacts: tuple[HKCaseExternalEvaluationArtifact, ...]
    registered_manifest_fingerprint: str
    observed_manifest_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseDeterministicArtifact:
    """One ordered artifact from an isolated deterministic execution."""

    path: str
    role: str
    byte_size: int
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseDeterministicRun:
    """One isolated run's exact inputs, build, and ordered outputs."""

    input_fingerprint: str
    build_fingerprint: str
    artifacts: tuple[HKCaseDeterministicArtifact, ...]


@dataclass(frozen=True, slots=True)
class HKCaseReproducibilityFacts:
    """Two isolated executions compared byte for byte."""

    first_run: HKCaseDeterministicRun
    second_run: HKCaseDeterministicRun


@dataclass(frozen=True, slots=True)
class HKCaseSideEffectFacts:
    """Denied capability attempts and independently observed mutation count."""

    attempted_capabilities: tuple[HKCaseForbiddenCapability, ...]
    observed_mutation_receipt_count: int


@dataclass(frozen=True, slots=True)
class HKCaseWorkflowComponent:
    """One expected and proposed workflow component fingerprint."""

    component_role: str
    admitted_fingerprint: str
    proposed_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKCaseWorkflowIdentityFacts:
    """One complete proposed workflow identity comparison."""

    components: tuple[HKCaseWorkflowComponent, ...]
    evaluation_run_eligible: bool
    impact_declaration_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class HKCaseAdmissionRequest:
    """One source-neutral assertion with exactly one applicable fact payload."""

    assertion: HKCaseAdmissionAssertion
    correction: HKCaseCorrectionFacts | None
    catalogue: HKCaseCatalogueFacts | None
    evaluation_packet: HKCaseEvaluationPacketFacts | None
    sealed_package: HKCaseSealedPackageFacts | None
    reproducibility: HKCaseReproducibilityFacts | None
    side_effects: HKCaseSideEffectFacts | None
    workflow_identity: HKCaseWorkflowIdentityFacts | None


@dataclass(frozen=True, slots=True)
class HKCaseAdmissionResult:
    """One effect-free deterministic correction/admission conclusion."""

    request_fingerprint: str
    outcome: HKCaseAdmissionOutcome
    reasons: tuple[HKCaseAdmissionReason, ...]
    reused_record_ids: tuple[str, ...]
    reused_embedding_fingerprints: tuple[str, ...]
    selected_current_record_ids: tuple[str, ...]
    deselected_prior_record_ids: tuple[str, ...]
    lineages: tuple[HKCaseCorrectionLineage, ...]
    new_official_version_required: bool
    new_ledger_required: bool
    processing_history_appended: bool
    ledger_history_appended: bool
    impact_declaration_required: bool
    catalogue_fingerprint: str | None
    leakage_fields: tuple[str, ...]
    sealed_package_fingerprint: str | None
    deterministic_artifact_fingerprint: str | None
    attempted_capabilities: tuple[HKCaseForbiddenCapability, ...]
    changed_workflow_component_roles: tuple[str, ...]
    complete_evaluation_required: bool
    workflow_admission_eligible: bool
    workflow_admission_created: bool
    provider_calls_authorized: bool
    deployment_authorized: bool
    search_records_created: int
    mutations_performed: int
    release_eligible: bool
    external_effects: str


_CASE_GROUPS = (
    ("SEM-MAT", "SMAT", 18),
    ("SEM-CNT", "SCNT", 18),
    ("SEM-BND", "SBND", 22),
    ("SEM-RSK", "SRSK", 20),
    ("DET-LED", "DLED", 20),
    ("DET-OUT", "DOUT", 16),
    ("DET-ADM", "DADM", 18),
)

_PAIR_CASES = (
    ("SEM-MAT-001", "SEM-MAT-013"),
    ("SEM-MAT-002", "SEM-MAT-003"),
    ("SEM-MAT-004", "SEM-MAT-005"),
    ("SEM-MAT-006", "SEM-MAT-007"),
    ("SEM-MAT-012", "SEM-MAT-013"),
    ("SEM-CNT-002", "SEM-CNT-008"),
    ("SEM-CNT-009", "SEM-CNT-014"),
    ("SEM-CNT-018", "SEM-CNT-017"),
    ("SEM-BND-001", "SEM-BND-003"),
    ("SEM-BND-005", "SEM-BND-007"),
    ("SEM-BND-010", "SEM-BND-013"),
    ("SEM-BND-016", "SEM-BND-017"),
    ("SEM-BND-010", "SEM-BND-014"),
    ("SEM-BND-005", "SEM-BND-021"),
    ("SEM-BND-019", "SEM-BND-018"),
    ("SEM-RSK-010", "SEM-RSK-011"),
    ("SEM-RSK-015", "SEM-RSK-014"),
    ("SEM-RSK-001", "SEM-RSK-007"),
    ("SEM-MAT-017", "SEM-RSK-016"),
    ("DET-LED-005", "DET-LED-006"),
    ("DET-LED-009", "DET-LED-010"),
    ("DET-OUT-001", "DET-OUT-002"),
    ("DET-OUT-003", "DET-OUT-004"),
    ("DET-OUT-005", "DET-OUT-006"),
    ("DET-OUT-007", "DET-OUT-008"),
    ("DET-ADM-008", "DET-ADM-009"),
    ("DET-ADM-010", "DET-ADM-011"),
    ("DET-ADM-012", "DET-ADM-013"),
    ("DET-ADM-014", "DET-ADM-015"),
    ("DET-ADM-017", "DET-ADM-018"),
    ("SEM-MAT-001", "SEM-MAT-015"),
)

_FORBIDDEN_PACKET_FIELDS = frozenset(
    {
        "case_title",
        "coverage_cell_id",
        "critical_error_tag",
        "expected_answer",
        "pair_role",
        "score",
    }
)

_REQUIRED_SEALED_ARTIFACT_ROLES = frozenset(
    {
        "PROTECTED_CATALOGUE",
        "REFERENCE_PROPOSITION_MAP",
        "SEALED_JUDGMENT",
        "SELECTION_MATRIX",
    }
)

_REQUIRED_WORKFLOW_COMPONENT_ROLES = frozenset(
    {
        "COVERAGE_MATRIX",
        "COVERAGE_UNIT_CONTRACT",
        "DEPENDENCY_CONTRACT",
        "DEPENDENCY_LOCK",
        "DETERMINISTIC_CATALOGUE",
        "EVALUATION_RESULT",
        "EVALUATOR",
        "LEGAL_DESK_DECISION_CONTRACT",
        "MODEL_PROFILE",
        "OPINION_ATTRIBUTION_CONTRACT",
        "ORIGINAL_EVIDENCE_PROFILE",
        "PARSER_PROFILE",
        "PROCESSING_BUILD",
        "PROPOSITION_CONTRACT",
        "RENDERER",
        "REPETITION_RULE",
        "SEGMENTATION_CONTRACT",
        "SEMANTIC_CATALOGUE",
        "SOURCE_RULEBOOK_PACKAGE",
        "STRUCTURAL_NORMALIZATION_CONTRACT",
        "TASK_CONTRACT",
        "THRESHOLD_PROFILE",
        "TOKENIZER",
        "VALIDATOR",
    }
)


def hk_case_frozen_case_ids() -> tuple[str, ...]:
    """Return the exact ordered 132-case synthetic catalogue."""
    return tuple(
        f"HKCASE-PROP-{case_group}-{number:03d}"
        for case_group, _, count in _CASE_GROUPS
        for number in range(1, count + 1)
    )


def hk_case_frozen_coverage_cell_ids() -> tuple[str, ...]:
    """Return the exact ordered 132 primary coverage cells."""
    return tuple(
        f"HKCASE-PROP-COV-{coverage_group}-{number:03d}"
        for _, coverage_group, count in _CASE_GROUPS
        for number in range(1, count + 1)
    )


def hk_case_frozen_pair_memberships() -> tuple[HKCasePairMembership, ...]:
    """Return all 62 explicit roles for the 31 frozen high-risk pairs."""
    memberships: list[HKCasePairMembership] = []
    for number, (positive_suffix, near_miss_suffix) in enumerate(_PAIR_CASES, 1):
        pair_id = f"HKCASE-PROP-PAIR-{number:03d}"
        memberships.extend(
            (
                HKCasePairMembership(pair_id, f"HKCASE-PROP-{positive_suffix}", "POSITIVE"),
                HKCasePairMembership(
                    pair_id,
                    f"HKCASE-PROP-{near_miss_suffix}",
                    "NEAR_MISS",
                ),
            )
        )
    return tuple(memberships)


def hk_case_frozen_catalogue_fingerprint() -> str:
    """Fingerprint the accepted explicit IDs, cells, and pair roles."""
    document: dict[str, JsonValue] = {
        "case_ids": list(hk_case_frozen_case_ids()),
        "coverage_cell_ids": list(hk_case_frozen_coverage_cell_ids()),
        "pair_memberships": [
            {"pair_id": item.pair_id, "case_id": item.case_id, "role": item.role}
            for item in hk_case_frozen_pair_memberships()
        ],
    }
    return fingerprint(checked_json_value(document))


def evaluate_hk_case_admission(request: HKCaseAdmissionRequest) -> HKCaseAdmissionResult:
    """Evaluate one fact-derived correction, package, security, or identity assertion."""
    request_fingerprint = fingerprint(
        checked_json_value(hk_case_admission_request_document(request))
    )
    if not _shape_valid(request):
        result = _empty_result(
            request_fingerprint,
            HKCaseAdmissionOutcome.INVALID,
            (HKCaseAdmissionReason.PACKAGE_SHAPE_INVALID,),
        )
    elif request.correction is not None:
        result = _correction_result(request_fingerprint, request.correction)
    elif request.catalogue is not None:
        result = _catalogue_result(request_fingerprint, request.catalogue)
    elif request.evaluation_packet is not None:
        result = _packet_result(request_fingerprint, request.evaluation_packet)
    elif request.sealed_package is not None:
        result = _sealed_result(request_fingerprint, request.sealed_package)
    elif request.reproducibility is not None:
        result = _reproducibility_result(request_fingerprint, request.reproducibility)
    elif request.side_effects is not None:
        result = _side_effect_result(request_fingerprint, request.side_effects)
    elif request.workflow_identity is not None:
        result = _workflow_result(request_fingerprint, request.workflow_identity)
    else:
        result = _empty_result(
            request_fingerprint,
            HKCaseAdmissionOutcome.INVALID,
            (HKCaseAdmissionReason.PACKAGE_SHAPE_INVALID,),
        )
    return result


def _shape_valid(request: HKCaseAdmissionRequest) -> bool:
    values = {
        HKCaseAdmissionAssertion.CORRECTION: request.correction,
        HKCaseAdmissionAssertion.CATALOGUE_COMPLETENESS: request.catalogue,
        HKCaseAdmissionAssertion.EVALUATION_PACKET: request.evaluation_packet,
        HKCaseAdmissionAssertion.SEALED_PACKAGE_INTEGRITY: request.sealed_package,
        HKCaseAdmissionAssertion.DETERMINISTIC_REPRODUCIBILITY: request.reproducibility,
        HKCaseAdmissionAssertion.FORBIDDEN_SIDE_EFFECTS: request.side_effects,
        HKCaseAdmissionAssertion.WORKFLOW_IDENTITY: request.workflow_identity,
    }
    return (
        values[request.assertion] is not None
        and sum(value is not None for value in values.values()) == 1
    )


def _correction_result(
    request_fingerprint: str,
    facts: HKCaseCorrectionFacts,
) -> HKCaseAdmissionResult:
    valid = _correction_valid(facts)
    if not valid:
        return _empty_result(
            request_fingerprint,
            HKCaseAdmissionOutcome.INVALID,
            (HKCaseAdmissionReason.CORRECTION_INVARIANT_INVALID,),
            details=_ResultDetails(
                impact_declaration_required=_correction_requires_impact(facts),
                complete_evaluation_required=(facts.kind is HKCaseCorrectionKind.COMPONENT_CHANGE),
            ),
        )
    prior_records = {item.record_id: item for item in facts.prior_records}
    reused_records = tuple(
        item.record_id
        for item in facts.current_records
        if prior_records.get(item.record_id) == item and item.selected
    )
    reused_embeddings = tuple(
        item.embedding_fingerprint
        for item in facts.current_records
        if item.record_id in reused_records
    )
    return _empty_result(
        request_fingerprint,
        HKCaseAdmissionOutcome.VALIDATED,
        (HKCaseAdmissionReason.CORRECTION_HISTORY_VALID,),
        details=_ResultDetails(
            reused_record_ids=reused_records,
            reused_embedding_fingerprints=reused_embeddings,
            selected_current_record_ids=tuple(
                item.record_id for item in facts.current_records if item.selected
            ),
            deselected_prior_record_ids=facts.deselected_prior_record_ids,
            lineages=facts.lineages,
            new_official_version_required=(
                facts.current_official_version_id != facts.prior_official_version_id
            ),
            new_ledger_required=(
                facts.current_ledger_fingerprint != facts.prior_ledger_fingerprint
            ),
            processing_history_appended=facts.processing_history_appended,
            ledger_history_appended=facts.ledger_history_appended,
            complete_evaluation_required=(facts.kind is HKCaseCorrectionKind.COMPONENT_CHANGE),
        ),
    )


def _correction_valid(facts: HKCaseCorrectionFacts) -> bool:
    if not _correction_common_valid(facts):
        return False
    validators = {
        HKCaseCorrectionKind.REPROCESSING_UNCHANGED: _reprocessing_unchanged_valid,
        HKCaseCorrectionKind.OFFICIAL_CORRECTION: _official_correction_valid,
        HKCaseCorrectionKind.SPLIT_CORRECTION: _split_correction_valid,
        HKCaseCorrectionKind.MERGE_CORRECTION: _merge_correction_valid,
        HKCaseCorrectionKind.GENUINELY_NEW_PROPOSITION: _new_proposition_valid,
        HKCaseCorrectionKind.PARTIAL_OFFICIAL_CORRECTION: _partial_correction_valid,
        HKCaseCorrectionKind.COMPONENT_CHANGE: _component_change_valid,
    }
    return validators[facts.kind](facts)


def _correction_common_valid(facts: HKCaseCorrectionFacts) -> bool:
    identity_groups = (
        tuple(item.proposition_id for item in facts.prior_propositions),
        tuple(item.proposition_id for item in facts.current_propositions),
        tuple(item.record_id for item in facts.prior_records),
        tuple(item.record_id for item in facts.current_records),
        facts.affected_prior_proposition_ids,
        facts.unaffected_reused_proposition_ids,
        facts.introduced_proposition_ids,
        facts.deselected_prior_record_ids,
        tuple(item.component_role for item in facts.component_changes),
    )
    prior_props = {item.proposition_id for item in facts.prior_propositions}
    current_props = {item.proposition_id for item in facts.current_propositions}
    prior_record_ids = {item.record_id for item in facts.prior_records}
    current_record_ids = {item.record_id for item in facts.current_records}
    selected_prior_record_ids = {item.record_id for item in facts.prior_records if item.selected}
    selected_current_record_ids = {
        item.record_id for item in facts.current_records if item.selected
    }
    return all(
        (
            not any(_duplicates(items) for items in identity_groups),
            set(facts.affected_prior_proposition_ids).issubset(prior_props),
            set(facts.unaffected_reused_proposition_ids).issubset(prior_props & current_props),
            set(facts.introduced_proposition_ids).issubset(current_props - prior_props),
            set(facts.deselected_prior_record_ids).issubset(prior_record_ids),
            set(facts.deselected_prior_record_ids).issubset(selected_prior_record_ids),
            set(facts.deselected_prior_record_ids).isdisjoint(selected_current_record_ids),
            not any(
                not set(item.proposition_ids).issubset(prior_props) for item in facts.prior_records
            ),
            not any(
                not set(item.proposition_ids).issubset(current_props)
                for item in facts.current_records
            ),
            not any(
                not set(item.predecessor_record_ids).issubset(prior_record_ids)
                or not set(item.successor_record_ids).issubset(current_record_ids)
                or not item.predecessor_record_ids
                or not item.successor_record_ids
                or _duplicates(item.predecessor_record_ids)
                or _duplicates(item.successor_record_ids)
                for item in facts.lineages
            ),
            not any(
                item.prior_fingerprint == item.current_fingerprint
                for item in facts.component_changes
            ),
            not facts.prior_ledger_mutated,
            not facts.prior_admission_mutated,
        )
    )


def _history_and_new_ledger(facts: HKCaseCorrectionFacts) -> bool:
    return (
        facts.processing_history_appended
        and facts.ledger_history_appended
        and facts.current_ledger_fingerprint != facts.prior_ledger_fingerprint
    )


def _reprocessing_unchanged_valid(facts: HKCaseCorrectionFacts) -> bool:
    return (
        facts.current_official_version_id == facts.prior_official_version_id
        and _history_and_new_ledger(facts)
        and facts.current_result_id != facts.prior_result_id
        and facts.current_admission_id == facts.prior_admission_id
        and facts.prior_propositions == facts.current_propositions
        and facts.prior_records == facts.current_records
        and set(facts.unaffected_reused_proposition_ids)
        == {item.proposition_id for item in facts.current_propositions}
        and not facts.affected_prior_proposition_ids
        and not facts.introduced_proposition_ids
        and not facts.deselected_prior_record_ids
        and not facts.lineages
        and not facts.component_changes
    )


def _official_correction_valid(facts: HKCaseCorrectionFacts) -> bool:
    return (
        facts.current_official_version_id != facts.prior_official_version_id
        and _history_and_new_ledger(facts)
        and bool(facts.affected_prior_proposition_ids)
        and facts.prior_propositions != facts.current_propositions
        and facts.prior_records != facts.current_records
        and bool(facts.lineages)
        and all(item.relation is HKCaseLineageRelation.FORWARD_SUCCESSOR for item in facts.lineages)
        and bool(facts.deselected_prior_record_ids)
        and facts.impact_declaration_fingerprint is not None
        and not facts.unaffected_reused_proposition_ids
        and not facts.introduced_proposition_ids
        and not facts.component_changes
    )


def _split_correction_valid(facts: HKCaseCorrectionFacts) -> bool:
    predecessor_id = facts.lineages[0].predecessor_record_ids[0] if facts.lineages else ""
    predecessor = next(
        (item for item in facts.prior_records if item.record_id == predecessor_id),
        None,
    )
    successor_ids: set[str] = (
        set(facts.lineages[0].successor_record_ids) if facts.lineages else set()
    )
    successors = tuple(item for item in facts.current_records if item.record_id in successor_ids)
    return (
        facts.current_official_version_id == facts.prior_official_version_id
        and _history_and_new_ledger(facts)
        and len(facts.lineages) == 1
        and facts.lineages[0].relation is HKCaseLineageRelation.SPLIT_FROM
        and len(facts.lineages[0].predecessor_record_ids) == 1
        and len(facts.lineages[0].successor_record_ids) >= _MIN_LINEAGE_BRANCHES
        and predecessor is not None
        and predecessor.selected
        and len(predecessor.proposition_ids) >= _MIN_LINEAGE_BRANCHES
        and len(successors) == len(successor_ids)
        and all(item.selected and len(item.proposition_ids) == 1 for item in successors)
        and {proposition_id for item in successors for proposition_id in item.proposition_ids}
        == set(predecessor.proposition_ids)
        and set(facts.deselected_prior_record_ids) == set(facts.lineages[0].predecessor_record_ids)
        and all(item.selected for item in facts.current_records)
        and facts.impact_declaration_fingerprint is not None
        and not facts.introduced_proposition_ids
        and not facts.component_changes
    )


def _merge_correction_valid(facts: HKCaseCorrectionFacts) -> bool:
    predecessor_ids: set[str] = (
        set(facts.lineages[0].predecessor_record_ids) if facts.lineages else set()
    )
    predecessors = tuple(item for item in facts.prior_records if item.record_id in predecessor_ids)
    successor_ids: set[str] = (
        set(facts.lineages[0].successor_record_ids) if facts.lineages else set()
    )
    successors = tuple(item for item in facts.current_records if item.record_id in successor_ids)
    return (
        facts.current_official_version_id == facts.prior_official_version_id
        and _history_and_new_ledger(facts)
        and len(facts.lineages) == 1
        and facts.lineages[0].relation is HKCaseLineageRelation.MERGED_FROM
        and len(facts.lineages[0].predecessor_record_ids) >= _MIN_LINEAGE_BRANCHES
        and len(facts.lineages[0].successor_record_ids) == 1
        and len(predecessors) == len(predecessor_ids)
        and all(item.selected for item in predecessors)
        and len(successors) == 1
        and successors[0].selected
        and len(successors[0].proposition_ids) == 1
        and set(facts.deselected_prior_record_ids) == set(facts.lineages[0].predecessor_record_ids)
        and len([item for item in facts.current_records if item.selected]) == 1
        and facts.impact_declaration_fingerprint is not None
        and not facts.introduced_proposition_ids
        and not facts.component_changes
    )


def _new_proposition_valid(facts: HKCaseCorrectionFacts) -> bool:
    introduced_ids = set(facts.introduced_proposition_ids)
    introduced_record_ids = {
        item.record_id
        for item in facts.current_records
        if set(item.proposition_ids) & introduced_ids
    }
    lineage_successors = {
        record_id for item in facts.lineages for record_id in item.successor_record_ids
    }
    introduced_record_propositions = tuple(
        proposition_id
        for item in facts.current_records
        if item.selected
        for proposition_id in item.proposition_ids
        if proposition_id in introduced_ids
    )
    prior_records = {item.record_id: item for item in facts.prior_records}
    return (
        facts.current_official_version_id == facts.prior_official_version_id
        and _history_and_new_ledger(facts)
        and bool(facts.introduced_proposition_ids)
        and set(introduced_record_propositions) == introduced_ids
        and not _duplicates(introduced_record_propositions)
        and all(
            prior_records.get(item.record_id) == item
            for item in facts.current_records
            if item.record_id in prior_records
        )
        and introduced_record_ids.isdisjoint(lineage_successors)
        and facts.impact_declaration_fingerprint is not None
        and not facts.affected_prior_proposition_ids
        and not facts.deselected_prior_record_ids
        and not facts.component_changes
    )


def _partial_correction_valid(facts: HKCaseCorrectionFacts) -> bool:
    prior_props = {item.proposition_id: item for item in facts.prior_propositions}
    current_props = {item.proposition_id: item for item in facts.current_propositions}
    prior_records = {item.record_id: item for item in facts.prior_records}
    current_records = {item.record_id: item for item in facts.current_records}
    exact_unaffected = all(
        prior_props[item] == current_props[item] for item in facts.unaffected_reused_proposition_ids
    )
    reused_record_props = {
        proposition_id
        for record_id, current in current_records.items()
        if prior_records.get(record_id) == current
        for proposition_id in current.proposition_ids
    }
    affected_ids = set(facts.affected_prior_proposition_ids)
    affected_predecessor_ids = {
        item.record_id for item in facts.prior_records if set(item.proposition_ids) & affected_ids
    }
    forward_predecessor_ids = {
        record_id
        for item in facts.lineages
        if item.relation is HKCaseLineageRelation.FORWARD_SUCCESSOR
        for record_id in item.predecessor_record_ids
    }
    return (
        facts.current_official_version_id != facts.prior_official_version_id
        and _history_and_new_ledger(facts)
        and bool(facts.affected_prior_proposition_ids)
        and bool(facts.unaffected_reused_proposition_ids)
        and facts.prior_propositions != facts.current_propositions
        and exact_unaffected
        and set(facts.unaffected_reused_proposition_ids).issubset(reused_record_props)
        and any(item.relation is HKCaseLineageRelation.FORWARD_SUCCESSOR for item in facts.lineages)
        and affected_predecessor_ids == forward_predecessor_ids
        and facts.impact_declaration_fingerprint is not None
        and not facts.introduced_proposition_ids
        and not facts.component_changes
    )


def _component_change_valid(facts: HKCaseCorrectionFacts) -> bool:
    return (
        bool(facts.component_changes)
        and (
            facts.current_result_id != facts.prior_result_id
            or facts.impact_declaration_fingerprint is not None
        )
        and facts.current_admission_id == facts.prior_admission_id
        and facts.current_ledger_fingerprint == facts.prior_ledger_fingerprint
        and not facts.affected_prior_proposition_ids
        and not facts.unaffected_reused_proposition_ids
        and not facts.introduced_proposition_ids
        and not facts.deselected_prior_record_ids
        and not facts.lineages
    )


def _correction_requires_impact(facts: HKCaseCorrectionFacts) -> bool:
    return facts.kind is not HKCaseCorrectionKind.REPROCESSING_UNCHANGED and (
        facts.impact_declaration_fingerprint is None
    )


def _catalogue_result(
    request_fingerprint: str,
    facts: HKCaseCatalogueFacts,
) -> HKCaseAdmissionResult:
    valid = (
        facts.completeness_method is HKCaseCatalogueCompletenessMethod.EXPLICIT
        and facts.case_ids == hk_case_frozen_case_ids()
        and facts.coverage_cell_ids == hk_case_frozen_coverage_cell_ids()
        and facts.pair_memberships == hk_case_frozen_pair_memberships()
        and not _duplicates(facts.case_ids)
        and not _duplicates(facts.coverage_cell_ids)
        and not _duplicates(facts.pair_memberships)
    )
    return _empty_result(
        request_fingerprint,
        HKCaseAdmissionOutcome.VALIDATED if valid else HKCaseAdmissionOutcome.INVALID,
        (
            HKCaseAdmissionReason.CATALOGUE_COMPLETE
            if valid
            else HKCaseAdmissionReason.CATALOGUE_INCOMPLETE,
        ),
        details=_ResultDetails(
            catalogue_fingerprint=(hk_case_frozen_catalogue_fingerprint() if valid else None)
        ),
    )


def _packet_result(
    request_fingerprint: str,
    facts: HKCaseEvaluationPacketFacts,
) -> HKCaseAdmissionResult:
    leakage_fields = tuple(sorted(_FORBIDDEN_PACKET_FIELDS & set(facts.packet_metadata_fields)))
    valid = (
        not leakage_fields
        and facts.packet_evidence_refs == facts.admitted_evidence_refs
        and facts.packet_task_contract_fingerprint == facts.admitted_task_contract_fingerprint
        and not _duplicates(facts.packet_evidence_refs)
        and not _duplicates(facts.packet_metadata_fields)
    )
    return _empty_result(
        request_fingerprint,
        HKCaseAdmissionOutcome.VALIDATED if valid else HKCaseAdmissionOutcome.INVALID,
        (
            HKCaseAdmissionReason.PACKET_NON_LEAKING
            if valid
            else HKCaseAdmissionReason.PACKET_LEAKAGE,
        ),
        details=_ResultDetails(leakage_fields=leakage_fields),
    )


def _artifact_inventory_fingerprint(
    artifacts: tuple[HKCaseExternalEvaluationArtifact, ...],
) -> str:
    document: list[JsonValue] = [
        {
            "role": item.role,
            "object_ref": item.object_ref,
            "content_fingerprint": item.content_fingerprint,
            "byte_size": item.byte_size,
        }
        for item in artifacts
    ]
    return fingerprint(checked_json_value(document))


def _sealed_result(
    request_fingerprint: str,
    facts: HKCaseSealedPackageFacts,
) -> HKCaseAdmissionResult:
    registered_roles = tuple(item.role for item in facts.registered_artifacts)
    observed_roles = tuple(item.role for item in facts.observed_artifacts)
    registered_fingerprint = _artifact_inventory_fingerprint(facts.registered_artifacts)
    observed_fingerprint = _artifact_inventory_fingerprint(facts.observed_artifacts)
    valid = (
        set(registered_roles) == set(_REQUIRED_SEALED_ARTIFACT_ROLES)
        and not _duplicates(registered_roles)
        and facts.registered_artifacts == facts.observed_artifacts
        and not _duplicates(observed_roles)
        and facts.registered_manifest_fingerprint == registered_fingerprint
        and facts.observed_manifest_fingerprint == observed_fingerprint
        and registered_fingerprint == observed_fingerprint
    )
    return _empty_result(
        request_fingerprint,
        HKCaseAdmissionOutcome.VALIDATED if valid else HKCaseAdmissionOutcome.INVALID,
        (
            HKCaseAdmissionReason.SEALED_PACKAGE_VALID
            if valid
            else HKCaseAdmissionReason.SEALED_PACKAGE_INVALID,
        ),
        details=_ResultDetails(
            sealed_package_fingerprint=registered_fingerprint if valid else None
        ),
    )


def _run_artifact_fingerprint(run: HKCaseDeterministicRun) -> str:
    document: dict[str, JsonValue] = {
        "input_fingerprint": run.input_fingerprint,
        "build_fingerprint": run.build_fingerprint,
        "artifacts": [
            {
                "path": item.path,
                "role": item.role,
                "byte_size": item.byte_size,
                "content_fingerprint": item.content_fingerprint,
            }
            for item in run.artifacts
        ],
    }
    return fingerprint(checked_json_value(document))


def _reproducibility_result(
    request_fingerprint: str,
    facts: HKCaseReproducibilityFacts,
) -> HKCaseAdmissionResult:
    first = facts.first_run
    second = facts.second_run
    paths = tuple(item.path for item in first.artifacts)
    valid = (
        first == second
        and bool(first.artifacts)
        and not _duplicates(paths)
        and all(item.byte_size > 0 for item in first.artifacts)
    )
    return _empty_result(
        request_fingerprint,
        HKCaseAdmissionOutcome.VALIDATED if valid else HKCaseAdmissionOutcome.INVALID,
        (
            HKCaseAdmissionReason.DETERMINISTIC_REPRODUCIBLE
            if valid
            else HKCaseAdmissionReason.DETERMINISTIC_ARTIFACT_DRIFT,
        ),
        details=_ResultDetails(
            deterministic_artifact_fingerprint=(_run_artifact_fingerprint(first) if valid else None)
        ),
    )


def _side_effect_result(
    request_fingerprint: str,
    facts: HKCaseSideEffectFacts,
) -> HKCaseAdmissionResult:
    mutation_detected = facts.observed_mutation_receipt_count != 0
    return _empty_result(
        request_fingerprint,
        (
            HKCaseAdmissionOutcome.INVALID
            if mutation_detected
            else HKCaseAdmissionOutcome.FORBIDDEN_SIDE_EFFECT
        ),
        (
            HKCaseAdmissionReason.SIDE_EFFECT_MUTATION_DETECTED
            if mutation_detected
            else HKCaseAdmissionReason.FORBIDDEN_SIDE_EFFECT_ATTEMPT,
        ),
        details=_ResultDetails(
            attempted_capabilities=facts.attempted_capabilities,
            mutations_performed=facts.observed_mutation_receipt_count,
        ),
    )


def _workflow_result(
    request_fingerprint: str,
    facts: HKCaseWorkflowIdentityFacts,
) -> HKCaseAdmissionResult:
    roles = tuple(item.component_role for item in facts.components)
    changed_roles = tuple(
        item.component_role
        for item in facts.components
        if item.admitted_fingerprint != item.proposed_fingerprint
    )
    valid = (
        set(roles) == set(_REQUIRED_WORKFLOW_COMPONENT_ROLES)
        and not _duplicates(roles)
        and not changed_roles
        and facts.evaluation_run_eligible
    )
    return _empty_result(
        request_fingerprint,
        (
            HKCaseAdmissionOutcome.ELIGIBLE_FOR_WORKFLOW_ADMISSION
            if valid
            else HKCaseAdmissionOutcome.NOT_ADMITTED
        ),
        (
            HKCaseAdmissionReason.WORKFLOW_IDENTITY_MATCH
            if valid
            else HKCaseAdmissionReason.WORKFLOW_IDENTITY_MISMATCH,
        ),
        details=_ResultDetails(
            changed_workflow_component_roles=changed_roles,
            complete_evaluation_required=not valid,
            impact_declaration_required=(
                not valid and facts.impact_declaration_fingerprint is None
            ),
            workflow_admission_eligible=valid,
        ),
    )


@dataclass(frozen=True, slots=True)
class _ResultDetails:
    reused_record_ids: tuple[str, ...] = ()
    reused_embedding_fingerprints: tuple[str, ...] = ()
    selected_current_record_ids: tuple[str, ...] = ()
    deselected_prior_record_ids: tuple[str, ...] = ()
    lineages: tuple[HKCaseCorrectionLineage, ...] = ()
    new_official_version_required: bool = False
    new_ledger_required: bool = False
    processing_history_appended: bool = False
    ledger_history_appended: bool = False
    impact_declaration_required: bool = False
    catalogue_fingerprint: str | None = None
    leakage_fields: tuple[str, ...] = ()
    sealed_package_fingerprint: str | None = None
    deterministic_artifact_fingerprint: str | None = None
    attempted_capabilities: tuple[HKCaseForbiddenCapability, ...] = ()
    changed_workflow_component_roles: tuple[str, ...] = ()
    complete_evaluation_required: bool = False
    workflow_admission_eligible: bool = False
    mutations_performed: int = 0


def _empty_result(
    request_fingerprint: str,
    outcome: HKCaseAdmissionOutcome,
    reasons: tuple[HKCaseAdmissionReason, ...],
    details: _ResultDetails | None = None,
) -> HKCaseAdmissionResult:
    resolved = details or _ResultDetails()
    return HKCaseAdmissionResult(
        request_fingerprint=request_fingerprint,
        outcome=outcome,
        reasons=reasons,
        reused_record_ids=resolved.reused_record_ids,
        reused_embedding_fingerprints=resolved.reused_embedding_fingerprints,
        selected_current_record_ids=resolved.selected_current_record_ids,
        deselected_prior_record_ids=resolved.deselected_prior_record_ids,
        lineages=resolved.lineages,
        new_official_version_required=resolved.new_official_version_required,
        new_ledger_required=resolved.new_ledger_required,
        processing_history_appended=resolved.processing_history_appended,
        ledger_history_appended=resolved.ledger_history_appended,
        impact_declaration_required=resolved.impact_declaration_required,
        catalogue_fingerprint=resolved.catalogue_fingerprint,
        leakage_fields=resolved.leakage_fields,
        sealed_package_fingerprint=resolved.sealed_package_fingerprint,
        deterministic_artifact_fingerprint=resolved.deterministic_artifact_fingerprint,
        attempted_capabilities=resolved.attempted_capabilities,
        changed_workflow_component_roles=resolved.changed_workflow_component_roles,
        complete_evaluation_required=resolved.complete_evaluation_required,
        workflow_admission_eligible=resolved.workflow_admission_eligible,
        workflow_admission_created=False,
        provider_calls_authorized=False,
        deployment_authorized=False,
        search_records_created=0,
        mutations_performed=resolved.mutations_performed,
        release_eligible=False,
        external_effects="NONE",
    )


def hk_case_admission_request_document(
    request: HKCaseAdmissionRequest,
) -> dict[str, JsonValue]:
    """Return the canonical JSON-compatible request projection."""
    return {
        "schema_id": "asklegal.hk-cases.admission-request",
        "schema_version": HK_CASE_ADMISSION_CONTRACT_VERSION,
        "rule_id": HK_CASE_ADMISSION_RULE_ID,
        "assertion": request.assertion.value,
        "correction": _correction_document(request.correction),
        "catalogue": _catalogue_document(request.catalogue),
        "evaluation_packet": _packet_document(request.evaluation_packet),
        "sealed_package": _sealed_document(request.sealed_package),
        "reproducibility": _reproducibility_document(request.reproducibility),
        "side_effects": _side_effects_document(request.side_effects),
        "workflow_identity": _workflow_document(request.workflow_identity),
    }


def _correction_document(value: HKCaseCorrectionFacts | None) -> JsonValue:
    if value is None:
        return None
    return {
        "kind": value.kind.value,
        "prior_official_version_id": value.prior_official_version_id,
        "current_official_version_id": value.current_official_version_id,
        "prior_ledger_fingerprint": value.prior_ledger_fingerprint,
        "current_ledger_fingerprint": value.current_ledger_fingerprint,
        "prior_result_id": value.prior_result_id,
        "current_result_id": value.current_result_id,
        "prior_admission_id": value.prior_admission_id,
        "current_admission_id": value.current_admission_id,
        "prior_propositions": [
            _correction_proposition_document(item) for item in value.prior_propositions
        ],
        "current_propositions": [
            _correction_proposition_document(item) for item in value.current_propositions
        ],
        "prior_records": [_correction_record_document(item) for item in value.prior_records],
        "current_records": [_correction_record_document(item) for item in value.current_records],
        "affected_prior_proposition_ids": list(value.affected_prior_proposition_ids),
        "unaffected_reused_proposition_ids": list(value.unaffected_reused_proposition_ids),
        "introduced_proposition_ids": list(value.introduced_proposition_ids),
        "deselected_prior_record_ids": list(value.deselected_prior_record_ids),
        "lineages": [_lineage_document(item) for item in value.lineages],
        "component_changes": [
            {
                "component_role": item.component_role,
                "prior_fingerprint": item.prior_fingerprint,
                "current_fingerprint": item.current_fingerprint,
            }
            for item in value.component_changes
        ],
        "processing_history_appended": value.processing_history_appended,
        "ledger_history_appended": value.ledger_history_appended,
        "impact_declaration_fingerprint": value.impact_declaration_fingerprint,
        "prior_ledger_mutated": value.prior_ledger_mutated,
        "prior_admission_mutated": value.prior_admission_mutated,
    }


def _correction_proposition_document(value: HKCaseCorrectionProposition) -> dict[str, JsonValue]:
    return {
        "proposition_id": value.proposition_id,
        "text_fingerprint": value.text_fingerprint,
        "support_fingerprint": value.support_fingerprint,
        "attribution_fingerprint": value.attribution_fingerprint,
        "payload_fingerprint": value.payload_fingerprint,
    }


def _correction_record_document(value: HKCaseCorrectionRecord) -> dict[str, JsonValue]:
    return {
        "record_id": value.record_id,
        "proposition_ids": list(value.proposition_ids),
        "payload_fingerprint": value.payload_fingerprint,
        "embedding_fingerprint": value.embedding_fingerprint,
        "selected": value.selected,
    }


def _lineage_document(value: HKCaseCorrectionLineage) -> dict[str, JsonValue]:
    return {
        "relation": value.relation.value,
        "predecessor_record_ids": list(value.predecessor_record_ids),
        "successor_record_ids": list(value.successor_record_ids),
    }


def _catalogue_document(value: HKCaseCatalogueFacts | None) -> JsonValue:
    if value is None:
        return None
    return {
        "completeness_method": value.completeness_method.value,
        "case_ids": list(value.case_ids),
        "coverage_cell_ids": list(value.coverage_cell_ids),
        "pair_memberships": [
            {"pair_id": item.pair_id, "case_id": item.case_id, "role": item.role}
            for item in value.pair_memberships
        ],
    }


def _packet_document(value: HKCaseEvaluationPacketFacts | None) -> JsonValue:
    if value is None:
        return None
    return {
        "admitted_evidence_refs": list(value.admitted_evidence_refs),
        "packet_evidence_refs": list(value.packet_evidence_refs),
        "admitted_task_contract_fingerprint": value.admitted_task_contract_fingerprint,
        "packet_task_contract_fingerprint": value.packet_task_contract_fingerprint,
        "packet_metadata_fields": list(value.packet_metadata_fields),
    }


def _external_artifact_document(value: HKCaseExternalEvaluationArtifact) -> dict[str, JsonValue]:
    return {
        "role": value.role,
        "object_ref": value.object_ref,
        "content_fingerprint": value.content_fingerprint,
        "byte_size": value.byte_size,
    }


def _sealed_document(value: HKCaseSealedPackageFacts | None) -> JsonValue:
    if value is None:
        return None
    return {
        "registered_artifacts": [
            _external_artifact_document(item) for item in value.registered_artifacts
        ],
        "observed_artifacts": [
            _external_artifact_document(item) for item in value.observed_artifacts
        ],
        "registered_manifest_fingerprint": value.registered_manifest_fingerprint,
        "observed_manifest_fingerprint": value.observed_manifest_fingerprint,
    }


def _run_document(value: HKCaseDeterministicRun) -> dict[str, JsonValue]:
    return {
        "input_fingerprint": value.input_fingerprint,
        "build_fingerprint": value.build_fingerprint,
        "artifacts": [
            {
                "path": item.path,
                "role": item.role,
                "byte_size": item.byte_size,
                "content_fingerprint": item.content_fingerprint,
            }
            for item in value.artifacts
        ],
    }


def _reproducibility_document(value: HKCaseReproducibilityFacts | None) -> JsonValue:
    if value is None:
        return None
    return {
        "first_run": _run_document(value.first_run),
        "second_run": _run_document(value.second_run),
    }


def _side_effects_document(value: HKCaseSideEffectFacts | None) -> JsonValue:
    if value is None:
        return None
    return {
        "attempted_capabilities": [item.value for item in value.attempted_capabilities],
        "observed_mutation_receipt_count": value.observed_mutation_receipt_count,
    }


def _workflow_document(value: HKCaseWorkflowIdentityFacts | None) -> JsonValue:
    if value is None:
        return None
    return {
        "components": [
            {
                "component_role": item.component_role,
                "admitted_fingerprint": item.admitted_fingerprint,
                "proposed_fingerprint": item.proposed_fingerprint,
            }
            for item in value.components
        ],
        "evaluation_run_eligible": value.evaluation_run_eligible,
        "impact_declaration_fingerprint": value.impact_declaration_fingerprint,
    }


def hk_case_admission_result_document(
    result: HKCaseAdmissionResult,
) -> dict[str, JsonValue]:
    """Return one canonical JSON-compatible result projection."""
    return {
        "schema_id": "asklegal.hk-cases.admission-result",
        "schema_version": HK_CASE_ADMISSION_CONTRACT_VERSION,
        "rule_id": HK_CASE_ADMISSION_RULE_ID,
        "request_fingerprint": result.request_fingerprint,
        "outcome": result.outcome.value,
        "reasons": [item.value for item in result.reasons],
        "reused_record_ids": list(result.reused_record_ids),
        "reused_embedding_fingerprints": list(result.reused_embedding_fingerprints),
        "selected_current_record_ids": list(result.selected_current_record_ids),
        "deselected_prior_record_ids": list(result.deselected_prior_record_ids),
        "lineages": [_lineage_document(item) for item in result.lineages],
        "new_official_version_required": result.new_official_version_required,
        "new_ledger_required": result.new_ledger_required,
        "processing_history_appended": result.processing_history_appended,
        "ledger_history_appended": result.ledger_history_appended,
        "impact_declaration_required": result.impact_declaration_required,
        "catalogue_fingerprint": result.catalogue_fingerprint,
        "leakage_fields": list(result.leakage_fields),
        "sealed_package_fingerprint": result.sealed_package_fingerprint,
        "deterministic_artifact_fingerprint": result.deterministic_artifact_fingerprint,
        "attempted_capabilities": [item.value for item in result.attempted_capabilities],
        "changed_workflow_component_roles": list(result.changed_workflow_component_roles),
        "complete_evaluation_required": result.complete_evaluation_required,
        "workflow_admission_eligible": result.workflow_admission_eligible,
        "workflow_admission_created": result.workflow_admission_created,
        "provider_calls_authorized": result.provider_calls_authorized,
        "deployment_authorized": result.deployment_authorized,
        "search_records_created": result.search_records_created,
        "mutations_performed": result.mutations_performed,
        "release_eligible": result.release_eligible,
        "external_effects": result.external_effects,
    }


def hk_case_admission_request_from_document(document: object) -> HKCaseAdmissionRequest:
    """Strictly decode one request and reject unknown or malformed fields."""
    root = _object(document)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "rule_id",
            "assertion",
            "correction",
            "catalogue",
            "evaluation_packet",
            "sealed_package",
            "reproducibility",
            "side_effects",
            "workflow_identity",
        },
    )
    _constant(root["schema_id"], "asklegal.hk-cases.admission-request")
    _constant(root["schema_version"], HK_CASE_ADMISSION_CONTRACT_VERSION)
    _constant(root["rule_id"], HK_CASE_ADMISSION_RULE_ID)
    return HKCaseAdmissionRequest(
        assertion=_enum(root["assertion"], HKCaseAdmissionAssertion),
        correction=_optional_object(root["correction"], _correction),
        catalogue=_optional_object(root["catalogue"], _catalogue),
        evaluation_packet=_optional_object(root["evaluation_packet"], _packet),
        sealed_package=_optional_object(root["sealed_package"], _sealed),
        reproducibility=_optional_object(root["reproducibility"], _reproducibility),
        side_effects=_optional_object(root["side_effects"], _side_effects),
        workflow_identity=_optional_object(root["workflow_identity"], _workflow),
    )


def _correction(value: JsonValue) -> HKCaseCorrectionFacts:
    root = _object(value)
    _exact_keys(
        root,
        {
            "kind",
            "prior_official_version_id",
            "current_official_version_id",
            "prior_ledger_fingerprint",
            "current_ledger_fingerprint",
            "prior_result_id",
            "current_result_id",
            "prior_admission_id",
            "current_admission_id",
            "prior_propositions",
            "current_propositions",
            "prior_records",
            "current_records",
            "affected_prior_proposition_ids",
            "unaffected_reused_proposition_ids",
            "introduced_proposition_ids",
            "deselected_prior_record_ids",
            "lineages",
            "component_changes",
            "processing_history_appended",
            "ledger_history_appended",
            "impact_declaration_fingerprint",
            "prior_ledger_mutated",
            "prior_admission_mutated",
        },
    )
    return HKCaseCorrectionFacts(
        kind=_enum(root["kind"], HKCaseCorrectionKind),
        prior_official_version_id=_identity(root["prior_official_version_id"]),
        current_official_version_id=_identity(root["current_official_version_id"]),
        prior_ledger_fingerprint=_fingerprint(root["prior_ledger_fingerprint"]),
        current_ledger_fingerprint=_fingerprint(root["current_ledger_fingerprint"]),
        prior_result_id=_identity(root["prior_result_id"]),
        current_result_id=_identity(root["current_result_id"]),
        prior_admission_id=_identity(root["prior_admission_id"]),
        current_admission_id=_identity(root["current_admission_id"]),
        prior_propositions=tuple(
            _correction_proposition(item) for item in _array(root["prior_propositions"])
        ),
        current_propositions=tuple(
            _correction_proposition(item) for item in _array(root["current_propositions"])
        ),
        prior_records=tuple(_correction_record(item) for item in _array(root["prior_records"])),
        current_records=tuple(_correction_record(item) for item in _array(root["current_records"])),
        affected_prior_proposition_ids=_identities(root["affected_prior_proposition_ids"]),
        unaffected_reused_proposition_ids=_identities(root["unaffected_reused_proposition_ids"]),
        introduced_proposition_ids=_identities(root["introduced_proposition_ids"]),
        deselected_prior_record_ids=_identities(root["deselected_prior_record_ids"]),
        lineages=tuple(_lineage(item) for item in _array(root["lineages"])),
        component_changes=tuple(
            _component_change(item) for item in _array(root["component_changes"])
        ),
        processing_history_appended=_boolean(root["processing_history_appended"]),
        ledger_history_appended=_boolean(root["ledger_history_appended"]),
        impact_declaration_fingerprint=_optional_fingerprint(
            root["impact_declaration_fingerprint"]
        ),
        prior_ledger_mutated=_boolean(root["prior_ledger_mutated"]),
        prior_admission_mutated=_boolean(root["prior_admission_mutated"]),
    )


def _correction_proposition(value: JsonValue) -> HKCaseCorrectionProposition:
    root = _object(value)
    _exact_keys(
        root,
        {
            "proposition_id",
            "text_fingerprint",
            "support_fingerprint",
            "attribution_fingerprint",
            "payload_fingerprint",
        },
    )
    return HKCaseCorrectionProposition(
        _identity(root["proposition_id"]),
        _fingerprint(root["text_fingerprint"]),
        _fingerprint(root["support_fingerprint"]),
        _fingerprint(root["attribution_fingerprint"]),
        _fingerprint(root["payload_fingerprint"]),
    )


def _correction_record(value: JsonValue) -> HKCaseCorrectionRecord:
    root = _object(value)
    _exact_keys(
        root,
        {
            "record_id",
            "proposition_ids",
            "payload_fingerprint",
            "embedding_fingerprint",
            "selected",
        },
    )
    return HKCaseCorrectionRecord(
        _identity(root["record_id"]),
        _identities(root["proposition_ids"]),
        _fingerprint(root["payload_fingerprint"]),
        _fingerprint(root["embedding_fingerprint"]),
        _boolean(root["selected"]),
    )


def _lineage(value: JsonValue) -> HKCaseCorrectionLineage:
    root = _object(value)
    _exact_keys(root, {"relation", "predecessor_record_ids", "successor_record_ids"})
    return HKCaseCorrectionLineage(
        _enum(root["relation"], HKCaseLineageRelation),
        _identities(root["predecessor_record_ids"]),
        _identities(root["successor_record_ids"]),
    )


def _component_change(value: JsonValue) -> HKCaseResultAffectingChange:
    root = _object(value)
    _exact_keys(root, {"component_role", "prior_fingerprint", "current_fingerprint"})
    return HKCaseResultAffectingChange(
        _code(root["component_role"]),
        _fingerprint(root["prior_fingerprint"]),
        _fingerprint(root["current_fingerprint"]),
    )


def _catalogue(value: JsonValue) -> HKCaseCatalogueFacts:
    root = _object(value)
    _exact_keys(
        root,
        {"completeness_method", "case_ids", "coverage_cell_ids", "pair_memberships"},
    )
    return HKCaseCatalogueFacts(
        _enum(root["completeness_method"], HKCaseCatalogueCompletenessMethod),
        _strings(root["case_ids"]),
        _strings(root["coverage_cell_ids"]),
        tuple(_pair_membership(item) for item in _array(root["pair_memberships"])),
    )


def _pair_membership(value: JsonValue) -> HKCasePairMembership:
    root = _object(value)
    _exact_keys(root, {"pair_id", "case_id", "role"})
    role = _string(root["role"])
    if role not in {"POSITIVE", "NEAR_MISS"}:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)
    return HKCasePairMembership(
        _string(root["pair_id"]),
        _string(root["case_id"]),
        role,
    )


def _packet(value: JsonValue) -> HKCaseEvaluationPacketFacts:
    root = _object(value)
    _exact_keys(
        root,
        {
            "admitted_evidence_refs",
            "packet_evidence_refs",
            "admitted_task_contract_fingerprint",
            "packet_task_contract_fingerprint",
            "packet_metadata_fields",
        },
    )
    return HKCaseEvaluationPacketFacts(
        _identities(root["admitted_evidence_refs"]),
        _identities(root["packet_evidence_refs"]),
        _fingerprint(root["admitted_task_contract_fingerprint"]),
        _fingerprint(root["packet_task_contract_fingerprint"]),
        _strings(root["packet_metadata_fields"]),
    )


def _external_artifact(value: JsonValue) -> HKCaseExternalEvaluationArtifact:
    root = _object(value)
    _exact_keys(root, {"role", "object_ref", "content_fingerprint", "byte_size"})
    return HKCaseExternalEvaluationArtifact(
        _code(root["role"]),
        _identity(root["object_ref"]),
        _fingerprint(root["content_fingerprint"]),
        _positive_integer(root["byte_size"]),
    )


def _sealed(value: JsonValue) -> HKCaseSealedPackageFacts:
    root = _object(value)
    _exact_keys(
        root,
        {
            "registered_artifacts",
            "observed_artifacts",
            "registered_manifest_fingerprint",
            "observed_manifest_fingerprint",
        },
    )
    return HKCaseSealedPackageFacts(
        tuple(_external_artifact(item) for item in _array(root["registered_artifacts"])),
        tuple(_external_artifact(item) for item in _array(root["observed_artifacts"])),
        _fingerprint(root["registered_manifest_fingerprint"]),
        _fingerprint(root["observed_manifest_fingerprint"]),
    )


def _deterministic_artifact(value: JsonValue) -> HKCaseDeterministicArtifact:
    root = _object(value)
    _exact_keys(root, {"path", "role", "byte_size", "content_fingerprint"})
    return HKCaseDeterministicArtifact(
        _string(root["path"]),
        _code(root["role"]),
        _positive_integer(root["byte_size"]),
        _fingerprint(root["content_fingerprint"]),
    )


def _run(value: JsonValue) -> HKCaseDeterministicRun:
    root = _object(value)
    _exact_keys(root, {"input_fingerprint", "build_fingerprint", "artifacts"})
    return HKCaseDeterministicRun(
        _fingerprint(root["input_fingerprint"]),
        _fingerprint(root["build_fingerprint"]),
        tuple(_deterministic_artifact(item) for item in _array(root["artifacts"])),
    )


def _reproducibility(value: JsonValue) -> HKCaseReproducibilityFacts:
    root = _object(value)
    _exact_keys(root, {"first_run", "second_run"})
    return HKCaseReproducibilityFacts(_run(root["first_run"]), _run(root["second_run"]))


def _side_effects(value: JsonValue) -> HKCaseSideEffectFacts:
    root = _object(value)
    _exact_keys(root, {"attempted_capabilities", "observed_mutation_receipt_count"})
    return HKCaseSideEffectFacts(
        tuple(
            _enum(item, HKCaseForbiddenCapability)
            for item in _array(root["attempted_capabilities"])
        ),
        _nonnegative_integer(root["observed_mutation_receipt_count"]),
    )


def _workflow_component(value: JsonValue) -> HKCaseWorkflowComponent:
    root = _object(value)
    _exact_keys(
        root,
        {"component_role", "admitted_fingerprint", "proposed_fingerprint"},
    )
    return HKCaseWorkflowComponent(
        _code(root["component_role"]),
        _fingerprint(root["admitted_fingerprint"]),
        _fingerprint(root["proposed_fingerprint"]),
    )


def _workflow(value: JsonValue) -> HKCaseWorkflowIdentityFacts:
    root = _object(value)
    _exact_keys(
        root,
        {"components", "evaluation_run_eligible", "impact_declaration_fingerprint"},
    )
    return HKCaseWorkflowIdentityFacts(
        tuple(_workflow_component(item) for item in _array(root["components"])),
        _boolean(root["evaluation_run_eligible"]),
        _optional_fingerprint(root["impact_declaration_fingerprint"]),
    )


def _optional_object[T](value: JsonValue, decoder: Callable[[JsonValue], T]) -> T | None:
    if value is None:
        return None
    return decoder(value)


def _object(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    if not isinstance(checked, dict):
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)
    return checked


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)
    return value


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)


def _string(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)
    return value


def _strings(value: JsonValue) -> tuple[str, ...]:
    return tuple(_string(item) for item in _array(value))


def _identity(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_IDENTITY_PATTERN, result) is None:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.IDENTITY)
    return result


def _identities(value: JsonValue) -> tuple[str, ...]:
    return tuple(_identity(item) for item in _array(value))


def _code(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_CODE_PATTERN, result) is None:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)
    return result


def _fingerprint(value: JsonValue) -> str:
    result = _string(value)
    if fullmatch(_FINGERPRINT_PATTERN, result) is None:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.FINGERPRINT)
    return result


def _optional_fingerprint(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _fingerprint(value)


def _boolean(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)
    return value


def _positive_integer(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)
    return value


def _nonnegative_integer(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)
    return value


def _constant(value: JsonValue, expected: str) -> None:
    if value != expected:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT)


def _enum[T: StrEnum](value: JsonValue, enum_type: type[T]) -> T:
    raw = _string(value)
    try:
        return enum_type(raw)
    except ValueError:
        raise HKCaseAdmissionError(HKCaseAdmissionErrorCode.CONTRACT) from None


def _duplicates(values: tuple[object, ...]) -> bool:
    return len(set(values)) != len(values)
