"""Declarative control-plane application boundary; no runtime behavior."""

APPLICATION_NAME: str = "control-plane"
CAPABILITY_PORTS: tuple[str, ...] = (
    "control_http_api",
    "coverage_report_read",
    "management_register_control",
    "source_registry_coordinate",
    "workflow_schedule",
)

__all__ = ["APPLICATION_NAME", "CAPABILITY_PORTS"]
