"""Strict Review API and minimal replaceable browser client."""

# FastAPI retains decorator-registered callbacks; route/OpenAPI tests prove their access.
# pyright: reportUnusedFunction=false

import hmac
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal, Never, Protocol, cast
from urllib.parse import urlsplit

from asklegal_application_runtime import (
    ApplicationConfiguration,
    AuthorizationError,
    AuthorizationErrorCode,
    CredentialMaterial,
    IdentityVerifier,
    LocalAdapterError,
    LocalAdapterErrorCode,
    LocalCommandRegister,
    LocalConfigurationSource,
    LocalPaginationStore,
    Principal,
    ProposalDecisionProjection,
    ProposalDetailProjection,
    ProposalProjection,
    TokenType,
    authorize,
    build_local_configuration,
    exclusive_local_state_lock,
)
from asklegal_contracts import ContractViolation, SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_management_register import (
    RegisteredApprovalTerminalCommand,
    RegisterEventCommand,
    V1CommandResult,
)
from asklegal_management_register_ports import (
    ApprovalConsumption,
    ApprovalDecision,
    ApprovalError,
    ApprovalErrorCode,
    ApprovalProjection,
    ApprovalState,
    ManifestSnapshot,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from asklegal_review_api.governance import (
    RegisteredReviewGovernanceConfiguration,
    RegisteredReviewGovernanceService,
    ReviewAuthorityEvidence,
    ReviewCommand,
    ReviewDecisionWindow,
    ReviewGovernance,
    StaticReviewAuthoritySource,
    SystemReviewDecisionWindowSource,
)
from asklegal_review_api.registered_proposals import (
    ProposalProjectionError,
    RegisteredLocalReviewProjectionStore,
)

_COMMAND_ID = re.compile(r"^cmd_[0-9a-f]{48}$")
_FORGED_HEADERS = frozenset(
    {"x-forwarded-user", "x-forwarded-roles", "x-auth-request-user", "x-original-user"}
)
_REVIEW_ORIGIN = "https://review.local.test"
_HK_V1_SCOPE_IDS = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_MAX_LOCAL_PIPELINE_ARTIFACT_BYTES = 1_000_000
_LOCAL_APPROVAL_LEDGER_INVALID = "LOCAL_APPROVAL_LEDGER_INVALID"
_LOCAL_APPROVAL_LEDGER_CONFLICT = "LOCAL_APPROVAL_LEDGER_CONFLICT"
_LOCAL_REVIEW_CREDENTIAL_INVALID = "LOCAL_REVIEW_CREDENTIAL_INVALID"
_LOCAL_REVIEW_ORIGIN_INVALID = "LOCAL_REVIEW_ORIGIN_INVALID"
_ARCHIVE_TEMP_MARKER = ".asklegal-review-approval-archive.tmp"
_ARCHIVE_TEMP_SCHEMA = "asklegal.local-review-approval-archive-temp/v1"
_ARCHIVE_TEMP_NAME = re.compile(r"^\.(apr_[0-9a-f]{48})\.[a-z0-9_-]{6,64}$")
_BEARER_TOKEN = re.compile(rb"^[A-Za-z0-9._~+/=-]{16,4096}$")


class RetryClass(StrEnum):
    """Closed HTTP retry advice."""

    NEVER = "NEVER"
    QUERY_RESULT = "QUERY_RESULT"
    SAME_COMMAND_AFTER = "SAME_COMMAND_AFTER"


class ErrorEnvelope(BaseModel):
    """Stable safe error response."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    error_code: str
    message: str
    correlation_id: str | None = None
    command_id: str | None = None
    current_version: int | None = None
    current_ref: str | None = None
    retry_class: RetryClass
    details: dict[str, str | int] = Field(default_factory=dict)


class ProposalSummary(BaseModel):
    """Immutable proposal summary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: str
    manifest_fingerprint: str
    status: str
    title: str
    review_version: int


class ProposalPage(BaseModel):
    """One snapshot-bound proposal page."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot: str
    items: tuple[ProposalSummary, ...]
    continuation_token: str | None


class ProposalArtifactSummary(BaseModel):
    """One immutable package member safe for Review display."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    role: str
    path: str
    media_type: str
    fingerprint: str
    byte_length: int


class ProposalDecisionSummary(BaseModel):
    """One immutable named-human decision safe for Review display."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    approval_id: str
    decision: str
    decision_time: str
    reviewer_identity_id: str
    reviewer_identity_fingerprint: str
    authority_evidence_id: str
    authority_evidence_fingerprint: str
    reason: str
    event_fingerprint: str


class HKV1ScopeDispositionSummary(BaseModel):
    """One of the four exact scope outcomes shown before Approval."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    scope_id: str
    result: str
    retryable_count: int


class HKV1ReviewReadinessSummary(BaseModel):
    """Complete immutable local-human V1 review surface."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    scope_dispositions: tuple[HKV1ScopeDispositionSummary, ...]
    limitations: tuple[str, ...]
    retryable_count: int
    model_evaluation_ref: str
    retrieval_evaluation_ref: str
    model_profile_fingerprint: str
    embedding_profile_fingerprint: str
    serving_profile_fingerprint: str
    target_namespace: str
    backup_profile_fingerprint: str
    target_members: tuple[tuple[str, str, str], ...]
    zero_record_scope_ids: tuple[str, ...]
    target_name: str
    native_backup_ref: str
    recovery_backup_ref: str
    rollback_state_id: str
    proposal_fingerprint: str
    fingerprint: str


class ProposalDetail(BaseModel):
    """Closed exact proposal review projection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal: ProposalSummary
    package_fingerprint: str
    promotion_manifest_id: str
    observation_cutoff: str
    valid_from: str
    valid_until: str
    validity_predicates: tuple[tuple[str, str, str], ...]
    base_serving_state_id: str
    base_serving_state_fingerprint: str
    candidate_serving_state_id: str
    candidate_serving_state_fingerprint: str
    artifacts: tuple[ProposalArtifactSummary, ...]
    decision: ProposalDecisionSummary | None
    hk_v1_readiness: HKV1ReviewReadinessSummary | None


class CommentRequest(BaseModel):
    """Comment bound to one exact manifest section."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["COMMENT"]
    manifest_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    review_section: Literal[
        "SUMMARY", "DIFF", "EVIDENCE", "COVERAGE", "RECOVERY", "VALIDATION", "COST", "ACTIONS"
    ]
    comment: str = Field(min_length=1, max_length=2_000)


class DecisionRequest(BaseModel):
    """Approve or reject one complete immutable manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["APPROVE", "REJECT"]
    manifest_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=2_000)


class RevocationRequest(BaseModel):
    """Revoke one exact unconsumed approval."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["REVOKE"]
    approval_ref: str = Field(pattern=r"^apr_[0-9a-f]{48}$")
    manifest_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=2_000)


class CommandResponse(BaseModel):
    """Authoritative review command result."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    command_id: str
    resolution: str
    result_code: str
    authoritative_version: int
    result_ref: str


