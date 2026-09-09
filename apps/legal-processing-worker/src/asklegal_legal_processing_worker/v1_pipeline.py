"""Fail-closed V1 evidence, semantic, and resumable preparation boundaries.

The legacy local builder remains provider-disabled. The continuous-service builder
composes the existing strict Azure runner only from exact immutable profile and
current-capability files, exact credentials, and the topology-bound proxy. It
re-reads authority before each provider call. Separate Case and Legislation
activities persist read-back-verified preparation artifacts while explicitly
withholding release creation until their owning positive mappers exist.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Never, Protocol
from urllib.parse import urlsplit

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_evidence_vault import (
    ExactObjectReference,
    RetentionProfile,
    VaultName,
    VaultWriteReceipt,
)
from asklegal_processing import (
    AzureDeployment,
    AzureSemanticTaskRunner,
    BoundedModelTransport,
    DisabledSemanticTaskRunner,
    ExactTokenCounter,
    ModelCall,
    ProcessingError,
    ProviderBudgetRequest,
    SemanticDecision,
    SemanticProfileSet,
    SemanticTaskRequest,
    load_semantic_profile_set,
    preflight_provider_budget,
    semantic_provider_input_text,
    validate_semantic_profile_set_authority,
    validate_semantic_task_contract,
)
from asklegal_processing.profiles import ProfileError
from asklegal_reporting import (
    ExactProposalArtifactReceipt,
    ProposalEvidenceArtifact,
    parse_prepared_batch_artifact,
    prepared_batch_logical_ref,
    provider_disabled_profile_receipt_ref,
)

from asklegal_legal_processing_worker.hk_legislation_release import (
    HKLegislationAcquisitionReleaseInput,
    HKLegislationDownstreamPorts,
    accept_hk_legislation_acquisition_manifest,
    route_hk_legislation_acquisition_input,
)
from asklegal_legal_processing_worker.v1_acceptance import (
    AcceptanceInputMaterializer,
    AcceptanceInputProducer,
    AcceptanceLegalInputReader,
    AcceptanceProposalFreezer,
    LocalAcceptanceInputMaterializer,
    LocalAcceptanceInputProducer,
    LocalAcceptanceLegalInputReader,
    LocalReviewArtifactFreezer,
    unavailable_hk_v1_acceptance_legal_processing,
)
from asklegal_legal_processing_worker.v1_acceptance import (
    prepare_hk_v1_acceptance_inputs as run_acceptance_input_preparation,
)
from asklegal_legal_processing_worker.v1_acceptance import (
    start_hk_v1_acceptance_legal_processing as run_acceptance_legal_processing,
)
from asklegal_legal_processing_worker.v1_infrastructure import LocalVerifiedBatchStore
from asklegal_legal_processing_worker.v1_live_acceptance import LiveAcceptanceComponentPreparer

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task
    from asklegal_legal_desks import SemanticTaskProfile

_LOGGER = logging.getLogger("asklegal_legal_processing_worker.v1_pipeline")
_MAX_EVIDENCE_BYTES = 24_000
_SEMANTIC_CAPABILITY_DISABLED = "SEMANTIC_CAPABILITY_DISABLED"
_UTC_SECOND_TIMESTAMP_LENGTH = 20
_LEGISLATION_SPOOL_ROOT = "ASKLEGAL_HK_V1_LEGISLATION_SPOOL_ROOT"
_SEMANTIC_PROFILE_PATH = "ASKLEGAL_HK_V1_SEMANTIC_PROFILE_PATH"
_SEMANTIC_EVIDENCE_PATH = "ASKLEGAL_HK_V1_SEMANTIC_CAPABILITY_EVIDENCE_PATH"
_PROCESSING_STATE_ROOT = "ASKLEGAL_HK_V1_PROCESSING_STATE_ROOT"
_ACCEPTANCE_INPUT_ROOT = "ASKLEGAL_HK_V1_ACCEPTANCE_INPUT_ROOT"
_ACQUISITION_JOURNAL_ROOT = "ASKLEGAL_HK_V1_ACQUISITION_JOURNAL_ROOT"
_REVIEW_ARTIFACT_ROOT = "ASKLEGAL_HK_V1_REVIEW_ARTIFACT_ROOT"
_CASE_PROCESSING_POLICY_PATH = "ASKLEGAL_HK_V1_CASE_PROCESSING_POLICY_PATH"
_PACKAGE_FACTS_ROOT = "ASKLEGAL_HK_V1_PACKAGE_FACTS_ROOT"
_LEGISLATION_STAGES = ("model", "embedding", "proposal", "pinecone")
_SPOOL_CONFIGURATION_INVALID = "LEGISLATION_LOCAL_SPOOL_CONFIGURATION_INVALID"
_SPOOL_CONFLICT = "LEGISLATION_LOCAL_DISPATCH_CONFLICT"
_SPOOL_FAILED = "LEGISLATION_LOCAL_DISPATCH_FAILED"
_SPOOL_INVALID = "LEGISLATION_LOCAL_DISPATCH_INVALID"
_SPOOL_READBACK_FAILED = "LEGISLATION_LOCAL_DISPATCH_READBACK_FAILED"
_SPOOL_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "stage",
        "cycle_id",
        "observation_cutoff",
        "scope_inputs",
        "changed",
        "source_register_fingerprint",
        "source_baseline_fingerprint",
        "work_plan_fingerprint",
        "acquisition_manifest_fingerprint",
        "fingerprint",
    }
)
_BATCH_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_BATCH_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,99}$")
_BATCH_SCOPES = {
    "CASES": frozenset({"HK-CASE-BINDING-POST-1997"}),
    "LEGISLATION": frozenset(
        {
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
            "HK-LEG-ORDINANCES",
            "HK-LEG-SUBSIDIARY",
        }
    ),
}
_BATCH_STORE_FAILURES = (OSError, RuntimeError, ValueError)
_MAX_PROFILE_BYTES = 2_000_000
_MAX_CAPABILITY_EVIDENCE_BYTES = 262_144
_LIVE_CONFIGURATION_INVALID = "LIVE_SEMANTIC_CONFIGURATION_INVALID"
_LIVE_PROFILE_INVALID = "LIVE_SEMANTIC_PROFILE_INVALID"
_LIVE_EVIDENCE_INVALID = "LIVE_SEMANTIC_EVIDENCE_INVALID"
_LIVE_CREDENTIAL_INVALID = "LIVE_SEMANTIC_CREDENTIAL_INVALID"
_EXPECTED_MODEL_PROXY = ("egress-model", 3128)
_LIVE_EVIDENCE_FIELDS = frozenset(
    {
        "admitted",
        "application",
        "environment",
        "fingerprint",
        "profile_content_fingerprint",
        "profile_fingerprint",
        "role",
        "schema_id",
        "tasks",
        "valid_from",
        "valid_until",
    }
)


class ProcessingPipelineError(RuntimeError):
    """One exact processing-pipeline failure, safe to log."""


@dataclass(frozen=True, slots=True)
class VerifiedBatchEvidence:
    """One exact retained evidence object already verified by acquisition."""

    evidence_ref: str
    content: bytes
    fingerprint: str


@dataclass(frozen=True, slots=True)
class VerifiedBatchInput:
    """Provider-disabled deterministic preparation request for one V1 scope."""

    material_family: str
    scope_id: str
    batch_id: str
    observation_cutoff: str
    acquisition_manifest_fingerprint: str
    journal_head_fingerprint: str
    semantic_profiles: SemanticProfileSet
    evidence_items: tuple[VerifiedBatchEvidence, ...]


@dataclass(frozen=True, slots=True)
class PreparedVerifiedBatch:
    """Read-back-verified local parse and model-request preparation artifact."""

    material_family: str
    scope_id: str
    observation_cutoff: str
    acquisition_manifest_fingerprint: str
    journal_head_fingerprint: str
    evidence_set_fingerprint: str
    semantic_profile_fingerprint: str
    semantic_profile_receipt_ref: str
    semantic_profile_receipt_fingerprint: str
    capability_evidence_ref: str
    capability_evidence_fingerprint: str
    artifact_ref: str
    document_fingerprint: str
    artifact_fingerprint: str
    content: bytes
    provider_invocation_count: int
    release_state: str


class VerifiedBatchStore(Protocol):
    """Exact durable store used by provider-disabled batch preparation."""

    def store_exact(self, logical_key: str, content: bytes, fingerprint: str) -> bytes:
        """Create and read back one immutable artifact."""
        ...


def prepare_verified_batch(
    request: VerifiedBatchInput,
    store: VerifiedBatchStore,
) -> PreparedVerifiedBatch:
    """Parse verified bytes and store deterministic model-request preparation only."""
    _validate_verified_batch_input(request)
    semantic_profile_fingerprint = request.semantic_profiles.fingerprint
    profile_receipt, capability_evidence = issue_model_provider_disabled_evidence(
        request.semantic_profiles, request.observation_cutoff
    )
    evidence_documents: list[dict[str, JsonValue]] = []
    evidence_facts: list[dict[str, JsonValue]] = []
    model_requests: list[dict[str, JsonValue]] = []
    for item in request.evidence_items:
        try:
            document = parse_json_bytes(item.content, max_bytes=_MAX_EVIDENCE_BYTES)
        except ContractViolation as error:
            _processing_fail_from("VERIFIED_BATCH_EVIDENCE_INVALID", error)
        if (
            type(document) is not dict
            or set(document) != {"language", "subject_id", "text"}
            or canonicalize(document) != item.content
        ):
            _processing_fail("VERIFIED_BATCH_EVIDENCE_INVALID")
        language = _batch_text(document["language"])
        subject_id = _batch_text(document["subject_id"])
        text = _batch_text(document["text"])
        if language not in {"en", "zh-Hant"}:
            _processing_fail("VERIFIED_BATCH_EVIDENCE_INVALID")
        evidence_documents.append(
            {
                "evidence_ref": item.evidence_ref,
                "fingerprint": item.fingerprint,
                "language": language,
                "subject_id": subject_id,
                "text_fingerprint": f"sha256:{sha256(text.encode()).hexdigest()}",
            }
        )
        evidence_facts.append(
            {
                "evidence_ref": item.evidence_ref,
                "fingerprint": item.fingerprint,
            }
        )
        request_facts: dict[str, JsonValue] = {
            "evidence_fingerprint": item.fingerprint,
            "evidence_ref": item.evidence_ref,
            "semantic_profile_fingerprint": semantic_profile_fingerprint,
            "subject_id": subject_id,
        }
        model_requests.append(
            {
                **request_facts,
                "request_id": f"request-{sha256(canonicalize(request_facts)).hexdigest()}",
            }
        )
    evidence_set_fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(evidence_facts))).hexdigest()}"
    )
    body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1-prepared-verified-batch/v1",
            "material_family": request.material_family,
            "scope_id": request.scope_id,
            "batch_id": request.batch_id,
            "observation_cutoff": request.observation_cutoff,
            "acquisition_manifest_fingerprint": request.acquisition_manifest_fingerprint,
            "journal_head_fingerprint": request.journal_head_fingerprint,
            "semantic_profile_fingerprint": semantic_profile_fingerprint,
            "capability_evidence_ref": capability_evidence.logical_ref,
            "evidence_set_fingerprint": evidence_set_fingerprint,
            "evidence_items": evidence_documents,
            "model_requests": model_requests,
            "provider_invocation_count": 0,
            "release_state": "WITHHELD_PENDING_TWO_FAMILY_RECONCILIATION",
        }
    )
    if type(body) is not dict:  # pragma: no cover - checked literal is an object.
        _processing_fail("VERIFIED_BATCH_EVIDENCE_INVALID")
    document_fingerprint = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    content = canonicalize({**body, "fingerprint": document_fingerprint})
    artifact_fingerprint = f"sha256:{sha256(content).hexdigest()}"
    artifact_ref = prepared_batch_logical_ref(
        request.material_family,
        request.scope_id,
        request.batch_id,
        evidence_set_fingerprint,
        semantic_profile_fingerprint,
    )
    parse_prepared_batch_artifact(
        ExactProposalArtifactReceipt(artifact_ref, artifact_fingerprint), content
    )
    _store_proposal_evidence(store, profile_receipt)
    _store_proposal_evidence(store, capability_evidence)
    try:
        stored = store.store_exact(artifact_ref, content, artifact_fingerprint)
    except _BATCH_STORE_FAILURES as error:
        _processing_fail_from("VERIFIED_BATCH_STORE_FAILED", error)
    if stored != content:
        _processing_fail("VERIFIED_BATCH_STORE_READBACK_FAILED")
    return PreparedVerifiedBatch(
        material_family=request.material_family,
        scope_id=request.scope_id,
        observation_cutoff=request.observation_cutoff,
        acquisition_manifest_fingerprint=request.acquisition_manifest_fingerprint,
        journal_head_fingerprint=request.journal_head_fingerprint,
        evidence_set_fingerprint=evidence_set_fingerprint,
        semantic_profile_fingerprint=semantic_profile_fingerprint,
        semantic_profile_receipt_ref=profile_receipt.logical_ref,
        semantic_profile_receipt_fingerprint=profile_receipt.fingerprint,
        capability_evidence_ref=capability_evidence.logical_ref,
        capability_evidence_fingerprint=capability_evidence.fingerprint,
        artifact_ref=artifact_ref,
        document_fingerprint=document_fingerprint,
        artifact_fingerprint=artifact_fingerprint,
        content=content,
        provider_invocation_count=0,
        release_state="WITHHELD_PENDING_TWO_FAMILY_RECONCILIATION",
    )


def issue_model_provider_disabled_evidence(
    semantic_profiles: SemanticProfileSet,
    observation_cutoff: str,
) -> tuple[ProposalEvidenceArtifact, ProposalEvidenceArtifact]:
    """Issue local MODEL evidence only from live legal-processing profile authority."""
    try:
        validate_semantic_profile_set_authority(semantic_profiles)
    except (ProfileError, TypeError, ValueError) as error:
        _processing_fail_from("VERIFIED_BATCH_PROFILE_INVALID", error)
    if _timestamp(observation_cutoff) is None:
        _processing_fail("VERIFIED_BATCH_PROFILE_INVALID")
    profile_fingerprint = semantic_profiles.fingerprint
    profile_body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1-provider-disabled-profile-receipt/v1",
            "capability": "MODEL",
            "issuer_application": "LEGAL_PROCESSING_WORKER",
            "profile_fingerprint": profile_fingerprint,
            "status": "PROVIDER_DISABLED_PREPARATION_ONLY",
        }
    )
    profile_content, profile_receipt_fingerprint = _sealed_proposal_evidence(profile_body)
    profile_receipt = ProposalEvidenceArtifact(
        provider_disabled_profile_receipt_ref("MODEL", profile_fingerprint),
        profile_receipt_fingerprint,
        profile_content,
    )
    capability_body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1-provider-disabled-capability-evidence/v1",
            "capability": "MODEL",
            "application": "LEGAL_PROCESSING_WORKER",
            "role": "generative_llm_provider",
            "observation_cutoff": observation_cutoff,
            "profile_receipt_ref": profile_receipt.logical_ref,
            "profile_receipt_fingerprint": profile_receipt.fingerprint,
            "profile_fingerprint": profile_fingerprint,
            "status": "PROVIDER_DISABLED_PREPARATION_ONLY",
        }
    )
    evidence_content, evidence_fingerprint = _sealed_proposal_evidence(capability_body)
    evidence_ref = (
        "proposal-readiness/capability-evidence/model/"
        f"{evidence_fingerprint.removeprefix('sha256:')}.json"
    )
    return profile_receipt, ProposalEvidenceArtifact(
        evidence_ref, evidence_fingerprint, evidence_content
    )


def _sealed_proposal_evidence(body: JsonValue) -> tuple[bytes, str]:
    if type(body) is not dict:  # pragma: no cover - checked literals are objects.
        _processing_fail("VERIFIED_BATCH_PROFILE_INVALID")
    fingerprint = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    return canonicalize({**body, "fingerprint": fingerprint}), fingerprint


def _validate_verified_batch_input(request: object) -> None:
    if (
        type(request) is not VerifiedBatchInput
        or request.material_family not in _BATCH_SCOPES
        or request.scope_id not in _BATCH_SCOPES[request.material_family]
        or _BATCH_ID.fullmatch(request.batch_id) is None
        or _timestamp(request.observation_cutoff) is None
        or any(
            _BATCH_FINGERPRINT.fullmatch(value) is None
            for value in (
                request.acquisition_manifest_fingerprint,
                request.journal_head_fingerprint,
            )
        )
        or type(request.evidence_items) is not tuple
        or not request.evidence_items
        or any(type(item) is not VerifiedBatchEvidence for item in request.evidence_items)
    ):
        _processing_fail("VERIFIED_BATCH_INPUT_INVALID")
    if type(request.semantic_profiles) is not SemanticProfileSet:
        _processing_fail("VERIFIED_BATCH_PROFILE_INVALID")
    try:
        validate_semantic_profile_set_authority(request.semantic_profiles)
    except ProfileError as error:
        _processing_fail_from("VERIFIED_BATCH_PROFILE_INVALID", error)
    identities: list[str] = []
    for item in request.evidence_items:
        if (
            type(item.evidence_ref) is not str
            or not item.evidence_ref
            or type(item.content) is not bytes
            or not item.content
            or _BATCH_FINGERPRINT.fullmatch(item.fingerprint) is None
            or item.fingerprint != f"sha256:{sha256(item.content).hexdigest()}"
        ):
            _processing_fail("VERIFIED_BATCH_EVIDENCE_INVALID")
        identities.append(item.evidence_ref)
    if len(set(identities)) != len(identities):
        _processing_fail("VERIFIED_BATCH_EVIDENCE_INVALID")


def _batch_text(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        _processing_fail("VERIFIED_BATCH_EVIDENCE_INVALID")
    return value


def _store_proposal_evidence(
    store: VerifiedBatchStore,
    artifact: ProposalEvidenceArtifact,
) -> None:
    try:
        content_fingerprint = f"sha256:{sha256(artifact.content).hexdigest()}"
        stored = store.store_exact(artifact.logical_ref, artifact.content, content_fingerprint)
    except _BATCH_STORE_FAILURES as error:
        _processing_fail_from("VERIFIED_BATCH_STORE_FAILED", error)
    if stored != artifact.content:
        _processing_fail("VERIFIED_BATCH_STORE_READBACK_FAILED")


def _processing_fail(code: str) -> Never:
    raise ProcessingPipelineError(code)


def _processing_fail_from(code: str, error: Exception) -> Never:
    raise ProcessingPipelineError(code) from error


@dataclass(frozen=True, slots=True)
class SemanticCapabilityRequirement:
    """Exact local requirement checked by the disabled-only evidence guard."""

    profile_ref: ImmutableReference
    application: str
    role: str
    task: str
    cutoff: str


@dataclass(frozen=True, slots=True)
class CurrentSemanticCapabilityEvidence:
    """Reader-supplied candidate; never authority to compose an adapter here."""

    profile_ref: ImmutableReference
    profile_fingerprint: str
    application: str
    role: str
    task: str
    cutoff: str
    admitted: bool
    valid_from: str
    valid_until: str
    evidence_ref: ImmutableReference


class CurrentSemanticCapabilityEvidenceReader(Protocol):
    """Reread one candidate for an exact requirement under the disabled-only guard."""

    def read_current(self, requirement: SemanticCapabilityRequirement) -> object:
        """Return one current-evidence candidate or raise an ordinary read failure."""
        ...


class AdmittedAzureSemanticRunner:
    """Exact-profile Azure runner with mandatory local token/cost preflight."""

    def __init__(
        self,
        profiles: SemanticProfileSet,
        counter: ExactTokenCounter,
        runner: AzureSemanticTaskRunner,
    ) -> None:
        """Bind one process-issued profile set to one exact Azure runner."""
        validate_semantic_profile_set_authority(profiles)
        profiles.validate()
        if type(counter) is not ExactTokenCounter:
            message = "TOKENIZER_ID_UNSUPPORTED"
            raise ProcessingError(message)
        self._profiles = profiles
        self._counter = counter
        self._runner = runner
        self._planned: tuple[ProviderBudgetRequest, ...] = ()

    def invoke(self, profile: object, request: SemanticTaskRequest) -> SemanticDecision:
        """Revalidate authority and budget before the sole provider invocation."""
        validate_semantic_profile_set_authority(self._profiles)
        self._profiles.validate()
        admitted = next(
            (item for item in self._profiles.profiles if item.profile_id == request.profile_id),
            None,
        )
        if admitted is None or profile is not admitted:
            message = "PROFILE_REQUEST_MISMATCH"
            raise ProcessingError(message)
        if self._counter.tokenizer_id != admitted.tokenizer:
            message = "TOKENIZER_ID_UNSUPPORTED"
            raise ProcessingError(message)
        count = self._counter.count(semantic_provider_input_text(request))
        if type(count) is not int:
            message = "TOKEN_COUNT_INVALID"
            raise ProcessingError(message)
        planned = (
            *self._planned,
            ProviderBudgetRequest(admitted.profile_id, count, admitted.max_output_tokens),
        )
        preflight_provider_budget(planned, self._profiles)
        self._planned = planned
        return self._runner.invoke(admitted, request)

    def invoke_batch(
        self,
        requests: tuple[tuple[object, SemanticTaskRequest], ...],
    ) -> tuple[SemanticDecision, ...]:
        """Preflight the complete cumulative batch before its first provider call."""
        if type(requests) is not tuple or not requests:
            message = "SEMANTIC_BATCH_INVALID"
            raise ProcessingError(message)
        plans: list[ProviderBudgetRequest] = []
        admitted_requests: list[tuple[SemanticTaskProfile, SemanticTaskRequest]] = []
        for profile, request in requests:
            admitted = next(
                (item for item in self._profiles.profiles if item.profile_id == request.profile_id),
                None,
            )
            if admitted is None or profile is not admitted:
                message = "PROFILE_REQUEST_MISMATCH"
                raise ProcessingError(message)
            validate_semantic_task_contract(admitted, request)
            count = self._counter.count(semantic_provider_input_text(request))
            plans.append(
                ProviderBudgetRequest(admitted.profile_id, count, admitted.max_output_tokens)
            )
            admitted_requests.append((admitted, request))
        cumulative = self._planned + tuple(plans)
        preflight_provider_budget(cumulative, self._profiles)
        self._planned = cumulative
        return tuple(
            self._runner.invoke(profile, request) for profile, request in admitted_requests
        )

    def invoke_exact_json(
        self,
        profile: object,
        request: SemanticTaskRequest,
        *,
        output_schema: str,
    ) -> bytes:
        """Budget and execute one profile-authorized task-specific JSON request."""
        validate_semantic_profile_set_authority(self._profiles)
        admitted = next(
            (item for item in self._profiles.profiles if item.profile_id == request.profile_id),
            None,
        )
        if admitted is None or profile is not admitted or admitted.output_schema != output_schema:
            message = "PROFILE_REQUEST_MISMATCH"
            raise ProcessingError(message)
        count = self._counter.count(semantic_provider_input_text(request))
        planned = (
            *self._planned,
            ProviderBudgetRequest(admitted.profile_id, count, admitted.max_output_tokens),
        )
        preflight_provider_budget(planned, self._profiles)
        self._planned = planned
        return self._runner.invoke_exact_json(
            admitted,
            request,
            output_schema=output_schema,
        )


def compose_admitted_azure_semantic_runner(
    profiles: SemanticProfileSet,
    counter: ExactTokenCounter,
    deployment: AzureDeployment,
    transport: ModelCall,
) -> AdmittedAzureSemanticRunner:
    """Compose one no-fallback Azure boundary from issued immutable authority."""
    validate_semantic_profile_set_authority(profiles)
    profiles.validate()
    deployments = {profile.deployment_name for profile in profiles.profiles}
    api_contracts = {profile.api_contract for profile in profiles.profiles}
    output_limits = {profile.max_output_tokens for profile in profiles.profiles}
    if (
        deployments != {deployment.deployment}
        or api_contracts != {deployment.api_version}
        or len(output_limits) != 1
    ):
        message = "SEMANTIC_DEPLOYMENT_MISMATCH"
        raise ProcessingError(message)
    return AdmittedAzureSemanticRunner(
        profiles,
        counter,
        AzureSemanticTaskRunner(
            deployment,
            transport,
            max_output_tokens=next(iter(output_limits)),
        ),
    )


@dataclass(frozen=True, slots=True)
class _ImmutableProfileFileReader:
    """Expose one no-symlink file through the immutable profile-reader port."""

    path: Path
    reference: ImmutableReference

    def read_exact(self, reference: ImmutableReference) -> bytes:
        if reference != self.reference:
            raise ProcessingPipelineError(_LIVE_PROFILE_INVALID)
        return _read_immutable_file(self.path, _MAX_PROFILE_BYTES, _LIVE_PROFILE_INVALID)


def _configured_path(environment: Mapping[str, str], variable: str, *, file_required: bool) -> Path:
    value = environment.get(variable)
    if type(value) is not str or not value or value != value.strip():
        raise ProcessingPipelineError(_LIVE_CONFIGURATION_INVALID)
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        raise ProcessingPipelineError(_LIVE_CONFIGURATION_INVALID)
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        if cursor.exists() and cursor.is_symlink():
            raise ProcessingPipelineError(_LIVE_CONFIGURATION_INVALID)
    if file_required and not path.is_file():
        raise ProcessingPipelineError(_LIVE_CONFIGURATION_INVALID)
    if not file_required and path.exists() and not path.is_dir():
        raise ProcessingPipelineError(_LIVE_CONFIGURATION_INVALID)
    return path


def _read_immutable_file(path: Path, limit: int, code: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ProcessingPipelineError(code)
    try:
        first = path.read_bytes()
        second = path.read_bytes()
    except ProcessingPipelineError:
        raise
    except OSError as error:
        raise ProcessingPipelineError(code) from error
    if not first or len(first) > limit or first != second:
        raise ProcessingPipelineError(code)
    return first


def _load_live_profiles(path: Path) -> tuple[SemanticProfileSet, ImmutableReference]:
    raw = _read_immutable_file(path, _MAX_PROFILE_BYTES, _LIVE_PROFILE_INVALID)
    digest = sha256(raw).hexdigest()
    reference = ImmutableReference(
        ReferenceType.WORKFLOW_PROFILE,
        f"wap_{digest[:48]}",
        f"sha256:{digest}",
    )
    try:
        profiles = load_semantic_profile_set(_ImmutableProfileFileReader(path, reference))
    except (ProfileError, OSError, TypeError, ValueError) as error:
        raise ProcessingPipelineError(_LIVE_PROFILE_INVALID) from error
    return profiles, reference


def _validate_live_evidence(
    path: Path,
    profiles: SemanticProfileSet,
    profile_reference: ImmutableReference,
    current_time: str,
) -> str:
    raw = _read_immutable_file(path, _MAX_CAPABILITY_EVIDENCE_BYTES, _LIVE_EVIDENCE_INVALID)
    try:
        document = parse_json_bytes(raw, max_bytes=_MAX_CAPABILITY_EVIDENCE_BYTES)
    except ContractViolation as error:
        raise ProcessingPipelineError(_LIVE_EVIDENCE_INVALID) from error
    if type(document) is not dict or frozenset(document) != _LIVE_EVIDENCE_FIELDS:
        raise ProcessingPipelineError(_LIVE_EVIDENCE_INVALID)
    body = dict(document)
    supplied = body.pop("fingerprint")
    valid_from = _timestamp(document.get("valid_from"))
    valid_until = _timestamp(document.get("valid_until"))
    now = _timestamp(current_time)
    expected_tasks = sorted(profile.task for profile in profiles.profiles)
    expected_fingerprint = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    if (
        canonicalize(document) != raw
        or supplied != expected_fingerprint
        or document.get("schema_id") != "asklegal.hk-v1-current-semantic-capability-evidence/v1"
        or document.get("application") != "LEGAL_PROCESSING_WORKER"
        or document.get("role") != "generative_llm_provider"
        or document.get("admitted") is not True
        or document.get("environment") != profiles.environment
        or document.get("profile_content_fingerprint") != profile_reference.fingerprint
        or document.get("profile_fingerprint") != profiles.fingerprint
        or document.get("tasks") != expected_tasks
        or valid_from is None
        or valid_until is None
        or now is None
        or not valid_from <= now < valid_until
    ):
        raise ProcessingPipelineError(_LIVE_EVIDENCE_INVALID)
    return expected_fingerprint


@dataclass(frozen=True, slots=True)
class _LiveSemanticAuthorityGuard:
    """Re-read startup authority immediately before each provider invocation."""

    profile_path: Path
    evidence_path: Path
    profiles: SemanticProfileSet
    profile_reference: ImmutableReference
    fixed_current_time: str | None = None

    def validate_current(self) -> None:
        raw = _read_immutable_file(self.profile_path, _MAX_PROFILE_BYTES, _LIVE_PROFILE_INVALID)
        if f"sha256:{sha256(raw).hexdigest()}" != self.profile_reference.fingerprint:
            raise ProcessingPipelineError(_LIVE_PROFILE_INVALID)
        cutoff = self.fixed_current_time or datetime.now(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        _validate_live_evidence(
            self.evidence_path,
            self.profiles,
            self.profile_reference,
            cutoff,
        )


def _live_deployment_and_transport(
    infrastructure: _ProcessingInfrastructure,
) -> tuple[AzureDeployment, BoundedModelTransport]:
    try:
        provider = infrastructure.model_provider_credential.reveal()
        proxy_raw = infrastructure.model_egress_proxy_credential.reveal()
        deployment = AzureDeployment.from_credential_json(provider)
        proxy_text = proxy_raw.decode("utf-8")
        proxy = urlsplit(proxy_text)
        endpoint = urlsplit(deployment.endpoint)
        proxy_port = proxy.port
        endpoint_port = endpoint.port
    except (AttributeError, ProcessingError, UnicodeDecodeError, ValueError) as error:
        raise ProcessingPipelineError(_LIVE_CREDENTIAL_INVALID) from error
    if (
        proxy_text != proxy_text.strip()
        or proxy.scheme != "http"
        or proxy.hostname != _EXPECTED_MODEL_PROXY[0]
        or proxy_port != _EXPECTED_MODEL_PROXY[1]
        or proxy.username is not None
        or proxy.password is not None
        or proxy.path not in {"", "/"}
        or proxy.query
        or proxy.fragment
        or endpoint.scheme != "https"
        or endpoint.hostname is None
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint_port not in {None, 443}
        or endpoint.path not in {"", "/"}
        or endpoint.query
        or endpoint.fragment
    ):
        raise ProcessingPipelineError(_LIVE_CREDENTIAL_INVALID)
    return deployment, BoundedModelTransport(*_EXPECTED_MODEL_PROXY)


def build_live_activities(
    infrastructure: _ProcessingInfrastructure,
    environment: Mapping[str, str],
    *,
    current_time: str | None = None,
) -> ProcessingActivities:
    """Compose live semantic authority and local resumable state without a remote call."""
    profile_path = _configured_path(environment, _SEMANTIC_PROFILE_PATH, file_required=True)
    evidence_path = _configured_path(environment, _SEMANTIC_EVIDENCE_PATH, file_required=True)
    state_root = _configured_path(environment, _PROCESSING_STATE_ROOT, file_required=False)
    acceptance_input_root = _configured_path(
        environment, _ACCEPTANCE_INPUT_ROOT, file_required=False
    )
    acquisition_journal_root = _configured_path(
        environment, _ACQUISITION_JOURNAL_ROOT, file_required=False
    )
    review_artifact_root = _configured_path(environment, _REVIEW_ARTIFACT_ROOT, file_required=False)
    case_policy_path = _configured_path(
        environment, _CASE_PROCESSING_POLICY_PATH, file_required=True
    )
    package_facts_root = _configured_path(environment, _PACKAGE_FACTS_ROOT, file_required=False)
    profiles, profile_reference = _load_live_profiles(profile_path)
    guard = _LiveSemanticAuthorityGuard(
        profile_path, evidence_path, profiles, profile_reference, current_time
    )
    guard.validate_current()
    deployment, transport = _live_deployment_and_transport(infrastructure)
    try:
        resource = (
            files("asklegal_processing").joinpath("_resources/o200k_base.tiktoken").read_bytes()
        )
        counter = ExactTokenCounter(profiles, "o200k_base", resource)
        runner = compose_admitted_azure_semantic_runner(profiles, counter, deployment, transport)
        store = LocalVerifiedBatchStore(state_root / "prepared-batches")
    except (OSError, ProcessingError, TypeError, ValueError) as error:
        raise ProcessingPipelineError(_LIVE_CREDENTIAL_INVALID) from error
    return ProcessingActivities(
        infrastructure,
        _ActivitiesConfiguration(
            runner=runner,
            legislation_spool_root=state_root / "legislation-spool",
            semantic_profiles=profiles,
            batch_store=store,
            deployment_name=deployment.deployment,
            semantic_guard=guard,
            acceptance_input_producer=LocalAcceptanceInputProducer(
                state_root / "acceptance-processed",
                acceptance_input_root / ".staged",
                acquisition_journal_root,
                infrastructure.primary_vault,
                LiveAcceptanceComponentPreparer(
                    infrastructure.primary_vault,
                    profiles,
                    counter,
                    runner,
                    case_policy_path,
                    state_root / "legal-identities",
                    state_root / "acceptance-processed",
                    package_facts_root,
                ),
            ),
            acceptance_input_reader=LocalAcceptanceLegalInputReader(acceptance_input_root),
            acceptance_input_materializer=LocalAcceptanceInputMaterializer(
                acceptance_input_root / ".staged",
                acceptance_input_root,
            ),
            acceptance_proposal_freezer=LocalReviewArtifactFreezer(
                acceptance_input_root,
                review_artifact_root,
                infrastructure.primary_vault,
                RetentionProfile("proposal-v1", "2099-12-31T00:00:00Z"),
            ),
        ),
    )


class _PrimaryEvidenceReader(Protocol):
    """The retained-evidence operation available while provider work is disabled."""

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        """Read one exact retained evidence version."""
        ...

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        """Resolve the current exact version of one retained acquisition object."""
        ...

    @property
    def vault_name(self) -> VaultName:
        """Identify the exact Primary vault."""
        ...

    def conditional_create(
        self, logical_key: str, content: bytes, retention: RetentionProfile
    ) -> VaultWriteReceipt:
        """Retain one exact proposal root and verify its version."""
        ...


class _CredentialReader(Protocol):
    def reveal(self) -> bytes:
        """Reveal bytes only to the exact adapter parser."""
        ...


class _ProcessingInfrastructure(Protocol):
    """Only the retained-evidence dependency needed while semantic work is disabled."""

    @property
    def primary_vault(self) -> _PrimaryEvidenceReader:
        """Return the sole retained-evidence reader used by these activities."""
        ...

    @property
    def model_provider_credential(self) -> _CredentialReader:
        """Return exact staged Azure deployment material."""
        ...

    @property
    def model_egress_proxy_credential(self) -> _CredentialReader:
        """Return exact staged bounded-proxy material."""
        ...


class _LocalLegislationDownstream:
    """Persist one exact local handoff without calling a provider or target."""

    def __init__(self, stage: str, root: Path) -> None:
        self._stage = stage
        self._root = root

    def enqueue(self, value: HKLegislationAcquisitionReleaseInput) -> None:
        if type(value) is not HKLegislationAcquisitionReleaseInput:
            message = "LEGISLATION_LOCAL_DISPATCH_INVALID"
            raise ProcessingPipelineError(message)
        document = _legislation_spool_record(self._stage, value)
        encoded = canonicalize(document)
        target = (
            self._root
            / self._stage
            / f"{value.acquisition_manifest_fingerprint.removeprefix('sha256:')}.json"
        )
        try:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if target.exists():
                if target.is_symlink() or target.read_bytes() != encoded:
                    raise ProcessingPipelineError(_SPOOL_CONFLICT)
                return
            temporary = target.with_suffix(".tmp")
            with temporary.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(target)
            if target.read_bytes() != encoded:
                raise ProcessingPipelineError(_SPOOL_READBACK_FAILED)
        except OSError as error:
            raise ProcessingPipelineError(_SPOOL_FAILED) from error


def _local_legislation_downstream(
    root: Path,
) -> HKLegislationDownstreamPorts:
    """Compose the four distinct effect-free local boundary records."""
    return HKLegislationDownstreamPorts(
        _LocalLegislationDownstream("model", root),
        _LocalLegislationDownstream("embedding", root),
        _LocalLegislationDownstream("proposal", root),
        _LocalLegislationDownstream("pinecone", root),
    )


def _legislation_spool_record(
    stage: str,
    value: HKLegislationAcquisitionReleaseInput,
) -> dict[str, JsonValue]:
    body: dict[str, JsonValue] = {
        "stage": stage,
        "cycle_id": value.cycle_id,
        "observation_cutoff": value.observation_cutoff,
        "scope_inputs": [
            {
                "scope_id": item.scope_id,
                "observation_cutoff": item.observation_cutoff,
                "verified_item_refs": list(item.verified_item_refs),
                "review_issue_refs": list(item.review_issue_refs),
                "acquisition_manifest_fingerprint": item.acquisition_manifest_fingerprint,
            }
            for item in value.scope_inputs
        ],
        "changed": value.changed,
        "source_register_fingerprint": value.source_register_fingerprint,
        "source_baseline_fingerprint": value.source_baseline_fingerprint,
        "work_plan_fingerprint": value.work_plan_fingerprint,
        "acquisition_manifest_fingerprint": value.acquisition_manifest_fingerprint,
    }
    return {
        "schema_id": "asklegal.local-legislation-stage-work",
        "schema_version": "1.0.0",
        **body,
        "fingerprint": f"sha256:{sha256(canonicalize(body)).hexdigest()}",
    }


def compose_semantic_runner(
    requirement: object,
    reader: CurrentSemanticCapabilityEvidenceReader | None,
) -> DisabledSemanticTaskRunner:
    """Return the no-call runner until a later admitted adapter path is implemented.

    The reader interface is deliberately exercised and strictly checked now, but a
    self-fingerprinted profile or current-evidence-shaped object cannot enable an
    external capability. Plan 7 owns the positive reread-and-verify composition.
    """
    with suppress(Exception):
        snapshot = _requirement_snapshot(requirement)
        if snapshot is None or reader is None:
            return DisabledSemanticTaskRunner()
        profile_ref, application, role, task, cutoff = snapshot
        callback_requirement = SemanticCapabilityRequirement(
            ImmutableReference(*profile_ref), application, role, task, cutoff
        )
        candidate = reader.read_current(callback_requirement)
        if not _evidence_matches(snapshot, candidate):
            return DisabledSemanticTaskRunner()
    return DisabledSemanticTaskRunner()


def _requirement_snapshot(
    value: object,
) -> tuple[tuple[ReferenceType, str, str], str, str, str, str] | None:
    """Copy every requirement fact before a reader callback can observe it."""
    if type(value) is not SemanticCapabilityRequirement:
        return None
    profile_ref = _reference_snapshot(value.profile_ref, ReferenceType.WORKFLOW_PROFILE)
    cutoff = _timestamp(value.cutoff)
    if (
        profile_ref is None
        or type(value.application) is not str
        or type(value.role) is not str
        or type(value.task) is not str
        or cutoff is None
    ):
        return None
    return (profile_ref, value.application, value.role, value.task, cutoff)


def _evidence_matches(
    requirement: tuple[tuple[ReferenceType, str, str], str, str, str, str],
    value: object,
) -> bool:
    """Accept only a current exact evidence shape; still leave execution disabled."""
    if type(value) is not CurrentSemanticCapabilityEvidence:
        return False
    profile_ref = _reference_snapshot(value.profile_ref, ReferenceType.WORKFLOW_PROFILE)
    evidence_ref = _reference_snapshot(value.evidence_ref, ReferenceType.EVIDENCE)
    valid_from = _timestamp(value.valid_from)
    valid_until = _timestamp(value.valid_until)
    if (
        profile_ref is None
        or evidence_ref is None
        or valid_from is None
        or valid_until is None
        or type(value.profile_fingerprint) is not str
        or type(value.application) is not str
        or type(value.role) is not str
        or type(value.task) is not str
        or type(value.cutoff) is not str
        or type(value.admitted) is not bool
    ):
        return False
    expected_ref, application, role, task, cutoff = requirement
    return (
        value.admitted
        and profile_ref == expected_ref
        and value.profile_fingerprint == expected_ref[2]
        and value.application == application
        and value.role == role
        and value.task == task
        and value.cutoff == cutoff
        and valid_from <= cutoff < valid_until
    )


def _reference_snapshot(
    value: object, expected_type: ReferenceType
) -> tuple[ReferenceType, str, str] | None:
    """Reconstruct one exact reference before comparing untrusted reader values."""
    if type(value) is not ImmutableReference:
        return None
    rebuilt = ImmutableReference(value.ref_type, value.ref_id, value.fingerprint)
    if rebuilt.ref_type is not expected_type:
        return None
    return (rebuilt.ref_type, rebuilt.ref_id, rebuilt.fingerprint)


def _timestamp(value: object) -> str | None:
    """Accept only one exact UTC-second spelling for current-evidence comparison."""
    if (
        type(value) is not str
        or len(value) != _UTC_SECOND_TIMESTAMP_LENGTH
        or not value.endswith("Z")
    ):
        return None
    parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != value:
        return None
    return value


@dataclass(frozen=True, slots=True)
class _ActivitiesConfiguration:
    runner: DisabledSemanticTaskRunner | AdmittedAzureSemanticRunner
    legislation_downstream: HKLegislationDownstreamPorts | None = None
    legislation_spool_root: Path | None = None
    semantic_profiles: SemanticProfileSet | None = None
    batch_store: VerifiedBatchStore | None = None
    deployment_name: str = _SEMANTIC_CAPABILITY_DISABLED
    semantic_guard: _LiveSemanticAuthorityGuard | None = None
    acceptance_input_producer: AcceptanceInputProducer | None = None
    acceptance_input_reader: AcceptanceLegalInputReader | None = None
    acceptance_input_materializer: AcceptanceInputMaterializer | None = None
    acceptance_proposal_freezer: AcceptanceProposalFreezer | None = None


class ProcessingActivities:
    """Retained-evidence, semantic, and resumable two-family activities."""

    def __init__(
        self,
        infrastructure: _ProcessingInfrastructure,
        configuration: _ActivitiesConfiguration,
    ) -> None:
        """Compose exact injected boundaries; construction performs no remote call."""
        self._vault = infrastructure.primary_vault
        self._runner = configuration.runner
        self._semantic_profiles = configuration.semantic_profiles
        self._batch_store = configuration.batch_store
        self._deployment_name = configuration.deployment_name
        self._semantic_guard = configuration.semantic_guard
        self._acceptance_input_producer = configuration.acceptance_input_producer
        self._legislation_spool_root = configuration.legislation_spool_root
        self._legislation_downstream = (
            configuration.legislation_downstream
            or _local_legislation_downstream(
                _required_legislation_spool_root(configuration.legislation_spool_root)
            )
        )
        self._acceptance_input_reader = configuration.acceptance_input_reader
        self._acceptance_input_materializer = configuration.acceptance_input_materializer
        self._acceptance_proposal_freezer = configuration.acceptance_proposal_freezer

    @property
    def deployment(self) -> str:
        """Return the exact deployment or visible fail-closed state."""
        return self._deployment_name

    @property
    def semantic_runner(self) -> DisabledSemanticTaskRunner | AdmittedAzureSemanticRunner:
        """Expose the composed runner for local composition verification."""
        return self._runner

    @property
    def legislation_dispatch_stages(self) -> tuple[str, ...]:
        """Expose local stage records without provider material or source content."""
        if self._legislation_spool_root is None:
            return ()
        records: list[tuple[str, int, str]] = []
        for stage_index, stage in enumerate(_LEGISLATION_STAGES):
            directory = self._legislation_spool_root / stage
            if not directory.exists():
                continue
            for path in directory.glob("*.json"):
                try:
                    document = parse_json_bytes(path.read_bytes(), max_bytes=4_194_304)
                except (OSError, ContractViolation, ValueError) as error:
                    raise ProcessingPipelineError(_SPOOL_INVALID) from error
                if (
                    type(document) is not dict
                    or frozenset(document) != _SPOOL_FIELDS
                    or document.get("schema_id") != "asklegal.local-legislation-stage-work"
                    or document.get("schema_version") != "1.0.0"
                    or document.get("stage") != stage
                    or type(document.get("cycle_id")) is not str
                    or document.get("changed") is not True
                ):
                    raise ProcessingPipelineError(_SPOOL_INVALID)
                cycle_id = document["cycle_id"]
                if type(cycle_id) is not str:  # pragma: no cover - guarded above.
                    raise ProcessingPipelineError(_SPOOL_INVALID)
                manifest_fingerprint = document["acquisition_manifest_fingerprint"]
                if type(
                    manifest_fingerprint
                ) is not str or path.stem != manifest_fingerprint.removeprefix("sha256:"):
                    raise ProcessingPipelineError(_SPOOL_INVALID)
                fingerprint = document.get("fingerprint")
                body = {
                    key: value
                    for key, value in document.items()
                    if key not in {"schema_id", "schema_version", "fingerprint"}
                }
                if fingerprint != f"sha256:{sha256(canonicalize(body)).hexdigest()}":
                    raise ProcessingPipelineError(_SPOOL_INVALID)
                records.append((cycle_id, stage_index, stage))
        return tuple(item[2] for item in sorted(records))

    def read_evidence(self, _context: ActivityContext, payload: object) -> object:
        """Read exactly one retained evidence version from the Primary vault."""
        document = _payload(payload, "read_evidence")
        reference = ExactObjectReference(
            VaultName.PRIMARY,
            _text(document, "logical_key"),
            _text(document, "version_id"),
            _text(document, "fingerprint"),
            _integer(document, "byte_length"),
        )
        body = self._vault.read_exact(reference)
        _LOGGER.info(
            "LEGAL_PROCESSING_WORKER read %s bytes from %s",
            len(body),
            reference.logical_key,
        )
        result: dict[str, JsonValue] = {
            "logical_key": reference.logical_key,
            "fingerprint": reference.fingerprint,
            "evidence_ref": f"ev_{reference.fingerprint.removeprefix('sha256:')[:16]}",
            "subject_id": _optional_text(document, "endpoint_id", reference.logical_key),
            # The capture is bounded here, so an oversized body is truncated once,
            # visibly, rather than silently.
            "text": body[:_MAX_EVIDENCE_BYTES].decode("utf-8", "replace"),
            "truncated": len(body) > _MAX_EVIDENCE_BYTES,
        }
        for field in ("request_id", "task", "phase", "profile_id", "package_fingerprint"):
            if field in document:
                result[field] = _text(document, field)
        return result

    def analyse_evidence(self, _context: ActivityContext, payload: object) -> object:
        """Invoke only the exact admitted profile after all local request checks."""
        del _context
        if isinstance(self._runner, DisabledSemanticTaskRunner):
            raise ProcessingError(_SEMANTIC_CAPABILITY_DISABLED)
        if self._semantic_profiles is None:
            raise ProcessingError(_SEMANTIC_CAPABILITY_DISABLED)
        if self._semantic_guard is None:
            raise ProcessingError(_SEMANTIC_CAPABILITY_DISABLED)
        self._semantic_guard.validate_current()
        document = _payload(payload, "analyse_evidence")
        profile_id = _text(document, "profile_id")
        task = _text(document, "task")
        profile = next(
            (
                item
                for item in self._semantic_profiles.profiles
                if item.profile_id == profile_id and item.task == task
            ),
            None,
        )
        if profile is None:
            message = "PROFILE_REQUEST_MISMATCH"
            raise ProcessingError(message)
        evidence_ref = _text(document, "evidence_ref")
        phase = _semantic_phase(document)
        request = SemanticTaskRequest(
            request_id=_text(document, "request_id"),
            task=task,
            phase=phase,
            profile_id=profile_id,
            package_fingerprint=_text(document, "package_fingerprint"),
            subject_id=_text(document, "subject_id"),
            evidence_refs=(evidence_ref,),
            evidence_bytes=_text(document, "text").encode(),
            input_fingerprint=_text(document, "fingerprint"),
        )
        decision = self._runner.invoke(profile, request)
        return {
            "subject_id": request.subject_id,
            "decision_code": decision.decision_code,
            "supporting_evidence_refs": list(decision.supporting_evidence_refs),
            "unresolved_facts": list(decision.unresolved_facts),
            "challenge_code": decision.challenge_code,
            "output_fingerprint": decision.output_fingerprint,
            "truncated_evidence": _boolean(document, "truncated"),
        }

    def prepare_cases_batch(self, context: ActivityContext, payload: object) -> object:
        """Persist one exact Case preparation artifact; never claim a Case release."""
        del context
        return self._prepare_batch("CASES", payload)

    def prepare_legislation_batch(self, context: ActivityContext, payload: object) -> object:
        """Persist one exact Legislation preparation artifact without making a release."""
        del context
        return self._prepare_batch("LEGISLATION", payload)

    def _prepare_batch(self, expected_family: str, payload: object) -> dict[str, JsonValue]:
        if self._semantic_profiles is None or self._batch_store is None:
            raise ProcessingPipelineError(_LIVE_CONFIGURATION_INVALID)
        document = _payload(payload, f"prepare_{expected_family.lower()}_batch")
        if document.get("material_family") != expected_family:
            _processing_fail("VERIFIED_BATCH_INPUT_INVALID")
        evidence_values = document.get("evidence_items")
        if type(evidence_values) is not list or not evidence_values:
            _processing_fail("VERIFIED_BATCH_INPUT_INVALID")
        evidence_items: list[VerifiedBatchEvidence] = []
        for value in evidence_values:
            if type(value) is not dict or frozenset(value) != frozenset(
                {"byte_length", "evidence_ref", "fingerprint", "logical_key", "version_id"}
            ):
                _processing_fail("VERIFIED_BATCH_INPUT_INVALID")
            reference = ExactObjectReference(
                VaultName.PRIMARY,
                _text(value, "logical_key"),
                _text(value, "version_id"),
                _text(value, "fingerprint"),
                _integer(value, "byte_length"),
            )
            evidence_items.append(
                VerifiedBatchEvidence(
                    _text(value, "evidence_ref"),
                    self._vault.read_exact(reference),
                    reference.fingerprint,
                )
            )
        prepared = prepare_verified_batch(
            VerifiedBatchInput(
                material_family=expected_family,
                scope_id=_text(document, "scope_id"),
                batch_id=_text(document, "batch_id"),
                observation_cutoff=_text(document, "observation_cutoff"),
                acquisition_manifest_fingerprint=_text(
                    document, "acquisition_manifest_fingerprint"
                ),
                journal_head_fingerprint=_text(document, "journal_head_fingerprint"),
                semantic_profiles=self._semantic_profiles,
                evidence_items=tuple(evidence_items),
            ),
            self._batch_store,
        )
        return {
            "artifact_fingerprint": prepared.artifact_fingerprint,
            "artifact_ref": prepared.artifact_ref,
            "capability_evidence_fingerprint": prepared.capability_evidence_fingerprint,
            "capability_evidence_ref": prepared.capability_evidence_ref,
            "evidence_set_fingerprint": prepared.evidence_set_fingerprint,
            "material_family": prepared.material_family,
            "provider_invocation_count": prepared.provider_invocation_count,
            "release_state": prepared.release_state,
            "scope_id": prepared.scope_id,
            "semantic_profile_fingerprint": prepared.semantic_profile_fingerprint,
        }

    def accept_legislation_manifest(self, _context: ActivityContext, payload: object) -> object:
        """Consume canonical acquisition bytes through this application's own gate."""
        accepted = accept_hk_legislation_acquisition_manifest(payload)
        changed = route_hk_legislation_acquisition_input(accepted, self._legislation_downstream)
        return {
            "accepted": True,
            "changed": changed,
            "manifest_fingerprint": accepted.acquisition_manifest_fingerprint,
        }

    def start_hk_v1_acceptance_legal_processing(
        self, _context: ActivityContext, payload: object
    ) -> object:
        """Own the exact positive acceptance activity; fail before calls if uncomposed."""
        del _context
        if self._acceptance_input_reader is None or self._acceptance_proposal_freezer is None:
            return unavailable_hk_v1_acceptance_legal_processing(payload)
        return run_acceptance_legal_processing(
            payload,
            self._acceptance_input_reader,
            self._acceptance_proposal_freezer,
            self._acceptance_input_materializer,
        )

    def prepare_hk_v1_acceptance_inputs(self, _context: ActivityContext, payload: object) -> object:
        """Assemble retained Legal outputs before the acceptance mapper runs."""
        del _context
        return run_acceptance_input_preparation(payload, self._acceptance_input_producer)


