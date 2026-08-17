"""Disabled V1 acquisition-worker infrastructure composition."""

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
class V1AcquisitionInfrastructure:
    """Exact process-side SQL and scheduler factories; no connection is opened."""

    sql: V1MssqlConnectionFactory
    scheduler: V1SchedulerSettings
    primary_vault: S3ImmutableVault
    recovery_vault: S3ImmutableVault
    source_egress_proxy_credential: CredentialMaterial


def load_v1_infrastructure(environment: Mapping[str, str]) -> V1AcquisitionInfrastructure:
    """Compose exact factories from the non-secret systemd directory path."""
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
    )
