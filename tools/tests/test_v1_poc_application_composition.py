"""Cross-application V1 file credential, SQL, and scheduler composition proof."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from asklegal_acquisition_worker.v1_infrastructure import (
    load_v1_infrastructure as load_acquisition,
)
from asklegal_application_runtime import (
    CredentialError,
    CredentialErrorCode,
    CredentialMaterial,
)
from asklegal_control_plane.v1_infrastructure import load_v1_infrastructure as load_control
from asklegal_evidence_vault import VaultName
from asklegal_legal_processing_worker.v1_infrastructure import (
    load_v1_infrastructure as load_processing,
)
from asklegal_management_register import V1MssqlConnectionFactory
from asklegal_promotion_worker.v1_infrastructure import (
    load_v1_infrastructure as load_promotion,
)
from asklegal_review_api.v1_infrastructure import load_v1_infrastructure as load_review

type InfrastructureResult = tuple[
    V1MssqlConnectionFactory,
    str | None,
    tuple[VaultName, ...],
    tuple[CredentialMaterial, ...],
]
type InfrastructureLoader = Callable[[dict[str, str]], InfrastructureResult]


@dataclass(frozen=True, slots=True)
class _ApplicationCase:
    loader: InfrastructureLoader
    sql_credential: str
    username: str
    task_hub: str | None
    vault_credentials: tuple[str, ...]
    opaque_credentials: tuple[str, ...]


def _control(environment: dict[str, str]) -> InfrastructureResult:
    infrastructure = load_control(environment)
    return (
        infrastructure.sql,
        infrastructure.scheduler.task_hub,
        (infrastructure.primary_vault.vault_name,),
        (infrastructure.review_client_credential,),
    )


def _review(environment: dict[str, str]) -> InfrastructureResult:
    infrastructure = load_review(environment)
    return (
        infrastructure.sql,
        None,
        (infrastructure.primary_vault.vault_name,),
        (infrastructure.review_api_credential,),
    )


def _acquisition(environment: dict[str, str]) -> InfrastructureResult:
    environment["ASKLEGAL_HK_V1_DUE_STATE_ROOT"] = str(
        Path(environment["CREDENTIALS_DIRECTORY"]).parent / "acquisition-due-cycle-state"
    )
    infrastructure = load_acquisition(environment)
    return (
        infrastructure.sql,
        infrastructure.scheduler.task_hub,
        (
            infrastructure.primary_vault.vault_name,
            infrastructure.recovery_vault.vault_name,
        ),
        (infrastructure.source_egress_proxy_credential,),
    )


def _processing(environment: dict[str, str]) -> InfrastructureResult:
    infrastructure = load_processing(environment)
    return (
        infrastructure.sql,
        infrastructure.scheduler.task_hub,
        (infrastructure.primary_vault.vault_name,),
        (
            infrastructure.model_egress_proxy_credential,
            infrastructure.model_provider_credential,
        ),
    )


def _promotion(environment: dict[str, str]) -> InfrastructureResult:
    infrastructure = load_promotion(environment)
    return (
        infrastructure.sql,
        infrastructure.scheduler.task_hub,
        (
            infrastructure.primary_vault.vault_name,
            infrastructure.recovery_vault.vault_name,
        ),
        (
            infrastructure.embedding_provider_credential,
            infrastructure.pinecone_credential,
            infrastructure.promotion_egress_proxy_credential,
        ),
    )


_APPLICATIONS = (
    _ApplicationCase(
        _control,
        "sql-control",
        "asklegal_control_app",
        "control",
        ("vault-primary-control",),
        ("review-client",),
    ),
    _ApplicationCase(
        _review,
        "sql-review",
        "asklegal_review_app",
        None,
        ("vault-primary-review",),
        ("review-api",),
    ),
    _ApplicationCase(
        _acquisition,
        "sql-acquisition",
        "asklegal_acquisition_app",
        "acquisition",
        ("vault-primary-acquisition", "vault-recovery-acquisition"),
        ("source-egress-proxy",),
    ),
    _ApplicationCase(
        _processing,
        "sql-processing",
        "asklegal_legal_processing_app",
        "legal-processing",
        ("vault-primary-processing",),
        ("model-egress-proxy", "model-provider"),
    ),
    _ApplicationCase(
        _promotion,
        "sql-promotion",
        "asklegal_promotion_app",
        "promotion",
        ("vault-primary-promotion", "vault-recovery-promotion"),
        ("embedding-provider", "pinecone-poc", "promotion-egress-proxy"),
    ),
)


def _write_credential(directory: Path, name: str, value: bytes) -> None:
    path = directory / name
    path.write_bytes(value)
    path.chmod(0o400)


@pytest.mark.parametrize("case", _APPLICATIONS)
def test_each_application_composes_only_its_exact_infrastructure_boundary(
    tmp_path: Path,
    case: _ApplicationCase,
) -> None:
    """Load exact process factories without connecting or exposing credentials."""
    secret = b"synthetic-application-password"
    _write_credential(tmp_path, case.sql_credential, secret)
    vault_secret = b'{"access_key_id":"synthetic-access","secret_access_key":"synthetic-secret"}'
    for vault_credential in case.vault_credentials:
        _write_credential(tmp_path, vault_credential, vault_secret)
    opaque_secret = b"synthetic-opaque-provider-material"
    for opaque_credential in case.opaque_credentials:
        _write_credential(tmp_path, opaque_credential, opaque_secret)

    sql, actual_task_hub, vault_names, opaque_materials = case.loader(
        {"CREDENTIALS_DIRECTORY": str(tmp_path)}
    )

    assert sql.username == case.username
    assert sql.server == "sql-server"
    assert sql.port == 1433
    assert sql.database == "AskLegalPocOperational"
    assert secret.decode() not in repr(sql)
    assert actual_task_hub == case.task_hub
    assert vault_names == tuple(
        VaultName.RECOVERY if "recovery" in name else VaultName.PRIMARY
        for name in case.vault_credentials
    )
    assert len(opaque_materials) == len(case.opaque_credentials)
    assert all(repr(material) == "CredentialMaterial(<redacted>)" for material in opaque_materials)
    assert opaque_secret.decode() not in repr(opaque_materials)


def test_application_composition_fails_closed_without_its_exact_credential(tmp_path: Path) -> None:
    """Do not fall back to another application's file or an environment secret."""
    _write_credential(tmp_path, "sql-review", b"wrong-application-password")
    environment = {
        "CREDENTIALS_DIRECTORY": str(tmp_path),
        "SQL_PASSWORD": "forbidden-environment-fallback",
    }

    with pytest.raises(CredentialError) as error:
        load_control(environment)

    assert error.value.code is CredentialErrorCode.FILE
    assert "forbidden-environment-fallback" not in str(error.value)


def test_application_composition_does_not_fall_back_for_opaque_provider_material(
    tmp_path: Path,
) -> None:
    """Require the declared provider file even before its adapter format is selected."""
    _write_credential(tmp_path, "sql-control", b"synthetic-password")
    _write_credential(
        tmp_path,
        "vault-primary-control",
        b'{"access_key_id":"synthetic-access","secret_access_key":"synthetic-secret"}',
    )
    environment = {
        "CREDENTIALS_DIRECTORY": str(tmp_path),
        "REVIEW_CLIENT_SECRET": "forbidden-environment-fallback",
    }

    with pytest.raises(CredentialError) as error:
        load_control(environment)

    assert error.value.code is CredentialErrorCode.FILE
    assert "forbidden-environment-fallback" not in str(error.value)
