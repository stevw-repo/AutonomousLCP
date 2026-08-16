"""Framework-free application boundary contracts and local adapters."""

from asklegal_application_runtime.config import (
    ApplicationConfiguration,
    ConfigurationError,
    ConfigurationErrorCode,
    LocalConfigurationSource,
    RuntimeLimits,
    build_local_configuration,
)
from asklegal_application_runtime.identity import (
    AuthorizationError,
    AuthorizationErrorCode,
    LocalIdentityVerifier,
    Principal,
    TokenType,
    authorize,
    default_local_identity,
)
from asklegal_application_runtime.local import (
    CommandOutcome,
    DisabledEffectPort,
    LocalAdapterError,
    LocalAdapterErrorCode,
    LocalCommandRegister,
    LocalPaginationStore,
    LocalReviewProjectionStore,
    PageCursor,
    ProposalProjection,
)
from asklegal_application_runtime.worker import (
    LocalTaskHub,
    WorkerResultCode,
    WorkerRuntime,
    WorkLease,
)

PACKAGE_ROLE: str = "application-runtime"

__all__ = [
    "PACKAGE_ROLE",
    "ApplicationConfiguration",
    "AuthorizationError",
    "AuthorizationErrorCode",
    "CommandOutcome",
    "ConfigurationError",
    "ConfigurationErrorCode",
    "DisabledEffectPort",
    "LocalAdapterError",
    "LocalAdapterErrorCode",
    "LocalCommandRegister",
    "LocalConfigurationSource",
    "LocalIdentityVerifier",
    "LocalPaginationStore",
    "LocalReviewProjectionStore",
    "LocalTaskHub",
    "PageCursor",
    "Principal",
    "ProposalProjection",
    "RuntimeLimits",
    "TokenType",
    "WorkLease",
    "WorkerResultCode",
    "WorkerRuntime",
    "authorize",
    "build_local_configuration",
    "default_local_identity",
]