def analyse_stored_evidence(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Replay-safe sequence: read retained evidence, then receive semantic disablement."""
    evidence = yield context.call_activity("read_evidence", input=payload)
    decision = yield context.call_activity("analyse_evidence", input=evidence)
    return decision


def process_cases_batch(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Replay-safe Case preparation ending at the explicit withheld state."""
    result = yield context.call_activity("prepare_cases_batch", input=payload)
    return result


def process_legislation_batch(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Replay-safe Legislation preparation ending at the explicit withheld state."""
    result = yield context.call_activity("prepare_legislation_batch", input=payload)
    return result


def run_hk_v1_acceptance_legal_processing(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], dict[str, JsonValue], object]:
    """Prepare exact Legal inputs, then return the unchanged acceptance result."""
    prepared = yield context.call_activity("prepare_hk_v1_acceptance_inputs", input=payload)
    if prepared.get("result") == "NOT_READY":
        return prepared
    result = yield context.call_activity("start_hk_v1_acceptance_legal_processing", input=payload)
    return result


def build_activities(
    infrastructure: _ProcessingInfrastructure,
    environment: Mapping[str, str],
    *,
    semantic_requirement: object = None,
    semantic_evidence_reader: CurrentSemanticCapabilityEvidenceReader | None = None,
    legislation_downstream: HKLegislationDownstreamPorts | None = None,
) -> ProcessingActivities:
    """Compose this worker's activities through the disabled evidence boundary."""
    spool_root = None
    if legislation_downstream is None:
        value = environment.get(_LEGISLATION_SPOOL_ROOT)
        if type(value) is not str or not value or value != value.strip():
            raise ProcessingPipelineError(_SPOOL_CONFIGURATION_INVALID)
        spool_root = Path(value)
        if not spool_root.is_absolute() or spool_root.is_symlink():
            raise ProcessingPipelineError(_SPOOL_CONFIGURATION_INVALID)
        try:
            spool_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            raise ProcessingPipelineError(_SPOOL_CONFIGURATION_INVALID) from error
    return ProcessingActivities(
        infrastructure,
        _ActivitiesConfiguration(
            runner=compose_semantic_runner(semantic_requirement, semantic_evidence_reader),
            legislation_downstream=legislation_downstream,
            legislation_spool_root=spool_root,
        ),
    )


def _required_legislation_spool_root(value: Path | None) -> Path:
    if value is None:
        raise ProcessingPipelineError(_SPOOL_CONFIGURATION_INVALID)
    return value


def _payload(value: object, operation: str) -> dict[str, JsonValue]:
    try:
        document = checked_json_value(value)
    except ContractViolation as error:
        message = f"{operation} needs one exact JSON object"
        raise ProcessingPipelineError(message) from error
    if not isinstance(document, dict):
        message = f"{operation} needs one exact JSON object"
        raise ProcessingPipelineError(message)
    return document


def _text(document: Mapping[str, JsonValue], field: str) -> str:
    value = document.get(field)
    if type(value) is not str or not value:
        message = f"{field} must be one exact non-empty string"
        raise ProcessingPipelineError(message)
    return value


def _optional_text(document: Mapping[str, JsonValue], field: str, default: str) -> str:
    value = document.get(field, default)
    if type(value) is not str or not value:
        message = f"{field} must be one exact non-empty string"
        raise ProcessingPipelineError(message)
    return value


def _integer(document: Mapping[str, JsonValue], field: str) -> int:
    value = document.get(field)
    if type(value) is not int or value < 0:
        message = f"{field} must be one non-negative integer"
        raise ProcessingPipelineError(message)
    return value


def _boolean(document: Mapping[str, JsonValue], field: str) -> bool:
    value = document.get(field)
    if type(value) is not bool:
        message = f"{field} must be one boolean"
        raise ProcessingPipelineError(message)
    return value


def _semantic_phase(document: Mapping[str, JsonValue]) -> Literal["DECISION", "CHALLENGE"]:
    value = _text(document, "phase")
    if value == "DECISION":
        return "DECISION"
    if value == "CHALLENGE":
        return "CHALLENGE"
    message = "SEMANTIC_TASK_PHASE_INVALID"
    raise ProcessingError(message)
