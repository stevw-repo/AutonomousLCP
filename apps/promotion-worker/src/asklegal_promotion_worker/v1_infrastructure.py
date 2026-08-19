"""Disabled V1 promotion-worker infrastructure composition."""

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
