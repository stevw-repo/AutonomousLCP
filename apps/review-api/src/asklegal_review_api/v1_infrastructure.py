"""Disabled V1 Review API infrastructure composition."""

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
from asklegal_evidence_vault import (
    S3AccessCredential,
    S3ImmutableVault,
    VaultName,
    create_exact_v1_s3_vault,
)
from asklegal_management_register import SqlServerPassword, V1MssqlConnectionFactory


@dataclass(frozen=True, slots=True)
class V1ReviewInfrastructure:
    """Exact process-side SQL factory; Review intentionally has no scheduler."""

    sql: V1MssqlConnectionFactory
    primary_vault: S3ImmutableVault
    review_api_credential: CredentialMaterial


def load_v1_infrastructure(environment: Mapping[str, str]) -> V1ReviewInfrastructure:
    """Compose the exact Review SQL factory without opening a connection."""
    credentials = SystemdCredentialDirectory.from_environment(environment)
    password = SqlServerPassword.from_bytes(credentials.read("sql-review").reveal())
    primary_credential = S3AccessCredential.from_bytes(
        credentials.read("vault-primary-review").reveal()
    )
    return V1ReviewInfrastructure(
        sql=V1MssqlConnectionFactory("asklegal_review_app", password),
        primary_vault=create_exact_v1_s3_vault(VaultName.PRIMARY, primary_credential),
        review_api_credential=credentials.read("review-api"),
    )


def readiness_probes(infrastructure: V1ReviewInfrastructure) -> tuple[ReadinessProbe, ...]:
    """Build the exact ordered dependency probes this application must prove.

    The order is the accepted readiness dependency order for REVIEW_API. A transport
    probe proves only that the declared destination accepts a bounded connection;
    the scheduler emulator, collector, and egress proxies publish no non-mutating
    health operation, and inventing one would be a false readiness signal.
    """
    return (
        CallableProbe(DependencyCode.MANAGEMENT_REGISTER, infrastructure.sql.check_readiness),
        CallableProbe(DependencyCode.PRIMARY_VAULT, infrastructure.primary_vault.check_readiness),
        TcpReachabilityProbe(
            DependencyCode.TELEMETRY,
            *destination_for("REVIEW_API", DependencyCode.TELEMETRY),
        ),
    )


def readiness_gate(infrastructure: V1ReviewInfrastructure) -> V1ReadinessGate:
    """Return the fail-closed gate for this application's complete dependency set."""
    return V1ReadinessGate("REVIEW_API", readiness_probes(infrastructure))
