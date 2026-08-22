"""Disabled V1 Review API infrastructure composition."""

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from asklegal_application_runtime import (
    CallableProbe,
    CredentialMaterial,
    DependencyCode,
    LocalCommandRegister,
    LocalConfigurationSource,
    LocalIdentityVerifier,
    LocalPaginationStore,
    ReadinessProbe,
    SystemdCredentialDirectory,
    TcpReachabilityProbe,
    V1ReadinessGate,
    build_local_configuration,
    destination_for,
)
from asklegal_evidence_vault import (
    S3AccessCredential,
    S3ImmutableVault,
    VaultName,
    create_exact_v1_s3_vault,
)
from asklegal_management_register import (
    RegisterEventStore,
    SqlServerPassword,
    V1MssqlConnectionFactory,
)

from asklegal_review_api.api import ReviewDependencies
from asklegal_review_api.registered_proposals import RegisteredReviewProjectionStore


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


def v1_dependencies(infrastructure: V1ReviewInfrastructure) -> ReviewDependencies:
    """Compose real registered projections while keeping Review writes fail-closed.

    Named-human authentication and durable Approval commands are not yet admitted.
    An empty verifier therefore refuses the known local proof token, and `None`
    governance makes every comment, decision, and revocation return `DISABLED`.
    """
    configuration = build_local_configuration(
        "REVIEW_APPLICATION",
        audience="api://asklegal-review",
        client="asklegal-review-client",
        task_hub=None,
    )
    pagination_secret = sha256(
        b"asklegal-review-pagination-v1\x00" + infrastructure.review_api_credential.reveal()
    ).digest()
    return ReviewDependencies(
        configuration=configuration,
        configuration_source=LocalConfigurationSource(configuration),
        identity=LocalIdentityVerifier({}),
        register=LocalCommandRegister(),
        projections=RegisteredReviewProjectionStore(
            RegisterEventStore(infrastructure.sql),
            infrastructure.primary_vault,
        ),
        pagination=LocalPaginationStore(secret=pagination_secret),
        governance=None,
    )
