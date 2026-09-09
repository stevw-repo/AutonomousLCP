"""V1 promotion-worker infrastructure and retained-input preflight."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Never, Protocol

from asklegal_application_runtime import (
    CallableProbe,
    CredentialMaterial,
    DependencyCode,
    ReadinessProbe,
    SystemdCredentialDirectory,
    TcpReachabilityProbe,
    V1ReadinessGate,
    destination_for,
)
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_durable_task import V1SchedulerSettings
from asklegal_evidence_vault import (
    S3AccessCredential,
    S3ImmutableVault,
    VaultName,
    create_exact_v1_s3_vault,
)
from asklegal_management_register import SqlServerPassword, V1MssqlConnectionFactory
from asklegal_processing import ExactTokenizerResourceCounter
from asklegal_promotion import (
    BackupPort,
    EmbeddingTokenCounter,
    PromotionError,
    PromotionErrorCode,
    ServingCapabilityProfile,
    load_serving_capability_profile,
)
from asklegal_promotion.backup import (
    BackupRequest,
    IndependentBackupAdapter,
    NativeBackupPort,
    RecoveryCopyPort,
)

from asklegal_promotion_worker.local_approval import LocalRetainedPromotionApprovalStore
from asklegal_promotion_worker.local_intents import retain_v1_effect_intents
from asklegal_promotion_worker.local_package import load_v1_promotion_manifest_from_review_package
from asklegal_promotion_worker.local_serving_state import (
    FileServingStateStore,
    open_or_initialize_serving_state,
)
from asklegal_promotion_worker.real_effects import (
    RetainedEffectIntentSource,
    V1RealEffectActivation,
    V1RealPromotionEffects,
    compose_v1_real_effects,
    issue_v1_real_effect_authority,
)

if TYPE_CHECKING:
    from asklegal_management_register_ports import ApprovalProjection
    from asklegal_promotion import PromotionManifest
    from asklegal_promotion.remote import ProviderCall

    from asklegal_promotion_worker.local_intents import LocalRetainedEffectIntentSource
    from asklegal_promotion_worker.real_effects import V1RealEffectAuthority

_APPROVAL_ID = re.compile(r"^apr_[0-9a-f]{48}$")
_EXECUTION_ID = re.compile(r"^exe_[0-9a-f]{48}$")
_EXECUTION_TIME = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)
_PROMOTION_CONFIGURATION_NOT_READY = "PROMOTION_LOCAL_INPUTS_NOT_READY"
_INPUT_KEYS = {
    "approval_ledger": "ASKLEGAL_PROMOTION_APPROVAL_LEDGER",
    "current_serving_state": "ASKLEGAL_PROMOTION_CURRENT_SERVING_STATE",
    "effect_intents": "ASKLEGAL_PROMOTION_EFFECT_INTENT_LEDGER",
    "native_backup_root": "ASKLEGAL_PROMOTION_NATIVE_BACKUP_ROOT",
    "package_root": "ASKLEGAL_PROMOTION_PACKAGE_ROOT",
    "recovery_backup_root": "ASKLEGAL_PROMOTION_RECOVERY_BACKUP_ROOT",
    "serving_profile": "ASKLEGAL_PROMOTION_SERVING_PROFILE",
    "state_root": "ASKLEGAL_PROMOTION_STATE_ROOT",
    "tokenizer_resource": "ASKLEGAL_PROMOTION_TOKENIZER_RESOURCE",
}
_WRITABLE_INPUTS = {
    "approval_ledger",
    "current_serving_state",
    "effect_intents",
    "native_backup_root",
    "recovery_backup_root",
    "state_root",
}


class PromotionCompositionError(RuntimeError):
    """One sanitized fail-closed promotion startup failure."""


def _promotion_fail() -> Never:
    raise PromotionCompositionError(_PROMOTION_CONFIGURATION_NOT_READY)


@dataclass(frozen=True, slots=True)
class V1PromotionPreflight:
    """Fully reread retained authority available before any credential or transport."""

    approval_id: str
    execution_lineage_id: str
    execution_time: str
    approvals: LocalRetainedPromotionApprovalStore
    intents: LocalRetainedEffectIntentSource
    manifest: PromotionManifest
    serving_profile: ServingCapabilityProfile
    token_counter: ExactTokenizerResourceCounter
    serving_states: FileServingStateStore
    state_root: Path
    native_backup_root: Path
    recovery_backup_root: Path
    current_serving_state_id: str


class _ExactProfileFile:
    """TOCTOU-closing serving-profile reader over one retained regular file."""

    def __init__(self, path: Path) -> None:
        content = path.read_bytes()
        fingerprint = f"sha256:{sha256(content).hexdigest()}"
        self.reference = ImmutableReference(
            ReferenceType.CAPABILITY_PROFILE,
            f"cap_{sha256(fingerprint.encode()).hexdigest()[:48]}",
            fingerprint,
        )
        self._path = path

    def read_exact(self, reference: ImmutableReference) -> bytes:
        if reference != self.reference or self._path.is_symlink() or not self._path.is_file():
            _promotion_fail()
        content = self._path.read_bytes()
        if f"sha256:{sha256(content).hexdigest()}" != reference.fingerprint:
            _promotion_fail()
        return content


def _configured_path(
    environment: Mapping[str, str],
    key: str,
    *,
    directory: bool,
    writable: bool,
) -> Path:
    value = environment.get(key)
    if type(value) is not str or not value or value != value.strip():
        raise PromotionCompositionError(_PROMOTION_CONFIGURATION_NOT_READY)
    path = Path(value)
    access = os.R_OK | (os.X_OK if directory else 0) | (os.W_OK if writable else 0)
    if (
        not path.is_absolute()
        or path == Path(path.anchor)
        or path.is_symlink()
        or (not path.is_dir() if directory else not path.is_file())
        or not os.access(path, access)
    ):
        raise PromotionCompositionError(_PROMOTION_CONFIGURATION_NOT_READY)
    return path


def _configured_future_file(environment: Mapping[str, str], key: str) -> Path:
    """Resolve an exact writable file location that may not exist yet."""
    value = environment.get(key)
    if type(value) is not str or not value or value != value.strip():
        _promotion_fail()
    path = Path(value)
    parent = path.parent
    if (
        not path.is_absolute()
        or path == Path(path.anchor)
        or path.is_symlink()
        or (path.exists() and not path.is_file())
        or (path.exists() and not os.access(path, os.R_OK | os.W_OK))
        or parent.is_symlink()
        or not parent.is_dir()
        or not os.access(parent, os.R_OK | os.W_OK | os.X_OK)
    ):
        _promotion_fail()
    return path


def _configured_state_directory(environment: Mapping[str, str], key: str) -> Path:
    """Create or reopen one application-owned stable state directory."""
    value = environment.get(key)
    if type(value) is not str or not value or value != value.strip():
        _promotion_fail()
    path = Path(value)
    parent = path.parent
    if (
        not path.is_absolute()
        or path == Path(path.anchor)
        or path.is_symlink()
        or parent.is_symlink()
        or not parent.is_dir()
        or not os.access(parent, os.R_OK | os.W_OK | os.X_OK)
    ):
        _promotion_fail()
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or not path.is_dir() or not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        _promotion_fail()
    return path


def promotion_trigger_root(environment: Mapping[str, str]) -> Path:
    """Resolve the shared retained Review wakeup queue without requiring an item."""
    raw = environment.get(_INPUT_KEYS["approval_ledger"])
    if type(raw) is not str or not raw or raw != raw.strip():
        _promotion_fail()
    ledger = Path(raw)
    parent = ledger.parent
    if (
        not ledger.is_absolute()
        or ledger == Path(ledger.anchor)
        or parent.is_symlink()
        or not parent.is_dir()
        or not os.access(parent, os.R_OK | os.W_OK | os.X_OK)
    ):
        _promotion_fail()
    return parent / "promotion-triggers"


def validate_v1_promotion_configuration(environment: Mapping[str, str]) -> Path:
    """Validate stable inputs while allowing future Approval-specific files."""
    try:
        paths: dict[str, Path] = {}
        for name, key in _INPUT_KEYS.items():
            if name == "approval_ledger":
                continue
            if name == "current_serving_state":
                paths[name] = _configured_future_file(environment, key)
                continue
            if name == "effect_intents":
                paths[name] = _configured_state_directory(environment, key)
                continue
            paths[name] = _configured_path(
                environment,
                key,
                directory=name.endswith("root") or name == "effect_intents",
                writable=name in _WRITABLE_INPUTS,
            )
        profile = load_serving_capability_profile(_ExactProfileFile(paths["serving_profile"]))
        ExactTokenizerResourceCounter(
            profile.embedding.tokenizer,
            paths["tokenizer_resource"].read_bytes(),
        )
        if paths["current_serving_state"].parent != paths["state_root"]:
            _promotion_fail()
        if paths["current_serving_state"].exists():
            serving_states = FileServingStateStore(paths["current_serving_state"])
            if not serving_states.active_state_id:
                _promotion_fail()
        return promotion_trigger_root(environment)
    except PromotionCompositionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise PromotionCompositionError(_PROMOTION_CONFIGURATION_NOT_READY) from error


def preflight_v1_promotion(  # noqa: C901, PLR0912, PLR0915 - closed trust boundary.
    environment: Mapping[str, str],
    *,
    trigger_path: Path | None = None,
) -> V1PromotionPreflight:
    """Validate every retained local input before credentials, transports, or effects."""
    try:
        paths: dict[str, Path] = {}
        for name, key in _INPUT_KEYS.items():
            if name == "current_serving_state":
                paths[name] = _configured_future_file(environment, key)
            elif name == "effect_intents":
                paths[name] = _configured_state_directory(environment, key)
            else:
                paths[name] = _configured_path(
                    environment,
                    key,
                    directory=name.endswith("root") or name == "effect_intents",
                    writable=name in _WRITABLE_INPUTS,
                )
        configured_trigger = trigger_path
        if configured_trigger is None:
            raw_trigger = environment.get("ASKLEGAL_PROMOTION_TRIGGER")
            if type(raw_trigger) is not str:
                _promotion_fail()
            configured_trigger = Path(raw_trigger)
        if (
            not configured_trigger.is_absolute()
            or configured_trigger.is_symlink()
            or not configured_trigger.is_file()
        ):
            _promotion_fail()
        trigger_content = configured_trigger.read_bytes()
        trigger = parse_json_bytes(trigger_content, max_bytes=10_000)
        if (
            not isinstance(trigger, dict)
            or set(trigger)
            != {"approval_id", "execution_lineage_id", "execution_time", "schema_id"}
            or trigger.get("schema_id") != "asklegal.local-promotion-trigger/v1"
            or canonicalize(trigger) != trigger_content
        ):
            _promotion_fail()
        approval_id = trigger.get("approval_id")
        execution_id = trigger.get("execution_lineage_id")
        execution_time = trigger.get("execution_time")
        if (
            type(approval_id) is not str
            or _APPROVAL_ID.fullmatch(approval_id) is None
            or type(execution_id) is not str
            or _EXECUTION_ID.fullmatch(execution_id) is None
            or type(execution_time) is not str
            or _EXECUTION_TIME.fullmatch(execution_time) is None
        ):
            _promotion_fail()
        if trigger_path is not None:
            retained_package_root = (
                paths["approval_ledger"].parent / "approved-packages" / approval_id
            )
            if (
                retained_package_root.is_symlink()
                or not retained_package_root.is_dir()
                or not os.access(retained_package_root, os.R_OK | os.X_OK)
            ):
                _promotion_fail()
            paths["package_root"] = retained_package_root
        approvals = LocalRetainedPromotionApprovalStore(
            paths["approval_ledger"],
            paths["approval_ledger"].parent / "review-authority.json",
        )
        approval = approvals.get(approval_id)
        approved_for_lineage = (
            approval.state.value == "APPROVAL_APPROVED" and not approval.execution_lineage_id
        ) or (
            approval.state.value == "APPROVAL_CONSUMED"
            and approval.execution_lineage_id == execution_id
        )
        if not approved_for_lineage:
            _promotion_fail()
        approvals.approved_package(approval_id)
        profile = load_serving_capability_profile(_ExactProfileFile(paths["serving_profile"]))
        token_counter = ExactTokenizerResourceCounter(
            profile.embedding.tokenizer,
            paths["tokenizer_resource"].read_bytes(),
        )
        manifest = load_v1_promotion_manifest_from_review_package(
            paths["package_root"],
            profile,
            expected_manifest_id=approval.decision.manifest_id,
            expected_manifest_fingerprint=approval.decision.manifest_fingerprint,
        )
        intents = retain_v1_effect_intents(
            paths["effect_intents"],
            approval_id=approval_id,
            execution_lineage_id=execution_id,
            execution_time=execution_time,
            manifest=manifest,
            profile=profile,
        )
        if paths["current_serving_state"].parent != paths["state_root"]:
            _promotion_fail()
        serving_states = open_or_initialize_serving_state(
            paths["current_serving_state"],
            manifest.base_serving_state_id,
        )
        state_content = serving_states.active_state_id
        permitted_states = {manifest.base_serving_state_id}
        if approval.execution_lineage_id == execution_id:
            permitted_states.add(manifest.candidate_serving_state_id)
        if state_content not in permitted_states:
            _promotion_fail()
        return V1PromotionPreflight(
            approval_id=approval_id,
            execution_lineage_id=execution_id,
            execution_time=execution_time,
            approvals=approvals,
            intents=intents,
            manifest=manifest,
            serving_profile=profile,
            token_counter=token_counter,
            serving_states=serving_states,
            state_root=paths["state_root"],
            native_backup_root=paths["native_backup_root"],
            recovery_backup_root=paths["recovery_backup_root"],
            current_serving_state_id=state_content,
        )
    except PromotionCompositionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise PromotionCompositionError(_PROMOTION_CONFIGURATION_NOT_READY) from error


class RetainedApprovalProjectionSource(Protocol):
    """Promotion-side read of one exact retained Approval projection."""

    def get(self, approval_id: str) -> ApprovalProjection:
        """Return the exact current state for one retained Approval."""
        ...


@dataclass(frozen=True, slots=True)
class V1PromotionInfrastructure:
    """Exact process-side SQL and scheduler factories; no connection is opened."""

    sql: V1MssqlConnectionFactory
    scheduler: V1SchedulerSettings
    primary_vault: S3ImmutableVault
    recovery_vault: S3ImmutableVault
    embedding_provider_credential: CredentialMaterial
    pinecone_credential: CredentialMaterial
    promotion_egress_proxy_credential: CredentialMaterial


def load_v1_infrastructure(environment: Mapping[str, str]) -> V1PromotionInfrastructure:
    """Compose exact factories from the non-secret systemd directory path."""
    credentials = SystemdCredentialDirectory.from_environment(environment)
    password = SqlServerPassword.from_bytes(credentials.read("sql-promotion").reveal())
    primary_credential = S3AccessCredential.from_bytes(
        credentials.read("vault-primary-promotion").reveal()
    )
    recovery_credential = S3AccessCredential.from_bytes(
        credentials.read("vault-recovery-promotion").reveal()
    )
    return V1PromotionInfrastructure(
        sql=V1MssqlConnectionFactory("asklegal_promotion_app", password),
        scheduler=V1SchedulerSettings.for_application("PROMOTION_WORKER"),
        primary_vault=create_exact_v1_s3_vault(VaultName.PRIMARY, primary_credential),
        recovery_vault=create_exact_v1_s3_vault(VaultName.RECOVERY, recovery_credential),
        embedding_provider_credential=credentials.read("embedding-provider"),
        pinecone_credential=credentials.read("pinecone-poc"),
        promotion_egress_proxy_credential=credentials.read("promotion-egress-proxy"),
    )


def readiness_probes(infrastructure: V1PromotionInfrastructure) -> tuple[ReadinessProbe, ...]:
    """Build the exact ordered dependency probes this application must prove.

    The order is the accepted readiness dependency order for PROMOTION_WORKER. A transport
    probe proves only that the declared destination accepts a bounded connection;
    the scheduler emulator, collector, and egress proxies publish no non-mutating
    health operation, and inventing one would be a false readiness signal.
    """
    return (
        CallableProbe(DependencyCode.MANAGEMENT_REGISTER, infrastructure.sql.check_readiness),
        TcpReachabilityProbe(
            DependencyCode.TASK_SCHEDULER_PROMOTION,
            *destination_for("PROMOTION_WORKER", DependencyCode.TASK_SCHEDULER_PROMOTION),
        ),
        CallableProbe(DependencyCode.PRIMARY_VAULT, infrastructure.primary_vault.check_readiness),
        CallableProbe(DependencyCode.RECOVERY_VAULT, infrastructure.recovery_vault.check_readiness),
        TcpReachabilityProbe(
            DependencyCode.TELEMETRY,
            *destination_for("PROMOTION_WORKER", DependencyCode.TELEMETRY),
        ),
        TcpReachabilityProbe(
            DependencyCode.PROMOTION_EGRESS,
            *destination_for("PROMOTION_WORKER", DependencyCode.PROMOTION_EGRESS),
        ),
    )


def readiness_gate(infrastructure: V1PromotionInfrastructure) -> V1ReadinessGate:
    """Return the fail-closed gate for this application's complete dependency set."""
    return V1ReadinessGate("PROMOTION_WORKER", readiness_probes(infrastructure))


