"""Executable ADR 0074/0075 HKEX package-integrity conformance boundary."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from re import fullmatch

from asklegal_contracts import ContractViolation, fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

HKEX_PACKAGE_INTEGRITY_RULE_ID = "HKREG-PACKAGE-INTEGRITY-001"
HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION = "1.0.0"
HKEX_PACKAGE_INTEGRITY_CASE_COUNT = 38

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_CASE_PATTERN = r"HKREG-DET-PKG-(0[0-2][0-9]|03[0-8])"
_MIN_CONTRACT_BINDINGS = 2
_PAIR_MEMBER_COUNT = 2
_MIN_REPRODUCIBILITY_RUNS = 2
_EXPECTED_PAIR_MEMBERSHIPS = {
    "HKREG-DET-PKG-011": ("HKREG-PAIR-050", "POSITIVE"),
    "HKREG-DET-PKG-012": ("HKREG-PAIR-050", "NEAR_MISS"),
    "HKREG-DET-PKG-013": ("HKREG-PAIR-051", "POSITIVE"),
    "HKREG-DET-PKG-014": ("HKREG-PAIR-051", "NEAR_MISS"),
    "HKREG-DET-PKG-017": ("HKREG-PAIR-052", "POSITIVE"),
    "HKREG-DET-PKG-018": ("HKREG-PAIR-052", "NEAR_MISS"),
    "HKREG-DET-PKG-019": ("HKREG-PAIR-053", "POSITIVE"),
    "HKREG-DET-PKG-020": ("HKREG-PAIR-053", "NEAR_MISS"),
    "HKREG-DET-PKG-025": ("HKREG-PAIR-054", "POSITIVE"),
    "HKREG-DET-PKG-026": ("HKREG-PAIR-054", "NEAR_MISS"),
    "HKREG-DET-PKG-029": ("HKREG-PAIR-055", "POSITIVE"),
    "HKREG-DET-PKG-030": ("HKREG-PAIR-055", "NEAR_MISS"),
    "HKREG-DET-PKG-031": ("HKREG-PAIR-056", "POSITIVE"),
    "HKREG-DET-PKG-032": ("HKREG-PAIR-056", "NEAR_MISS"),
}


class HKEXPackageIntegrityErrorCode(StrEnum):
    """Closed malformed fixture-envelope failures."""

    CONTRACT = "HKREG_PACKAGE_INTEGRITY_CONTRACT_INVALID"
    IDENTITY = "HKREG_PACKAGE_INTEGRITY_IDENTITY_INVALID"
    FINGERPRINT = "HKREG_PACKAGE_INTEGRITY_FINGERPRINT_INVALID"


class HKEXPackageIntegrityError(ValueError):
    """One fail-closed fixture-envelope rejection."""

    code: HKEXPackageIntegrityErrorCode

    def __init__(self, code: HKEXPackageIntegrityErrorCode) -> None:
        """Create one stable fixture-envelope failure."""
        self.code = code
        super().__init__(code.value)


class HKEXPackageIntegrityOutcome(StrEnum):
    """Observed package condition, independent of expected conformance truth."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class HKEXPackageIntegrityReason(StrEnum):
    """Closed package-integrity result branches."""

    PACKAGE_VALID = "PACKAGE_VALID"
    CLOSED_SCHEMA_VIOLATION = "CLOSED_SCHEMA_VIOLATION"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    UNDECLARED_FILE_ACCESS = "UNDECLARED_FILE_ACCESS"
    REQUIRED_FILE_ABSENT = "REQUIRED_FILE_ABSENT"
    PATH_CONTAINMENT_INVALID = "PATH_CONTAINMENT_INVALID"
    SYMLINK_FORBIDDEN = "SYMLINK_FORBIDDEN"
    REMOTE_RESOURCE_FORBIDDEN = "REMOTE_RESOURCE_FORBIDDEN"
    DYNAMIC_DISCOVERY_FORBIDDEN = "DYNAMIC_DISCOVERY_FORBIDDEN"
    INPUT_AVAILABLE_ADMITTED = "INPUT_AVAILABLE_ADMITTED"
    INPUT_AVAILABLE_INVALID = "INPUT_AVAILABLE_INVALID"
    DELIBERATE_ABSENCE_ADMITTED = "DELIBERATE_ABSENCE_ADMITTED"
    UNREADABLE_CONDITION_ADMITTED = "UNREADABLE_CONDITION_ADMITTED"
    AVAILABLE_FACT_CONDITION_ADMITTED = "AVAILABLE_FACT_CONDITION_ADMITTED"
    EXACT_ARTIFACT_MATCHED = "EXACT_ARTIFACT_MATCHED"
    EXPECTED_EXACT_INVALID = "EXPECTED_EXACT_INVALID"
    ZERO_OUTPUT_PROVED = "ZERO_OUTPUT_PROVED"
    ZERO_OUTPUT_PROOF_INVALID = "ZERO_OUTPUT_PROOF_INVALID"
    NOT_APPLICABLE_PROVED = "NOT_APPLICABLE_PROVED"
    NOT_APPLICABLE_INVALID = "NOT_APPLICABLE_INVALID"
    MATRIX_COMPLETE = "MATRIX_COMPLETE"
    MATRIX_INCOMPLETE = "MATRIX_INCOMPLETE"
    PAIR_COMPLETE = "PAIR_COMPLETE"
    PAIR_INCOMPLETE = "PAIR_INCOMPLETE"
    PROPOSAL_PACKET_CLEAN = "PROPOSAL_PACKET_CLEAN"
    PROPOSAL_TRUTH_LEAKAGE = "PROPOSAL_TRUTH_LEAKAGE"
    FINGERPRINT_OR_TRUTH_MUTATION = "FINGERPRINT_OR_TRUTH_MUTATION"
    REPRODUCIBLE = "REPRODUCIBLE"
    REPRODUCIBILITY_FAILURE = "REPRODUCIBILITY_FAILURE"
    HOSTILE_TEXT_INERT = "HOSTILE_TEXT_INERT"
    HOSTILE_INPUT_CONTROL_BREACH = "HOSTILE_INPUT_CONTROL_BREACH"
    FORBIDDEN_CAPABILITY_ATTEMPT = "FORBIDDEN_CAPABILITY_ATTEMPT"
    PACKAGE_VALIDITY_ONLY = "PACKAGE_VALIDITY_ONLY"
    BUILD_COMPATIBILITY_ONLY = "BUILD_COMPATIBILITY_ONLY"
    AUTHORITY_BROADENING = "AUTHORITY_BROADENING"
    ATTESTATION_MISMATCH = "ATTESTATION_MISMATCH"
    MEDIA_OR_PERMISSION_INVALID = "MEDIA_OR_PERMISSION_INVALID"