class HistoryResponse(BaseModel):
    """Immutable decision and lifecycle history."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: str
    snapshot_ref: str
    events: tuple[str, ...]


class ReviewProjectionStore(Protocol):
    """Exact immutable proposal projection surface consumed by Review routes."""

    def load(self) -> tuple[str, tuple[ProposalProjection, ...]]:
        """Return one internally consistent projection generation."""
        ...

    def get(self, proposal_id: str) -> ProposalProjection | None:
        """Return one exact proposal from a verified generation, if present."""
        ...

    def detail(self, proposal_id: str) -> ProposalDetailProjection | None:
        """Return one fully reread immutable proposal package, if present."""
        ...

    def check(self) -> bool:
        """Perform a bounded non-mutating readiness check."""
        ...

    def record_evidence_read(self, *, subject: str, evidence_id: str) -> None:
        """Record or explicitly refuse one sanitized evidence-read audit fact."""
        ...

    def read_evidence(self, evidence_id: str) -> bytes:
        """Return exact retained bytes that bind the requested evidence."""
        ...


@dataclass(frozen=True, slots=True)
class ReviewDependencies:
    """Injected Review adapters with no implicit external success."""

    configuration: ApplicationConfiguration
    configuration_source: LocalConfigurationSource
    identity: IdentityVerifier
    register: LocalCommandRegister
    projections: ReviewProjectionStore
    pagination: LocalPaginationStore
    governance: ReviewGovernance | None = None
    allowed_origin: str = _REVIEW_ORIGIN


class SealedReviewIdentityVerifier:
    """Authenticate one exact sealed bearer and bind one retained human principal."""

    def __init__(self, credential: CredentialMaterial, principal: Principal) -> None:
        """Retain only the opaque comparison bytes and the configured principal."""
        if type(credential) is not CredentialMaterial or type(principal) is not Principal:
            raise RuntimeError(_LOCAL_REVIEW_CREDENTIAL_INVALID)
        token = credential.reveal()
        if _BEARER_TOKEN.fullmatch(token) is None:
            raise RuntimeError(_LOCAL_REVIEW_CREDENTIAL_INVALID)
        self._expected = b"Bearer " + bytes(token)
        self._principal = principal

    def verify(self, authorization: str | None) -> Principal:
        """Compare the complete Authorization value without token-dependent branching."""
        if authorization is None or not authorization.startswith("Bearer "):
            raise AuthorizationError(AuthorizationErrorCode.MISSING)
        try:
            supplied = authorization.encode("ascii")
        except UnicodeEncodeError as error:
            raise AuthorizationError(AuthorizationErrorCode.UNKNOWN) from error
        if not hmac.compare_digest(supplied, self._expected):
            raise AuthorizationError(AuthorizationErrorCode.UNKNOWN)
        return self._principal


def _resolve_review_artifact_root(configured: Path | None) -> Path:
    root = configured
    if root is None:
        value = os.environ.get("ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT")
        if value is None:
            message = "ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT is required"
            raise RuntimeError(message)
        root = Path(value)
    if root.is_symlink() or not root.is_dir():
        message = "LOCAL_REVIEW_ARTIFACT_ROOT_INVALID"
        raise RuntimeError(message)
    current_generation = root / "current"
    if current_generation.is_symlink():
        try:
            resolved_generation = current_generation.resolve(strict=True)
        except OSError as error:
            message = "LOCAL_REVIEW_ARTIFACT_ROOT_INVALID"
            raise RuntimeError(message) from error
        expected_parent = (root / ".generations").resolve()
        if (
            resolved_generation.parent != expected_parent
            or not resolved_generation.is_dir()
            or resolved_generation.is_symlink()
        ):
            message = "LOCAL_REVIEW_ARTIFACT_ROOT_INVALID"
            raise RuntimeError(message)
        return resolved_generation
    if current_generation.exists():
        message = "LOCAL_REVIEW_ARTIFACT_ROOT_INVALID"
        raise RuntimeError(message)
    return root


def local_dependencies(
    state_root: Path | None = None,
    artifact_root: Path | None = None,
    authority_path: Path | None = None,
    *,
    review_api_credential: CredentialMaterial,
    allowed_origin: str = _REVIEW_ORIGIN,
) -> ReviewDependencies:
    """Create deterministic local Review dependencies from retained pipeline files."""
    configuration = build_local_configuration(
        "REVIEW_APPLICATION",
        audience="api://asklegal-review",
        client="asklegal-review-client",
        task_hub=None,
    )
    configured_artifact_base = artifact_root
    if configured_artifact_base is None:
        configured = os.environ.get("ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT")
        if configured is None:
            message = "ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT is required"
            raise RuntimeError(message)
        configured_artifact_base = Path(configured)
    _resolve_review_artifact_root(configured_artifact_base)
    configured_root = state_root
    if configured_root is None:
        configured = os.environ.get("ASKLEGAL_LOCAL_REVIEW_STATE_ROOT")
        if configured is None:
            message = "ASKLEGAL_LOCAL_REVIEW_STATE_ROOT is required"
            raise RuntimeError(message)
        configured_root = Path(configured)

    def read_snapshot() -> tuple[bytes, bytes, bytes, Callable[[str], bytes]] | None:
        snapshot_root = _resolve_review_artifact_root(configured_artifact_base)
        root_paths = (
            snapshot_root / "hk-v1-two-family-proposal.json",
            snapshot_root / "hk-v1-review-readiness.json",
            snapshot_root / "hk-v1-review-package.json",
        )
        present = tuple(path.exists() or path.is_symlink() for path in root_paths)
        if not any(present):
            return None
        if not all(present):
            message = "LOCAL_REVIEW_SNAPSHOT_INCOMPLETE"
            raise RuntimeError(message)

        def read_member(path: str) -> bytes:
            return _read_local_pipeline_artifact(
                snapshot_root / path,
                error_code="LOCAL_REVIEW_MEMBER_INVALID",
                allow_empty=path.endswith(".ndjson"),
            )

        return (
            _read_local_pipeline_artifact(
                root_paths[0],
                error_code="LOCAL_TASK7_PROPOSAL_INVALID",
            ),
            _read_local_pipeline_artifact(
                root_paths[1],
                error_code="LOCAL_TASK8_READINESS_INVALID",
            ),
            _read_local_pipeline_artifact(
                root_paths[2],
                error_code="LOCAL_REVIEW_PACKAGE_INVALID",
            ),
            read_member,
        )

    registered_projections = RegisteredLocalReviewProjectionStore(
        None,
        None,
        None,
        lambda path: _read_local_pipeline_artifact(
            _resolve_review_artifact_root(configured_artifact_base) / path,
            error_code="LOCAL_REVIEW_MEMBER_INVALID",
            allow_empty=path.endswith(".ndjson"),
        ),
        read_snapshot,
    )
    registered_projections.bind_evidence_audit(configured_root / "evidence-read-ledger.json")
    configured_authority = authority_path
    if configured_authority is None:
        raw_authority_path = os.environ.get("ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH")
        if raw_authority_path is None:
            message = "ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH is required"
            raise RuntimeError(message)
        configured_authority = Path(raw_authority_path)
    authority = _read_local_review_authority(configured_authority)
    retained_authority = configured_root / "review-authority.json"
    _retain_local_review_authority(configured_authority, retained_authority)
    register = LocalRetainedApprovalRegister(
        registered_projections,
        configured_root / "approval-register.json",
        approved_package_source_root=lambda: _resolve_review_artifact_root(
            configured_artifact_base
        ),
    )
    registered_projections.bind_decision_source(register.decision_for_proposal)
    configured_decision_time = os.environ.get("ASKLEGAL_LOCAL_REVIEW_DECISION_TIME")
    configured_command_expiry = os.environ.get("ASKLEGAL_LOCAL_REVIEW_COMMAND_EXPIRES_AT")
    if (configured_decision_time is None) != (configured_command_expiry is None):
        message = "local Review decision time and command expiry must be configured together"
        raise RuntimeError(message)
    decision_window = (
        SystemReviewDecisionWindowSource()
        if configured_decision_time is None or configured_command_expiry is None
        else ReviewDecisionWindow(configured_decision_time, configured_command_expiry)
    )
    governance = RegisteredReviewGovernanceService(
        register,
        registered_projections,
        StaticReviewAuthoritySource({authority.subject: authority}),
        SchemaRegistry.from_contracts_root(_contracts_root()),
        RegisteredReviewGovernanceConfiguration(
            decision_window,
            register,
            register,
        ),
    )
    return ReviewDependencies(
        configuration=configuration,
        configuration_source=LocalConfigurationSource(configuration),
        identity=SealedReviewIdentityVerifier(
            review_api_credential,
            Principal(
                authority.subject,
                configuration.identity_audience,
                configuration.identity_client,
                authority.roles,
                TokenType.DELEGATED_HUMAN,
            ),
        ),
        register=register,
        projections=registered_projections,
        pagination=LocalPaginationStore(secret=b"local-pagination-key-not-a-production-secret"),
        governance=governance,
        allowed_origin=allowed_origin,
    )


def _read_local_review_authority(path: Path) -> ReviewAuthorityEvidence:
    """Load the exact retained named-human Review authority configuration."""
    content = _read_local_pipeline_artifact(path, error_code="LOCAL_REVIEW_AUTHORITY_INVALID")
    value = parse_json_bytes(content, max_bytes=100_000)
    keys = {
        "authority_evidence_fingerprint",
        "authority_evidence_id",
        "reviewer_identity_fingerprint",
        "reviewer_identity_id",
        "roles",
        "schema_id",
        "subject",
    }
    roles_value = value.get("roles") if isinstance(value, dict) else None
    roles = cast("list[JsonValue]", roles_value) if isinstance(roles_value, list) else []
    if not roles or any(type(role) is not str or not role for role in roles):
        message = "LOCAL_REVIEW_AUTHORITY_INVALID"
        raise RuntimeError(message)
    role_names = cast("list[str]", roles)
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or value.get("schema_id") != "asklegal.local-review-authority/v1"
        or canonicalize(value) != content
        or type(value.get("subject")) is not str
        or not value["subject"]
        or role_names != sorted(set(role_names))
        or re.fullmatch(r"act_[0-9a-f]{48}", str(value.get("reviewer_identity_id"))) is None
        or re.fullmatch(r"evi_[0-9a-f]{48}", str(value.get("authority_evidence_id"))) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(value.get("reviewer_identity_fingerprint")))
        is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(value.get("authority_evidence_fingerprint")))
        is None
    ):
        message = "LOCAL_REVIEW_AUTHORITY_INVALID"
        raise RuntimeError(message)
    return ReviewAuthorityEvidence(
        str(value["subject"]),
        frozenset(role_names),
        str(value["reviewer_identity_id"]),
        str(value["reviewer_identity_fingerprint"]),
        str(value["authority_evidence_id"]),
        str(value["authority_evidence_fingerprint"]),
    )


def _retain_local_review_authority(source: Path, destination: Path) -> None:
    """Persist/read back the exact authority bytes used by Review and Promotion."""
    content = source.read_bytes()
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != content:
            message = "LOCAL_REVIEW_AUTHORITY_DRIFT"
            raise RuntimeError(message)
        return
    temporary = destination.parent / ".review-authority.tmp"
    temporary.write_bytes(content)
    temporary.chmod(0o600)
    temporary.replace(destination)
    if destination.read_bytes() != content:
        message = "LOCAL_REVIEW_AUTHORITY_INVALID"
        raise RuntimeError(message)


def _contracts_root() -> Path:
    """Return the repository contracts root for the deterministic local app."""
    return Path(__file__).parents[4] / "contracts"


def _read_local_pipeline_artifact(
    path: Path,
    *,
    error_code: str,
    allow_empty: bool = False,
) -> bytes:
    """Read one exact bounded regular file without substituting packaged demo data."""
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(error_code)
    size = path.stat().st_size
    if size < (0 if allow_empty else 1) or size > _MAX_LOCAL_PIPELINE_ARTIFACT_BYTES:
        raise RuntimeError(error_code)
    content = path.read_bytes()
    if len(content) != size:
        raise RuntimeError(error_code)
    return content


def _local_decision_predicates(value: JsonValue | None) -> tuple[tuple[str, str, str], ...]:
    """Recover exact retained condition refs when rebuilding a local Approval."""
    if not isinstance(value, list):
        raise TypeError(_LOCAL_APPROVAL_LEDGER_INVALID)
    result: list[tuple[str, str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "contract_id",
            "fingerprint",
            "version",
        }:
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        contract_id = item.get("contract_id")
        version = item.get("version")
        condition_fingerprint = item.get("fingerprint")
        if (
            type(contract_id) is not str
            or not contract_id
            or type(version) is not str
            or not version
            or type(condition_fingerprint) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", condition_fingerprint) is None
        ):
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        result.append((contract_id, version, condition_fingerprint))
    return tuple(result)


class LocalRetainedApprovalRegister(LocalCommandRegister):
    """One retained local command/event ledger shared by HTTP and governance."""

    def __init__(
        self,
        projections: ReviewProjectionStore,
        state_path: Path,
        promotion_trigger_root: Path | None = None,
        approved_package_source_root: Callable[[], Path] | None = None,
    ) -> None:
        """Open one restart-safe local ledger at an explicit retained path."""
        super().__init__()
        self._projections = projections
        self._state_path = state_path
        self._promotion_trigger_root = (
            promotion_trigger_root or state_path.parent / "promotion-triggers"
        )
        self._approved_package_source_root = approved_package_source_root
        self._registered: dict[str, tuple[bytes, V1CommandResult]] = {}
        self._winners: set[str] = set()
        self._decided: dict[str, ProposalDetailProjection] = {}
        self._approved: dict[str, ProposalDetailProjection] = {}
        self._approved_packages: dict[str, tuple[bytes, bytes]] = {}
        self._approval_states: dict[str, ApprovalProjection] = {}
        self._revoked: set[str] = set()
        self._events: list[dict[str, JsonValue]] = []
        self._loaded_state_fingerprint: str | None = None
        self._reconcile_approval_archive_temps()
        self._load_state()
        self._reconcile_promotion_triggers()

    def record_event(self, command: RegisterEventCommand) -> V1CommandResult:
        """Append one exact governance event and retain its resolved result."""
        prior = self._registered.get(command.command_id)
        if prior is not None:
            if prior[0] != command.command_bytes:
                raise LocalAdapterError(LocalAdapterErrorCode.COMMAND_ID_CONFLICT)
            self._retain_approved_package(command.event_bytes)
            self._ensure_promotion_trigger(command.event_bytes, command.target_id)
            return replace(prior[1], replayed=True)
        if command.winner_key is not None and command.winner_key in self._winners:
            return V1CommandResult(
                command_id=command.command_id,
                result_code="REJECTED_CONFLICT",
                authoritative_version=1,
                result_bytes=b'{"result_code":"REJECTED_CONFLICT"}',
                replayed=False,
            )
        result = V1CommandResult(
            command_id=command.command_id,
            result_code="APPLIED",
            authoritative_version=1,
            result_bytes=b'{"result_code":"APPLIED"}',
            replayed=False,
        )
        before = self._memory_snapshot()
        try:
            self._registered[command.command_id] = (command.command_bytes, result)
            if command.winner_key is not None:
                self._winners.add(command.winner_key)
            package = self._restore_approval(command.target_id, command.event_bytes)
            self._retain_approved_package(command.event_bytes)
            self._events.append(
                {
                    "command_bytes": command.command_bytes.hex(),
                    "command_id": command.command_id,
                    "event_bytes": command.event_bytes.hex(),
                    "proposal_bytes": None if package is None else package[0].hex(),
                    "readiness_bytes": None if package is None else package[1].hex(),
                    "target_id": command.target_id,
                    "winner_key": command.winner_key,
                }
            )
            self._persist()
        except Exception:
            self._restore_memory_snapshot(before)
            raise
        self._ensure_promotion_trigger(command.event_bytes, command.target_id)
        return result

    def _retain_approved_package(self, event_bytes: bytes) -> None:
        document = parse_json_bytes(event_bytes, max_bytes=1_000_000)
        if not isinstance(document, dict) or document.get("decision") != "APPROVED":
            return
        approval_id = document.get("approval_id")
        source_reader = self._approved_package_source_root
        if type(approval_id) is not str or source_reader is None:
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        source = source_reader()
        destination = self._state_path.parent / "approved-packages" / approval_id
        if destination.exists():
            if destination.is_symlink() or not destination.is_dir():
                raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
            archived = self._archived_projection(approval_id)
            if archived.retained_package() != self._approved_packages.get(approval_id):
                raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
            return
        if source.is_symlink() or not source.is_dir():
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        for member in source.rglob("*"):
            if member.is_symlink() or (not member.is_dir() and not member.is_file()):
                raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        parent = destination.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{approval_id}.", dir=parent))
        marker = temporary / _ARCHIVE_TEMP_MARKER
        marker_content = self._archive_temp_marker(approval_id)
        marker.write_bytes(marker_content)
        marker.chmod(0o600)
        shutil.copytree(source, temporary, dirs_exist_ok=True)
        if marker.is_symlink() or marker.read_bytes() != marker_content:
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        marker.unlink()
        temporary.replace(destination)
        archived = self._archived_projection(approval_id)
        if archived.retained_package() != self._approved_packages.get(approval_id):
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)

    def _archived_projection(self, approval_id: str) -> RegisteredLocalReviewProjectionStore:
        root = self._state_path.parent / "approved-packages" / approval_id
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        return RegisteredLocalReviewProjectionStore(
            _read_local_pipeline_artifact(
                root / "hk-v1-two-family-proposal.json",
                error_code=_LOCAL_APPROVAL_LEDGER_INVALID,
            ),
            _read_local_pipeline_artifact(
                root / "hk-v1-review-readiness.json",
                error_code=_LOCAL_APPROVAL_LEDGER_INVALID,
            ),
            _read_local_pipeline_artifact(
                root / "hk-v1-review-package.json",
                error_code=_LOCAL_APPROVAL_LEDGER_INVALID,
            ),
            lambda path: _read_local_pipeline_artifact(
                root / path,
                error_code=_LOCAL_APPROVAL_LEDGER_INVALID,
                allow_empty=path.endswith(".ndjson"),
            ),
        )

    def _ensure_promotion_trigger(self, event_bytes: bytes, proposal_id: str) -> None:
        document = parse_json_bytes(event_bytes, max_bytes=1_000_000)
        if not isinstance(document, dict) or document.get("decision") != "APPROVED":
            return
        approval_id = document.get("approval_id")
        decision_time = document.get("decision_time")
        if (
            type(approval_id) is not str
            or re.fullmatch(r"apr_[0-9a-f]{48}", approval_id) is None
            or type(decision_time) is not str
        ):
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        execution_lineage_id = (
            "exe_"
            + sha256(
                b"asklegal.local-promotion-trigger/v1\0"
                + approval_id.encode()
                + b"\0"
                + proposal_id.encode()
                + b"\0"
                + sha256(event_bytes).digest()
            ).hexdigest()[:48]
        )
        content = canonicalize(
            checked_json_value(
                {
                    "approval_id": approval_id,
                    "execution_lineage_id": execution_lineage_id,
                    "execution_time": decision_time,
                    "schema_id": "asklegal.local-promotion-trigger/v1",
                }
            )
        )
        root = self._promotion_trigger_root
        if root.exists() and (root.is_symlink() or not root.is_dir()):
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = root / f"{approval_id}.json"
        if path.exists():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                raise RuntimeError(_LOCAL_APPROVAL_LEDGER_CONFLICT)
            return
        temporary = root / f".{approval_id}.tmp"
        temporary.write_bytes(content)
        temporary.chmod(0o600)
        temporary.replace(path)
        if path.is_symlink() or path.read_bytes() != content:
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)

    def _reconcile_promotion_triggers(self) -> None:
        """Repair the only crash window: Approval ledger durable, trigger absent."""
        for item in self._events:
            event_bytes = bytes.fromhex(str(item.get("event_bytes")))
            self._retain_approved_package(event_bytes)
            self._ensure_promotion_trigger(event_bytes, str(item.get("target_id")))

    @staticmethod
    def _archive_temp_marker(approval_id: str) -> bytes:
        return canonicalize(
            checked_json_value(
                {
                    "approval_id": approval_id,
                    "schema_id": _ARCHIVE_TEMP_SCHEMA,
                }
            )
        )

    def _reconcile_approval_archive_temps(self) -> None:
        """Remove only marker-proved staging directories left by this writer."""
        root = self._state_path.parent / "approved-packages"
        if not root.exists():
            return
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        for candidate in root.iterdir():
            match = _ARCHIVE_TEMP_NAME.fullmatch(candidate.name)
            if match is None or candidate.is_symlink() or not candidate.is_dir():
                continue
            marker = candidate / _ARCHIVE_TEMP_MARKER
            try:
                marker_content = marker.read_bytes()
            except OSError:
                continue
            if (
                marker.is_symlink()
                or marker_content != self._archive_temp_marker(match.group(1))
                or any(member.is_symlink() for member in candidate.rglob("*"))
            ):
                continue
            shutil.rmtree(candidate)

    def _restore_approval(
        self,
        target_id: str,
        event_bytes: bytes,
        retained_package: tuple[bytes, bytes] | None = None,
    ) -> tuple[bytes, bytes] | None:
        document = parse_json_bytes(event_bytes, max_bytes=1_000_000)
        if isinstance(document, dict) and document.get("decision") in {"APPROVED", "REJECTED"}:
            decision_value = str(document.get("decision"))
            is_approved = decision_value == "APPROVED"
            approval_id = document.get("approval_id")
            current_package = (
                self._projections.retained_package()
                if isinstance(self._projections, RegisteredLocalReviewProjectionStore)
                else None
            )
            projection_source = self._projections
            if is_approved and retained_package is not None and retained_package != current_package:
                projection_source = self._archived_projection(str(approval_id))
                current_package = projection_source.retained_package()
            base = projection_source.detail(target_id)
            reviewer = document.get("reviewer_identity_ref")
            authority = document.get("authority_evidence_ref")
            promotion = document.get("promotion_manifest_ref")
            expected_base = document.get("expected_base_serving_state_ref")
            readiness = None if base is None else base.hk_v1_readiness
            validity = _local_decision_predicates(document.get("validity_condition_refs"))
            if (
                isinstance(approval_id, str)
                and base is not None
                and isinstance(reviewer, dict)
                and isinstance(authority, dict)
                and isinstance(promotion, dict)
                and isinstance(expected_base, dict)
                and promotion.get("ref_id") == base.promotion_manifest_id
                and promotion.get("fingerprint") == base.proposal.manifest_fingerprint
                and expected_base.get("ref_id") == base.base_serving_state_id
                and expected_base.get("fingerprint") == base.base_serving_state_fingerprint
                and document.get("valid_from") == base.valid_from
                and validity == base.validity_predicates
                and (
                    (
                        is_approved
                        and readiness is not None
                        and current_package is not None
                        and document.get("review_readiness_fingerprint") == readiness.fingerprint
                        and (retained_package is None or retained_package == current_package)
                    )
                    or (
                        not is_approved
                        and document.get("review_readiness_fingerprint") is None
                        and retained_package is None
                    )
                )
            ):
                decision = ProposalDecisionProjection(
                    approval_id,
                    decision_value,
                    str(document.get("decision_time")),
                    str(reviewer.get("ref_id")),
                    str(reviewer.get("fingerprint")),
                    str(authority.get("ref_id")),
                    str(authority.get("fingerprint")),
                    str(document.get("reason")),
                    f"sha256:{sha256(event_bytes).hexdigest()}",
                )
                decided = replace(
                    base,
                    proposal=replace(base.proposal, status=decision_value, review_version=1),
                    decision=decision,
                )
                self._decided[target_id] = decided
                if not is_approved:
                    return None
                if current_package is None:  # Narrowed by the accepted approval condition.
                    raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
                self._approved[approval_id] = decided
                self._approval_states[approval_id] = ApprovalProjection(
                    ApprovalDecision(
                        approval_id,
                        str(promotion.get("ref_id")),
                        str(promotion.get("fingerprint")),
                        "APPROVED",
                        str(reviewer.get("ref_id")),
                        str(document.get("reason")),
                        str(document.get("decision_time")),
                        str(expected_base.get("ref_id")),
                        str(authority.get("ref_id")),
                    ),
                    ApprovalState.APPROVED,
                    "",
                )
                self._approved_packages[approval_id] = current_package
                return current_package
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        return None

    def approved(self, approval_id: str) -> ProposalDetailProjection | None:
        """Return the retained approved Review package when it remains current."""
        if approval_id in self._revoked:
            return None
        return self._approved.get(approval_id)

    def decision_for_proposal(self, proposal_id: str) -> ProposalDetailProjection | None:
        """Return one authoritative retained decision overlay by proposal identity."""
        return self._decided.get(proposal_id)

    def get(self, approval_id: str) -> ApprovalProjection:
        """Read the same retained Approval projection consumed by promotion."""
        try:
            return self._approval_states[approval_id]
        except KeyError as error:
            raise ApprovalError(ApprovalErrorCode.APPROVAL_NOT_FOUND) from error

    def consume(
        self,
        approval_id: str,
        execution_lineage_id: str,
        manifest: ManifestSnapshot,
        context: ApprovalConsumption,
    ) -> ApprovalProjection:
        """Atomically bind one exact retained Approval to one execution lineage."""
        current = self.get(approval_id)
        if current.state is ApprovalState.CONSUMED:
            if current.execution_lineage_id == execution_lineage_id:
                return current
            raise ApprovalError(ApprovalErrorCode.APPROVAL_CONSUMED)
        if (
            current.state is not ApprovalState.APPROVED
            or current.decision.manifest_id != manifest.manifest_id
            or current.decision.manifest_fingerprint != manifest.fingerprint
            or current.decision.expected_base_serving_state_id
            != context.current_base_serving_state_id
            or manifest.validity_predicates != context.current_predicates
            or not manifest.valid_from <= context.at <= manifest.valid_until
        ):
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
        consumed = replace(
            current,
            state=ApprovalState.CONSUMED,
            execution_lineage_id=execution_lineage_id,
        )
        self._approval_states[approval_id] = consumed
        try:
            self._persist()
        except Exception:
            self._approval_states[approval_id] = current
            raise
        return consumed

    def approved_package(self, approval_id: str) -> tuple[bytes, bytes]:
        """Return exact file-backed package bytes only for a current Approval."""
        state = self.get(approval_id).state
        if state is ApprovalState.REVOKED:
            raise ApprovalError(ApprovalErrorCode.APPROVAL_REVOKED)
        if state is ApprovalState.INVALIDATED:
            raise ApprovalError(ApprovalErrorCode.APPROVAL_INVALIDATED)
        if state is ApprovalState.REJECTED:
            raise ApprovalError(ApprovalErrorCode.APPROVAL_REJECTED)
        if state not in {ApprovalState.APPROVED, ApprovalState.CONSUMED}:
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT)
        try:
            return self._approved_packages[approval_id]
        except KeyError as error:
            raise ApprovalError(ApprovalErrorCode.MANIFEST_DRIFT) from error

    def revoke(
        self,
        command: RegisteredApprovalTerminalCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Revoke one exact current Approval and retain the transition."""
        del simulate_lost_ack
        if command.approval_id not in self._approved or command.approval_id in self._revoked:
            return V1CommandResult(
                command_id=command.command_id,
                result_code="REJECTED_CONFLICT",
                authoritative_version=2,
                result_bytes=b'{"result_code":"REJECTED_CONFLICT"}',
                replayed=False,
            )
        current = self._approval_states[command.approval_id]
        self._revoked.add(command.approval_id)
        self._approval_states[command.approval_id] = replace(current, state=ApprovalState.REVOKED)
        try:
            self._persist()
        except Exception:
            self._revoked.discard(command.approval_id)
            self._approval_states[command.approval_id] = current
            raise
        return V1CommandResult(
            command_id=command.command_id,
            result_code="APPLIED",
            authoritative_version=2,
            result_bytes=b'{"result_code":"APPLIED"}',
            replayed=False,
        )

    def _persist(self) -> None:
        state = checked_json_value(
            {
                "approval_states": {
                    key: {
                        "lineage": value.execution_lineage_id,
                        "state": value.state.value,
                    }
                    for key, value in sorted(self._approval_states.items())
                },
                "events": self._events,
                "revoked": sorted(self._revoked),
                "schema_id": "asklegal.local-review-approval-ledger/v1",
            }
        )
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        content = canonicalize(state)
        with exclusive_local_state_lock(self._state_path):
            current_fingerprint = (
                f"sha256:{sha256(self._state_path.read_bytes()).hexdigest()}"
                if self._state_path.is_file()
                else None
            )
            if current_fingerprint != self._loaded_state_fingerprint:
                raise RuntimeError(_LOCAL_APPROVAL_LEDGER_CONFLICT)
            temporary = self._state_path.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(self._state_path)
            self._loaded_state_fingerprint = f"sha256:{sha256(content).hexdigest()}"

    def _memory_snapshot(
        self,
    ) -> tuple[
        dict[str, tuple[bytes, V1CommandResult]],
        set[str],
        dict[str, ProposalDetailProjection],
        dict[str, ProposalDetailProjection],
        dict[str, tuple[bytes, bytes]],
        dict[str, ApprovalProjection],
        set[str],
        list[dict[str, JsonValue]],
    ]:
        """Copy all mutable state before one atomic file replacement attempt."""
        return (
            dict(self._registered),
            set(self._winners),
            dict(self._decided),
            dict(self._approved),
            dict(self._approved_packages),
            dict(self._approval_states),
            set(self._revoked),
            list(self._events),
        )

    def _restore_memory_snapshot(
        self,
        snapshot: tuple[
            dict[str, tuple[bytes, V1CommandResult]],
            set[str],
            dict[str, ProposalDetailProjection],
            dict[str, ProposalDetailProjection],
            dict[str, tuple[bytes, bytes]],
            dict[str, ApprovalProjection],
            set[str],
            list[dict[str, JsonValue]],
        ],
    ) -> None:
        """Make a failed retained replacement invisible to later local calls."""
        (
            self._registered,
            self._winners,
            self._decided,
            self._approved,
            self._approved_packages,
            self._approval_states,
            self._revoked,
            self._events,
        ) = snapshot

    def _load_state(self) -> None:  # noqa: PLR0912 - exact ledger checks stay explicit.
        if not self._state_path.exists():
            return
        content = self._state_path.read_bytes()
        value = parse_json_bytes(content, max_bytes=5_000_000)
        if (
            not isinstance(value, dict)
            or set(value) != {"approval_states", "events", "revoked", "schema_id"}
            or value.get("schema_id") != "asklegal.local-review-approval-ledger/v1"
            or canonicalize(value) != content
        ):
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        events = value.get("events")
        if not isinstance(events, list):
            raise TypeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        for item in events:
            if not isinstance(item, dict):
                raise TypeError(_LOCAL_APPROVAL_LEDGER_INVALID)
            command_id = str(item.get("command_id"))
            command_bytes = bytes.fromhex(str(item.get("command_bytes")))
            event_bytes = bytes.fromhex(str(item.get("event_bytes")))
            target_id = str(item.get("target_id"))
            winner = item.get("winner_key")
            result = V1CommandResult(
                command_id=command_id,
                result_code="APPLIED",
                authoritative_version=1,
                result_bytes=b'{"result_code":"APPLIED"}',
                replayed=False,
            )
            self._registered[command_id] = (command_bytes, result)
            if isinstance(winner, str):
                self._winners.add(winner)
            proposal_hex = item.get("proposal_bytes")
            readiness_hex = item.get("readiness_bytes")
            event_document = parse_json_bytes(event_bytes, max_bytes=1_000_000)
            is_approval = (
                isinstance(event_document, dict) and event_document.get("decision") == "APPROVED"
            )
            if is_approval and (type(proposal_hex) is not str or type(readiness_hex) is not str):
                raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
            retained_package = (
                (bytes.fromhex(proposal_hex), bytes.fromhex(readiness_hex))
                if isinstance(proposal_hex, str) and isinstance(readiness_hex, str)
                else None
            )
            self._restore_approval(target_id, event_bytes, retained_package)
            self._events.append(item)
        states = value.get("approval_states")
        if not isinstance(states, dict) or set(states) != set(self._approval_states):
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        for approval_id, raw in states.items():
            if (
                not isinstance(raw, dict)
                or set(raw) != {"lineage", "state"}
                or type(raw.get("lineage")) is not str
                or type(raw.get("state")) is not str
            ):
                raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
            try:
                state = ApprovalState(raw["state"])
            except ValueError as error:
                raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID) from error
            lineage = raw["lineage"]
            if (state is ApprovalState.CONSUMED) != bool(lineage):
                raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
            self._approval_states[approval_id] = replace(
                self._approval_states[approval_id],
                state=state,
                execution_lineage_id=lineage,
            )
        revoked = value.get("revoked")
        if (
            not isinstance(revoked, list)
            or any(type(item) is not str for item in revoked)
            or len(set(revoked)) != len(revoked)
        ):
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        expected_revoked = {
            approval_id
            for approval_id, approval in self._approval_states.items()
            if approval.state is ApprovalState.REVOKED
        }
        if set(revoked) != expected_revoked:
            raise RuntimeError(_LOCAL_APPROVAL_LEDGER_INVALID)
        revoked_ids = tuple(item for item in revoked if type(item) is str)
        self._revoked.update(revoked_ids)
        self._loaded_state_fingerprint = f"sha256:{sha256(content).hexdigest()}"


