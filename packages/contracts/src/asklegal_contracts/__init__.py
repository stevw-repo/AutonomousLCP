"""Strict adapters for the repository-owned AskLegal contracts."""

from asklegal_contracts.canonical import canonicalize, fingerprint
from asklegal_contracts.errors import ContractErrorCode, ContractViolation
from asklegal_contracts.models import ServingMetadataBoundary, ServingRecordBoundary
from asklegal_contracts.pipeline import parse_serving_record
from asklegal_contracts.proposal_members import (
    ProposalMemberBindings,
    ProposalMemberViolation,
    validate_v1_proposal_members,
)
from asklegal_contracts.schemas import SchemaRegistry
from asklegal_contracts.strict_json import parse_json_bytes

PACKAGE_ROLE: str = "contracts"

__all__ = [
    "PACKAGE_ROLE",
    "ContractErrorCode",
    "ContractViolation",
    "ProposalMemberBindings",
    "ProposalMemberViolation",
    "SchemaRegistry",
    "ServingMetadataBoundary",
    "ServingRecordBoundary",
    "canonicalize",
    "fingerprint",
    "parse_json_bytes",
    "parse_serving_record",
    "validate_v1_proposal_members",
]