class HKEXPackageAssertionScope(StrEnum):
    """Orthogonal fact dimension selected by one permanent case."""

    COMPLETE_PACKAGE = "COMPLETE_PACKAGE"
    CLOSED_SCHEMA = "CLOSED_SCHEMA"
    ARTIFACT_HASH = "ARTIFACT_HASH"
    DECLARED_ACCESS = "DECLARED_ACCESS"
    REQUIRED_FILE = "REQUIRED_FILE"
    ABSOLUTE_PATH = "ABSOLUTE_PATH"
    NORMALIZED_PATH = "NORMALIZED_PATH"
    SYMLINK = "SYMLINK"
    REMOTE_RESOURCE = "REMOTE_RESOURCE"
    EXPLICIT_INVENTORY = "EXPLICIT_INVENTORY"
    AVAILABLE_INPUT = "AVAILABLE_INPUT"
    DELIBERATE_ABSENCE = "DELIBERATE_ABSENCE"
    UNREADABLE_INPUT = "UNREADABLE_INPUT"
    AVAILABLE_FACT_CONDITION = "AVAILABLE_FACT_CONDITION"
    EXACT_OUTPUT = "EXACT_OUTPUT"
    ZERO_OUTPUT = "ZERO_OUTPUT"
    NOT_APPLICABLE_OUTPUT = "NOT_APPLICABLE_OUTPUT"
    MATRIX_COMPLETENESS = "MATRIX_COMPLETENESS"
    PAIR_COMPLETENESS = "PAIR_COMPLETENESS"
    PROPOSAL_ISOLATION = "PROPOSAL_ISOLATION"
    IMMUTABLE_FINGERPRINT = "IMMUTABLE_FINGERPRINT"
    REPRODUCIBILITY = "REPRODUCIBILITY"
    HOSTILE_SOURCE_TEXT = "HOSTILE_SOURCE_TEXT"
    LOCAL_CAPABILITY_DENIAL = "LOCAL_CAPABILITY_DENIAL"
    EXTERNAL_CAPABILITY_DENIAL = "EXTERNAL_CAPABILITY_DENIAL"
    AUTHORITY_CONTAINMENT = "AUTHORITY_CONTAINMENT"
    ATTESTATION_COMPATIBILITY = "ATTESTATION_COMPATIBILITY"
    MEDIA_AND_PERMISSION = "MEDIA_AND_PERMISSION"


class HKEXInputState(StrEnum):
    """Exact ADR 0074 declared input state."""

    AVAILABLE = "AVAILABLE"
    INTENTIONALLY_ABSENT = "INTENTIONALLY_ABSENT"
    UNREADABLE = "UNREADABLE"


class HKEXInputFactCondition(StrEnum):
    """Facts carried by available evidence rather than invented input states."""

    ORDINARY = "ORDINARY"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    WRONG_BOARD = "WRONG_BOARD"
    DIFFERENT_VERSION = "DIFFERENT_VERSION"


class HKEXExpectedArtifactState(StrEnum):
    """Exact ADR 0074 expected-artifact state."""

    EXACT = "EXACT"
    NONE = "NONE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class HKEXVirtualNodeType(StrEnum):
    """Closed synthetic package node classes."""

    REGULAR_FILE = "REGULAR_FILE"
    SYMLINK = "SYMLINK"


class HKEXVirtualContentClass(StrEnum):
    """Whether exact bytes are ordinary or intentionally unparsable."""

    NORMAL = "NORMAL"
    CORRUPT_OR_UNSUPPORTED = "CORRUPT_OR_UNSUPPORTED"


class HKEXDiscoveryMethod(StrEnum):
    """Closed inventory construction methods."""

    EXPLICIT_INVENTORY = "EXPLICIT_INVENTORY"
    GLOB = "GLOB"
    RANGE = "RANGE"
    FILENAME_CONVENTION = "FILENAME_CONVENTION"
    DIRECTORY_SCAN = "DIRECTORY_SCAN"


class HKEXFingerprintScope(StrEnum):
    """Whether a package projection correctly excludes its fingerprint field."""

    EXCLUDES_SELF = "EXCLUDES_SELF"
    INCLUDES_SELF = "INCLUDES_SELF"


class HKEXForbiddenCapability(StrEnum):
    """Capabilities forbidden inside a deterministic conformance run."""

    SOURCE = "SOURCE"
    GENERATIVE_MODEL = "GENERATIVE_MODEL"
    EMBEDDING = "EMBEDDING"
    NETWORK = "NETWORK"
    CREDENTIAL = "CREDENTIAL"
    AZURE = "AZURE"
    PINECONE = "PINECONE"
    BACKUP = "BACKUP"
    ROUTING = "ROUTING"
    PROMOTION = "PROMOTION"
    PRODUCTION_STORE = "PRODUCTION_STORE"
    UNDECLARED_FILE = "UNDECLARED_FILE"
    LIVE_STATE = "LIVE_STATE"


@dataclass(frozen=True, slots=True)
class HKEXContractBinding:
    """One exact versioned contract used by a case."""

    contract_id: str
    version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXPairMembership:
    """One case's exact positive or near-miss pair role."""

    pair_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKEXDeclaredArtifact:
    """One explicit virtual-package manifest entry."""

    path: str
    role: str
    media_type: str
    fingerprint: str
    required: bool


