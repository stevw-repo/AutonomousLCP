"""Declarative acquisition-worker boundary; no source access."""

APPLICATION_NAME: str = "acquisition-worker"
CAPABILITY_PORTS: tuple[str, ...] = (
    "durable_acquisition_work",
    "external_source_read",
    "management_register_acquisition",
    "primary_evidence_write",
)

__all__ = ["APPLICATION_NAME", "CAPABILITY_PORTS"]
