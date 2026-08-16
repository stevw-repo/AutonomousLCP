"""Closed JSON value types and recursive runtime checks."""

from typing import cast

from asklegal_contracts.errors import ContractErrorCode, ContractViolation

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

_HIGH_SURROGATE_START = 0xD800
_LOW_SURROGATE_END = 0xDFFF


def _reject_surrogates(value: str, location: str) -> None:
    for character in value:
        if _HIGH_SURROGATE_START <= ord(character) <= _LOW_SURROGATE_END:
            raise ContractViolation(ContractErrorCode.MALFORMED_JSON, location)


def checked_json_value(value: object, location: str = "$") -> JsonValue:
    """Return a recursively checked JSON value with no unknown runtime types."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        _reject_surrogates(value, location)
        return value
    if isinstance(value, list):
        raw_items = cast("list[object]", value)
        return [
            checked_json_value(item, f"{location}[{index}]") for index, item in enumerate(raw_items)
        ]
    if isinstance(value, dict):
        raw_mapping = cast("dict[object, object]", value)
        result: dict[str, JsonValue] = {}
        for raw_key, raw_value in raw_mapping.items():
            if not isinstance(raw_key, str):
                raise ContractViolation(ContractErrorCode.MALFORMED_JSON, location)
            _reject_surrogates(raw_key, location)
            result[raw_key] = checked_json_value(raw_value, f"{location}.{raw_key}")
        return result
    raise ContractViolation(ContractErrorCode.MALFORMED_JSON, location)