@dataclass(frozen=True, slots=True)
class HKEXVirtualArtifact:
    """One exact synthetic file node supplied to the isolated runner."""

    path: str
    media_type: str
    content_base64: str
    node_type: HKEXVirtualNodeType
    content_class: HKEXVirtualContentClass
    readable: bool
    schema_valid: bool
    canonical_bytes: bool

    def bytes(self) -> bytes:
        """Decode the exact embedded bytes without repair."""
        try:
            return b64decode(self.content_base64, validate=True)
        except (Base64Error, ValueError) as error:
            raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT) from error


@dataclass(frozen=True, slots=True)
class HKEXInputSlot:
    """One declared evidence input and its exact ADR 0074 state."""

    slot_id: str
    state: HKEXInputState
    path: str | None
    fact_condition: HKEXInputFactCondition


@dataclass(frozen=True, slots=True)
class HKEXExpectedArtifact:
    """One complete expected-artifact inventory entry."""

    role: str
    state: HKEXExpectedArtifactState
    path: str | None
    expected_fingerprint: str | None
    zero_count: int | None
    checkpoint_applicable: bool
    matrix_proves_nonapplicable: bool
    implementation_completed: bool


@dataclass(frozen=True, slots=True)
class HKEXPrimaryCoverage:
    """One required cell's direct primary executable case."""

    cell_id: str
    case_id: str


@dataclass(frozen=True, slots=True)
class HKEXPairMember:
    """One member of a high-risk positive/near-miss pair."""

    case_id: str
    role: str


@dataclass(frozen=True, slots=True)
class HKEXPairDefinition:
    """One exact high-risk pair definition."""

    pair_id: str
    members: tuple[HKEXPairMember, ...]


@dataclass(frozen=True, slots=True)
class HKEXCoverageMatrixFacts:
    """Complete matrix facts used by the isolated checkpoint runner."""

    required_cell_ids: tuple[str, ...]
    executable_case_ids: tuple[str, ...]
    primary_coverage: tuple[HKEXPrimaryCoverage, ...]
    required_rule_ids: tuple[str, ...]
    covered_rule_ids: tuple[str, ...]
    required_result_branches: tuple[str, ...]
    covered_result_branches: tuple[str, ...]
    required_pair_ids: tuple[str, ...]
    pairs: tuple[HKEXPairDefinition, ...]


@dataclass(frozen=True, slots=True)
class HKEXAttestationFacts:
    """Current and attested build-compatibility bindings."""

    complete: bool
    compatibility_only: bool
    current_bindings: tuple[tuple[str, str], ...]
    attested_bindings: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class HKEXPackageIntegrityFacts:
    """All orthogonal facts observed by the package-integrity runner."""

    closed_schema_violations: tuple[str, ...]
    declared_artifacts: tuple[HKEXDeclaredArtifact, ...]
    virtual_artifacts: tuple[HKEXVirtualArtifact, ...]
    runner_access_paths: tuple[str, ...]
    discovery_methods: tuple[HKEXDiscoveryMethod, ...]
    input_slots: tuple[HKEXInputSlot, ...]
    expected_artifacts: tuple[HKEXExpectedArtifact, ...]
    matrix: HKEXCoverageMatrixFacts
    proposal_packet_fields: tuple[str, ...]
    fingerprint_scope: HKEXFingerprintScope
    expected_truth_mutated: bool
    run_output_fingerprints: tuple[tuple[str, ...], ...]
    source_instruction_present: bool
    source_instruction_effects: tuple[str, ...]
    attempted_capabilities: tuple[HKEXForbiddenCapability, ...]
    external_state_mutated: bool
    authority_claims: tuple[str, ...]
    attestation: HKEXAttestationFacts


@dataclass(frozen=True, slots=True)
class HKEXPackageIntegrityCase:
    """One strict common envelope and its orthogonal virtual-package facts."""

    case_id: str
    primary_coverage_cell_id: str
    pair_membership: HKEXPairMembership | None
    assertion_scope: HKEXPackageAssertionScope
    package_fingerprint: str
    title: str
    purpose: str
    expected_outcome: HKEXPackageIntegrityOutcome
    expected_reason: HKEXPackageIntegrityReason
    facts: HKEXPackageIntegrityFacts


@dataclass(frozen=True, slots=True)
class HKEXPackageIntegrityDecision:
    """Observed fact-derived package result; expected truth is not consulted."""

    outcome: HKEXPackageIntegrityOutcome
    reason: HKEXPackageIntegrityReason
    package_valid: bool
    external_state_mutated: bool
    authority_grants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKEXPackageIntegrityReport:
    """One deterministic expected-versus-observed conformance report."""

    case_id: str
    assertion_scope: HKEXPackageAssertionScope
    observed_outcome: HKEXPackageIntegrityOutcome
    observed_reason: HKEXPackageIntegrityReason
    expected_outcome: HKEXPackageIntegrityOutcome
    expected_reason: HKEXPackageIntegrityReason
    conformance_status: str
    package_valid: bool
    external_state_mutated: bool
    authority_grants: tuple[str, ...]

    def document(self) -> dict[str, object]:
        """Return the closed deterministic report document."""
        return {
            "schema_id": "asklegal.hk-regulatory.package-integrity-report",
            "schema_version": HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION,
            "rule_id": HKEX_PACKAGE_INTEGRITY_RULE_ID,
            "case_id": self.case_id,
            "assertion_scope": self.assertion_scope.value,
            "observed_outcome": self.observed_outcome.value,
            "observed_reason": self.observed_reason.value,
            "expected_outcome": self.expected_outcome.value,
            "expected_reason": self.expected_reason.value,
            "conformance_status": self.conformance_status,
            "package_valid": self.package_valid,
            "external_state_mutated": self.external_state_mutated,
            "authority_grants": list(self.authority_grants),
            "source_authorized": False,
            "provider_authorized": False,
            "release_authorized": False,
            "serving_authorized": False,
            "deployment_authorized": False,
            "external_effects": "NONE",
        }


