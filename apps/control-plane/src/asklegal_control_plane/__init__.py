"""Private control-plane HTTP application boundary."""

APPLICATION_NAME: str = "control-plane"
CAPABILITY_PORTS: tuple[str, ...] = (
    "control_http_api",
    "coverage_report_read",
    "management_register_control",
    "proposal_package_prepare",
    "source_registry_coordinate",
    "workflow_schedule",
)

from asklegal_control_plane.api import create_app
from asklegal_control_plane.proposal import (
    ProposalMemberReceipt,
    ProposalPreparationService,
    ProposalRegistrationService,
    StoredProposalPackage,
    VaultProposalPreparationService,
)

__all__ = [
    "APPLICATION_NAME",
    "CAPABILITY_PORTS",
    "ProposalMemberReceipt",
    "ProposalPreparationService",
    "ProposalRegistrationService",
    "StoredProposalPackage",
    "VaultProposalPreparationService",
    "create_app",
]