def compose_admitted_provider_effects(  # noqa: PLR0913 - exact composition inputs.
    infrastructure: V1PromotionInfrastructure,
    profile: ServingCapabilityProfile,
    embedding_transport: ProviderCall,
    target_transport: ProviderCall,
    *,
    authority: V1RealEffectAuthority,
    backup_profile_ref: ImmutableReference,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> V1RealPromotionEffects:
    """Reveal staged credentials only for exact admitted, explicitly authorized composition."""
    return compose_v1_real_effects(
        profile,
        infrastructure.embedding_provider_credential.reveal(),
        infrastructure.pinecone_credential.reveal(),
        embedding_transport,
        target_transport,
        authority=authority,
        backup_profile_ref=backup_profile_ref,
        now=now,
    )


def compose_approved_provider_effects(  # noqa: PLR0913, PLR0917 - exact authority inputs.
    infrastructure: V1PromotionInfrastructure,
    profile: ServingCapabilityProfile,
    manifest: PromotionManifest,
    token_counter: EmbeddingTokenCounter,
    approvals: RetainedApprovalProjectionSource,
    intents: RetainedEffectIntentSource,
    embedding_transport: ProviderCall,
    target_transport: ProviderCall,
    *,
    approval_id: str,
    execution_lineage_id: str,
    backup_profile_ref: ImmutableReference,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> V1RealPromotionEffects:
    """Compose closed adapters from the retained Approval, actions, and intents."""
    authority = issue_v1_real_effect_authority(
        approvals.get(approval_id),
        intents,
        profile,
        manifest,
        token_counter,
        execution_lineage_id=execution_lineage_id,
    )
    return compose_admitted_provider_effects(
        infrastructure,
        profile,
        embedding_transport,
        target_transport,
        authority=authority,
        backup_profile_ref=backup_profile_ref,
        now=now,
    )


def compose_independent_backup_adapter(
    profile: ServingCapabilityProfile,
    request: BackupRequest,
    native: NativeBackupPort,
    recovery: RecoveryCopyPort,
    *,
    activation: V1RealEffectActivation,
) -> BackupPort:
    """Bind the admitted backup profile to two nominally distinct effect ports."""
    if request.backup_profile_ref != profile.backup_profile_ref:
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "backup profile drift")
    return activation.bind_backup(
        request,
        IndependentBackupAdapter(request, native, recovery),
    )