def hkex_package_integrity_case_from_document(document: object) -> HKEXPackageIntegrityCase:
    """Strictly decode and fingerprint one ADR 0074 common case envelope."""
    root = _json_object(document)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "package_contract_version",
            "case_id",
            "suite_layer",
            "primary_checkpoint",
            "frozen",
            "synthetic_evidence_class",
            "contract_bindings",
            "synthetic_cutoff",
            "scope_id",
            "prior_state",
            "primary_coverage_cell_ids",
            "secondary_coverage_cell_ids",
            "pair_membership",
            "declared_input_inventory",
            "declared_reference_inventory",
            "declared_expected_inventory",
            "required_result_dimensions",
            "assertion_scope",
            "package_fingerprint",
            "title",
            "purpose",
            "expected_outcome",
            "expected_reason",
            "facts",
            "case_fingerprint",
        },
    )
    _constant(root["schema_id"], "asklegal.hk-regulatory.package-integrity-case")
    _constant(root["schema_version"], HKEX_PACKAGE_INTEGRITY_CONTRACT_VERSION)
    _constant(root["package_contract_version"], "1.0.0")
    case_id = _pattern_text(root["case_id"], _CASE_PATTERN)
    suffix = case_id.rsplit("-", maxsplit=1)[1]
    _constant(root["suite_layer"], "DECISION_TO_ARTIFACT")
    _constant(root["primary_checkpoint"], "PACKAGE_INTEGRITY")
    _true(root["frozen"])
    _constant(root["synthetic_evidence_class"], "SYNTHETIC_NO_REAL_AUTHORITY")
    bindings = _contract_bindings(root["contract_bindings"])
    if len(bindings) < _MIN_CONTRACT_BINDINGS:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    _constant(root["synthetic_cutoff"], "2026-08-24T00:00:00Z")
    _constant(root["scope_id"], "HKEX_CROSS_BOARD")
    _constant(root["prior_state"], "NO_LIVE_STATE")
    primary_cells = _json_strings(root["primary_coverage_cell_ids"])
    if primary_cells != (f"HKREG-COV-DPKG-{suffix}",):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.IDENTITY)
    secondary_cells = _json_strings(root["secondary_coverage_cell_ids"])
    if secondary_cells != tuple(sorted(set(secondary_cells))):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.IDENTITY)
    pair_membership = _case_pair_membership(root["pair_membership"], case_id)
    declared_inputs = _json_strings(root["declared_input_inventory"])
    declared_references = _json_strings(root["declared_reference_inventory"])
    declared_expected = _json_strings(root["declared_expected_inventory"])
    dimensions = _json_strings(root["required_result_dimensions"])
    if dimensions != ("AUTHORITY", "FORBIDDEN_EFFECTS", "PACKAGE_INTEGRITY"):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    scope = _json_enum(root["assertion_scope"], HKEXPackageAssertionScope)
    package_fingerprint = _json_fingerprint(root["package_fingerprint"])
    title = _json_text(root["title"])
    purpose = _json_text(root["purpose"])
    expected_outcome = _json_enum(root["expected_outcome"], HKEXPackageIntegrityOutcome)
    expected_reason = _json_enum(root["expected_reason"], HKEXPackageIntegrityReason)
    facts = _facts(root["facts"])
    if declared_inputs != tuple(slot.slot_id for slot in facts.input_slots):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    if declared_references != tuple(binding.contract_id for binding in bindings):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    if declared_expected != tuple(item.role for item in facts.expected_artifacts):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    case_fingerprint = _json_fingerprint(root["case_fingerprint"])
    projection = dict(root)
    projection.pop("case_fingerprint")
    if fingerprint(checked_json_value(projection)) != case_fingerprint:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.FINGERPRINT)
    return HKEXPackageIntegrityCase(
        case_id,
        primary_cells[0],
        pair_membership,
        scope,
        package_fingerprint,
        title,
        purpose,
        expected_outcome,
        expected_reason,
        facts,
    )


def evaluate_hkex_package_integrity(
    case: HKEXPackageIntegrityCase,
) -> HKEXPackageIntegrityDecision:
    """Evaluate orthogonal package facts without switching on the case ID."""
    if type(case) is not HKEXPackageIntegrityCase:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    facts = case.facts
    rejection = _preflight_rejection(facts)
    if rejection is None:
        rejection = _input_rejection(facts)
    if rejection is None:
        rejection = _expected_artifact_rejection(facts)
    if rejection is None:
        rejection = _matrix_rejection(facts)
    if rejection is None:
        rejection = _proposal_and_execution_rejection(facts)
    if rejection is None:
        rejection = _authority_and_attestation_rejection(case.assertion_scope, facts)
    if rejection is not None:
        return HKEXPackageIntegrityDecision(
            outcome=HKEXPackageIntegrityOutcome.REJECTED,
            reason=rejection,
            package_valid=False,
            external_state_mutated=facts.external_state_mutated,
            authority_grants=(),
        )
    reason = _accepted_reason(case.assertion_scope)
    grants: tuple[str, ...] = ()
    if reason is HKEXPackageIntegrityReason.PACKAGE_VALIDITY_ONLY:
        grants = ("PACKAGE_VALIDITY",)
    elif reason is HKEXPackageIntegrityReason.BUILD_COMPATIBILITY_ONLY:
        grants = ("BUILD_COMPATIBILITY",)
    return HKEXPackageIntegrityDecision(
        outcome=HKEXPackageIntegrityOutcome.ACCEPTED,
        reason=reason,
        package_valid=True,
        external_state_mutated=False,
        authority_grants=grants,
    )


