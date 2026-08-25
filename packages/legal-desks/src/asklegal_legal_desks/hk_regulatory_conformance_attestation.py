"""Immutable external HKEX Rulebook Conformance Attestation contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from typing import TypeIs

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

HKEX_CONFORMANCE_ATTESTATION_CONTRACT_VERSION = "1.0.0"
HKEX_CONFORMANCE_ATTESTATION_RULE_ID = "HKREG-CONFORMANCE-ATTESTATION-001"
HKEX_CONFORMANCE_ATTESTATION_KIND = "REGULATORY_RULEBOOK_CONFORMANCE"
HKEX_CONFORMANCE_CASE_RESULT_COUNT = 284
HKEX_CONFORMANCE_COVERAGE_CELL_COUNT = 284
HKEX_CONFORMANCE_PAIR_COUNT = 57

_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_ATTESTATION_ID_PATTERN = r"rba_[0-9a-f]{48}"
_ISOLATED_RUN_COUNT = 2


class HKEXConformanceAttestationErrorCode(StrEnum):
    """Closed malformed-contract failures."""

    CONTRACT = "HKREG_CONFORMANCE_ATTESTATION_CONTRACT_INVALID"
    EVIDENCE = "HKREG_CONFORMANCE_ATTESTATION_EVIDENCE_INVALID"


class HKEXConformanceAttestationError(ValueError):
    """One attestation document that cannot safely be interpreted."""

    code: HKEXConformanceAttestationErrorCode

    def __init__(self, code: HKEXConformanceAttestationErrorCode) -> None:
        """Create one stable fail-closed error."""
        self.code = code
        super().__init__(code.value)


class HKEXConformanceAttestationOutcome(StrEnum):
    """Terminal compatibility-validation outcome."""

    VALID = "VALID"
    INVALID = "INVALID"


class HKEXConformanceAttestationReason(StrEnum):
    """Stable exact reasons for accepting or rejecting one attestation."""

    COMPLETE_SOURCE_NEUTRAL_BUILD_COMPATIBILITY = "COMPLETE_SOURCE_NEUTRAL_BUILD_COMPATIBILITY"
    PACKAGE_BINDING_MISMATCH = "PACKAGE_BINDING_MISMATCH"
    SUITE_BINDING_MISMATCH = "SUITE_BINDING_MISMATCH"
    PROCESSING_BUILD_BINDING_MISMATCH = "PROCESSING_BUILD_BINDING_MISMATCH"
    DEPENDENCY_LOCK_BINDING_MISMATCH = "DEPENDENCY_LOCK_BINDING_MISMATCH"
    RUNNER_BINDING_MISMATCH = "RUNNER_BINDING_MISMATCH"
    CONTRACT_SET_BINDING_MISMATCH = "CONTRACT_SET_BINDING_MISMATCH"
    CASE_RESULT_INVENTORY_MISMATCH = "CASE_RESULT_INVENTORY_MISMATCH"
    REPRODUCIBILITY_MISMATCH = "REPRODUCIBILITY_MISMATCH"
    ARCHITECTURE_PROOF_MISMATCH = "ARCHITECTURE_PROOF_MISMATCH"
    ATTESTATION_ID_MISMATCH = "ATTESTATION_ID_MISMATCH"
    FINAL_RESULT_NOT_SUCCESSFUL = "FINAL_RESULT_NOT_SUCCESSFUL"
    AUTHORITY_OVERREACH = "AUTHORITY_OVERREACH"
    EXTERNAL_EFFECT_CLAIM = "EXTERNAL_EFFECT_CLAIM"


@dataclass(frozen=True, slots=True)
class HKEXConformanceArtifactBinding:
    """One exact repository artifact used by the conformance proof."""

    path: str
    byte_size: int
    fingerprint: str

    def __post_init__(self) -> None:
        """Reject ambiguous paths, sizes, or fingerprints."""
        _relative_path(self.path)
        if type(self.byte_size) is not int or self.byte_size < 1:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
        _fingerprint(self.fingerprint)

    def document(self) -> dict[str, JsonValue]:
        """Return the canonical JSON-compatible projection."""
        return {
            "path": self.path,
            "byte_size": self.byte_size,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HKEXRulebookPackageBinding:
    """Exact immutable Source Rulebook Package identity."""

    package_id: str
    package_version: str
    package_fingerprint: str

    def __post_init__(self) -> None:
        """Validate the closed package identity."""
        _text(self.package_id)
        _text(self.package_version)
        _fingerprint(self.package_fingerprint)

    def document(self) -> dict[str, JsonValue]:
        """Return one stable package projection."""
        return {
            "package_id": self.package_id,
            "package_version": self.package_version,
            "package_fingerprint": self.package_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HKEXConformanceSuiteBinding:
    """Exact frozen 284-case/284-cell/57-pair suite binding."""

    universe: HKEXConformanceArtifactBinding
    universe_fingerprint: str
    case_count: int
    coverage_cell_count: int
    pair_count: int

    def __post_init__(self) -> None:
        """Require the accepted complete suite arithmetic."""
        if type(self.universe) is not HKEXConformanceArtifactBinding:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        _fingerprint(self.universe_fingerprint)
        if (
            self.case_count != HKEX_CONFORMANCE_CASE_RESULT_COUNT
            or self.coverage_cell_count != HKEX_CONFORMANCE_COVERAGE_CELL_COUNT
            or self.pair_count != HKEX_CONFORMANCE_PAIR_COUNT
        ):
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)

    def document(self) -> dict[str, JsonValue]:
        """Return the exact suite projection."""
        return {
            "universe": self.universe.document(),
            "universe_fingerprint": self.universe_fingerprint,
            "case_count": self.case_count,
            "coverage_cell_count": self.coverage_cell_count,
            "pair_count": self.pair_count,
        }


@dataclass(frozen=True, slots=True)
class HKEXConformanceArtifactSetBinding:
    """Closed sorted artifact inventory and its aggregate fingerprint."""

    members: tuple[HKEXConformanceArtifactBinding, ...]
    inventory_fingerprint: str

    def __post_init__(self) -> None:
        """Require a unique byte-sorted complete inventory."""
        if type(self.members) is not tuple or not self.members:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
        if any(type(member) is not HKEXConformanceArtifactBinding for member in self.members):
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        paths = tuple(member.path for member in self.members)
        if paths != tuple(sorted(set(paths), key=lambda value: value.encode())):
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
        _fingerprint(self.inventory_fingerprint)

    def document(self) -> dict[str, JsonValue]:
        """Return the exact artifact-set projection."""
        return {
            "members": [member.document() for member in self.members],
            "inventory_fingerprint": self.inventory_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HKEXConformanceCaseResultBinding:
    """One executed permanent case and exact frozen result bytes."""

    case_id: str
    result: HKEXConformanceArtifactBinding

    def __post_init__(self) -> None:
        """Validate permanent identity and result binding."""
        if fullmatch(r"HKREG-(?:DEC|DET)-[A-Z]{3}-\d{3}", self.case_id) is None:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
        if type(self.result) is not HKEXConformanceArtifactBinding:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)

    def document(self) -> dict[str, JsonValue]:
        """Return one case-result inventory entry."""
        return {"case_id": self.case_id, "result": self.result.document()}


@dataclass(frozen=True, slots=True)
class HKEXConformanceCaseResultSet:
    """Complete exact result inventory for all 284 permanent cases."""

    members: tuple[HKEXConformanceCaseResultBinding, ...]
    result_set_fingerprint: str

    def __post_init__(self) -> None:
        """Require a unique complete permanent case inventory."""
        if type(self.members) is not tuple or len(self.members) != (
            HKEX_CONFORMANCE_CASE_RESULT_COUNT
        ):
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
        if any(type(member) is not HKEXConformanceCaseResultBinding for member in self.members):
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        identities = tuple(member.case_id for member in self.members)
        paths = tuple(member.result.path for member in self.members)
        if identities != tuple(sorted(set(identities))) or len(paths) != len(set(paths)):
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
        _fingerprint(self.result_set_fingerprint)

    def document(self) -> dict[str, JsonValue]:
        """Return the complete result-set projection."""
        return {
            "case_count": len(self.members),
            "members": [member.document() for member in self.members],
            "result_set_fingerprint": self.result_set_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HKEXConformanceRunBinding:
    """One isolated clean execution summary."""

    run_id: str
    case_count: int
    result_set_fingerprint: str
    tree_fingerprint: str

    def __post_init__(self) -> None:
        """Validate a complete isolated run summary."""
        if self.run_id not in {"ISOLATED_RUN_1", "ISOLATED_RUN_2"}:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        if self.case_count != HKEX_CONFORMANCE_CASE_RESULT_COUNT:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
        _fingerprint(self.result_set_fingerprint)
        _fingerprint(self.tree_fingerprint)

    def document(self) -> dict[str, JsonValue]:
        """Return one isolated-run projection."""
        return {
            "run_id": self.run_id,
            "case_count": self.case_count,
            "result_set_fingerprint": self.result_set_fingerprint,
            "tree_fingerprint": self.tree_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HKEXConformanceReproducibilityProof:
    """Two isolated clean executions with byte-identical result trees."""

    runs: tuple[HKEXConformanceRunBinding, HKEXConformanceRunBinding]
    byte_identical: bool

    def __post_init__(self) -> None:
        """Require both named executions while leaving equality to evaluation."""
        if type(self.runs) is not tuple or len(self.runs) != _ISOLATED_RUN_COUNT:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        if tuple(run.run_id for run in self.runs) != ("ISOLATED_RUN_1", "ISOLATED_RUN_2"):
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        if type(self.byte_identical) is not bool:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)

    def document(self) -> dict[str, JsonValue]:
        """Return the exact two-run projection."""
        return {
            "isolated_run_count": 2,
            "runs": [run.document() for run in self.runs],
            "byte_identical": self.byte_identical,
        }


@dataclass(frozen=True, slots=True)
class HKEXConformanceArchitectureProof:
    """Exact successful repository architecture-test evidence."""

    tool: HKEXConformanceArtifactBinding
    policy: HKEXConformanceArtifactBinding
    applications: int
    packages: int
    dependency_edges: int
    capability_ports: int
    policy_fingerprint: str
    report_fingerprint: str
    result: str

    def __post_init__(self) -> None:
        """Validate the closed successful report shape."""
        if (
            type(self.tool) is not HKEXConformanceArtifactBinding
            or type(self.policy) is not HKEXConformanceArtifactBinding
        ):
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        for count in (
            self.applications,
            self.packages,
            self.dependency_edges,
            self.capability_ports,
        ):
            if type(count) is not int or count < 1:
                raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
        _fingerprint(self.policy_fingerprint)
        _fingerprint(self.report_fingerprint)
        if self.result not in {"PASS", "FAIL"}:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)

    def document(self) -> dict[str, JsonValue]:
        """Return one exact architecture proof."""
        return {
            "tool": self.tool.document(),
            "policy": self.policy.document(),
            "applications": self.applications,
            "packages": self.packages,
            "dependency_edges": self.dependency_edges,
            "capability_ports": self.capability_ports,
            "policy_fingerprint": self.policy_fingerprint,
            "report_fingerprint": self.report_fingerprint,
            "result": self.result,
        }


@dataclass(frozen=True, slots=True)
class HKEXConformanceAttestationEvidence:
    """All exact current facts one build-specific attestation must bind."""

    rulebook_package: HKEXRulebookPackageBinding
    suite: HKEXConformanceSuiteBinding
    processing_build: HKEXConformanceArtifactSetBinding
    dependency_lock: HKEXConformanceArtifactBinding
    conformance_runner: HKEXConformanceArtifactBinding
    contract_set: HKEXConformanceArtifactBinding
    contract_set_fingerprint: str
    case_results: HKEXConformanceCaseResultSet
    reproducibility: HKEXConformanceReproducibilityProof
    architecture: HKEXConformanceArchitectureProof

    def __post_init__(self) -> None:
        """Reject missing or incorrectly typed proof components."""
        expected_types: tuple[tuple[object, type[object]], ...] = (
            (self.rulebook_package, HKEXRulebookPackageBinding),
            (self.suite, HKEXConformanceSuiteBinding),
            (self.processing_build, HKEXConformanceArtifactSetBinding),
            (self.dependency_lock, HKEXConformanceArtifactBinding),
            (self.conformance_runner, HKEXConformanceArtifactBinding),
            (self.contract_set, HKEXConformanceArtifactBinding),
            (self.case_results, HKEXConformanceCaseResultSet),
            (self.reproducibility, HKEXConformanceReproducibilityProof),
            (self.architecture, HKEXConformanceArchitectureProof),
        )
        if any(type(value) is not expected for value, expected in expected_types):
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        _fingerprint(self.contract_set_fingerprint)

    def document(self) -> dict[str, JsonValue]:
        """Return all exact evidence bindings."""
        return {
            "rulebook_package": self.rulebook_package.document(),
            "suite": self.suite.document(),
            "processing_build": self.processing_build.document(),
            "dependency_lock": self.dependency_lock.document(),
            "conformance_runner": self.conformance_runner.document(),
            "contract_set": self.contract_set.document(),
            "contract_set_fingerprint": self.contract_set_fingerprint,
            "case_results": self.case_results.document(),
            "reproducibility": self.reproducibility.document(),
            "architecture": self.architecture.document(),
        }


@dataclass(frozen=True, slots=True)
class HKEXConformanceAttestation:
    """Immutable external proof of one exact build/package combination."""

    attestation_id: str
    evidence: HKEXConformanceAttestationEvidence
    final_result: str
    capability_claims: tuple[str, ...]
    real_source_evaluation: bool
    source_access_authorized: bool
    release_creation_authorized: bool
    approval_authorized: bool
    pinecone_authorized: bool
    deployment_authorized: bool
    activation_authorized: bool
    external_effects: str

    def __post_init__(self) -> None:
        """Validate the immutable outer contract without repairing facts."""
        if fullmatch(_ATTESTATION_ID_PATTERN, self.attestation_id) is None:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        if type(self.evidence) is not HKEXConformanceAttestationEvidence:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        if self.final_result not in {"PASS", "FAIL"}:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        if type(self.capability_claims) is not tuple or not self.capability_claims:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        for value in self.capability_claims:
            _text(value)
        for value in (
            self.real_source_evaluation,
            self.source_access_authorized,
            self.release_creation_authorized,
            self.approval_authorized,
            self.pinecone_authorized,
            self.deployment_authorized,
            self.activation_authorized,
        ):
            if type(value) is not bool:
                raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        if self.external_effects not in {"NONE", "PRESENT"}:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)

    def document(self) -> dict[str, JsonValue]:
        """Return the strict external attestation document."""
        return {
            "schema_id": "asklegal.hk-regulatory.conformance-attestation",
            "schema_version": HKEX_CONFORMANCE_ATTESTATION_CONTRACT_VERSION,
            "attestation_id": self.attestation_id,
            "attestation_kind": HKEX_CONFORMANCE_ATTESTATION_KIND,
            "jurisdiction": "HK",
            "material_family": "REGULATORY_MATERIALS",
            "rule_id": HKEX_CONFORMANCE_ATTESTATION_RULE_ID,
            "evidence": self.evidence.document(),
            "final_result": self.final_result,
            "capability_claims": list(self.capability_claims),
            "real_source_evaluation": self.real_source_evaluation,
            "source_access_authorized": self.source_access_authorized,
            "release_creation_authorized": self.release_creation_authorized,
            "approval_authorized": self.approval_authorized,
            "pinecone_authorized": self.pinecone_authorized,
            "deployment_authorized": self.deployment_authorized,
            "activation_authorized": self.activation_authorized,
            "external_effects": self.external_effects,
        }


@dataclass(frozen=True, slots=True)
class HKEXConformanceAttestationResult:
    """Effect-free validation result for one candidate attestation."""

    attestation_id: str
    outcome: HKEXConformanceAttestationOutcome
    reason: HKEXConformanceAttestationReason
    build_compatibility_valid: bool
    source_access_authorized: bool = False
    release_creation_authorized: bool = False
    approval_authorized: bool = False
    pinecone_authorized: bool = False
    deployment_authorized: bool = False
    activation_authorized: bool = False
    external_effects: str = "NONE"

    def document(self) -> dict[str, JsonValue]:
        """Return one stable effect-free result document."""
        return {
            "schema_id": "asklegal.hk-regulatory.conformance-attestation-result",
            "schema_version": HKEX_CONFORMANCE_ATTESTATION_CONTRACT_VERSION,
            "rule_id": HKEX_CONFORMANCE_ATTESTATION_RULE_ID,
            "attestation_id": self.attestation_id,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "build_compatibility_valid": self.build_compatibility_valid,
            "source_access_authorized": self.source_access_authorized,
            "release_creation_authorized": self.release_creation_authorized,
            "approval_authorized": self.approval_authorized,
            "pinecone_authorized": self.pinecone_authorized,
            "deployment_authorized": self.deployment_authorized,
            "activation_authorized": self.activation_authorized,
            "external_effects": self.external_effects,
        }


def seal_hkex_conformance_attestation(
    evidence: HKEXConformanceAttestationEvidence,
) -> HKEXConformanceAttestation:
    """Create one content-addressed compatibility-only attestation."""
    candidate = HKEXConformanceAttestation(
        attestation_id=f"rba_{'0' * 48}",
        evidence=evidence,
        final_result="PASS",
        capability_claims=("BUILD_COMPATIBILITY",),
        real_source_evaluation=False,
        source_access_authorized=False,
        release_creation_authorized=False,
        approval_authorized=False,
        pinecone_authorized=False,
        deployment_authorized=False,
        activation_authorized=False,
        external_effects="NONE",
    )
    return HKEXConformanceAttestation(
        attestation_id=_derived_attestation_id(candidate),
        evidence=evidence,
        final_result=candidate.final_result,
        capability_claims=candidate.capability_claims,
        real_source_evaluation=candidate.real_source_evaluation,
        source_access_authorized=candidate.source_access_authorized,
        release_creation_authorized=candidate.release_creation_authorized,
        approval_authorized=candidate.approval_authorized,
        pinecone_authorized=candidate.pinecone_authorized,
        deployment_authorized=candidate.deployment_authorized,
        activation_authorized=candidate.activation_authorized,
        external_effects=candidate.external_effects,
    )


def evaluate_hkex_conformance_attestation(
    attestation: HKEXConformanceAttestation,
    current_evidence: HKEXConformanceAttestationEvidence,
) -> HKEXConformanceAttestationResult:
    """Validate exact current build compatibility and grant nothing else."""
    if (
        type(attestation) is not HKEXConformanceAttestation
        or type(current_evidence) is not HKEXConformanceAttestationEvidence
    ):
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
    mismatch_checks = (
        (
            attestation.evidence.rulebook_package != current_evidence.rulebook_package,
            HKEXConformanceAttestationReason.PACKAGE_BINDING_MISMATCH,
        ),
        (
            attestation.evidence.suite != current_evidence.suite,
            HKEXConformanceAttestationReason.SUITE_BINDING_MISMATCH,
        ),
        (
            attestation.evidence.processing_build != current_evidence.processing_build,
            HKEXConformanceAttestationReason.PROCESSING_BUILD_BINDING_MISMATCH,
        ),
        (
            attestation.evidence.dependency_lock != current_evidence.dependency_lock,
            HKEXConformanceAttestationReason.DEPENDENCY_LOCK_BINDING_MISMATCH,
        ),
        (
            attestation.evidence.conformance_runner != current_evidence.conformance_runner,
            HKEXConformanceAttestationReason.RUNNER_BINDING_MISMATCH,
        ),
        (
            (
                attestation.evidence.contract_set != current_evidence.contract_set
                or attestation.evidence.contract_set_fingerprint
                != current_evidence.contract_set_fingerprint
            ),
            HKEXConformanceAttestationReason.CONTRACT_SET_BINDING_MISMATCH,
        ),
        (
            attestation.evidence.case_results != current_evidence.case_results,
            HKEXConformanceAttestationReason.CASE_RESULT_INVENTORY_MISMATCH,
        ),
        (
            attestation.evidence.reproducibility != current_evidence.reproducibility,
            HKEXConformanceAttestationReason.REPRODUCIBILITY_MISMATCH,
        ),
        (
            attestation.evidence.architecture != current_evidence.architecture,
            HKEXConformanceAttestationReason.ARCHITECTURE_PROOF_MISMATCH,
        ),
    )
    for mismatched, reason in mismatch_checks:
        if mismatched:
            return _invalid(attestation.attestation_id, reason)
    terminal_rejection = _terminal_attestation_rejection(attestation)
    if terminal_rejection is not None:
        return _invalid(attestation.attestation_id, terminal_rejection)
    return HKEXConformanceAttestationResult(
        attestation_id=attestation.attestation_id,
        outcome=HKEXConformanceAttestationOutcome.VALID,
        reason=(HKEXConformanceAttestationReason.COMPLETE_SOURCE_NEUTRAL_BUILD_COMPATIBILITY),
        build_compatibility_valid=True,
    )


def hkex_conformance_attestation_from_document(
    document: object,
) -> HKEXConformanceAttestation:
    """Strictly decode one external attestation without repair."""
    root = _document(document)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "attestation_id",
            "attestation_kind",
            "jurisdiction",
            "material_family",
            "rule_id",
            "evidence",
            "final_result",
            "capability_claims",
            "real_source_evaluation",
            "source_access_authorized",
            "release_creation_authorized",
            "approval_authorized",
            "pinecone_authorized",
            "deployment_authorized",
            "activation_authorized",
            "external_effects",
        },
    )
    _constant(root["schema_id"], "asklegal.hk-regulatory.conformance-attestation")
    _constant(root["schema_version"], HKEX_CONFORMANCE_ATTESTATION_CONTRACT_VERSION)
    _constant(root["attestation_kind"], HKEX_CONFORMANCE_ATTESTATION_KIND)
    _constant(root["jurisdiction"], "HK")
    _constant(root["material_family"], "REGULATORY_MATERIALS")
    _constant(root["rule_id"], HKEX_CONFORMANCE_ATTESTATION_RULE_ID)
    return HKEXConformanceAttestation(
        attestation_id=_json_text(root["attestation_id"]),
        evidence=_evidence(root["evidence"]),
        final_result=_json_text(root["final_result"]),
        capability_claims=_json_strings(root["capability_claims"]),
        real_source_evaluation=_json_bool(root["real_source_evaluation"]),
        source_access_authorized=_json_bool(root["source_access_authorized"]),
        release_creation_authorized=_json_bool(root["release_creation_authorized"]),
        approval_authorized=_json_bool(root["approval_authorized"]),
        pinecone_authorized=_json_bool(root["pinecone_authorized"]),
        deployment_authorized=_json_bool(root["deployment_authorized"]),
        activation_authorized=_json_bool(root["activation_authorized"]),
        external_effects=_json_text(root["external_effects"]),
    )


def hkex_conformance_attestation_evidence_from_document(
    document: object,
) -> HKEXConformanceAttestationEvidence:
    """Strictly decode current evidence assembled by the isolated runner."""
    return _evidence(document)


def _derived_attestation_id(attestation: HKEXConformanceAttestation) -> str:
    projection = attestation.document()
    projection.pop("attestation_id")
    digest = fingerprint(checked_json_value(projection)).removeprefix("sha256:")
    return f"rba_{digest[:48]}"


def _terminal_attestation_rejection(
    attestation: HKEXConformanceAttestation,
) -> HKEXConformanceAttestationReason | None:
    reproduction = attestation.evidence.reproducibility
    first, second = reproduction.runs
    if attestation.capability_claims != ("BUILD_COMPATIBILITY",) or any(
        (
            attestation.real_source_evaluation,
            attestation.source_access_authorized,
            attestation.release_creation_authorized,
            attestation.approval_authorized,
            attestation.pinecone_authorized,
            attestation.deployment_authorized,
            attestation.activation_authorized,
        )
    ):
        reason = HKEXConformanceAttestationReason.AUTHORITY_OVERREACH
    elif attestation.external_effects != "NONE":
        reason = HKEXConformanceAttestationReason.EXTERNAL_EFFECT_CLAIM
    elif attestation.attestation_id != _derived_attestation_id(attestation):
        reason = HKEXConformanceAttestationReason.ATTESTATION_ID_MISMATCH
    elif (
        not reproduction.byte_identical
        or first.result_set_fingerprint != second.result_set_fingerprint
        or first.tree_fingerprint != second.tree_fingerprint
        or first.result_set_fingerprint != attestation.evidence.case_results.result_set_fingerprint
    ):
        reason = HKEXConformanceAttestationReason.REPRODUCIBILITY_MISMATCH
    elif attestation.evidence.architecture.result != "PASS":
        reason = HKEXConformanceAttestationReason.ARCHITECTURE_PROOF_MISMATCH
    elif attestation.final_result != "PASS":
        reason = HKEXConformanceAttestationReason.FINAL_RESULT_NOT_SUCCESSFUL
    else:
        reason = None
    return reason


def _invalid(
    attestation_id: str,
    reason: HKEXConformanceAttestationReason,
) -> HKEXConformanceAttestationResult:
    return HKEXConformanceAttestationResult(
        attestation_id=attestation_id,
        outcome=HKEXConformanceAttestationOutcome.INVALID,
        reason=reason,
        build_compatibility_valid=False,
    )


def _evidence(value: object) -> HKEXConformanceAttestationEvidence:
    item = _document(value)
    _exact_keys(
        item,
        {
            "rulebook_package",
            "suite",
            "processing_build",
            "dependency_lock",
            "conformance_runner",
            "contract_set",
            "contract_set_fingerprint",
            "case_results",
            "reproducibility",
            "architecture",
        },
    )
    return HKEXConformanceAttestationEvidence(
        rulebook_package=_package_binding(item["rulebook_package"]),
        suite=_suite_binding(item["suite"]),
        processing_build=_artifact_set(item["processing_build"]),
        dependency_lock=_artifact(item["dependency_lock"]),
        conformance_runner=_artifact(item["conformance_runner"]),
        contract_set=_artifact(item["contract_set"]),
        contract_set_fingerprint=_json_fingerprint(item["contract_set_fingerprint"]),
        case_results=_case_results(item["case_results"]),
        reproducibility=_reproducibility(item["reproducibility"]),
        architecture=_architecture(item["architecture"]),
    )


def _package_binding(value: object) -> HKEXRulebookPackageBinding:
    item = _document(value)
    _exact_keys(item, {"package_id", "package_version", "package_fingerprint"})
    return HKEXRulebookPackageBinding(
        package_id=_json_text(item["package_id"]),
        package_version=_json_text(item["package_version"]),
        package_fingerprint=_json_fingerprint(item["package_fingerprint"]),
    )


def _suite_binding(value: object) -> HKEXConformanceSuiteBinding:
    item = _document(value)
    _exact_keys(
        item,
        {
            "universe",
            "universe_fingerprint",
            "case_count",
            "coverage_cell_count",
            "pair_count",
        },
    )
    return HKEXConformanceSuiteBinding(
        universe=_artifact(item["universe"]),
        universe_fingerprint=_json_fingerprint(item["universe_fingerprint"]),
        case_count=_json_integer(item["case_count"]),
        coverage_cell_count=_json_integer(item["coverage_cell_count"]),
        pair_count=_json_integer(item["pair_count"]),
    )


def _artifact(value: object) -> HKEXConformanceArtifactBinding:
    item = _document(value)
    _exact_keys(item, {"path", "byte_size", "fingerprint"})
    return HKEXConformanceArtifactBinding(
        path=_json_text(item["path"]),
        byte_size=_json_integer(item["byte_size"]),
        fingerprint=_json_fingerprint(item["fingerprint"]),
    )


def _artifact_set(value: object) -> HKEXConformanceArtifactSetBinding:
    item = _document(value)
    _exact_keys(item, {"members", "inventory_fingerprint"})
    return HKEXConformanceArtifactSetBinding(
        members=tuple(_artifact(member) for member in _json_array(item["members"])),
        inventory_fingerprint=_json_fingerprint(item["inventory_fingerprint"]),
    )


def _case_results(value: object) -> HKEXConformanceCaseResultSet:
    item = _document(value)
    _exact_keys(item, {"case_count", "members", "result_set_fingerprint"})
    if _json_integer(item["case_count"]) != HKEX_CONFORMANCE_CASE_RESULT_COUNT:
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
    members: list[HKEXConformanceCaseResultBinding] = []
    for raw_member in _json_array(item["members"]):
        member = _document(raw_member)
        _exact_keys(member, {"case_id", "result"})
        members.append(
            HKEXConformanceCaseResultBinding(
                case_id=_json_text(member["case_id"]),
                result=_artifact(member["result"]),
            )
        )
    return HKEXConformanceCaseResultSet(
        members=tuple(members),
        result_set_fingerprint=_json_fingerprint(item["result_set_fingerprint"]),
    )


def _reproducibility(value: object) -> HKEXConformanceReproducibilityProof:
    item = _document(value)
    _exact_keys(item, {"isolated_run_count", "runs", "byte_identical"})
    if _json_integer(item["isolated_run_count"]) != _ISOLATED_RUN_COUNT:
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
    raw_runs = _json_array(item["runs"])
    if len(raw_runs) != _ISOLATED_RUN_COUNT:
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
    runs: list[HKEXConformanceRunBinding] = []
    for raw_run in raw_runs:
        run = _document(raw_run)
        _exact_keys(
            run,
            {"run_id", "case_count", "result_set_fingerprint", "tree_fingerprint"},
        )
        runs.append(
            HKEXConformanceRunBinding(
                run_id=_json_text(run["run_id"]),
                case_count=_json_integer(run["case_count"]),
                result_set_fingerprint=_json_fingerprint(run["result_set_fingerprint"]),
                tree_fingerprint=_json_fingerprint(run["tree_fingerprint"]),
            )
        )
    return HKEXConformanceReproducibilityProof(
        runs=(runs[0], runs[1]),
        byte_identical=_json_bool(item["byte_identical"]),
    )


def _architecture(value: object) -> HKEXConformanceArchitectureProof:
    item = _document(value)
    _exact_keys(
        item,
        {
            "tool",
            "policy",
            "applications",
            "packages",
            "dependency_edges",
            "capability_ports",
            "policy_fingerprint",
            "report_fingerprint",
            "result",
        },
    )
    return HKEXConformanceArchitectureProof(
        tool=_artifact(item["tool"]),
        policy=_artifact(item["policy"]),
        applications=_json_integer(item["applications"]),
        packages=_json_integer(item["packages"]),
        dependency_edges=_json_integer(item["dependency_edges"]),
        capability_ports=_json_integer(item["capability_ports"]),
        policy_fingerprint=_json_fingerprint(item["policy_fingerprint"]),
        report_fingerprint=_json_fingerprint(item["report_fingerprint"]),
        result=_json_text(item["result"]),
    )


def _relative_path(value: object) -> str:
    text = _text(value)
    if (
        text.startswith("/")
        or "\\" in text
        or "//" in text
        or any(part in {"", ".", ".."} for part in text.split("/"))
    ):
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
    return text


def _fingerprint(value: object) -> str:
    text = _text(value)
    if fullmatch(_FINGERPRINT_PATTERN, text) is None:
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.EVIDENCE)
    return text


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
    return value


def _document(value: object) -> dict[str, object]:
    if not _is_object_dict(value):
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
    result: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
        result[key] = item
    return result


def _exact_keys(value: dict[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)


def _json_array(value: object) -> tuple[object, ...]:
    if not _is_object_list(value):
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
    return tuple(value)


def _json_strings(value: object) -> tuple[str, ...]:
    values = tuple(_json_text(item) for item in _json_array(value))
    if not values or len(values) != len(set(values)):
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
    return values


def _json_text(value: object) -> str:
    return _text(value)


def _json_fingerprint(value: object) -> str:
    return _fingerprint(value)


def _json_integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
    return value


def _json_bool(value: object) -> bool:
    if type(value) is not bool:
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)
    return value


def _constant(value: object, expected: str) -> None:
    if _json_text(value) != expected:
        raise HKEXConformanceAttestationError(HKEXConformanceAttestationErrorCode.CONTRACT)


def _is_object_dict(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return isinstance(value, list)
