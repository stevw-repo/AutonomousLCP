"""No-ingress acquisition-worker process boundary."""

APPLICATION_NAME: str = "acquisition-worker"
CAPABILITY_PORTS: tuple[str, ...] = (
    "durable_acquisition_work",
    "external_source_read",
    "management_register_acquisition",
    "primary_evidence_write",
)

from asklegal_acquisition_worker.runtime import create_runtime
from asklegal_acquisition_worker.service import AcquisitionService, PendingObservation

__all__ = [
    "APPLICATION_NAME",
    "CAPABILITY_PORTS",
    "AcquisitionService",
    "PendingObservation",
    "create_runtime",
]
