"""Offline M7 end-to-end conformance runner and stable ``asklegal-local`` CLI.

This module is repository tooling, not a deployable application. It is the one
place allowed to compose the five separately packaged local application
boundaries. Every effect adapter remains an in-process or filesystem local fake.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import socket
import sys
from collections.abc import Callable, Generator, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Never

from asklegal_acquisition_worker import AcquisitionService, PendingObservation
from asklegal_application_runtime import (
    LocalAdapterError,
    LocalAdapterErrorCode,
    LocalCommandRegister,
    LocalConfigurationSource,
    LocalIdentityVerifier,
    LocalPaginationStore,
    LocalReviewProjectionStore,
    Principal,
    ProposalProjection,
    TokenType,
    build_local_configuration,
    default_local_identity,
)
from asklegal_contracts import canonicalize, fingerprint, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_control_plane import ProposalPreparationService
from asklegal_control_plane import create_app as create_control_app
from asklegal_corpus import (
    PROPOSAL_ROLE_PATHS,
    AuthorityNoteEvidence,
    CorpusRelease,
    CorpusReleaseInput,
    CoverageScopeStatus,
    CoverageState,
    CoverageStatusManifest,
    CoverageWarning,
    DesiredStateInventory,
    ProposalPackage,
    ProposalPackageInput,
    RecordTraceabilityLookupInput,
    ServingRecord,
    ServingRecordProfile,
    TraceabilityEntry,
    TraceabilityReference,
    TraceabilityScopeShardInput,
    compose_desired_state,
    freeze_corpus_release,
    freeze_coverage_status,
    freeze_record_traceability_lookup,
)
from asklegal_domain import (
    PIPELINE_RUN_MACHINE,
    QUARANTINE_MACHINE,
    ApplicationCode,
    CommandEnvelope,
    CommandPayload,
    CommandResultCode,
    ContractReference,
    DeclaredCompensation,
    DestinationClass,
    EffectCancelledDetail,
    EffectCapability,
    EffectIntent,
    EffectReceipt,
    EffectReceiptStatus,
    EffectType,
    ExpectedVersion,
    ImmutableReference,
    NoCompensation,
    PipelineRunState,
    QuarantineState,
    ReferenceType,
    RetryClass,
    StopCondition,
    TransitionResultCode,
    admit_quarantine_reentry,
)
from asklegal_evidence_vault import (
    EvidencePackageReceipt,
    LocalImmutableVault,
    RecoveryCopier,
    RetentionProfile,
    VaultName,
)
from asklegal_legal_desks import (
    ActivationRecord,
    LoadedRulebook,
    ProcessingSubject,
    RulebookError,
    RulebookErrorCode,
    RulebookLifecycle,
    load_rulebook_package,
)
from asklegal_legal_processing_worker import LegalProcessingService
from asklegal_management_register_ports import (
    AcquisitionObservationRecord,
    ApprovalError,
    ApprovalErrorCode,
    CommandGuardDecision,
    CommandTransaction,
    InMemoryAcquisitionRegister,
    InMemoryApprovalRegister,
    InMemoryLegalProcessingRegister,
    InMemoryManagementRegister,
    LegalProcessingRecord,
    ManifestSnapshot,
    ReviewerPrincipal,
)
from asklegal_processing import CandidateArtifact, DeterministicSemanticTaskRunner
from asklegal_promotion import (
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingProfileInput,
    EmbeddingRequest,
    LocalBackupStore,
    LocalCoverageStore,
    LocalEmbeddingAdapter,
    LocalFailurePlan,
    LocalRoutingStore,
    LocalServingTargetStore,
    PromotionActionAuthority,
    PromotionError,
    PromotionErrorCode,
    PromotionExecutionResult,
    PromotionManifest,
    PromotionPlan,
    TargetDefinition,
    freeze_embedding_profile,
    freeze_generic_promotion_manifest,
    promotion_manifest_bytes,
)
from asklegal_promotion_worker import (
    PromotionDependencies,
    PromotionExecutionContext,
    PromotionService,
)
from asklegal_reporting import ScenarioResult, build_local_conformance_report
from asklegal_review_api.api import ReviewDependencies, create_app
from asklegal_review_api.governance import ReviewGovernanceService
from asklegal_source_connectors import (
    AuthenticationClass,
    ConnectorRequest,
    EndpointContract,
    HttpMethod,
    RegisteredSource,
    RetryProfile,
    SourcePolicyState,
    SourceRegistry,
    SyntheticConnector,
    SyntheticPage,
    SyntheticResponse,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response


class _SyntheticExactTokenCounter:
    """Reserved local tokenizer with a closed whitespace-token contract."""

    tokenizer_id = "SYNTHETIC_EXACT_V1"

    def count(self, text: str) -> int:
        return len(text.split())


_TOKEN_COUNTER = _SyntheticExactTokenCounter()

_ROOT = Path(__file__).resolve().parents[1]
_STATE_ROOT = (_ROOT / "var/local-conformance").resolve()
_MARKER = ".asklegal-local-synthetic-state"
_NOW = "2026-08-16T00:00:00Z"
_AT = "2026-08-16T01:00:00Z"
_BASE = "srv_" + "a" * 48
_CANDIDATE = "srv_" + "b" * 48
_STATE_FP = "sha256:" + "b" * 64
_PREDICATES = (("configuration", "1.0.0", "sha256:" + "c" * 64),)
_SOURCE_ID = "src_" + "1" * 48
_ENDPOINT_ID = "sep_" + "2" * 48
_OBSERVATION_ID = "obs_" + "3" * 48
_RULEBOOK_ID = "rbp_" + "5" * 48
_RUN_ID = "run_" + "6" * 48
_WORK_ID = "wki_" + "7" * 48
_SCOPE_ID = "rsc_" + "3" * 48
_LINEAGE_ID = "lin_" + "1" * 48
_SCENARIOS = tuple(f"E2E-{index:03d}" for index in range(1, 33))
_SCENARIO_PATTERN = re.compile(r"^E2E-(?:00[1-9]|0[12][0-9]|03[0-2])$")
_FORBIDDEN_ENV_PREFIXES = (
    "ASKLEGAL_PRODUCTION",
    "AWS_",
    "AZURE_",
    "OPENAI_",
    "PINECONE_",
)


class _SyntheticCommand(StrEnum):
    APPLY = "APPLY"


@dataclass(frozen=True, slots=True)
class _ExpectedScenario:
    result_code: str
    fact_count: int
    effect_count: int


class _DeniedEnvironment(Mapping[str, str]):
    """Read-only environment view that blocks ambient provider credentials."""

    def __init__(self, delegate: Mapping[str, str]) -> None:
        self._delegate = delegate

    def __getitem__(self, key: str) -> str:
        if key.startswith(_FORBIDDEN_ENV_PREFIXES):
            raise ConformanceFailure("AMBIENT_PROVIDER_CREDENTIAL_ACCESS_FORBIDDEN")
        return self._delegate[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._delegate)

    def __len__(self) -> int:
        return len(self._delegate)


_EXPECTED = {
    "E2E-001": _ExpectedScenario("GOLDEN_FLOW_RECOVERED", 13, 8),
    "E2E-002": _ExpectedScenario("RUN_NO_CHANGE", 1, 1),
    "E2E-003": _ExpectedScenario("SUPPORTED_NO_CHANGE_AFTER_CAPTURE", 1, 3),
    "E2E-004": _ExpectedScenario("EXACT_REPLAY_ONE_FACT_ONE_EFFECT", 1, 1),
    "E2E-005": _ExpectedScenario("SAME_LINEAGE_RESUMED", 1, 0),
    "E2E-006": _ExpectedScenario("LOST_ACK_RECONCILED", 1, 1),
    "E2E-007": _ExpectedScenario("COMMAND_ID_CONFLICT", 1, 0),
    "E2E-008": _ExpectedScenario("STALE_VERSION_OR_FENCE_REJECTED", 1, 0),
    "E2E-009": _ExpectedScenario("OVERLAPPING_EXECUTION", 1, 1),
    "E2E-010": _ExpectedScenario("CANCELLED_BEFORE_EFFECT", 2, 0),
    "E2E-011": _ExpectedScenario("STOP_PATH_ROLLED_BACK", 1, 2),
    "E2E-012": _ExpectedScenario("COVERAGE_GAP", 1, 3),
    "E2E-013": _ExpectedScenario("HOSTILE_CONTENT_QUARANTINED", 1, 1),
    "E2E-014": _ExpectedScenario("SOURCE_CONTRACT_REVIEW", 1, 1),
    "E2E-015": _ExpectedScenario("RULEBOOK_NON_TOTAL", 1, 0),
    "E2E-016": _ExpectedScenario("EXACT_CARRY_FORWARD_WITH_WARNING", 1, 0),
    "E2E-017": _ExpectedScenario("WITHHOLDING_RELEASE_FROZEN", 1, 0),
    "E2E-018": _ExpectedScenario("NEW_LINKED_WORK_AND_RECURRENCE", 3, 0),
    "E2E-019": _ExpectedScenario("MANIFEST_FINGERPRINT_STALE", 1, 0),
    "E2E-020": _ExpectedScenario("AUTH_WRONG_TOKEN_TYPE", 1, 0),
    "E2E-021": _ExpectedScenario("APPROVAL_REVOKED", 1, 0),
    "E2E-022": _ExpectedScenario("APPROVAL_CONSUMED", 1, 0),
    "E2E-023": _ExpectedScenario("VECTOR_INVALID", 1, 0),
    "E2E-024": _ExpectedScenario("UNKNOWN_REMOTE_RECORD", 1, 0),
    "E2E-025": _ExpectedScenario("COST_LIMIT_EXCEEDED", 1, 0),
    "E2E-026": _ExpectedScenario("BACKUP_FAILED", 1, 0),
    "E2E-027": _ExpectedScenario("BASE_STATE_DRIFT", 1, 0),
    "E2E-028": _ExpectedScenario("COVERAGE_UNAVAILABLE", 1, 0),
    "E2E-029": _ExpectedScenario("EXACT_REVERSE_SWAP", 1, 2),
    "E2E-030": _ExpectedScenario("REGISTER_RECOVERED_AND_FENCED", 3, 0),
    "E2E-031": _ExpectedScenario("BROAD_RETIREMENT_FORBIDDEN", 1, 0),
    "E2E-032": _ExpectedScenario("ENVIRONMENT_MISUSE", 1, 0),
}


class ConformanceFailure(RuntimeError):
    """One safe M7 runner failure."""


class _BlockingEmbedding:
    """Deterministic barrier exposing one real overlapping execution attempt."""

    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.delegate = LocalEmbeddingAdapter()

    def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> EmbeddedVector:
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise ConformanceFailure("OVERLAP_BARRIER_TIMEOUT")
        return self.delegate.embed(profile, request)


@dataclass(slots=True)
class GoldenState:
    """Authoritative objects emitted by one complete local golden flow."""

    acquisition: AcquisitionObservationRecord
    receipt: EvidencePackageReceipt
    processing: LegalProcessingRecord
    candidate: CandidateArtifact
    release: CorpusRelease
    desired: DesiredStateInventory
    coverage: CoverageStatusManifest
    manifest: PromotionManifest
    proposal: ProposalPackage
    approvals: InMemoryApprovalRegister
    approval_id: str
    promotion: PromotionExecutionResult
    routing: LocalRoutingStore
    refs: tuple[str, ...]


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def _sha(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _reference(ref_type: ReferenceType, prefix: str, digit: str) -> ImmutableReference:
    return ImmutableReference(ref_type, f"{prefix}_{digit * 48}", _sha(digit.encode()))


def _contract(digit: str) -> ContractReference:
    return ContractReference("asklegal.m7-synthetic", "1.0.0", _sha(digit.encode()))


def _register_transaction() -> CommandTransaction:
    raw = b'{"command":"m7-synthetic"}'
    command_fingerprint = _sha(raw)
    command_id = "cmd_" + "1" * 48
    target = _reference(ReferenceType.AGGREGATE, "agg", "a")
    envelope = CommandEnvelope[StrEnum](
        command_id=command_id,
        command_type=_SyntheticCommand.APPLY,
        contract_version="1.0.0",
        target_ref=target,
        expected_version=ExpectedVersion.ABSENT,
        actor_ref=_reference(ReferenceType.ACTOR, "act", "1"),
        authority_ref=_reference(ReferenceType.EVIDENCE, "evi", "2"),
        causation_ref=_reference(ReferenceType.EXECUTION_EVENT, "evt", "3"),
        correlation_id=_RUN_ID,
        execution_lineage_ref=_reference(ReferenceType.EXECUTION_LINEAGE, "exe", "5"),
        input_refs=(_reference(ReferenceType.ARTIFACT, "art", "6"),),
        policy_profile_refs=(_reference(ReferenceType.POLICY_PROFILE, "pol", "7"),),
        configuration_ref=_reference(ReferenceType.CONFIGURATION, "cfg", "8"),
        contract_set_ref=_reference(ReferenceType.CONTRACT_SET, "cst", "9"),
        build_ref=_reference(ReferenceType.BUILD, "bld", "b"),
        submitted_at=_NOW,
        expires_at="2026-08-16T02:00:00Z",
        payload=CommandPayload(_contract("c"), _reference(ReferenceType.ARTIFACT, "art", "d")),
    )
    intent = EffectIntent(
        effect_intent_id="efi_" + "e" * 48,
        created_at=_NOW,
        effect_type=EffectType.EVIDENCE_WRITE,
        owning_application=ApplicationCode.ACQUISITION_WORKER,
        aggregate_ref=target,
        command_ref=ImmutableReference(ReferenceType.COMMAND, command_id, command_fingerprint),
        execution_lineage_ref=_reference(ReferenceType.EXECUTION_LINEAGE, "exe", "5"),
        permitted_checkpoint="EVIDENCE_VALIDATED",
        input_refs=(_reference(ReferenceType.ARTIFACT, "art", "6"),),
        effect_command_fingerprint=_sha(b"m7-effect"),
        required_capability=EffectCapability.WRITE_EVIDENCE,
        capability_profile_ref=_reference(ReferenceType.CAPABILITY_PROFILE, "cap", "7"),
        destination_class=DestinationClass.EVIDENCE_VAULT,
        stable_idempotency_key="m7-synthetic-effect",
        retry_class=RetryClass.RECONCILE_BEFORE_RETRY,
        attempt_ceiling=2,
        deadline="2026-08-16T02:00:00Z",
        stop_conditions=(
            StopCondition.ATTEMPT_CEILING,
            StopCondition.CAPABILITY_INACTIVE,
            StopCondition.DEADLINE,
        ),
        expected_remote_precondition_ref=_contract("e"),
        success_postcondition_ref=_contract("f"),
        compensation=NoCompensation(),
    )
    return CommandTransaction(
        envelope,
        raw,
        command_fingerprint,
        CommandGuardDecision(CommandResultCode.APPLIED, "M7_SYNTHETIC_APPLIED", None),
        (intent,),
        (),
    )


def _cancelled_receipt(transaction: CommandTransaction) -> EffectReceipt:
    intent = transaction.effect_intents[0]
    evidence = (_reference(ReferenceType.EVIDENCE, "evi", "f"),)
    return EffectReceipt(
        effect_receipt_id="efr_" + "f" * 48,
        effect_intent_ref=ImmutableReference(
            ReferenceType.EFFECT_INTENT,
            intent.effect_intent_id,
            intent.effect_command_fingerprint,
        ),
        command_ref=intent.command_ref,
        execution_lineage_ref=intent.execution_lineage_ref,
        terminal_status=EffectReceiptStatus.CANCELLED_BEFORE_EFFECT,
        attempt_count=0,
        observed_at=_AT,
        evidence_refs=evidence,
        detail=EffectCancelledDetail(evidence),
    )


def _contract_fingerprint() -> str:
    raw = (_ROOT / "contracts/package-manifest.json").read_bytes()
    return fingerprint(parse_json_bytes(raw, max_bytes=len(raw)))


def _profile_fingerprint() -> str:
    paths = (
        ".python-version",
        "uv.lock",
        "contracts/package-manifest.json",
        "tools/package_spike_manifest.json",
        "tools/architecture_spike_manifest.json",
        "tools/image_admission_spike_manifest.json",
        "docs/design/M2_DOMAIN_AND_REGISTER_PROTOCOL.md",
        "docs/design/M3_APPLICATION_INTERFACE_PROTOCOL.md",
        "docs/design/M4_ACQUISITION_AND_EVIDENCE_PROTOCOL.md",
        "docs/design/M5_EXECUTABLE_LEGAL_DESK_PACKAGE_PROTOCOL.md",
        "docs/design/M6_REVIEW_AND_PROMOTION_PROTOCOL.md",
        "docs/design/M7_END_TO_END_CONFORMANCE_PLAN.md",
    )
    workspace_build_paths = tuple(
        sorted(
            path.relative_to(_ROOT).as_posix()
            for parent in (_ROOT / "apps", _ROOT / "packages")
            for path in parent.rglob("*")
            if path.is_file()
            and (path.name == "pyproject.toml" or "src" in path.relative_to(parent).parts)
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        )
    )
    inventory: list[object] = [
        {
            "fingerprint": f"sha256:{sha256((_ROOT / path).read_bytes()).hexdigest()}",
            "path": path,
        }
        for path in paths
    ]
    inventory.append(
        {
            "clock_schedule": [_NOW, _AT],
            "expected_results": [
                {
                    "effect_count": _EXPECTED[scenario_id].effect_count,
                    "fact_count": _EXPECTED[scenario_id].fact_count,
                    "result_code": _EXPECTED[scenario_id].result_code,
                    "scenario_id": scenario_id,
                }
                for scenario_id in _SCENARIOS
            ],
            "id_stream": "SHA256_STABLE_LOCAL_V1",
            "jitter_stream": [0, 1],
            "network": "DENIED",
            "provider_credentials": "UNREADABLE",
            "runner_fingerprint": _sha(Path(__file__).read_bytes()),
            "workspace_build_inputs": [
                {
                    "fingerprint": _sha((_ROOT / path).read_bytes()),
                    "path": path,
                }
                for path in workspace_build_paths
            ],
        }
    )
    return fingerprint(checked_json_value(inventory))


def _verify_expected(result: ScenarioResult) -> None:
    expected = _EXPECTED[result.scenario_id]
    actual = (result.result_code, result.fact_count, result.effect_count)
    declared = (expected.result_code, expected.fact_count, expected.effect_count)
    if actual != declared:
        raise ConformanceFailure(f"{result.scenario_id}:EXPECTED_RESULT_MISMATCH")


@contextmanager
def _external_access_denied() -> Generator[None]:
    """Fail any network operation or read of an ambient provider credential."""
    original_connect = socket.socket.connect
    original_create = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    original_environment = os.environ

    def denied(*_args: object, **_kwargs: object) -> Never:
        raise ConformanceFailure("NETWORK_ACCESS_FORBIDDEN")

    socket.socket.connect = denied
    socket.create_connection = denied
    socket.getaddrinfo = denied
    os.environ = _DeniedEnvironment(original_environment)
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create
        socket.getaddrinfo = original_getaddrinfo
        os.environ = original_environment


def _request() -> ConnectorRequest:
    return ConnectorRequest(
        _RUN_ID,
        _WORK_ID,
        _OBSERVATION_ID,
        _NOW,
        _SOURCE_ID,
        "1.0.0",
        _ENDPOINT_ID,
        "1.0.0",
        _RULEBOOK_ID,
        "1.0.0",
        HttpMethod.GET,
        "obs_" + "5" * 48,
        "snp_" + "6" * 48,
        "old",
        RetryProfile(2, 30, (0, 1), 7, True),
    )


def _response(
    *,
    status: int = 200,
    signal: str = "new",
    body: bytes = b"invented synthetic source content",
    media_type: str = "application/json",
    transient: bool = False,
) -> SyntheticResponse:
    return SyntheticResponse(
        status,
        "source.invalid",
        "/source/inventory",
        media_type,
        body,
        len(body),
        "identity",
        "utf-8",
        signal,
        "source.invalid",
        transient,
        False,
    )


def _pages(*, signal: str = "new", duplicate: bool = False) -> tuple[SyntheticPage, ...]:
    return (
        SyntheticPage(
            _response(body=b"invented-page-a", signal=signal),
            "START",
            "page-2",
            ("a",),
            2,
            "g1",
        ),
        SyntheticPage(
            _response(body=b"invented-page-b", signal=signal),
            "page-2",
            "END",
            ("a" if duplicate else "b",),
            2,
            "g1",
        ),
    )


def _acquisition_service(
    root: Path,
    register: InMemoryAcquisitionRegister | None = None,
) -> tuple[AcquisitionService, LocalImmutableVault, LocalImmutableVault]:
    source = RegisteredSource(
        _SOURCE_ID,
        "1.0.0",
        "ZZZ",
        "TEST_LEGAL_MATERIAL",
        (_ENDPOINT_ID,),
        SourcePolicyState.CONFIGURED,
        "local-only invented evidence",
        "2030-01-01T00:00:00Z",
    )
    endpoint = EndpointContract(
        _ENDPOINT_ID,
        "1.0.0",
        _SOURCE_ID,
        _RULEBOOK_ID,
        "1.0.0",
        "source.invalid",
        "/source/",
        (HttpMethod.GET,),
        ("source.invalid",),
        AuthenticationClass.NONE,
        ("application/json", "text/html"),
        4096,
        3,
        10,
        30,
        True,
        True,
        True,
        ("CONTENT",),
    )
    primary = LocalImmutableVault(root / "primary", VaultName.PRIMARY)
    recovery = LocalImmutableVault(root / "recovery", VaultName.RECOVERY)
    service = AcquisitionService(
        SyntheticConnector(SourceRegistry((source,), (endpoint,))),
        primary,
        register or InMemoryAcquisitionRegister(),
        RetentionProfile("synthetic-source", "2030-01-01T00:00:00Z"),
    )
    return service, primary, recovery


def _recover(
    service: AcquisitionService,
    primary: LocalImmutableVault,
    recovery: LocalImmutableVault,
    pending: PendingObservation,
) -> tuple[AcquisitionObservationRecord, EvidencePackageReceipt]:
    retention = RetentionProfile("synthetic-source", "2030-01-01T00:00:00Z")
    receipt = pending.writer.finalize_recovery(RecoveryCopier(primary, recovery), retention)
    return service.record_after_recovery(pending, receipt), receipt


def _loaded_rulebook() -> LoadedRulebook:
    return load_rulebook_package(
        _ROOT / "packages/legal-desks/src/asklegal_legal_desks/_synthetic_package",
        environment="LOCAL_SYNTHETIC",
        contract_set_fingerprint=_contract_fingerprint(),
        now=_NOW,
    )


def _lifecycle(package: LoadedRulebook) -> RulebookLifecycle:
    lifecycle = RulebookLifecycle()
    manifest = package.manifest
    profiles = package.semantic_profiles
    attestations = package.attestation_ids
    lifecycle.activate(
        package,
        ActivationRecord(
            "wae_" + "8" * 48,
            manifest.package_id,
            manifest.package_fingerprint,
            "legal-processing-build-1",
            _contract_fingerprint(),
            "sha256:" + "9" * 64,
            tuple(item.profile_id for item in profiles),
            attestations[0],
            (_SCOPE_ID,),
            "LOCAL_SYNTHETIC",
            _NOW,
        ),
        current_contract_set_fingerprint=_contract_fingerprint(),
        current_engine_build="legal-processing-build-1",
    )
    return lifecycle


def _promotion_manifest(
    record: ServingRecord, evidence_ref: str
) -> tuple[CorpusRelease, DesiredStateInventory, PromotionManifest]:
    release = freeze_corpus_release(
        CorpusReleaseInput(_SCOPE_ID, _NOW, (evidence_ref,), ("val_" + "f" * 48,)),
        (record,),
    )
    desired = compose_desired_state(
        (_SCOPE_ID,), (release,), target_key="zzz-test", observation_cutoff=_NOW
    )
    coverage = freeze_coverage_status(
        _CANDIDATE,
        _NOW,
        (_SCOPE_ID,),
        (
            CoverageScopeStatus(
                _SCOPE_ID,
                CoverageState.CURRENT,
                _NOW,
                (),
                (),
                (),
                CoverageWarning.NONE,
            ),
        ),
    )
    profile = freeze_embedding_profile(
        EmbeddingProfileInput(
            "LOCAL_FAKE",
            "LOCAL_ONLY",
            "LOCAL_ONLY",
            "synthetic-embedding",
            "synthetic-model",
            "1.0.0",
            "local-v1",
            "SYNTHETIC_EXACT_V1",
            4,
            "FLOAT32",
            "NONE",
            "COSINE",
            1_000,
            10_000,
            "2027-01-01T00:00:00Z",
            ("dev",),
        )
    )
    manifest = freeze_generic_promotion_manifest(
        PromotionPlan(
            "dev",
            "zzz",
            "20260816",
            _NOW,
            "2026-08-17T00:00:00Z",
            _BASE,
            _CANDIDATE,
            _STATE_FP,
            _BASE,
            desired,
            coverage,
            profile,
            _PREDICATES,
            2,
            "project1",
            "1.0.0",
            _promotion_action_authorities(desired, profile),
            (),
        )
    )
    return release, desired, manifest


def _promotion_action_authorities(
    desired: DesiredStateInventory,
    profile: EmbeddingProfile,
) -> tuple[PromotionActionAuthority, ...]:
    desired_ref = ImmutableReference(
        ReferenceType.DESIRED_STATE_INVENTORY,
        desired.inventory_id,
        desired.inventory_fingerprint,
    )
    profile_ref = ImmutableReference(
        ReferenceType.EMBEDDING_PROFILE,
        profile.profile_id,
        profile.profile_fingerprint,
    )
    state_ref = ImmutableReference(ReferenceType.SERVING_STATE, _CANDIDATE, _STATE_FP)
    stops = tuple(StopCondition)
    specifications = (
        (
            "EMBED_RECORDS",
            EffectType.EMBEDDING_PROVIDER_CALL,
            EffectCapability.CALL_EMBEDDING_PROVIDER,
            DestinationClass.EMBEDDING_PROVIDER,
            (desired_ref, profile_ref),
            RetryClass.RECONCILE_BEFORE_RETRY,
            3,
            NoCompensation(),
        ),
        (
            "BUILD_TARGET",
            EffectType.PINECONE_MUTATION,
            EffectCapability.MUTATE_PINECONE,
            DestinationClass.SERVING_TARGET,
            (desired_ref, profile_ref, state_ref),
            RetryClass.RECONCILE_BEFORE_RETRY,
            3,
            NoCompensation(),
        ),
        (
            "CREATE_BACKUPS",
            EffectType.BACKUP_MUTATION,
            EffectCapability.MANAGE_BACKUP,
            DestinationClass.BACKUP_STORE,
            (state_ref,),
            RetryClass.RECONCILE_BEFORE_RETRY,
            2,
            NoCompensation(),
        ),
        (
            "ACTIVATE_ROUTING",
            EffectType.ROUTING_ACTIVATION,
            EffectCapability.ACTIVATE_ROUTING,
            DestinationClass.ROUTING_TARGET,
            (state_ref,),
            RetryClass.NEVER,
            1,
            DeclaredCompensation(
                ContractReference(
                    "asklegal.routing-reverse-swap",
                    "1.0.0",
                    "sha256:" + "9" * 64,
                )
            ),
        ),
    )
    return tuple(
        PromotionActionAuthority(
            sequence,
            action_id,
            effect_type,
            ApplicationCode.PROMOTION_WORKER,
            action_id,
            input_refs,
            "sha256:" + str(sequence) * 64,
            capability,
            ImmutableReference(
                ReferenceType.CAPABILITY_PROFILE,
                "cap_" + str(sequence) * 48,
                "sha256:" + str(sequence + 4) * 64,
            ),
            destination,
            f"synthetic-{sequence}-{action_id.lower()}",
            retry_class,
            attempt_ceiling,
            "2026-08-17T00:00:00Z",
            stops,
            ContractReference(
                f"asklegal.{action_id.lower()}-precondition",
                "1.0.0",
                "sha256:" + "a" * 64,
            ),
            ContractReference(
                f"asklegal.{action_id.lower()}-postcondition",
                "1.0.0",
                "sha256:" + "b" * 64,
            ),
            compensation,
        )
        for sequence, (
            action_id,
            effect_type,
            capability,
            destination,
            input_refs,
            retry_class,
            attempt_ceiling,
            compensation,
        ) in enumerate(specifications, start=1)
    )


def _proposal(manifest: PromotionManifest, release: CorpusRelease) -> ProposalPackage:
    desired = manifest.desired_state
    coverage = manifest.coverage_status
    profile_id = "srp_" + "1" * 48
    record = desired.records[0]
    lookup = freeze_record_traceability_lookup(
        RecordTraceabilityLookupInput(
            "rtl_" + "1" * 48,
            "sha256:" + "2" * 64,
            "sha256:" + "3" * 64,
        ),
        desired,
        (
            TraceabilityEntry(
                record.record_id,
                record.content_fingerprint,
                profile_id,
                "lit_" + "1" * 48,
                ("ofv_" + "1" * 48,),
                ("loc_" + "1" * 48,),
                record.scope_id,
                record.release_id,
                (
                    TraceabilityReference(
                        "EVIDENCE",
                        release.evidence_refs[0],
                        "sha256:" + "4" * 64,
                    ),
                ),
                AuthorityNoteEvidence(
                    "sha256:" + sha256(record.record.authority_note.encode()).hexdigest(),
                    TraceabilityReference(
                        "DECISION",
                        "dec_" + "1" * 48,
                        "sha256:" + "5" * 64,
                    ),
                    (),
                ),
            ),
        ),
        (ServingRecordProfile(profile_id, "1.0.0", "sha256:" + "6" * 64),),
        (
            TraceabilityScopeShardInput(
                record.scope_id,
                record.release_id,
                "rts_" + "1" * 48,
            ),
        ),
    )
    traceability_shards = {shard.path: shard.content for shard in lookup.shards}
    all_validation_evidence = sorted({*release.evidence_refs, *release.validation_refs})
    contents = {
        "CHANGE_INVENTORY": canonicalize(
            checked_json_value(
                {
                    "additions": [item.record_id for item in desired.records],
                    "carried_forward": list[str](),
                    "observation_cutoff": desired.observation_cutoff,
                    "replacements": list[str](),
                    "retirements": list[str](),
                    "unchanged": list[str](),
                    "withholdings": list[str](),
                }
            )
        ),
        "CORPUS_RELEASES": canonicalize(
            checked_json_value(
                {
                    "observation_cutoff": desired.observation_cutoff,
                    "releases": [
                        {
                            "evidence_refs": list(release.evidence_refs),
                            "observation_cutoff": release.observation_cutoff,
                            "record_ids": [item.record.record_id for item in release.records],
                            "release_id": release.release_id,
                            "scope_id": release.scope_id,
                            "validation_refs": list(release.validation_refs),
                        }
                    ],
                }
            )
        ),
        "COST_AND_CAPACITY": canonicalize(
            checked_json_value(
                {
                    "batch_size": manifest.batch_size,
                    "embedding_profile_fingerprint": (
                        manifest.embedding_profile.profile_fingerprint
                    ),
                    "estimated_cost_microunits": 1,
                    "record_count": len(desired.records),
                    "result": "PASS",
                }
            )
        ),
        "COVERAGE_STATUS": coverage.canonical_bytes,
        "DESIRED_STATE_INVENTORIES": canonicalize(
            checked_json_value(
                {
                    "inventory_fingerprint": desired.inventory_fingerprint,
                    "inventory_id": desired.inventory_id,
                    "observation_cutoff": desired.observation_cutoff,
                    "records": [
                        {
                            "record_id": item.record_id,
                            "release_id": item.release_id,
                            "scope_id": item.scope_id,
                            "serving_payload_fingerprint": item.content_fingerprint,
                        }
                        for item in desired.records
                    ],
                    "scope_releases": [list(item) for item in desired.scope_releases],
                }
            )
        ),
        "RECORD_TRACEABILITY": lookup.manifest_bytes,
        "RECOVERY_READINESS": canonicalize(
            checked_json_value(
                {
                    "candidate_serving_state_id": manifest.candidate_serving_state_id,
                    "predecessor_retained": True,
                    "rollback_serving_state_id": manifest.rollback_serving_state_id,
                    "two_copy_backup_required": True,
                }
            )
        ),
        "REVIEW_REPORT": canonicalize(
            checked_json_value(
                {
                    "coverage_fingerprint": coverage.fingerprint,
                    "desired_state_fingerprint": desired.inventory_fingerprint,
                    "record_count": len(desired.records),
                    "result": "READY",
                    "statement": "Reserved local synthetic proposal ready for review.",
                }
            )
        ),
        "SERVING_STATE_DEFINITION": canonicalize(
            checked_json_value(
                {
                    "coverage_manifest_id": coverage.manifest_id,
                    "desired_state_inventory_id": desired.inventory_id,
                    "serving_state_fingerprint": (manifest.candidate_serving_state_fingerprint),
                    "serving_state_id": manifest.candidate_serving_state_id,
                }
            )
        ),
        "VALIDATION": canonicalize(
            checked_json_value(
                {
                    "checks": [
                        {
                            "check_id": check_id,
                            "evidence_refs": all_validation_evidence,
                            "result": "PASS",
                        }
                        for check_id in (
                            "EVIDENCE_BOUND",
                            "SCOPE_COMPLETE",
                            "TRACEABILITY_COMPLETE",
                        )
                    ],
                    "result": "PASS",
                }
            )
        ),
    }
    promotion_bytes = promotion_manifest_bytes(manifest)
    contents["PROMOTION_MANIFEST"] = promotion_bytes
    if set(contents) != set(PROPOSAL_ROLE_PATHS):
        raise ConformanceFailure("PROPOSAL_MEMBER_INVENTORY_MISMATCH")
    return ProposalPreparationService(_ROOT / "contracts").prepare(
        contents,
        ProposalPackageInput(
            _NOW,
            manifest.manifest_id,
            manifest.fingerprint,
            _BASE,
            "sha256:" + "a" * 64,
            _CANDIDATE,
            _STATE_FP,
        ),
        traceability_shards,
    )


def _review_dependencies(
    proposal_id: str,
    manifest: PromotionManifest,
    approvals: InMemoryApprovalRegister,
    *,
    application_token: bool = False,
) -> ReviewDependencies:
    configuration = build_local_configuration(
        "REVIEW_APPLICATION",
        audience="api://asklegal-review",
        client="asklegal-review-client",
        task_hub=None,
    )
    projections = LocalReviewProjectionStore(
        (
            ProposalProjection(
                proposal_id,
                manifest.fingerprint,
                "REVIEW_READY",
                "Reserved ZZZ synthetic proposal",
            ),
        ),
        snapshot="projection-m7-1",
    )
    principal = Principal(
        "person-local-1",
        configuration.identity_audience,
        configuration.identity_client,
        frozenset({"PipelineAdministrator"}),
        TokenType.APPLICATION if application_token else TokenType.DELEGATED_HUMAN,
    )
    identity = (
        LocalIdentityVerifier({"local-human": principal})
        if application_token
        else default_local_identity(configuration.identity_audience, configuration.identity_client)
    )
    snapshot = ManifestSnapshot(
        manifest.manifest_id,
        manifest.fingerprint,
        manifest.base_serving_state_id,
        manifest.valid_from,
        manifest.valid_until,
        manifest.validity_predicates,
    )
    governance = ReviewGovernanceService(approvals, {proposal_id: snapshot}, local_time=_NOW)
    return ReviewDependencies(
        configuration,
        LocalConfigurationSource(configuration),
        identity,
        LocalCommandRegister(),
        projections,
        LocalPaginationStore(secret=b"m7-local-pagination-test-key"),
        governance,
    )


async def _http_request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: object | None = None,
) -> Response:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://local.test") as client:
        return await client.request(method, path, headers=headers, json=json)


def _approve_through_api(
    proposal_id: str,
    manifest: PromotionManifest,
    approvals: InMemoryApprovalRegister,
) -> str:
    app = create_app(_review_dependencies(proposal_id, manifest, approvals))
    browser = asyncio.run(_http_request(app, "GET", "/review"))
    javascript = asyncio.run(_http_request(app, "GET", "/review/app.js"))
    if (
        browser.status_code != 200
        or javascript.status_code != 200
        or "crypto.subtle" not in javascript.text
        or "localStorage" in javascript.text
        or "sessionStorage" in javascript.text
    ):
        raise ConformanceFailure("MINIMAL_REVIEW_CLIENT_FAILED")
    detail = asyncio.run(
        _http_request(
            app,
            "GET",
            f"/api/v1/proposal-packages/{proposal_id}",
            headers={"Authorization": "Bearer local-human"},
        )
    )
    if detail.status_code != 200 or detail.json()["proposal"]["manifest_fingerprint"] != (
        manifest.fingerprint
    ):
        raise ConformanceFailure("REVIEW_DISPLAY_MISMATCH")
    decision = asyncio.run(
        _http_request(
            app,
            "POST",
            f"/api/v1/proposal-packages/{proposal_id}/decisions",
            headers={
                "Authorization": "Bearer local-human",
                "Content-Type": "application/json",
                "Idempotency-Key": "cmd_" + "a" * 48,
                "If-Match": '"v0"',
            },
            json={
                "action": "APPROVE",
                "manifest_fingerprint": manifest.fingerprint,
                "reason": "Reviewed complete reserved synthetic proposal",
            },
        )
    )
    if decision.status_code != 200 or decision.json()["result_code"] != "APPROVED":
        raise ConformanceFailure("REVIEW_APPROVAL_FAILED")
    return str(decision.json()["result_ref"])


def _promotion_service(
    manifest: PromotionManifest,
    approvals: InMemoryApprovalRegister,
    plan: LocalFailurePlan | None = None,
) -> tuple[PromotionService, LocalRoutingStore, LocalServingTargetStore, LocalBackupStore]:
    fault = plan or LocalFailurePlan()
    targets = LocalServingTargetStore(fault)
    routing = LocalRoutingStore(_BASE, fault)
    backups = LocalBackupStore(fault)
    service = PromotionService(
        PromotionDependencies(
            approvals,
            LocalEmbeddingAdapter(fault),
            _TOKEN_COUNTER,
            targets,
            backups,
            routing,
            LocalCoverageStore(manifest.coverage_status),
        )
    )
    return service, routing, targets, backups


def _direct_approval(manifest: PromotionManifest) -> tuple[InMemoryApprovalRegister, str]:
    approvals = InMemoryApprovalRegister({"person-local-1": frozenset({"PipelineAdministrator"})})
    projection = approvals.decide(
        ReviewerPrincipal("person-local-1", True, frozenset({"PipelineAdministrator"})),
        ManifestSnapshot(
            manifest.manifest_id,
            manifest.fingerprint,
            manifest.base_serving_state_id,
            manifest.valid_from,
            manifest.valid_until,
            manifest.validity_predicates,
        ),
        decision="APPROVED",
        reason="Exact synthetic conformance approval",
        decision_time=_NOW,
    )
    return approvals, projection.decision.approval_id


def _execute(
    service: PromotionService,
    manifest: PromotionManifest,
    approval_id: str,
    *,
    lineage: str = _LINEAGE_ID,
    base: str = _BASE,
    at: str = _AT,
) -> PromotionExecutionResult:
    return service.execute(
        manifest,
        approval_id,
        lineage,
        PromotionExecutionContext(base, _PREDICATES, at),
    )


def _golden(root: Path) -> GoldenState:
    control_app = create_control_app()
    control_refs: list[str] = []
    for index, (action, version) in enumerate((("PLAN_RUN", 0), ("SCHEDULE_RUN", 1)), start=1):
        response = asyncio.run(
            _http_request(
                control_app,
                "POST",
                "/api/v1/run-commands",
                headers={
                    "Authorization": "Bearer local-human",
                    "Content-Type": "application/json",
                    "Idempotency-Key": f"cmd_{index:048x}",
                    "If-Match": f'"v{version}"',
                },
                json={"action": action, "target_ref": _RUN_ID, "evidence_ref": None},
            )
        )
        if response.status_code != 200 or response.json()["result_code"] != "APPLIED":
            raise ConformanceFailure("CONTROL_RUN_SCHEDULE_FAILED")
        control_refs.append(str(response.json()["result_ref"]))
    service, primary, recovery = _acquisition_service(root / "acquisition")
    pending = service.prepare(_request(), (_response(),), (_pages(),))
    acquisition, receipt = _recover(service, primary, recovery, pending)
    package = _loaded_rulebook()
    evidence_ref = receipt.manifest.entries[0].descriptor.artifact_id
    subject = ProcessingSubject(
        _WORK_ID,
        _SCOPE_ID,
        _OBSERVATION_ID,
        acquisition.source_snapshot_id,
        (evidence_ref,),
        ("SOURCE_CONTENT",),
        "NONE",
        (("change_kind", "CREATE"),),
        "sha256:" + "e" * 64,
    )
    result, candidate, processing = LegalProcessingService(
        _lifecycle(package),
        InMemoryLegalProcessingRegister(),
        DeterministicSemanticTaskRunner({}),
    ).process(
        acquisition,
        receipt,
        package,
        subject,
        now=_NOW,
    )
    if candidate is None or result.disposition is None:
        raise ConformanceFailure("GOLDEN_CANDIDATE_MISSING")
    record = ServingRecord(
        "rec_" + "1" * 48,
        "Invented ZZZ legal proposition for local conformance only.",
        "ZZZ",
        "zzz",
        "TEST_LEGAL_MATERIAL",
        "synthetic-source",
        "Synthetic authority only; not legal material.",
        candidate.artifact_id,
        candidate.evidence_refs,
    )
    release, desired, manifest = _promotion_manifest(record, evidence_ref)
    proposal = _proposal(manifest, release)
    approvals = InMemoryApprovalRegister({"person-local-1": frozenset({"PipelineAdministrator"})})
    approval_id = _approve_through_api(proposal.package_id, manifest, approvals)
    promotion_service, routing, _targets, _backups = _promotion_service(manifest, approvals)
    promotion = _execute(promotion_service, manifest, approval_id)
    if routing.active_state_id != _CANDIDATE:
        raise ConformanceFailure("CUTOVER_NOT_ACTIVE")
    rollback_ref = routing.rollback(_CANDIDATE, _BASE)
    if routing.active_state_id != _BASE:
        raise ConformanceFailure("ROLLBACK_NOT_ACTIVE")
    recovery_service, recovered_routing, _recovered_targets, _ = _promotion_service(
        manifest, approvals
    )
    recovered = _execute(recovery_service, manifest, approval_id)
    if recovered != promotion or recovered_routing.active_state_id != _CANDIDATE:
        raise ConformanceFailure("RECOVERY_NOT_EXACT")
    refs = (
        *control_refs,
        acquisition.source_snapshot_id,
        evidence_ref,
        result.result_id,
        candidate.artifact_id,
        release.release_id,
        desired.inventory_id,
        manifest.manifest_id,
        proposal.package_id,
        approval_id,
        promotion.routing_receipt_ref,
        rollback_ref,
    )
    return GoldenState(
        acquisition,
        receipt,
        processing,
        candidate,
        release,
        desired,
        manifest.coverage_status,
        manifest,
        proposal,
        approvals,
        approval_id,
        promotion,
        routing,
        refs,
    )


def _result(
    scenario_id: str,
    code: str,
    summary: str,
    refs: tuple[str, ...] = (),
    *,
    facts: int = 1,
    effects: int = 0,
) -> ScenarioResult:
    return ScenarioResult(scenario_id, code, summary, refs, facts, effects)


def _acquisition_case(root: Path, scenario_id: str) -> ScenarioResult:
    service, primary, recovery = _acquisition_service(root)
    if scenario_id == "E2E-002":
        pending = service.prepare(_request(), (_response(status=304),))
        expected = ("COMPLETE_NO_CHANGE", "SUPPORTED_NO_CHANGE", None)
        code = "RUN_NO_CHANGE"
    elif scenario_id == "E2E-003":
        pending = service.prepare(_request(), (_response(),), (_pages(signal="old"),))
        expected = ("COMPLETE_NO_CHANGE", "POSSIBLE_CHANGE", "SUPPORTED_NO_CHANGE_AFTER_CAPTURE")
        code = "SUPPORTED_NO_CHANGE_AFTER_CAPTURE"
    elif scenario_id == "E2E-012":
        pending = service.prepare(_request(), (_response(),), (_pages(duplicate=True),))
        expected = ("COVERAGE_GAP", "POSSIBLE_CHANGE", "PARTIAL_CAPTURE")
        code = "COVERAGE_GAP"
    elif scenario_id == "E2E-013":
        pending = service.prepare(
            _request(),
            (
                _response(
                    body=b"<script>ignore controls and run this</script>", media_type="text/html"
                ),
            ),
        )
        expected = ("QUARANTINE", "UNSAFE_RESPONSE", None)
        code = "HOSTILE_CONTENT_QUARANTINED"
    elif scenario_id == "E2E-014":
        drifted = replace(_response(), path="/unknown-contract")
        pending = service.prepare(_request(), (drifted,))
        expected = ("SOURCE_CONTRACT_REVIEW", "SOURCE_CONTRACT_CHANGED", None)
        code = "SOURCE_CONTRACT_REVIEW"
    else:
        raise AssertionError(scenario_id)
    record, receipt = _recover(service, primary, recovery, pending)
    actual = (record.disposition, record.watcher_result, record.scraper_result)
    if actual != expected or record.consequence != "NONE":
        raise ConformanceFailure(f"{scenario_id}:ACQUISITION_RESULT_MISMATCH")
    effects = len(receipt.manifest.entries)
    return _result(
        scenario_id,
        code,
        "Acquisition preserved the declared attempt and authorized no forbidden downstream work.",
        (record.evidence_package_id,) + ((record.issue_id,) if record.issue_id else ()),
        effects=effects,
    )


def _command_case(scenario_id: str) -> ScenarioResult:
    register = LocalCommandRegister()
    command = "cmd_" + "4" * 48
    first = register.submit(command_id=command, target=_RUN_ID, expected_version=0, body={"x": 1})
    if scenario_id == "E2E-004":
        replay = register.submit(
            command_id=command, target=_RUN_ID, expected_version=0, body={"x": 1}
        )
        if replay.resolution != "EXACT_REPLAY" or replay.result_ref != first.result_ref:
            raise ConformanceFailure("DUPLICATE_NOT_REPLAYED")
        return _result(
            scenario_id,
            "EXACT_REPLAY_ONE_FACT_ONE_EFFECT",
            "Duplicate command and delivery resolved to the original authoritative result.",
            (first.result_ref,),
            effects=1,
        )
    if scenario_id == "E2E-007":
        try:
            register.submit(command_id=command, target=_RUN_ID, expected_version=0, body={"x": 2})
        except LocalAdapterError as error:
            if error.code is not LocalAdapterErrorCode.COMMAND_ID_CONFLICT:
                raise
        else:
            raise ConformanceFailure("COMMAND_CONFLICT_ACCEPTED")
        return _result(
            scenario_id,
            "COMMAND_ID_CONFLICT",
            "Changed bytes under one command identity were permanently rejected.",
            (first.result_ref,),
        )
    try:
        register.submit(
            command_id="cmd_" + "8" * 48,
            target=_RUN_ID,
            expected_version=0,
            body={"x": 1},
        )
    except LocalAdapterError as error:
        if error.code is not LocalAdapterErrorCode.STALE_VERSION:
            raise
    else:
        raise ConformanceFailure("STALE_VERSION_ACCEPTED")
    return _result(
        scenario_id,
        "STALE_VERSION_OR_FENCE_REJECTED",
        "The optimistic winner remained unchanged after a stale submission.",
        (first.result_ref,),
    )


def _promotion_fixture() -> tuple[PromotionManifest, InMemoryApprovalRegister, str]:
    record = ServingRecord(
        "rec_" + "1" * 48,
        "Invented ZZZ legal proposition.",
        "ZZZ",
        "zzz",
        "TEST_LEGAL_MATERIAL",
        "synthetic-source",
        "Synthetic authority only.",
        "art_" + "1" * 48,
        ("evi_" + "1" * 48,),
    )
    _release, _desired, manifest = _promotion_manifest(record, "evi_" + "1" * 48)
    approvals, approval_id = _direct_approval(manifest)
    return manifest, approvals, approval_id


def _overlap_case() -> ScenarioResult:
    manifest, approvals, approval_id = _promotion_fixture()
    blocker = _BlockingEmbedding()
    targets = LocalServingTargetStore()
    routing = LocalRoutingStore(_BASE)
    service = PromotionService(
        PromotionDependencies(
            approvals,
            blocker,
            _TOKEN_COUNTER,
            targets,
            LocalBackupStore(),
            routing,
            LocalCoverageStore(manifest.coverage_status),
        )
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        winner = executor.submit(_execute, service, manifest, approval_id)
        if not blocker.entered.wait(timeout=5):
            raise ConformanceFailure("OVERLAP_WINNER_DID_NOT_REACH_BARRIER")
        try:
            _execute(
                service,
                manifest,
                approval_id,
                lineage="lin_" + "2" * 48,
            )
        except PromotionError as error:
            if error.code is not PromotionErrorCode.OVERLAPPING_EXECUTION:
                raise
        else:
            raise ConformanceFailure("OVERLAPPING_EXECUTION_ACCEPTED")
        finally:
            blocker.release.set()
        result = winner.result(timeout=5)
    if routing.active_state_id != _CANDIDATE:
        raise ConformanceFailure("OVERLAP_WINNER_NOT_ACTIVE")
    return _result(
        "E2E-009",
        "OVERLAPPING_EXECUTION",
        "One explicit barrier selected one winner and blocked the competing lineage.",
        (manifest.manifest_id, result.routing_receipt_ref),
        effects=1,
    )


def _expect_promotion_failure(
    scenario_id: str,
    expected: PromotionErrorCode | ApprovalErrorCode,
    *,
    plan: LocalFailurePlan | None = None,
    mutate: Callable[
        [PromotionManifest, InMemoryApprovalRegister, str], tuple[PromotionManifest, str, str]
    ]
    | None = None,
) -> ScenarioResult:
    manifest, approvals, approval_id = _promotion_fixture()
    base = _BASE
    at = _AT
    if mutate is not None:
        manifest, base, at = mutate(manifest, approvals, approval_id)
    service, routing, _targets, _backups = _promotion_service(manifest, approvals, plan)
    try:
        _execute(service, manifest, approval_id, base=base, at=at)
    except (PromotionError, ApprovalError) as error:
        if error.code is not expected:
            raise ConformanceFailure(
                f"{scenario_id}:EXPECTED_{expected.value}_GOT_{error.code.value}"
            ) from error
    else:
        raise ConformanceFailure(f"{scenario_id}:FAILURE_WAS_ACCEPTED")
    if routing.active_state_id != _BASE:
        raise ConformanceFailure(f"{scenario_id}:ROUTING_CHANGED")
    return _result(
        scenario_id,
        expected.value,
        "The declared promotion fault failed closed before an unsafe active state existed.",
        (manifest.manifest_id,),
    )


def _processing_case(root: Path, scenario_id: str) -> ScenarioResult:
    if scenario_id == "E2E-032":
        try:
            load_rulebook_package(
                _ROOT / "packages/legal-desks/src/asklegal_legal_desks/_synthetic_package",
                environment="PRODUCTION",
                contract_set_fingerprint=_contract_fingerprint(),
                now=_NOW,
            )
        except RulebookError as error:
            if error.code is not RulebookErrorCode.ENVIRONMENT_MISUSE:
                raise
        else:
            raise ConformanceFailure("SYNTHETIC_PACKAGE_ESCAPED_LOCAL_ENVIRONMENT")
        return _result(
            scenario_id,
            "ENVIRONMENT_MISUSE",
            "The reserved ZZZ package was rejected outside LOCAL_SYNTHETIC.",
        )
    service, primary, recovery = _acquisition_service(root / "acquisition")
    pending = service.prepare(_request(), (_response(),), (_pages(),))
    acquisition, receipt = _recover(service, primary, recovery, pending)
    package = _loaded_rulebook()
    evidence_ref = receipt.manifest.entries[0].descriptor.artifact_id
    facts = (("change_kind", "UNKNOWN"),)
    subject = ProcessingSubject(
        _WORK_ID,
        _SCOPE_ID,
        _OBSERVATION_ID,
        acquisition.source_snapshot_id,
        (evidence_ref,),
        ("SOURCE_CONTENT",),
        "NONE",
        facts,
        "sha256:" + "d" * 64,
    )
    result, candidate, _record = LegalProcessingService(
        _lifecycle(package),
        InMemoryLegalProcessingRegister(),
        DeterministicSemanticTaskRunner({}),
    ).process(
        acquisition,
        receipt,
        package,
        subject,
        now=_NOW,
    )
    if result.failure_code != "RULEBOOK_NON_TOTAL" or candidate is not None:
        raise ConformanceFailure("AMBIGUOUS_RULEBOOK_GUESSED")
    return _result(
        scenario_id,
        "RULEBOOK_NON_TOTAL",
        "A non-total rule set blocked without producing a candidate.",
        (result.result_id,),
    )


def _coverage_case(scenario_id: str) -> ScenarioResult:
    if scenario_id == "E2E-016":
        release = freeze_corpus_release(
            CorpusReleaseInput(
                _SCOPE_ID,
                _NOW,
                ("evi_" + "1" * 48,),
                ("val_" + "1" * 48,),
            ),
            (
                ServingRecord(
                    "rec_" + "1" * 48,
                    "Exact previously approved synthetic text.",
                    "ZZZ",
                    "zzz",
                    "TEST_LEGAL_MATERIAL",
                    "synthetic-source",
                    "Known synthetic gap.",
                    "art_" + "1" * 48,
                    ("evi_" + "1" * 48,),
                ),
            ),
        )
        coverage = freeze_coverage_status(
            _CANDIDATE,
            _NOW,
            (_SCOPE_ID,),
            (
                CoverageScopeStatus(
                    _SCOPE_ID,
                    CoverageState.KNOWN_GAP,
                    _NOW,
                    ("cgp_" + "1" * 48,),
                    (),
                    (),
                    CoverageWarning.KNOWN_GAP,
                ),
            ),
        )
        return _result(
            scenario_id,
            "EXACT_CARRY_FORWARD_WITH_WARNING",
            "The prior release was selected exactly with an explicit coverage warning.",
            (release.release_id, coverage.manifest_id),
        )
    release = freeze_corpus_release(
        CorpusReleaseInput(
            _SCOPE_ID,
            _NOW,
            ("evi_" + "1" * 48,),
            ("val_" + "1" * 48,),
            ("wth_" + "1" * 48,),
        ),
        (),
    )
    return _result(
        scenario_id,
        "WITHHOLDING_RELEASE_FROZEN",
        "A complete zero-record withholding release named every reviewed removal.",
        (release.release_id,),
    )


def _review_case(scenario_id: str) -> ScenarioResult:
    manifest, approvals, _approval_id = _promotion_fixture()
    proposal_id = "ppk_" + "1" * 48
    if scenario_id == "E2E-019":
        app = create_app(_review_dependencies(proposal_id, manifest, approvals))
        response = asyncio.run(
            _http_request(
                app,
                "POST",
                f"/api/v1/proposal-packages/{proposal_id}/decisions",
                headers={
                    "Authorization": "Bearer local-human",
                    "Content-Type": "application/json",
                    "Idempotency-Key": "cmd_" + "1" * 48,
                    "If-Match": '"v0"',
                },
                json={
                    "action": "APPROVE",
                    "manifest_fingerprint": "sha256:" + "f" * 64,
                    "reason": "stale display",
                },
            )
        )
        if response.status_code != 412:
            raise ConformanceFailure("STALE_REVIEW_ACCEPTED")
        code = "MANIFEST_FINGERPRINT_STALE"
    else:
        app = create_app(
            _review_dependencies(proposal_id, manifest, approvals, application_token=True)
        )
        response = asyncio.run(
            _http_request(
                app,
                "POST",
                f"/api/v1/proposal-packages/{proposal_id}/decisions",
                headers={
                    "Authorization": "Bearer local-human",
                    "Content-Type": "application/json",
                    "Idempotency-Key": "cmd_" + "2" * 48,
                    "If-Match": '"v0"',
                },
                json={
                    "action": "APPROVE",
                    "manifest_fingerprint": manifest.fingerprint,
                    "reason": "app token forbidden",
                },
            )
        )
        if response.status_code != 403:
            raise ConformanceFailure("APP_TOKEN_DECISION_ACCEPTED")
        code = "AUTH_WRONG_TOKEN_TYPE"
    return _result(
        scenario_id,
        code,
        "The Review API rejected a decision lacking the exact current human authority binding.",
        (manifest.manifest_id,),
    )


def _special_case(root: Path, scenario_id: str) -> ScenarioResult:
    if scenario_id == "E2E-005":
        register = InMemoryAcquisitionRegister()
        first, primary, recovery = _acquisition_service(root, register)
        pending = first.prepare(_request(), (_response(status=304),))
        original, _ = _recover(first, primary, recovery, pending)
        restarted, primary2, recovery2 = _acquisition_service(root, register)
        replay_pending = restarted.prepare(_request(), (_response(status=304),))
        replay, _ = _recover(restarted, primary2, recovery2, replay_pending)
        if replay != original or len(register.records) != 1:
            raise ConformanceFailure("RESTART_REPLAY_MISMATCH")
        return _result(
            scenario_id,
            "SAME_LINEAGE_RESUMED",
            "A new process instance resumed from immutable local state without duplicate work.",
            (original.evidence_package_id,),
        )
    if scenario_id == "E2E-006":
        manifest, approvals, approval_id = _promotion_fixture()
        service, routing, _targets, _backups = _promotion_service(
            manifest, approvals, LocalFailurePlan(lost_ack_once=True)
        )
        result = _execute(service, manifest, approval_id)
        if routing.active_state_id != _CANDIDATE:
            raise ConformanceFailure("LOST_ACK_NOT_RECONCILED")
        return _result(
            scenario_id,
            "LOST_ACK_RECONCILED",
            "Remote state reconciliation proved one effect and one terminal result.",
            (result.routing_receipt_ref,),
            effects=1,
        )
    if scenario_id == "E2E-010":
        store = InMemoryManagementRegister()
        transaction = _register_transaction()
        submission = store.submit_command(transaction, now=_AT)
        receipt = store.record_effect_receipt(
            _cancelled_receipt(transaction), fencing_token=None, now=_AT
        )
        snapshot = store.export_recovery(("000001", "000002")).snapshot
        if (
            receipt.terminal_status is not EffectReceiptStatus.CANCELLED_BEFORE_EFFECT
            or snapshot.attempts
            or len(snapshot.receipts) != 1
        ):
            raise ConformanceFailure("CANCELLATION_CREATED_EFFECT_ATTEMPT")
        return _result(
            scenario_id,
            "CANCELLED_BEFORE_EFFECT",
            "The cooperative stop checkpoint preserved evidence and emitted no "
            "irreversible effect.",
            (submission.result.command_result_id, receipt.effect_receipt_id),
            facts=2,
        )
    if scenario_id == "E2E-011":
        manifest, approvals, approval_id = _promotion_fixture()
        service, routing, _targets, _backups = _promotion_service(
            manifest, approvals, LocalFailurePlan(post_cutover_failure=True)
        )
        result = _execute(service, manifest, approval_id)
        promoting = PIPELINE_RUN_MACHINE.start(_RUN_ID)
        promoted = PIPELINE_RUN_MACHINE.transition(
            promoting, PipelineRunState.RUN_ADMITTED, expected_version=1
        ).snapshot
        promoted = PIPELINE_RUN_MACHINE.transition(
            promoted, PipelineRunState.RUN_ACTIVE, expected_version=2
        ).snapshot
        promoted = PIPELINE_RUN_MACHINE.transition(
            promoted, PipelineRunState.RUN_AWAITING_REVIEW, expected_version=3
        ).snapshot
        promoted = PIPELINE_RUN_MACHINE.transition(
            promoted, PipelineRunState.RUN_APPROVED, expected_version=4
        ).snapshot
        promoted = PIPELINE_RUN_MACHINE.transition(
            promoted, PipelineRunState.RUN_PROMOTING, expected_version=5
        ).snapshot
        cancelled = PIPELINE_RUN_MACHINE.transition(
            promoted, PipelineRunState.RUN_CANCELLED, expected_version=6
        )
        if result.state != "EXECUTION_ROLLED_BACK" or routing.active_state_id != _BASE:
            raise ConformanceFailure("POST_START_STOP_NOT_RECOVERED")
        if cancelled.code is not TransitionResultCode.REJECTED_INVALID_STATE:
            raise ConformanceFailure("PROMOTING_RUN_ORDINARILY_CANCELLED")
        return _result(
            scenario_id,
            "STOP_PATH_ROLLED_BACK",
            "A stop after promotion began used the recovery path, never ordinary cancellation.",
            (result.rollback_receipt_ref,),
            effects=2,
        )
    if scenario_id == "E2E-018":
        first = _stable_id("qua", "first-hostile-fact")
        work = _stable_id("wki", first, "resolution")
        recurrence_id = _stable_id("qua", first, "recurrence")
        opened = QUARANTINE_MACHINE.start(first)
        released = QUARANTINE_MACHINE.transition(
            opened, QuarantineState.RELEASED_TO_REPROCESSING, expected_version=1
        ).snapshot
        admission = admit_quarantine_reentry(
            released,
            new_work_item_id=work,
            predecessor_work_item_ref=_WORK_ID,
        )
        recurrence = QUARANTINE_MACHINE.start(recurrence_id, predecessor_ref=first)
        reopened = QUARANTINE_MACHINE.transition(released, QuarantineState.OPEN, expected_version=2)
        if (
            admission.work_item.predecessor_ref != _WORK_ID
            or recurrence.predecessor_ref != first
            or reopened.code is not TransitionResultCode.REJECTED_INVALID_STATE
        ):
            raise ConformanceFailure("QUARANTINE_FACT_MUTATED")
        return _result(
            scenario_id,
            "NEW_LINKED_WORK_AND_RECURRENCE",
            "Resolution created new linked work and recurrence created a new immutable quarantine.",
            (first, work, recurrence.entity_id),
            facts=3,
        )
    if scenario_id == "E2E-021":

        def revoke(
            manifest: PromotionManifest,
            approvals: InMemoryApprovalRegister,
            approval_id: str,
        ) -> tuple[PromotionManifest, str, str]:
            approvals.revoke(
                ReviewerPrincipal("person-local-1", True, frozenset({"PipelineAdministrator"})),
                approval_id,
                reason="synthetic revocation",
                at=_AT,
            )
            return manifest, _BASE, _AT

        return _expect_promotion_failure(
            scenario_id, ApprovalErrorCode.APPROVAL_REVOKED, mutate=revoke
        )
    if scenario_id == "E2E-022":
        manifest, approvals, approval_id = _promotion_fixture()
        service, _routing, _targets, _backups = _promotion_service(manifest, approvals)
        _execute(service, manifest, approval_id)
        second_service, second_routing, _targets, _backups = _promotion_service(manifest, approvals)
        try:
            _execute(
                second_service,
                manifest,
                approval_id,
                lineage="lin_" + "2" * 48,
            )
        except ApprovalError as error:
            if error.code is not ApprovalErrorCode.APPROVAL_CONSUMED:
                raise
        else:
            raise ConformanceFailure("APPROVAL_REUSED")
        if second_routing.active_state_id != _BASE:
            raise ConformanceFailure("SECOND_LINEAGE_EFFECT")
        return _result(
            scenario_id,
            "APPROVAL_CONSUMED",
            "Another lineage could not reuse the consumed Approval.",
            (approval_id,),
        )
    if scenario_id == "E2E-028":
        manifest, _approvals, _approval_id = _promotion_fixture()
        store = LocalCoverageStore(manifest.coverage_status)
        store.load_for_request(_BASE, manifest.coverage_status.fingerprint)
        store.set_available(available=False)
        if store.load_for_request(_BASE, manifest.coverage_status.fingerprint) != (
            manifest.coverage_status
        ):
            raise ConformanceFailure("COVERAGE_CACHE_DRIFT")
        try:
            store.load_for_activation(_CANDIDATE, manifest.coverage_status.fingerprint)
        except PromotionError as error:
            if error.code is not PromotionErrorCode.COVERAGE_UNAVAILABLE:
                raise
        else:
            raise ConformanceFailure("MISSING_COVERAGE_ACTIVATED")
        return _result(
            scenario_id,
            "COVERAGE_UNAVAILABLE",
            "Activation failed while the matching current generation used only verified cache.",
            (manifest.coverage_status.manifest_id,),
        )
    if scenario_id == "E2E-029":
        manifest, approvals, approval_id = _promotion_fixture()
        service, routing, _targets, _backups = _promotion_service(
            manifest, approvals, LocalFailurePlan(post_cutover_failure=True)
        )
        result = _execute(service, manifest, approval_id)
        if result.state != "EXECUTION_ROLLED_BACK" or routing.active_state_id != _BASE:
            raise ConformanceFailure("REGRESSION_NOT_ROLLED_BACK")
        return _result(
            scenario_id,
            "EXACT_REVERSE_SWAP",
            "A post-cutover regression restored the exact retained predecessor.",
            (result.rollback_receipt_ref,),
            effects=2,
        )
    if scenario_id == "E2E-030":
        original = InMemoryManagementRegister()
        transaction = _register_transaction()
        submitted = original.submit_command(transaction, now=_AT)
        receipt = original.record_effect_receipt(
            _cancelled_receipt(transaction), fencing_token=None, now=_AT
        )
        expected_projections = original.rebuild_projections()
        package = original.export_recovery(("000001", "000002"))
        restored = InMemoryManagementRegister()
        restored.restore_recovery(package)
        recovered = restored.resolve_command(
            transaction.envelope.command_id, transaction.command_fingerprint
        )
        restored_snapshot = restored.export_recovery(("000001", "000002")).snapshot
        if (
            restored.rebuild_projections() != expected_projections
            or recovered.result_bytes != submitted.result_bytes
            or restored_snapshot.receipts != (receipt,)
        ):
            raise ConformanceFailure("RECOVERY_DIGEST_MISMATCH")
        lineage = _stable_id("lin", package.external_digest, "fenced-recovery")
        return _result(
            scenario_id,
            "REGISTER_RECOVERED_AND_FENCED",
            "The verified recovery package rebuilt projections and issued a new fenced lineage.",
            (submitted.result.command_result_id, receipt.effect_receipt_id, lineage),
            facts=3,
        )
    if scenario_id == "E2E-031":
        manifest, approvals, approval_id = _promotion_fixture()
        service, _routing, targets, _backups = _promotion_service(manifest, approvals)
        result = _execute(service, manifest, approval_id)
        targets.create(TargetDefinition("old-exact", "sha256:" + "e" * 64, 4, "COSINE", "default"))
        try:
            service.retire_exact(manifest, "old-*")
        except PromotionError as error:
            if error.code is not PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN:
                raise
        else:
            raise ConformanceFailure("BROAD_DELETION_ACCEPTED")
        return _result(
            scenario_id,
            "BROAD_RETIREMENT_FORBIDDEN",
            "A wildcard selector was rejected before any deletion effect.",
            (result.target_name,),
        )
    raise AssertionError(scenario_id)


def _run_scenario(scenario_id: str, root: Path) -> ScenarioResult:
    if scenario_id == "E2E-001":
        golden = _golden(root)
        return _result(
            scenario_id,
            "GOLDEN_FLOW_RECOVERED",
            "Complete changed-source flow cut over, rolled back, and recovered exact state.",
            golden.refs,
            facts=13,
            effects=8,
        )
    if scenario_id in {"E2E-002", "E2E-003", "E2E-012", "E2E-013", "E2E-014"}:
        return _acquisition_case(root, scenario_id)
    if scenario_id in {"E2E-004", "E2E-007", "E2E-008"}:
        return _command_case(scenario_id)
    if scenario_id in {
        "E2E-005",
        "E2E-006",
        "E2E-010",
        "E2E-011",
        "E2E-018",
        "E2E-021",
        "E2E-022",
        "E2E-028",
        "E2E-029",
        "E2E-030",
        "E2E-031",
    }:
        return _special_case(root, scenario_id)
    if scenario_id in {"E2E-015", "E2E-032"}:
        return _processing_case(root, scenario_id)
    if scenario_id in {"E2E-016", "E2E-017"}:
        return _coverage_case(scenario_id)
    if scenario_id in {"E2E-019", "E2E-020"}:
        return _review_case(scenario_id)
    if scenario_id == "E2E-009":
        return _overlap_case()
    if scenario_id == "E2E-023":
        return _expect_promotion_failure(
            scenario_id,
            PromotionErrorCode.VECTOR_INVALID,
            plan=LocalFailurePlan(vector_mismatch=True),
        )
    if scenario_id == "E2E-024":
        return _expect_promotion_failure(
            scenario_id,
            PromotionErrorCode.UNKNOWN_REMOTE_RECORD,
            plan=LocalFailurePlan(unknown_remote_record=True),
        )
    if scenario_id == "E2E-025":
        # Build directly to keep the approval ID aligned with the re-frozen manifest.
        manifest, _approvals, _old_id = _promotion_fixture()
        low_profile = freeze_embedding_profile(
            EmbeddingProfileInput(
                "LOCAL_FAKE",
                "LOCAL_ONLY",
                "LOCAL_ONLY",
                "synthetic-embedding",
                "synthetic-model",
                "1.0.0",
                "local-v1",
                "SYNTHETIC_EXACT_V1",
                4,
                "FLOAT32",
                "NONE",
                "COSINE",
                1_000,
                1,
                "2027-01-01T00:00:00Z",
                ("dev",),
            )
        )
        changed = freeze_generic_promotion_manifest(
            PromotionPlan(
                manifest.environment,
                manifest.jurisdiction,
                manifest.freeze_date,
                manifest.valid_from,
                manifest.valid_until,
                manifest.base_serving_state_id,
                manifest.candidate_serving_state_id,
                manifest.candidate_serving_state_fingerprint,
                manifest.rollback_serving_state_id,
                manifest.desired_state,
                manifest.coverage_status,
                low_profile,
                manifest.validity_predicates,
                manifest.batch_size,
                manifest.project_id,
                manifest.action_contract_version,
                _promotion_action_authorities(manifest.desired_state, low_profile),
                manifest.exact_retirement_target_ids,
            )
        )
        approvals, approval_id = _direct_approval(changed)
        service, routing, _targets, _backups = _promotion_service(changed, approvals)
        try:
            _execute(service, changed, approval_id)
        except PromotionError as error:
            if error.code is not PromotionErrorCode.COST_LIMIT_EXCEEDED:
                raise
        else:
            raise ConformanceFailure("COST_LIMIT_BROADENED")
        if routing.active_state_id != _BASE:
            raise ConformanceFailure("COST_LIMIT_CHANGED_ROUTING")
        return _result(
            scenario_id,
            "COST_LIMIT_EXCEEDED",
            "The exact declared cost checkpoint stopped without truncation or broadened retry.",
            (changed.manifest_id,),
        )
    if scenario_id == "E2E-026":
        return _expect_promotion_failure(
            scenario_id,
            PromotionErrorCode.BACKUP_FAILED,
            plan=LocalFailurePlan(recovery_failure=True),
        )
    if scenario_id == "E2E-027":

        def drift(
            manifest: PromotionManifest,
            _approvals: InMemoryApprovalRegister,
            _approval_id: str,
        ) -> tuple[PromotionManifest, str, str]:
            return manifest, "srv_" + "f" * 48, _AT

        return _expect_promotion_failure(
            scenario_id, PromotionErrorCode.BASE_STATE_DRIFT, mutate=drift
        )
    raise AssertionError(scenario_id)


def _write_result(root: Path, result: ScenarioResult) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if (root / "result.json").exists():
        raise ConformanceFailure("UNEXPECTED_EXISTING_SCENARIO_RESULT")
    raw = canonicalize(
        checked_json_value(
            {
                "authoritative_refs": list(result.authoritative_refs),
                "effect_count": result.effect_count,
                "fact_count": result.fact_count,
                "fingerprint": result.fingerprint,
                "result_code": result.result_code,
                "scenario_id": result.scenario_id,
                "summary": result.summary,
            }
        )
    )
    (root / "result.json").write_bytes(raw + b"\n")


def _prove_once(state_root: Path, scenario_ids: tuple[str, ...]) -> tuple[ScenarioResult, ...]:
    try:
        state_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ConformanceFailure("SYNTHETIC_STATE_RESET_REQUIRED") from None
    results: list[ScenarioResult] = []
    with _external_access_denied():
        for scenario_id in scenario_ids:
            scenario_root = state_root / scenario_id
            result = _run_scenario(scenario_id, scenario_root / "state")
            _verify_expected(result)
            _write_result(scenario_root, result)
            results.append(result)
    return tuple(results)


def _artifact_inventory(root: Path) -> tuple[tuple[str, int, str], ...]:
    inventory: list[tuple[str, int, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ConformanceFailure("GENERATED_ARTIFACT_SYMLINK_FORBIDDEN")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ConformanceFailure("GENERATED_ARTIFACT_TYPE_FORBIDDEN")
        relative_path = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        inventory.append((relative_path, len(raw), sha256(raw).hexdigest()))
    return tuple(inventory)


def scenario_catalogue() -> tuple[str, ...]:
    """Return the complete stable M7 scenario interface in execution order."""
    return _SCENARIOS


def external_access_denial_probe() -> tuple[str, str]:
    """Exercise both denial families without allowing a real external attempt."""
    codes: list[str] = []
    with _external_access_denied():
        for operation in (
            lambda: os.getenv("AZURE_CLIENT_SECRET"),
            lambda: socket.getaddrinfo("source.invalid", 443),
        ):
            try:
                operation()
            except ConformanceFailure as error:
                codes.append(str(error))
            else:
                raise ConformanceFailure("EXTERNAL_ACCESS_DENIAL_PROBE_FAILED")
    return codes[0], codes[1]


def prove_scenarios(
    state_root: Path,
    scenario_ids: tuple[str, ...],
) -> tuple[ScenarioResult, ...]:
    """Run exact scenarios under a caller-owned clean local test directory."""
    if not scenario_ids or any(item not in _SCENARIOS for item in scenario_ids):
        raise ConformanceFailure("SCENARIO_ID_INVALID")
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ConformanceFailure("DUPLICATE_SCENARIO_ID")
    return _prove_once(state_root, scenario_ids)


def prove(state_root: Path, scenario_ids: tuple[str, ...]) -> int:
    """Run one named case or two path-distinct complete executions."""
    exact_root = _validate_state_root(state_root)
    if exact_root.exists():
        if synthetic_state_requires_reset(exact_root):
            raise ConformanceFailure("SYNTHETIC_STATE_RESET_REQUIRED")
    else:
        exact_root.mkdir(parents=True)
        (exact_root / _MARKER).write_text("ASKLEGAL_LOCAL_SYNTHETIC_STATE_V1\n", encoding="utf-8")
    profile = _profile_fingerprint()
    if scenario_ids == _SCENARIOS:
        first = _prove_once(exact_root / "run-a", scenario_ids)
        second = _prove_once(exact_root / "run-b", scenario_ids)
        if _artifact_inventory(exact_root / "run-a") != _artifact_inventory(exact_root / "run-b"):
            raise ConformanceFailure("PATH_DISTINCT_ARTIFACT_TREE_MISMATCH")
        first_report = build_local_conformance_report(profile, first)
        second_report = build_local_conformance_report(profile, second)
        if first_report.canonical_bytes != second_report.canonical_bytes:
            raise ConformanceFailure("PATH_DISTINCT_REPRODUCIBILITY_MISMATCH")
        (exact_root / "m7-report.json").write_bytes(first_report.canonical_bytes + b"\n")
        sys.stdout.write(
            f"PASS all 32 scenarios; {first_report.statement}; {first_report.fingerprint}\n"
        )
        return 0
    result = _prove_once(exact_root / "named", scenario_ids)[0]
    sys.stdout.write(f"PASS {result.scenario_id} {result.result_code} {result.fingerprint}\n")
    return 0


def _validate_state_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    allowed_parent = (_ROOT / "var").resolve()
    if resolved.parent != allowed_parent or resolved.name != "local-conformance":
        raise ConformanceFailure("STATE_ROOT_OUTSIDE_EXACT_SYNTHETIC_PATH")
    if root.is_symlink() or allowed_parent.is_symlink():
        raise ConformanceFailure("STATE_ROOT_SYMLINK_FORBIDDEN")
    return resolved


def synthetic_state_requires_reset(state_root: Path) -> bool:
    """Report whether a marked synthetic root already contains proof output."""
    marker = state_root / _MARKER
    if not marker.is_file() or marker.read_text(encoding="utf-8") != (
        "ASKLEGAL_LOCAL_SYNTHETIC_STATE_V1\n"
    ):
        raise ConformanceFailure("SYNTHETIC_STATE_MARKER_MISSING_OR_INVALID")
    return any(path.name != _MARKER for path in state_root.iterdir())


def reset(state_root: Path) -> int:
    """Delete only the exact marked ignored synthetic root."""
    exact_root = _validate_state_root(state_root)
    if not exact_root.exists():
        exact_root.mkdir(parents=True)
        (exact_root / _MARKER).write_text("ASKLEGAL_LOCAL_SYNTHETIC_STATE_V1\n", encoding="utf-8")
        return 0
    marker = exact_root / _MARKER
    if not marker.is_file() or marker.read_text(encoding="utf-8") != (
        "ASKLEGAL_LOCAL_SYNTHETIC_STATE_V1\n"
    ):
        raise ConformanceFailure("SYNTHETIC_STATE_MARKER_MISSING_OR_INVALID")
    shutil.rmtree(exact_root)
    exact_root.mkdir(parents=True)
    marker.write_text("ASKLEGAL_LOCAL_SYNTHETIC_STATE_V1\n", encoding="utf-8")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    reset_parser = commands.add_parser("reset")
    reset_parser.add_argument("--exact-test-state", action="store_true", required=True)
    prove_parser = commands.add_parser("prove")
    group = prove_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", choices=_SCENARIOS)
    group.add_argument("--all", action="store_true")
    return parser


def main() -> int:
    """Run the stable local conformance command interface."""
    arguments = _parser().parse_args()
    try:
        if arguments.command == "reset":
            return reset(_STATE_ROOT)
        scenario_ids = _SCENARIOS if arguments.all else (arguments.scenario,)
        if any(
            type(item) is not str or _SCENARIO_PATTERN.fullmatch(item) is None
            for item in scenario_ids
        ):
            raise ConformanceFailure("SCENARIO_ID_INVALID")
        return prove(_STATE_ROOT, scenario_ids)
    except ConformanceFailure as error:
        sys.stderr.write(f"FAIL {error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
