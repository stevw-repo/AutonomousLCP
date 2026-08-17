"""Disabled V1 control-plane infrastructure composition."""

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
