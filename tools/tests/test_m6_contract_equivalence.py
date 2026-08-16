"""Independent JSON-contract oracle for M6 closed runtime code sets."""

from pathlib import Path
from typing import TYPE_CHECKING

from asklegal_contracts import parse_json_bytes
from asklegal_corpus import CoverageState, CoverageWarning
from asklegal_management_register_ports import ApprovalState

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "contracts"


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _definitions(name: str) -> dict[str, JsonValue]:
    path = _CONTRACTS_ROOT / "schemas" / name
    raw = path.read_bytes()
    schema = _object(parse_json_bytes(raw, max_bytes=len(raw)))
    return _object(schema["$defs"])


def _property_enum(definition: JsonValue, property_name: str) -> set[str]:
    properties = _object(_object(definition)["properties"])
    values = _array(_object(properties[property_name])["enum"])
    return {_text(value) for value in values}


def test_m6_runtime_enums_equal_the_normative_json_contract() -> None:
    """Coverage and Approval runtime codes cannot drift from contract 1.5.0."""
    corpus = _definitions("corpus-domain.schema.json")
    promotion = _definitions("promotion-domain.schema.json")
    assert {item.value for item in CoverageState} == _property_enum(
        corpus["scope_status"], "status"
    )
    assert {item.value for item in CoverageWarning} == _property_enum(
        corpus["scope_status"], "warning_code"
    )
    lifecycle = _object(promotion["approval_lifecycle_event"])
    assert {item.value for item in ApprovalState} == _property_enum(lifecycle, "from_state")
    assert {item.value for item in ApprovalState} == _property_enum(lifecycle, "to_state")