def run_hkex_package_integrity_case(
    case: HKEXPackageIntegrityCase,
) -> HKEXPackageIntegrityReport:
    """Compare observed facts to separately frozen expected truth."""
    decision = evaluate_hkex_package_integrity(case)
    status = (
        "PASS"
        if decision.outcome is case.expected_outcome and decision.reason is case.expected_reason
        else "FAIL"
    )
    return HKEXPackageIntegrityReport(
        case.case_id,
        case.assertion_scope,
        decision.outcome,
        decision.reason,
        case.expected_outcome,
        case.expected_reason,
        status,
        decision.package_valid,
        decision.external_state_mutated,
        decision.authority_grants,
    )


def _preflight_rejection(
    facts: HKEXPackageIntegrityFacts,
) -> HKEXPackageIntegrityReason | None:
    for check in (_path_rejection, _declaration_rejection, _artifact_bytes_rejection):
        result = check(facts)
        if result is not None:
            return result
    return None


def _path_rejection(
    facts: HKEXPackageIntegrityFacts,
) -> HKEXPackageIntegrityReason | None:
    paths = (
        *(item.path for item in facts.declared_artifacts),
        *(item.path for item in facts.virtual_artifacts),
        *facts.runner_access_paths,
    )
    if any("://" in path for path in paths):
        return HKEXPackageIntegrityReason.REMOTE_RESOURCE_FORBIDDEN
    if any(not _safe_relative_path(path) for path in paths):
        return HKEXPackageIntegrityReason.PATH_CONTAINMENT_INVALID
    if any(item.node_type is HKEXVirtualNodeType.SYMLINK for item in facts.virtual_artifacts):
        return HKEXPackageIntegrityReason.SYMLINK_FORBIDDEN
    if any(
        method is not HKEXDiscoveryMethod.EXPLICIT_INVENTORY for method in facts.discovery_methods
    ):
        return HKEXPackageIntegrityReason.DYNAMIC_DISCOVERY_FORBIDDEN
    return None


def _declaration_rejection(
    facts: HKEXPackageIntegrityFacts,
) -> HKEXPackageIntegrityReason | None:
    if facts.closed_schema_violations:
        return HKEXPackageIntegrityReason.CLOSED_SCHEMA_VIOLATION
    declarations = {item.path: item for item in facts.declared_artifacts}
    virtual_paths = {item.path for item in facts.virtual_artifacts}
    if len(declarations) != len(facts.declared_artifacts) or len(virtual_paths) != len(
        facts.virtual_artifacts
    ):
        return HKEXPackageIntegrityReason.CLOSED_SCHEMA_VIOLATION
    if any(path not in declarations for path in facts.runner_access_paths):
        return HKEXPackageIntegrityReason.UNDECLARED_FILE_ACCESS
    intentionally_absent = {
        slot.path for slot in facts.input_slots if slot.state is HKEXInputState.INTENTIONALLY_ABSENT
    }
    if any(
        declaration.required
        and declaration.path not in virtual_paths
        and declaration.path not in intentionally_absent
        for declaration in facts.declared_artifacts
    ):
        return HKEXPackageIntegrityReason.REQUIRED_FILE_ABSENT
    return None


def _artifact_bytes_rejection(
    facts: HKEXPackageIntegrityFacts,
) -> HKEXPackageIntegrityReason | None:
    declarations = {item.path: item for item in facts.declared_artifacts}
    for artifact in facts.virtual_artifacts:
        declaration = declarations.get(artifact.path)
        if declaration is None:
            continue
        if declaration.fingerprint != _raw_fingerprint(artifact.bytes()):
            return HKEXPackageIntegrityReason.ARTIFACT_HASH_MISMATCH
        if declaration.media_type != artifact.media_type or not artifact.readable:
            return HKEXPackageIntegrityReason.MEDIA_OR_PERMISSION_INVALID
    return None


def _input_rejection(
    facts: HKEXPackageIntegrityFacts,
) -> HKEXPackageIntegrityReason | None:
    declarations = {item.path: item for item in facts.declared_artifacts}
    virtual = {item.path: item for item in facts.virtual_artifacts}
    for slot in facts.input_slots:
        if slot.state is HKEXInputState.AVAILABLE:
            if slot.path is None or slot.path not in declarations or slot.path not in virtual:
                return HKEXPackageIntegrityReason.INPUT_AVAILABLE_INVALID
            artifact = virtual[slot.path]
            if artifact.content_class is not HKEXVirtualContentClass.NORMAL:
                return HKEXPackageIntegrityReason.INPUT_AVAILABLE_INVALID
        elif slot.state is HKEXInputState.INTENTIONALLY_ABSENT:
            if slot.path is None or slot.path not in declarations or slot.path in virtual:
                return HKEXPackageIntegrityReason.INPUT_AVAILABLE_INVALID
        elif slot.state is HKEXInputState.UNREADABLE:
            if slot.path is None or slot.path not in declarations or slot.path not in virtual:
                return HKEXPackageIntegrityReason.INPUT_AVAILABLE_INVALID
            if (
                virtual[slot.path].content_class
                is not HKEXVirtualContentClass.CORRUPT_OR_UNSUPPORTED
            ):
                return HKEXPackageIntegrityReason.INPUT_AVAILABLE_INVALID
    return None


def _expected_artifact_rejection(
    facts: HKEXPackageIntegrityFacts,
) -> HKEXPackageIntegrityReason | None:
    virtual = {item.path: item for item in facts.virtual_artifacts}
    for expected in facts.expected_artifacts:
        if expected.state is HKEXExpectedArtifactState.EXACT:
            if expected.path is None or expected.expected_fingerprint is None:
                return HKEXPackageIntegrityReason.EXPECTED_EXACT_INVALID
            artifact = virtual.get(expected.path)
            if (
                artifact is None
                or _raw_fingerprint(artifact.bytes()) != expected.expected_fingerprint
                or not artifact.schema_valid
                or not artifact.canonical_bytes
            ):
                return HKEXPackageIntegrityReason.EXPECTED_EXACT_INVALID
        elif expected.state is HKEXExpectedArtifactState.NONE:
            if (
                expected.path is not None
                or expected.expected_fingerprint is not None
                or expected.zero_count != 0
            ):
                return HKEXPackageIntegrityReason.ZERO_OUTPUT_PROOF_INVALID
        elif expected.state is HKEXExpectedArtifactState.NOT_APPLICABLE:
            if (
                expected.path is not None
                or expected.expected_fingerprint is not None
                or expected.checkpoint_applicable
                or not expected.matrix_proves_nonapplicable
                or not expected.implementation_completed
            ):
                return HKEXPackageIntegrityReason.NOT_APPLICABLE_INVALID
    return None


