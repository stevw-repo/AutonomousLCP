"""Typed SQL Server Management Register boundary."""

from asklegal_management_register.driver import (
    SqlCredentialError,
    SqlCredentialErrorCode,
    SqlServerPassword,
    V1MssqlConnectionFactory,
)
from asklegal_management_register.store import (
    AmbiguousCommit,
    ClaimedEffect,
    CommandFingerprintMismatch,
    CommandResult,
    EffectHandoffStore,
    ManagementRegisterStore,
)

PACKAGE_ROLE: str = "management-register-adapter"

__all__ = [
    "PACKAGE_ROLE",
    "AmbiguousCommit",
    "ClaimedEffect",
    "CommandFingerprintMismatch",
    "CommandResult",
    "EffectHandoffStore",
    "ManagementRegisterStore",
    "SqlCredentialError",
    "SqlCredentialErrorCode",
    "SqlServerPassword",
    "V1MssqlConnectionFactory",
]
