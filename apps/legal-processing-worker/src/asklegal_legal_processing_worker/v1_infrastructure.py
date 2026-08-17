"""Disabled V1 legal-processing-worker infrastructure composition."""

from collections.abc import Mapping
from dataclasses import dataclass

from asklegal_application_runtime import CredentialMaterial, SystemdCredentialDirectory
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
        model_egress_proxy_credential=credentials.read("model-egress-proxy"),
    )
