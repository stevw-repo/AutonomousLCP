"""Disabled V1 acquisition-worker infrastructure composition."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Never

from asklegal_application_runtime import (
    CallableProbe,
    ConfigurationError,
    ConfigurationErrorCode,
    CredentialMaterial,
    DependencyCode,
    ReadinessProbe,
    SystemdCredentialDirectory,
    TcpReachabilityProbe,
    V1ReadinessGate,
    destination_for,
)
from asklegal_durable_task import V1SchedulerSettings
from asklegal_evidence_vault import (
    S3AccessCredential,
    S3ImmutableVault,
    VaultName,
    create_exact_v1_s3_vault,
)
from asklegal_management_register import SqlServerPassword, V1MssqlConnectionFactory


@dataclass(frozen=True, slots=True)
class V1AcquisitionInfrastructure:
    """Exact process-side SQL and scheduler factories; no connection is opened."""

    sql: V1MssqlConnectionFactory
    scheduler: V1SchedulerSettings
    primary_vault: S3ImmutableVault
    recovery_vault: S3ImmutableVault
    source_egress_proxy_credential: CredentialMaterial
    due_cycle_state_root: Path

    @property
    def acquisition_journal_root(self) -> Path:
        """Derive the sole journal namespace from the configured cycle-state authority."""
        return self.due_cycle_state_root / "acquisition-journals"


_DUE_CYCLE_STATE_ROOT_ENVIRONMENT_KEY = "ASKLEGAL_HK_V1_DUE_STATE_ROOT"
_ASCII_CONTROL_LIMIT = 32
_ASCII_DELETE = 127


def _invalid_due_cycle_state_root() -> Never:
    """Stop one malformed local-state configuration before any process composition."""
    raise ValueError


def _due_cycle_state_root(environment: Mapping[str, str]) -> Path:
    """Require one explicit lexical local state authority without an inferred fallback."""
    try:
        configured = environment.get(_DUE_CYCLE_STATE_ROOT_ENVIRONMENT_KEY)
        if (
            type(configured) is not str
            or not configured
            or configured != configured.strip()
            or "\\" in configured
            or any(
                ord(character) < _ASCII_CONTROL_LIMIT or ord(character) == _ASCII_DELETE
                for character in configured
            )
            or any(part in {"", ".", ".."} for part in configured.split("/")[1:])
        ):
            _invalid_due_cycle_state_root()
        lexical = PurePath(configured)
        root = Path(configured)
        if (
            not root.is_absolute()
            or root == Path(root.anchor)
            or any(part in {".", ".."} for part in lexical.parts)
        ):
            _invalid_due_cycle_state_root()
    except Exception:  # noqa: BLE001 - hostile process configuration is one closed boundary.
        raise ConfigurationError(ConfigurationErrorCode.INVALID) from None
    return root


def load_v1_infrastructure(environment: Mapping[str, str]) -> V1AcquisitionInfrastructure:
    """Compose exact factories from the non-secret systemd directory path."""
    due_cycle_state_root = _due_cycle_state_root(environment)
    credentials = SystemdCredentialDirectory.from_environment(environment)
    password = SqlServerPassword.from_bytes(credentials.read("sql-acquisition").reveal())
    primary_credential = S3AccessCredential.from_bytes(
        credentials.read("vault-primary-acquisition").reveal()
    )
    recovery_credential = S3AccessCredential.from_bytes(
        credentials.read("vault-recovery-acquisition").reveal()
    )
    return V1AcquisitionInfrastructure(
        sql=V1MssqlConnectionFactory("asklegal_acquisition_app", password),
        scheduler=V1SchedulerSettings.for_application("ACQUISITION_WORKER"),
        primary_vault=create_exact_v1_s3_vault(VaultName.PRIMARY, primary_credential),
        recovery_vault=create_exact_v1_s3_vault(VaultName.RECOVERY, recovery_credential),
        source_egress_proxy_credential=credentials.read("source-egress-proxy"),
        due_cycle_state_root=due_cycle_state_root,
    )


def readiness_probes(infrastructure: V1AcquisitionInfrastructure) -> tuple[ReadinessProbe, ...]:
    """Build the exact ordered dependency probes this application must prove.

    The order is the accepted readiness dependency order for ACQUISITION_WORKER. A transport
    probe proves only that the declared destination accepts a bounded connection;
    the scheduler emulator, collector, and egress proxies publish no non-mutating
    health operation, and inventing one would be a false readiness signal.
    """
    return (
        CallableProbe(DependencyCode.MANAGEMENT_REGISTER, infrastructure.sql.check_readiness),
        TcpReachabilityProbe(
            DependencyCode.TASK_SCHEDULER_GENERAL,
            *destination_for("ACQUISITION_WORKER", DependencyCode.TASK_SCHEDULER_GENERAL),
        ),
        CallableProbe(DependencyCode.PRIMARY_VAULT, infrastructure.primary_vault.check_readiness),
        CallableProbe(DependencyCode.RECOVERY_VAULT, infrastructure.recovery_vault.check_readiness),
        TcpReachabilityProbe(
            DependencyCode.TELEMETRY,
            *destination_for("ACQUISITION_WORKER", DependencyCode.TELEMETRY),
        ),
        TcpReachabilityProbe(
            DependencyCode.SOURCE_EGRESS,
            *destination_for("ACQUISITION_WORKER", DependencyCode.SOURCE_EGRESS),
        ),
    )


def readiness_gate(infrastructure: V1AcquisitionInfrastructure) -> V1ReadinessGate:
    """Return the fail-closed gate for this application's complete dependency set."""
    return V1ReadinessGate("ACQUISITION_WORKER", readiness_probes(infrastructure))
