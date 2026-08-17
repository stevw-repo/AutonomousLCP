"""Disabled V1 Review API infrastructure composition."""

from collections.abc import Mapping
from dataclasses import dataclass

from asklegal_application_runtime import CredentialMaterial, SystemdCredentialDirectory
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