def _matrix_rejection(
    facts: HKEXPackageIntegrityFacts,
) -> HKEXPackageIntegrityReason | None:
    matrix = facts.matrix
    required_cells = set(matrix.required_cell_ids)
    executable_cases = set(matrix.executable_case_ids)
    coverage_cells = tuple(item.cell_id for item in matrix.primary_coverage)
    coverage_cases = tuple(item.case_id for item in matrix.primary_coverage)
    if (
        len(required_cells) != len(matrix.required_cell_ids)
        or len(executable_cases) != len(matrix.executable_case_ids)
        or len(set(coverage_cells)) != len(coverage_cells)
        or required_cells != set(coverage_cells)
        or not executable_cases
        or not executable_cases.issubset(set(coverage_cases))
        or set(matrix.required_rule_ids) != set(matrix.covered_rule_ids)
        or set(matrix.required_result_branches) != set(matrix.covered_result_branches)
    ):
        return HKEXPackageIntegrityReason.MATRIX_INCOMPLETE
    for pair in matrix.pairs:
        roles = tuple(member.role for member in pair.members)
        case_ids = tuple(member.case_id for member in pair.members)
        if (
            len(pair.members) != _PAIR_MEMBER_COUNT
            or set(roles) != {"POSITIVE", "NEAR_MISS"}
            or len(set(case_ids)) != _PAIR_MEMBER_COUNT
            or not set(case_ids).issubset(executable_cases)
        ):
            return HKEXPackageIntegrityReason.PAIR_INCOMPLETE
    pair_ids = {pair.pair_id for pair in matrix.pairs}
    if (
        len(pair_ids) != len(matrix.pairs)
        or pair_ids != set(matrix.required_pair_ids)
        or len(pair_ids) != len(matrix.required_pair_ids)
    ):
        return HKEXPackageIntegrityReason.PAIR_INCOMPLETE
    return None


def _proposal_and_execution_rejection(
    facts: HKEXPackageIntegrityFacts,
) -> HKEXPackageIntegrityReason | None:
    forbidden_fragments = (
        "case_id",
        "title",
        "package_path",
        "coverage_cell",
        "pair_role",
        "expected_result",
        "adjudication",
        "critical_error",
    )
    if any(
        any(fragment in field.lower() for fragment in forbidden_fragments)
        for field in facts.proposal_packet_fields
    ):
        return HKEXPackageIntegrityReason.PROPOSAL_TRUTH_LEAKAGE
    reproducibility_failed = len(facts.run_output_fingerprints) < _MIN_REPRODUCIBILITY_RUNS or any(
        run != facts.run_output_fingerprints[0] for run in facts.run_output_fingerprints[1:]
    )
    rejections = (
        (
            facts.fingerprint_scope is HKEXFingerprintScope.INCLUDES_SELF
            or facts.expected_truth_mutated,
            HKEXPackageIntegrityReason.FINGERPRINT_OR_TRUTH_MUTATION,
        ),
        (reproducibility_failed, HKEXPackageIntegrityReason.REPRODUCIBILITY_FAILURE),
        (
            bool(facts.source_instruction_effects),
            HKEXPackageIntegrityReason.HOSTILE_INPUT_CONTROL_BREACH,
        ),
        (
            bool(facts.attempted_capabilities) or facts.external_state_mutated,
            HKEXPackageIntegrityReason.FORBIDDEN_CAPABILITY_ATTEMPT,
        ),
    )
    return next((reason for rejected, reason in rejections if rejected), None)


def _authority_and_attestation_rejection(
    scope: HKEXPackageAssertionScope,
    facts: HKEXPackageIntegrityFacts,
) -> HKEXPackageIntegrityReason | None:
    allowed_claims = {"PACKAGE_VALIDITY", "BUILD_COMPATIBILITY"}
    if not set(facts.authority_claims).issubset(allowed_claims):
        return HKEXPackageIntegrityReason.AUTHORITY_BROADENING
    expected_claims: tuple[str, ...] = ()
    if scope is HKEXPackageAssertionScope.AUTHORITY_CONTAINMENT:
        expected_claims = ("PACKAGE_VALIDITY",)
    elif scope is HKEXPackageAssertionScope.ATTESTATION_COMPATIBILITY:
        expected_claims = ("BUILD_COMPATIBILITY",)
    if facts.authority_claims != expected_claims:
        return HKEXPackageIntegrityReason.AUTHORITY_BROADENING
    attestation = facts.attestation
    if (
        not attestation.complete
        or not attestation.compatibility_only
        or attestation.current_bindings != attestation.attested_bindings
    ):
        return HKEXPackageIntegrityReason.ATTESTATION_MISMATCH
    return None


