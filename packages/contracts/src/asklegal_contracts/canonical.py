"""Narrow RFC 8785 and SHA-256 adapter."""

from hashlib import sha256

import rfc8785

from asklegal_contracts.errors import ContractErrorCode, ContractViolation
from asklegal_contracts.json_types import JsonValue


def canonicalize(value: JsonValue) -> bytes:
    """Return exact RFC 8785 canonical UTF-8 bytes."""
    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as error:
        raise ContractViolation(ContractErrorCode.CANONICALIZATION_FAILED) from error


def fingerprint(value: JsonValue) -> str:
    """Fingerprint canonical JSON using the repository encoding."""
    return f"sha256:{sha256(canonicalize(value)).hexdigest()}"
