"""V1 Review API infrastructure and retained local governance composition."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Never

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

from asklegal_review_api.api import ReviewDependencies, local_dependencies

_ARTIFACT_ROOT = "ASKLEGAL_LOCAL_REVIEW_ARTIFACT_ROOT"
_STATE_ROOT = "ASKLEGAL_LOCAL_REVIEW_STATE_ROOT"
_AUTHORITY_PATH = "ASKLEGAL_LOCAL_REVIEW_AUTHORITY_PATH"
_COMPOSITION_NOT_READY = "LOCAL_REVIEW_CONFIGURATION_NOT_READY"


class ReviewCompositionError(RuntimeError):
    """One sanitized fail-closed local Review composition failure."""


def _composition_fail() -> Never:
    raise ReviewCompositionError(_COMPOSITION_NOT_READY)


def _configured_directory(environment: Mapping[str, str], key: str, *, writable: bool) -> Path:
    """Resolve one explicit existing non-symlink local authority directory."""
    value = environment.get(key)
    if type(value) is not str or not value or value != value.strip():
        _composition_fail()
    path = Path(value)
    required_access = os.R_OK | os.X_OK | (os.W_OK if writable else 0)
    if (
        not path.is_absolute()
        or path == Path(path.anchor)
        or path.is_symlink()
        or not path.is_dir()
        or not os.access(path, required_access)
    ):
        _composition_fail()
    return path


def _configured_file(environment: Mapping[str, str], key: str) -> Path:
    value = environment.get(key)
    if type(value) is not str or not value or value != value.strip():
        _composition_fail()
    path = Path(value)
    if (
        not path.is_absolute()
        or path == Path(path.anchor)
        or path.is_symlink()
        or not path.is_file()
        or not os.access(path, os.R_OK)
    ):
        _composition_fail()
    return path


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


def v1_dependencies(
    infrastructure: V1ReviewInfrastructure,
    environment: Mapping[str, str],
) -> ReviewDependencies:
    """Compose the retained Task 8 package, named-human, and Approval bridge."""
    artifact_root = _configured_directory(environment, _ARTIFACT_ROOT, writable=False)
    state_root = _configured_directory(environment, _STATE_ROOT, writable=True)
    authority_path = _configured_file(environment, _AUTHORITY_PATH)
    try:
        dependencies = local_dependencies(
            state_root=state_root,
            artifact_root=artifact_root,
            authority_path=authority_path,
            review_api_credential=infrastructure.review_api_credential,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise ReviewCompositionError(_COMPOSITION_NOT_READY) from error
    if dependencies.governance is None:
        _composition_fail()
    return dependencies