def _accepted_reason(scope: HKEXPackageAssertionScope) -> HKEXPackageIntegrityReason:
    reasons = {
        HKEXPackageAssertionScope.AVAILABLE_INPUT: (
            HKEXPackageIntegrityReason.INPUT_AVAILABLE_ADMITTED
        ),
        HKEXPackageAssertionScope.DELIBERATE_ABSENCE: (
            HKEXPackageIntegrityReason.DELIBERATE_ABSENCE_ADMITTED
        ),
        HKEXPackageAssertionScope.UNREADABLE_INPUT: (
            HKEXPackageIntegrityReason.UNREADABLE_CONDITION_ADMITTED
        ),
        HKEXPackageAssertionScope.AVAILABLE_FACT_CONDITION: (
            HKEXPackageIntegrityReason.AVAILABLE_FACT_CONDITION_ADMITTED
        ),
        HKEXPackageAssertionScope.EXACT_OUTPUT: (HKEXPackageIntegrityReason.EXACT_ARTIFACT_MATCHED),
        HKEXPackageAssertionScope.ZERO_OUTPUT: HKEXPackageIntegrityReason.ZERO_OUTPUT_PROVED,
        HKEXPackageAssertionScope.NOT_APPLICABLE_OUTPUT: (
            HKEXPackageIntegrityReason.NOT_APPLICABLE_PROVED
        ),
        HKEXPackageAssertionScope.MATRIX_COMPLETENESS: (HKEXPackageIntegrityReason.MATRIX_COMPLETE),
        HKEXPackageAssertionScope.PAIR_COMPLETENESS: HKEXPackageIntegrityReason.PAIR_COMPLETE,
        HKEXPackageAssertionScope.PROPOSAL_ISOLATION: (
            HKEXPackageIntegrityReason.PROPOSAL_PACKET_CLEAN
        ),
        HKEXPackageAssertionScope.REPRODUCIBILITY: HKEXPackageIntegrityReason.REPRODUCIBLE,
        HKEXPackageAssertionScope.HOSTILE_SOURCE_TEXT: (
            HKEXPackageIntegrityReason.HOSTILE_TEXT_INERT
        ),
        HKEXPackageAssertionScope.AUTHORITY_CONTAINMENT: (
            HKEXPackageIntegrityReason.PACKAGE_VALIDITY_ONLY
        ),
        HKEXPackageAssertionScope.ATTESTATION_COMPATIBILITY: (
            HKEXPackageIntegrityReason.BUILD_COMPATIBILITY_ONLY
        ),
    }
    return reasons.get(scope, HKEXPackageIntegrityReason.PACKAGE_VALID)


def _facts(value: JsonValue) -> HKEXPackageIntegrityFacts:
    root = _json_object(value)
    _exact_keys(
        root,
        {
            "closed_schema_violations",
            "declared_artifacts",
            "virtual_artifacts",
            "runner_access_paths",
            "discovery_methods",
            "input_slots",
            "expected_artifacts",
            "matrix",
            "proposal_packet_fields",
            "fingerprint_scope",
            "expected_truth_mutated",
            "run_output_fingerprints",
            "source_instruction_present",
            "source_instruction_effects",
            "attempted_capabilities",
            "external_state_mutated",
            "authority_claims",
            "attestation",
        },
    )
    return HKEXPackageIntegrityFacts(
        _json_strings(root["closed_schema_violations"]),
        tuple(_declared_artifact(item) for item in _json_object_array(root["declared_artifacts"])),
        tuple(_virtual_artifact(item) for item in _json_object_array(root["virtual_artifacts"])),
        _json_strings(root["runner_access_paths"]),
        tuple(
            _json_enum(item, HKEXDiscoveryMethod) for item in _json_array(root["discovery_methods"])
        ),
        tuple(_input_slot(item) for item in _json_object_array(root["input_slots"])),
        tuple(_expected_artifact(item) for item in _json_object_array(root["expected_artifacts"])),
        _matrix(root["matrix"]),
        _json_strings(root["proposal_packet_fields"]),
        _json_enum(root["fingerprint_scope"], HKEXFingerprintScope),
        _json_boolean(root["expected_truth_mutated"]),
        tuple(_json_strings(item) for item in _json_array(root["run_output_fingerprints"])),
        _json_boolean(root["source_instruction_present"]),
        _json_strings(root["source_instruction_effects"]),
        tuple(
            _json_enum(item, HKEXForbiddenCapability)
            for item in _json_array(root["attempted_capabilities"])
        ),
        _json_boolean(root["external_state_mutated"]),
        _json_strings(root["authority_claims"]),
        _attestation(root["attestation"]),
    )


def _contract_bindings(value: JsonValue) -> tuple[HKEXContractBinding, ...]:
    bindings: list[HKEXContractBinding] = []
    for item in _json_object_array(value):
        _exact_keys(item, {"contract_id", "version", "fingerprint"})
        bindings.append(
            HKEXContractBinding(
                _json_text(item["contract_id"]),
                _json_text(item["version"]),
                _json_fingerprint(item["fingerprint"]),
            )
        )
    if tuple(item.contract_id for item in bindings) != tuple(
        sorted({item.contract_id for item in bindings})
    ):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    return tuple(bindings)


def _pair_membership(value: JsonValue) -> HKEXPairMembership | None:
    if value is None:
        return None
    item = _json_object(value)
    _exact_keys(item, {"pair_id", "role"})
    pair_id = _pattern_text(item["pair_id"], r"HKREG-PAIR-0(5[0-6])")
    role = _json_text(item["role"])
    if role not in {"POSITIVE", "NEAR_MISS"}:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    return HKEXPairMembership(pair_id, role)


def _case_pair_membership(value: JsonValue, case_id: str) -> HKEXPairMembership | None:
    membership = _pair_membership(value)
    actual = None if membership is None else (membership.pair_id, membership.role)
    if actual != _EXPECTED_PAIR_MEMBERSHIPS.get(case_id):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.IDENTITY)
    return membership


def _declared_artifact(value: dict[str, JsonValue]) -> HKEXDeclaredArtifact:
    _exact_keys(value, {"path", "role", "media_type", "fingerprint", "required"})
    return HKEXDeclaredArtifact(
        _json_text(value["path"]),
        _json_text(value["role"]),
        _json_text(value["media_type"]),
        _json_fingerprint(value["fingerprint"]),
        _json_boolean(value["required"]),
    )


