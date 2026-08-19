"""Disabled V1 control-plane infrastructure composition."""

from collections.abc import Mapping
from dataclasses import dataclass

from asklegal_application_runtime import (
    V1_INTERNAL_CA_BUNDLE,
    CallableProbe,
    CredentialMaterial,
    DependencyCode,
    ReadinessProbe,
    SystemdCredentialDirectory,
    TcpReachabilityProbe,
    TlsReachabilityProbe,
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
class V1ControlInfrastructure:
    """Exact process-side SQL and scheduler factories; no connection is opened."""

    sql: V1MssqlConnectionFactory
    scheduler: V1SchedulerSettings
    primary_vault: S3ImmutableVault
    review_client_credential: CredentialMaterial


def load_v1_infrastructure(environment: Mapping[str, str]) -> V1ControlInfrastructure:
    """Compose exact factories from the non-secret systemd directory path."""
    credentials = SystemdCredentialDirectory.from_environment(environment)
    password = SqlServerPassword.from_bytes(credentials.read("sql-control").reveal())
    primary_credential = S3AccessCredential.from_bytes(
        credentials.read("vault-primary-control").reveal()
    )
    return V1ControlInfrastructure(
        sql=V1MssqlConnectionFactory("asklegal_control_app", password),
        scheduler=V1SchedulerSettings.for_application("CONTROL_PLANE"),
        primary_vault=create_exact_v1_s3_vault(VaultName.PRIMARY, primary_credential),
        review_client_credential=credentials.read("review-client"),
    )


def readiness_probes(infrastructure: V1ControlInfrastructure) -> tuple[ReadinessProbe, ...]:
    """Build the exact ordered dependency probes this application must prove.

    The order is the accepted readiness dependency order for CONTROL_PLANE. A transport
    probe proves only that the declared destination accepts a bounded connection;
    the scheduler emulator, collector, and egress proxies publish no non-mutating
    health operation, and inventing one would be a false readiness signal.
    """
    return (
        CallableProbe(DependencyCode.MANAGEMENT_REGISTER, infrastructure.sql.check_readiness),
        TcpReachabilityProbe(
            DependencyCode.TASK_SCHEDULER_GENERAL,
            *destination_for("CONTROL_PLANE", DependencyCode.TASK_SCHEDULER_GENERAL),
        ),
        # The control plane sequences the other stages, so it is the one
        # application that reaches a second scheduler.
        TcpReachabilityProbe(
            DependencyCode.TASK_SCHEDULER_PROMOTION,
            *destination_for("CONTROL_PLANE", DependencyCode.TASK_SCHEDULER_PROMOTION),
        ),
        CallableProbe(DependencyCode.PRIMARY_VAULT, infrastructure.primary_vault.check_readiness),
        TcpReachabilityProbe(
            DependencyCode.TELEMETRY,
            *destination_for("CONTROL_PLANE", DependencyCode.TELEMETRY),
        ),
        TlsReachabilityProbe(
            DependencyCode.REVIEW_API,
            *destination_for("CONTROL_PLANE", DependencyCode.REVIEW_API),
            V1_INTERNAL_CA_BUNDLE,
        ),
    )


def readiness_gate(infrastructure: V1ControlInfrastructure) -> V1ReadinessGate:
    """Return the fail-closed gate for this application's complete dependency set."""
    return V1ReadinessGate("CONTROL_PLANE", readiness_probes(infrastructure))
