"""Declarative Review API application boundary; no HTTP behavior."""

APPLICATION_NAME: str = "review-api"
CAPABILITY_PORTS: tuple[str, ...] = (
    "approval_command",
    "evidence_read",
    "proposal_read",
    "rejection_command",
    "review_http_api",
    "revocation_command",
)

__all__ = ["APPLICATION_NAME", "CAPABILITY_PORTS"]
