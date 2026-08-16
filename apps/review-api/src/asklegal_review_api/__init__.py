"""Public human Review API application boundary."""

APPLICATION_NAME: str = "review-api"
CAPABILITY_PORTS: tuple[str, ...] = (
    "approval_command",
    "evidence_read",
    "proposal_read",
    "rejection_command",
    "review_http_api",
    "revocation_command",
)

from asklegal_review_api.api import create_app

__all__ = ["APPLICATION_NAME", "CAPABILITY_PORTS", "create_app"]