def _validate_allowed_origin(value: str) -> str:
    """Accept one exact HTTPS origin or a loopback-only HTTP demo origin."""
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(_LOCAL_REVIEW_ORIGIN_INVALID)
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        raise ValueError(_LOCAL_REVIEW_ORIGIN_INVALID) from error
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.geturl() != value
        or (
            parsed.scheme != "https"
            and not (
                parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            )
        )
    ):
        raise ValueError(_LOCAL_REVIEW_ORIGIN_INVALID)
    return value


def create_app(  # noqa: PLR0915 - routes are one explicit closed API surface.
    dependencies: ReviewDependencies,
) -> FastAPI:
    """Create the independent Review API and replaceable local browser shell."""
    deps = dependencies
    allowed_origin = _validate_allowed_origin(deps.allowed_origin)
    app = FastAPI(
        title="AskLegal Review API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.dependencies = deps
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[allowed_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "If-Match",
            "X-Correlation-ID",
        ],
        expose_headers=["ETag"],
    )
    _install_handlers(app)

    async def reviewer(request: Request) -> Principal:
        return _authenticate(request, deps)

    @app.get("/internal/live", include_in_schema=False)
    async def _live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/internal/ready", include_in_schema=False)
    async def _ready() -> JSONResponse:
        is_ready = (
            deps.configuration_source.is_current(deps.configuration.configuration_fingerprint)
            and deps.register.check()
            and deps.projections.check()
            and (deps.governance is None or deps.governance.check())
        )
        return JSONResponse(
            {"status": "ready" if is_ready else "not_ready"}, status_code=200 if is_ready else 503
        )

    @app.get("/review", include_in_schema=False, response_class=HTMLResponse)
    async def _browser_client() -> HTMLResponse:
        html = (
            files("asklegal_review_api.client").joinpath("index.html").read_text(encoding="utf-8")
        )
        return HTMLResponse(html)

    @app.get("/review/app.js", include_in_schema=False)
    async def _browser_javascript() -> Response:
        javascript = (
            files("asklegal_review_api.client").joinpath("app.js").read_text(encoding="utf-8")
        )
        return Response(javascript, media_type="text/javascript")

    @app.get(
        "/api/v1/proposal-packages",
        operation_id="listProposalPackages",
        response_model=ProposalPage,
    )
    async def _list_proposals(
        principal: Annotated[Principal, Depends(reviewer)],
        status: Annotated[
            Literal["REVIEW_READY", "APPROVED", "REJECTED"] | None,
            Query(),
        ] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 2,
        continuation: Annotated[str | None, Query(max_length=80)] = None,
    ) -> JSONResponse:
        snapshot, generation = deps.projections.load()
        proposals = (
            generation
            if status is None
            else tuple(item for item in generation if item.status == status)
        )
        filters = (("status", "ALL" if status is None else status),)
        offset = 0
        cursor = None
        if continuation is not None:
            cursor = deps.pagination.resolve(
                continuation,
                snapshot=snapshot,
                filters=filters,
                sort="proposal_id",
                subject=principal.subject,
            )
            offset = cursor.offset
        items = proposals[offset : offset + limit]
        next_offset = offset + len(items)
        next_token = None
        if next_offset < len(proposals):
            next_cursor = (
                deps.pagination.next_cursor(
                    snapshot=snapshot,
                    filters=filters,
                    sort="proposal_id",
                    subject=principal.subject,
                    offset=next_offset,
                )
                if cursor is None
                else deps.pagination.advance(cursor, offset=next_offset)
            )
            next_token = deps.pagination.issue(next_cursor)
        page = ProposalPage(
            snapshot=snapshot,
            items=tuple(_proposal_summary(item) for item in items),
            continuation_token=next_token,
        )
        return JSONResponse(page.model_dump(mode="json"), headers={"ETag": f'"{snapshot}"'})

    @app.get(
        "/api/v1/proposal-packages/{proposal_id}",
        operation_id="getProposalPackage",
        response_model=ProposalDetail,
    )
    async def _get_proposal(
        proposal_id: str, _principal: Annotated[Principal, Depends(reviewer)]
    ) -> JSONResponse:
        projection = deps.projections.detail(proposal_id)
        if projection is None:
            _raise_http("PROPOSAL_NOT_FOUND", status=404)
        detail = ProposalDetail(
            proposal=_proposal_summary(projection.proposal),
            package_fingerprint=projection.package_fingerprint,
            promotion_manifest_id=projection.promotion_manifest_id,
            observation_cutoff=projection.observation_cutoff,
            valid_from=projection.valid_from,
            valid_until=projection.valid_until,
            validity_predicates=projection.validity_predicates,
            base_serving_state_id=projection.base_serving_state_id,
            base_serving_state_fingerprint=projection.base_serving_state_fingerprint,
            candidate_serving_state_id=projection.candidate_serving_state_id,
            candidate_serving_state_fingerprint=(projection.candidate_serving_state_fingerprint),
            artifacts=tuple(
                ProposalArtifactSummary(
                    role=item.role,
                    path=item.path,
                    media_type=item.media_type,
                    fingerprint=item.fingerprint,
                    byte_length=item.byte_length,
                )
                for item in projection.artifacts
            ),
            decision=(
                None
                if projection.decision is None
                else ProposalDecisionSummary(
                    approval_id=projection.decision.approval_id,
                    decision=projection.decision.decision,
                    decision_time=projection.decision.decision_time,
                    reviewer_identity_id=projection.decision.reviewer_identity_id,
                    reviewer_identity_fingerprint=(
                        projection.decision.reviewer_identity_fingerprint
                    ),
                    authority_evidence_id=projection.decision.authority_evidence_id,
                    authority_evidence_fingerprint=(
                        projection.decision.authority_evidence_fingerprint
                    ),
                    reason=projection.decision.reason,
                    event_fingerprint=projection.decision.event_fingerprint,
                )
            ),
            hk_v1_readiness=(
                None
                if projection.hk_v1_readiness is None
                else HKV1ReviewReadinessSummary(
                    scope_dispositions=tuple(
                        HKV1ScopeDispositionSummary(
                            scope_id=item.scope_id,
                            result=item.result,
                            retryable_count=item.retryable_count,
                        )
                        for item in projection.hk_v1_readiness.scope_dispositions
                    ),
                    limitations=projection.hk_v1_readiness.limitations,
                    retryable_count=projection.hk_v1_readiness.retryable_count,
                    model_evaluation_ref=projection.hk_v1_readiness.model_evaluation_ref,
                    retrieval_evaluation_ref=(projection.hk_v1_readiness.retrieval_evaluation_ref),
                    model_profile_fingerprint=(
                        projection.hk_v1_readiness.model_profile_fingerprint
                    ),
                    embedding_profile_fingerprint=(
                        projection.hk_v1_readiness.embedding_profile_fingerprint
                    ),
                    serving_profile_fingerprint=(
                        projection.hk_v1_readiness.serving_profile_fingerprint
                    ),
                    target_namespace=projection.hk_v1_readiness.target_namespace,
                    backup_profile_fingerprint=(
                        projection.hk_v1_readiness.backup_profile_fingerprint
                    ),
                    target_members=projection.hk_v1_readiness.target_members,
                    zero_record_scope_ids=(projection.hk_v1_readiness.zero_record_scope_ids),
                    target_name=projection.hk_v1_readiness.target_name,
                    native_backup_ref=projection.hk_v1_readiness.native_backup_ref,
                    recovery_backup_ref=projection.hk_v1_readiness.recovery_backup_ref,
                    rollback_state_id=projection.hk_v1_readiness.rollback_state_id,
                    proposal_fingerprint=projection.hk_v1_readiness.proposal_fingerprint,
                    fingerprint=projection.hk_v1_readiness.fingerprint,
                )
            ),
        )
        return JSONResponse(
            detail.model_dump(mode="json"),
            headers={"ETag": f'"v{projection.proposal.review_version}"'},
        )

    @app.get("/api/v1/evidence/{evidence_id}", operation_id="streamEvidence")
    async def _evidence(
        evidence_id: str, principal: Annotated[Principal, Depends(reviewer)]
    ) -> Response:
        if re.fullmatch(r"evi_[0-9a-f]{48}", evidence_id) is None:
            _raise_http("EVIDENCE_NOT_FOUND", status=404)
        try:
            content = deps.projections.read_evidence(evidence_id)
        except ContractViolation, ProposalProjectionError:
            _raise_http("EVIDENCE_NOT_FOUND", status=404)
        deps.projections.record_evidence_read(subject=principal.subject, evidence_id=evidence_id)
        return Response(
            content,
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.post(
        "/api/v1/proposal-packages/{proposal_id}/comments",
        operation_id="appendReviewerComment",
        response_model=CommandResponse,
    )
    async def _comment(
        proposal_id: str,
        request: Request,
        principal: Annotated[Principal, Depends(reviewer)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request, deps, principal, idempotency_key, if_match, proposal_id, CommentRequest
        )

    @app.post(
        "/api/v1/proposal-packages/{proposal_id}/decisions",
        operation_id="decideProposalPackage",
        response_model=CommandResponse,
    )
    async def _decide(
        proposal_id: str,
        request: Request,
        principal: Annotated[Principal, Depends(reviewer)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request, deps, principal, idempotency_key, if_match, proposal_id, DecisionRequest
        )

    @app.post(
        "/api/v1/approvals/{approval_id}/revocations",
        operation_id="revokeApproval",
        response_model=CommandResponse,
    )
    async def _revoke(
        approval_id: str,
        request: Request,
        principal: Annotated[Principal, Depends(reviewer)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        if_match: Annotated[str, Header(alias="If-Match")],
    ) -> CommandResponse:
        return await _submit(
            request,
            deps,
            principal,
            idempotency_key,
            if_match,
            approval_id,
            RevocationRequest,
        )

    @app.get(
        "/api/v1/proposal-packages/{proposal_id}/history",
        operation_id="getProposalHistory",
        response_model=HistoryResponse,
    )
    async def _history(
        proposal_id: str, _principal: Annotated[Principal, Depends(reviewer)]
    ) -> JSONResponse:
        projection = deps.projections.detail(proposal_id)
        if projection is None:
            _raise_http("PROPOSAL_NOT_FOUND", status=404)
        decision = projection.decision
        result = HistoryResponse(
            proposal_id=proposal_id,
            snapshot_ref=(
                projection.package_fingerprint if decision is None else decision.event_fingerprint
            ),
            events=("REVIEW_READY",) if decision is None else ("REVIEW_READY", decision.decision),
        )
        return JSONResponse(
            result.model_dump(mode="json"), headers={"ETag": f'"{result.snapshot_ref}"'}
        )

    return app


def _install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthorizationError)
    async def _authorization_error(request: Request, error: AuthorizationError) -> JSONResponse:
        return _error_response(request, error.code.value, 403, RetryClass.NEVER)

    @app.exception_handler(LocalAdapterError)
    async def _adapter_error(request: Request, error: LocalAdapterError) -> JSONResponse:
        statuses = {
            LocalAdapterErrorCode.COMMAND_ID_CONFLICT: 409,
            LocalAdapterErrorCode.STALE_VERSION: 412,
            LocalAdapterErrorCode.CONTINUATION_INVALID: 400,
        }
        return _error_response(
            request, error.code.value, statuses.get(error.code, 503), RetryClass.NEVER
        )

    @app.exception_handler(ContractViolation)
    async def _contract_error(request: Request, error: ContractViolation) -> JSONResponse:
        return _error_response(request, error.code.value, 400, RetryClass.NEVER)

    @app.exception_handler(ApprovalError)
    async def _approval_error(request: Request, error: ApprovalError) -> JSONResponse:
        status = (
            403
            if error.code is ApprovalErrorCode.UNAUTHORIZED_PRINCIPAL
            else 404
            if error.code is ApprovalErrorCode.APPROVAL_NOT_FOUND
            else 409
        )
        return _error_response(request, error.code.value, status, RetryClass.NEVER)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, _error: RequestValidationError) -> JSONResponse:
        return _error_response(request, "REQUEST_INVALID", 400, RetryClass.NEVER)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, error: HTTPException) -> JSONResponse:
        code = error.detail if type(error.detail) is str else "REQUEST_INVALID"
        return _error_response(request, code, error.status_code, RetryClass.NEVER)

    @app.exception_handler(Exception)
    async def _internal_error(request: Request, _error: Exception) -> JSONResponse:
        return _error_response(request, "INTERNAL_ERROR", 500, RetryClass.QUERY_RESULT)


def _authenticate(request: Request, dependencies: ReviewDependencies) -> Principal:
    if {name.lower() for name in request.headers} & _FORGED_HEADERS:
        raise AuthorizationError(AuthorizationErrorCode.FORGED_PROXY_HEADER)
    origin = request.headers.get("Origin")
    if origin is not None and origin != dependencies.allowed_origin:
        raise AuthorizationError(AuthorizationErrorCode.ORIGIN)
    principal = dependencies.identity.verify(request.headers.get("Authorization"))
    authorize(
        principal,
        audience=dependencies.configuration.identity_audience,
        client=dependencies.configuration.identity_client,
    )
    return principal


def _proposal_summary(proposal: ProposalProjection) -> ProposalSummary:
    return ProposalSummary(
        proposal_id=proposal.proposal_id,
        manifest_fingerprint=proposal.manifest_fingerprint,
        status=proposal.status,
        title=proposal.title,
        review_version=proposal.review_version,
    )


async def _submit(
    request: Request,
    dependencies: ReviewDependencies,
    principal: Principal,
    command_id: str,
    if_match: str,
    target: str,
    model_type: type[CommentRequest | DecisionRequest | RevocationRequest],
) -> CommandResponse:
    if _COMMAND_ID.fullmatch(command_id) is None:
        _raise_http("IDEMPOTENCY_KEY_INVALID")
    expected_version = _expected_version(if_match)
    if request.headers.get("Content-Type") != "application/json":
        _raise_http("MEDIA_TYPE_UNSUPPORTED", status=415)
    value = parse_json_bytes(
        await request.body(), max_bytes=dependencies.configuration.limits.max_body_bytes
    )
    try:
        model = model_type.model_validate(value, strict=True)
    except ValidationError as error:
        raise RequestValidationError([]) from error
    if isinstance(model, CommentRequest | DecisionRequest):
        proposal = dependencies.projections.get(target)
        if proposal is None:
            _raise_http("PROPOSAL_NOT_FOUND", status=404)
        if model.manifest_fingerprint != proposal.manifest_fingerprint:
            _raise_http("MANIFEST_FINGERPRINT_STALE", status=412)
    if isinstance(model, RevocationRequest) and model.approval_ref != target:
        _raise_http("APPROVAL_REFERENCE_MISMATCH")
    body = model.model_dump(mode="json")
    json_body: dict[str, JsonValue] = dict(body)
    if dependencies.governance is None:
        raise LocalAdapterError(LocalAdapterErrorCode.DISABLED)
    outcome = dependencies.governance.submit(
        ReviewCommand(command_id, target, expected_version, json_body, principal)
    )
    return CommandResponse(
        command_id=outcome.command_id,
        resolution=outcome.resolution,
        result_code=outcome.result_code,
        authoritative_version=outcome.authoritative_version,
        result_ref=outcome.result_ref,
    )


def _expected_version(value: str) -> int:
    if not value.startswith('"v') or not value.endswith('"'):
        _raise_http("IF_MATCH_INVALID")
    digits = value[2:-1]
    if not digits.isdigit() or (len(digits) > 1 and digits.startswith("0")):
        _raise_http("IF_MATCH_INVALID")
    return int(digits)


def _raise_http(code: str, *, status: int = 400) -> Never:
    raise HTTPException(status_code=status, detail=code)


def _error_response(request: Request, code: str, status: int, retry: RetryClass) -> JSONResponse:
    command = request.headers.get("Idempotency-Key")
    if command is None or _COMMAND_ID.fullmatch(command) is None:
        command = None
    envelope = ErrorEnvelope(
        error_code=code,
        message="Request could not be completed.",
        command_id=command,
        retry_class=retry,
    )
    return JSONResponse(envelope.model_dump(mode="json"), status_code=status)
