"""No-ingress acquisition-worker process boundary."""

APPLICATION_NAME: str = "acquisition-worker"
CAPABILITY_PORTS: tuple[str, ...] = (
    "durable_acquisition_work",
    "external_source_read",
    "management_register_acquisition",
    "primary_evidence_write",
)

from asklegal_acquisition_worker.patchright_discovery import (
    PatchrightDiscovery,
    PatchrightDiscoveryPolicy,
    PatchrightDiscoveryTransport,
    PatchrightObservedRequest,
    patchright_policy_for_endpoint,
)
from asklegal_acquisition_worker.runtime import create_runtime
from asklegal_acquisition_worker.service import AcquisitionService, PendingObservation

__all__ = [
    "APPLICATION_NAME",
    "CAPABILITY_PORTS",
    "AcquisitionService",
    "PatchrightDiscovery",
    "PatchrightDiscoveryPolicy",
    "PatchrightDiscoveryTransport",
    "PatchrightObservedRequest",
    "PendingObservation",
    "create_runtime",
    "patchright_policy_for_endpoint",
]
