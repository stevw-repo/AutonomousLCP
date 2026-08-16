"""Stable errors emitted by the strict contract boundary."""

from enum import StrEnum


class ContractErrorCode(StrEnum):
    """Closed error codes for the local contract adapter."""

    BODY_TOO_LARGE = "CONTRACT_BODY_TOO_LARGE"
    CANONICALIZATION_FAILED = "CONTRACT_CANONICALIZATION_FAILED"
    MALFORMED_JSON = "CONTRACT_MALFORMED_JSON"
    NON_CANONICAL_JSON = "CONTRACT_NON_CANONICAL_JSON"
    SCHEMA_INVALID = "CONTRACT_SCHEMA_INVALID"
    SCHEMA_REFERENCE_FORBIDDEN = "CONTRACT_SCHEMA_REFERENCE_FORBIDDEN"
    TYPE_BINDING_INVALID = "CONTRACT_TYPE_BINDING_INVALID"
    UNKNOWN_SCHEMA = "CONTRACT_UNKNOWN_SCHEMA"


class ContractViolation(ValueError):
    """One normalized boundary failure without third-party error text."""

    code: ContractErrorCode
    location: str

    def __init__(self, code: ContractErrorCode, location: str = "$") -> None:
        """Create a stable error with no dependency-owned message."""
        self.code = code
        self.location = location
        super().__init__(f"{code.value} at {location}")