def _virtual_artifact(value: dict[str, JsonValue]) -> HKEXVirtualArtifact:
    _exact_keys(
        value,
        {
            "path",
            "media_type",
            "content_base64",
            "node_type",
            "content_class",
            "readable",
            "schema_valid",
            "canonical_bytes",
        },
    )
    result = HKEXVirtualArtifact(
        _json_text(value["path"]),
        _json_text(value["media_type"]),
        _json_text(value["content_base64"]),
        _json_enum(value["node_type"], HKEXVirtualNodeType),
        _json_enum(value["content_class"], HKEXVirtualContentClass),
        _json_boolean(value["readable"]),
        _json_boolean(value["schema_valid"]),
        _json_boolean(value["canonical_bytes"]),
    )
    result.bytes()
    return result


def _input_slot(value: dict[str, JsonValue]) -> HKEXInputSlot:
    _exact_keys(value, {"slot_id", "state", "path", "fact_condition"})
    return HKEXInputSlot(
        _json_text(value["slot_id"]),
        _json_enum(value["state"], HKEXInputState),
        _json_optional_text(value["path"]),
        _json_enum(value["fact_condition"], HKEXInputFactCondition),
    )


def _expected_artifact(value: dict[str, JsonValue]) -> HKEXExpectedArtifact:
    _exact_keys(
        value,
        {
            "role",
            "state",
            "path",
            "expected_fingerprint",
            "zero_count",
            "checkpoint_applicable",
            "matrix_proves_nonapplicable",
            "implementation_completed",
        },
    )
    expected_fingerprint = value["expected_fingerprint"]
    return HKEXExpectedArtifact(
        _json_text(value["role"]),
        _json_enum(value["state"], HKEXExpectedArtifactState),
        _json_optional_text(value["path"]),
        None if expected_fingerprint is None else _json_fingerprint(expected_fingerprint),
        _json_optional_nonnegative_integer(value["zero_count"]),
        _json_boolean(value["checkpoint_applicable"]),
        _json_boolean(value["matrix_proves_nonapplicable"]),
        _json_boolean(value["implementation_completed"]),
    )


def _matrix(value: JsonValue) -> HKEXCoverageMatrixFacts:
    root = _json_object(value)
    _exact_keys(
        root,
        {
            "required_cell_ids",
            "executable_case_ids",
            "primary_coverage",
            "required_rule_ids",
            "covered_rule_ids",
            "required_result_branches",
            "covered_result_branches",
            "required_pair_ids",
            "pairs",
        },
    )
    coverage: list[HKEXPrimaryCoverage] = []
    for item in _json_object_array(root["primary_coverage"]):
        _exact_keys(item, {"cell_id", "case_id"})
        coverage.append(
            HKEXPrimaryCoverage(_json_text(item["cell_id"]), _json_text(item["case_id"]))
        )
    pairs: list[HKEXPairDefinition] = []
    for item in _json_object_array(root["pairs"]):
        _exact_keys(item, {"pair_id", "members"})
        members: list[HKEXPairMember] = []
        for member in _json_object_array(item["members"]):
            _exact_keys(member, {"case_id", "role"})
            members.append(
                HKEXPairMember(_json_text(member["case_id"]), _json_text(member["role"]))
            )
        pairs.append(HKEXPairDefinition(_json_text(item["pair_id"]), tuple(members)))
    return HKEXCoverageMatrixFacts(
        _json_strings(root["required_cell_ids"]),
        _json_strings(root["executable_case_ids"]),
        tuple(coverage),
        _json_strings(root["required_rule_ids"]),
        _json_strings(root["covered_rule_ids"]),
        _json_strings(root["required_result_branches"]),
        _json_strings(root["covered_result_branches"]),
        _json_strings(root["required_pair_ids"]),
        tuple(pairs),
    )


def _attestation(value: JsonValue) -> HKEXAttestationFacts:
    root = _json_object(value)
    _exact_keys(root, {"complete", "compatibility_only", "current_bindings", "attested_bindings"})
    return HKEXAttestationFacts(
        _json_boolean(root["complete"]),
        _json_boolean(root["compatibility_only"]),
        _bindings(root["current_bindings"]),
        _bindings(root["attested_bindings"]),
    )


def _bindings(value: JsonValue) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    for item in _json_object_array(value):
        _exact_keys(item, {"name", "fingerprint"})
        items.append((_json_text(item["name"]), _json_fingerprint(item["fingerprint"])))
    if tuple(name for name, _ in items) != tuple(sorted({name for name, _ in items})):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    return tuple(items)


def _safe_relative_path(path: str) -> bool:
    if path.startswith("/") or "\\" in path:
        return False
    segments = path.split("/")
    return bool(segments) and all(segment not in {"", ".", ".."} for segment in segments)


def _raw_fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _json_object(value: object) -> dict[str, JsonValue]:
    try:
        checked = checked_json_value(value)
    except ContractViolation as error:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT) from error
    if not isinstance(checked, dict):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    return checked


def _json_object_array(value: JsonValue) -> tuple[dict[str, JsonValue], ...]:
    return tuple(_json_object(item) for item in _json_array(value))


def _json_array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    return value


def _json_strings(value: JsonValue) -> tuple[str, ...]:
    return tuple(_json_text(item) for item in _json_array(value))


def _json_text(value: JsonValue) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    return value


def _json_optional_text(value: JsonValue) -> str | None:
    return None if value is None else _json_text(value)


def _json_boolean(value: JsonValue) -> bool:
    if type(value) is not bool:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    return value


def _json_optional_nonnegative_integer(value: JsonValue) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
    return value


def _json_fingerprint(value: JsonValue) -> str:
    return _pattern_text(value, _FINGERPRINT_PATTERN)


def _pattern_text(value: JsonValue, pattern: str) -> str:
    text = _json_text(value)
    if fullmatch(pattern, text) is None:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.IDENTITY)
    return text


def _json_enum[E: StrEnum](value: JsonValue, enum_type: type[E]) -> E:
    text = _json_text(value)
    try:
        return enum_type(text)
    except ValueError as error:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT) from error


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)


def _constant(value: JsonValue, expected: str) -> None:
    if value != expected or type(value) is not str:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)


def _true(value: JsonValue) -> None:
    if value is not True:
        raise HKEXPackageIntegrityError(HKEXPackageIntegrityErrorCode.CONTRACT)
