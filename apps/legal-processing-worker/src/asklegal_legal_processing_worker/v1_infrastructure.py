"""Disabled V1 legal-processing-worker infrastructure composition."""

from collections.abc import Mapping
from dataclasses import dataclass

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
from asklegal_durable_task import V1SchedulerSettings
from asklegal_evidence_vault import (
    S3AccessCredential,
    S3ImmutableVault,
    VaultName,
    create_exact_v1_s3_vault,
)
from asklegal_management_register import SqlServerPassword, V1MssqlConnectionFactory


@dataclass(frozen=True, slots=True)
class V1LegalProcessingInfrastructure:
    """Exact process-side SQL and scheduler factories; no connection is opened."""

    sql: V1MssqlConnectionFactory
    scheduler: V1SchedulerSettings
    primary_vault: S3ImmutableVault
    model_provider_credential: CredentialMaterial
    model_egress_proxy_credential: CredentialMaterial


def load_v1_infrastructure(
    environment: Mapping[str, str],
) -> V1LegalProcessingInfrastructure:
    """Compose exact factories from the non-secret systemd directory path."""
    credentials = SystemdCredentialDirectory.from_environment(environment)
    password = SqlServerPassword.from_bytes(credentials.read("sql-processing").reveal())
    primary_credential = S3AccessCredential.from_bytes(
        credentials.read("vault-primary-processing").reveal()
    )
    return V1LegalProcessingInfrastructure(
        sql=V1MssqlConnectionFactory("asklegal_legal_processing_app", password),
        scheduler=V1SchedulerSettings.for_application("LEGAL_PROCESSING_WORKER"),
        primary_vault=create_exact_v1_s3_vault(VaultName.PRIMARY, primary_credential),
        model_provider_credential=credentials.read("model-provider"),
        model_egress_proxy_credential=credentials.read("model-egress-proxy"),
    )


def readiness_probes(infrastructure: V1LegalProcessingInfrastructure) -> tuple[ReadinessProbe, ...]:
    """Build the exact ordered dependency probes this application must prove.

    The order is the accepted readiness dependency order for LEGAL_PROCESSING_WORKER. A transport
    probe proves only that the declared destination accepts a bounded connection;
    the scheduler emulator, collector, and egress proxies publish no non-mutating
    health operation, and inventing one would be a false readiness signal.
    """
    return (
        CallableProbe(DependencyCode.MANAGEMENT_REGISTER, infrastructure.sql.check_readiness),
        TcpReachabilityProbe(
            DependencyCode.TASK_SCHEDULER_GENERAL,
            *destination_for("LEGAL_PROCESSING_WORKER", DependencyCode.TASK_SCHEDULER_GENERAL),
        ),
        CallableProbe(DependencyCode.PRIMARY_VAULT, infrastructure.primary_vault.check_readiness),
        TcpReachabilityProbe(
            DependencyCode.TELEMETRY,
            *destination_for("LEGAL_PROCESSING_WORKER", DependencyCode.TELEMETRY),
        ),
        TcpReachabilityProbe(
            DependencyCode.MODEL_EGRESS,
            *destination_for("LEGAL_PROCESSING_WORKER", DependencyCode.MODEL_EGRESS),
        ),
    )


def readiness_gate(infrastructure: V1LegalProcessingInfrastructure) -> V1ReadinessGate:
    """Return the fail-closed gate for this application's complete dependency set."""
    return V1ReadinessGate("LEGAL_PROCESSING_WORKER", readiness_probes(infrastructure))
