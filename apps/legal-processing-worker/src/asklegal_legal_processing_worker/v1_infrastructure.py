"""Provider-disabled V1 legal-processing-worker infrastructure composition."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
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
from asklegal_durable_task import V1SchedulerSettings
from asklegal_evidence_vault import (
    S3AccessCredential,
    S3ImmutableVault,
    VaultName,
    create_exact_v1_s3_vault,
)
from asklegal_management_register import SqlServerPassword, V1MssqlConnectionFactory

_PREPARED_KEY = re.compile(r"^[a-z0-9][a-z0-9._/-]{2,1023}$")
_PREPARED_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


class LocalVerifiedBatchStore:
    """Content-checked local store for deterministic provider-disabled batch work."""

    def __init__(self, root: Path) -> None:
        """Create one exact non-symlink local root."""
        if not root.is_absolute() or root.is_symlink():
            _store_fail("VERIFIED_BATCH_STORE_INVALID")
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            _store_fail_from("VERIFIED_BATCH_STORE_INVALID", error)
        self._root = root

    def store_exact(self, logical_key: str, content: bytes, fingerprint: str) -> bytes:
        """Create once, reject conflicts, and return verified read-back bytes."""
        path = self._path(logical_key)
        if (
            type(content) is not bytes
            or not content
            or _PREPARED_FINGERPRINT.fullmatch(fingerprint) is None
            or fingerprint != f"sha256:{sha256(content).hexdigest()}"
        ):
            _store_fail("VERIFIED_BATCH_STORE_INVALID")
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if path.exists():
                if path.is_symlink() or path.read_bytes() != content:
                    _store_fail("VERIFIED_BATCH_STORE_CONFLICT")
            else:
                with path.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
            return self.read_exact(logical_key, fingerprint)
        except ValueError:
            raise
        except OSError as error:
            _store_fail_from("VERIFIED_BATCH_STORE_INVALID", error)

    def read_exact(self, logical_key: str, fingerprint: str | None = None) -> bytes:
        """Read one exact artifact and optionally recheck its content digest."""
        path = self._path(logical_key)
        try:
            if path.is_symlink() or not path.is_file():
                _store_fail("VERIFIED_BATCH_STORE_READBACK_FAILED")
            content = path.read_bytes()
        except ValueError:
            raise
        except OSError as error:
            _store_fail_from("VERIFIED_BATCH_STORE_READBACK_FAILED", error)
        if fingerprint is not None and (
            _PREPARED_FINGERPRINT.fullmatch(fingerprint) is None
            or fingerprint != f"sha256:{sha256(content).hexdigest()}"
        ):
            _store_fail("VERIFIED_BATCH_STORE_READBACK_FAILED")
        return content

    def _path(self, logical_key: str) -> Path:
        if (
            type(logical_key) is not str
            or _PREPARED_KEY.fullmatch(logical_key) is None
            or "//" in logical_key
            or any(part in {"", ".", ".."} for part in logical_key.split("/"))
        ):
            _store_fail("VERIFIED_BATCH_STORE_INVALID")
        path = self._root.joinpath(*logical_key.split("/"))
        candidate = self._root
        for part in logical_key.split("/"):
            candidate /= part
            if candidate.is_symlink():
                _store_fail("VERIFIED_BATCH_STORE_INVALID")
        return path


def _store_fail(code: str) -> Never:
    raise ValueError(code)


def _store_fail_from(code: str, error: Exception) -> Never:
    raise ValueError(code) from error


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
