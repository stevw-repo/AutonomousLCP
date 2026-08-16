"""Strict, size-bounded raw-byte JSON parsing."""

import codecs
import json
import math
from collections.abc import Callable
from typing import cast

from asklegal_contracts.errors import ContractErrorCode, ContractViolation
from asklegal_contracts.json_types import JsonValue, checked_json_value

MAX_SAFE_INTEGER = 9_007_199_254_740_991


def _parse_integer(token: str) -> int:
    if token == "-0":
        raise ContractViolation(ContractErrorCode.NON_CANONICAL_JSON)
    value = int(token)
    if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
        raise ContractViolation(ContractErrorCode.NON_CANONICAL_JSON)
    return value


def _parse_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ContractViolation(ContractErrorCode.MALFORMED_JSON)
    if value == 0.0 and token.startswith("-"):
        raise ContractViolation(ContractErrorCode.NON_CANONICAL_JSON)
    return value


def _reject_constant(_token: str) -> float:
    raise ContractViolation(ContractErrorCode.MALFORMED_JSON)


def _object_from_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ContractViolation(ContractErrorCode.MALFORMED_JSON)
        result[key] = value
    return result


def _decoder() -> Callable[[str], object]:
    def decode(text: str) -> object:
        return cast(
            "object",
            json.loads(
                text,
                object_pairs_hook=_object_from_pairs,
                parse_float=_parse_float,
                parse_int=_parse_integer,
                parse_constant=_reject_constant,
            ),
        )

    return decode


def parse_json_bytes(raw: bytes, *, max_bytes: int) -> JsonValue:
    """Parse one strict JSON value after enforcing an explicit byte ceiling."""
    if max_bytes < 1 or len(raw) > max_bytes:
        raise ContractViolation(ContractErrorCode.BODY_TOO_LARGE)
    if raw.startswith(codecs.BOM_UTF8):
        raise ContractViolation(ContractErrorCode.NON_CANONICAL_JSON)
    try:
        text = raw.decode("utf-8", errors="strict")
        value = _decoder()(text)
        return checked_json_value(value)
    except ContractViolation:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ContractViolation(ContractErrorCode.MALFORMED_JSON) from error
