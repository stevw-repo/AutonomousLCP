"""Closed deterministic source-fact acquisition boundary."""

from .admission import ResponseAdmissionPolicy, admit_response
from .model import (
    AcquisitionArtifact,
    AcquisitionConsequence,
    AcquisitionOutcome,
    AuthenticationClass,
    ConnectorRequest,
    CoverageAccounting,
    CoverageAccountingResult,
    EndpointContract,
    HttpMethod,
    ObservationDisposition,
    RegisteredSource,
    RetryProfile,
    ScraperResult,
    ScraperResultCode,
    SourcePolicyState,
    SourceRegistry,
    SyntheticPage,
    SyntheticResponse,
    WatcherResult,
    WatcherResultCode,
)
from .synthetic import SyntheticConnector

PACKAGE_ROLE: str = "source-connectors"

__all__ = [
    "PACKAGE_ROLE",
    "AcquisitionArtifact",
    "AcquisitionConsequence",
    "AcquisitionOutcome",
    "AuthenticationClass",
    "ConnectorRequest",
    "CoverageAccounting",
    "CoverageAccountingResult",
    "EndpointContract",
    "HttpMethod",
    "ObservationDisposition",
    "RegisteredSource",
    "ResponseAdmissionPolicy",
    "RetryProfile",
    "ScraperResult",
    "ScraperResultCode",
    "SourcePolicyState",
    "SourceRegistry",
    "SyntheticConnector",
    "SyntheticPage",
    "SyntheticResponse",
    "WatcherResult",
    "WatcherResultCode",
    "admit_response",
]
