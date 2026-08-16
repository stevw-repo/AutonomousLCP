"""Independent JSON-contract oracle for M5 closed runtime code sets."""

from pathlib import Path
from typing import TYPE_CHECKING

from asklegal_contracts import parse_json_bytes
from asklegal_legal_desks import GenerativeTask, LegalDisposition, PredicateOperator, ReadinessState

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


def _definitions() -> dict[str, JsonValue]:
    path = _CONTRACTS_ROOT / "schemas/processing-domain.schema.json"
    raw = path.read_bytes()
    schema = _object(parse_json_bytes(raw, max_bytes=len(raw)))
    return _object(schema["$defs"])


def _property_enum(definition: JsonValue, property_name: str) -> set[str]:
    properties = _object(_object(definition)["properties"])
    values = _array(_object(properties[property_name])["enum"])
    return {_text(value) for value in values}


def test_m5_runtime_enums_equal_the_normative_json_contract() -> None:
    """No executable package runtime code can drift from contract 1.4.0."""
    definitions = _definitions()
    assert {item.value for item in ReadinessState} == _property_enum(
        definitions["scope_readiness"],
        "state",
    )
    result_properties = _object(_object(definitions["rule_execution_result"])["properties"])
    disposition_any_of = _array(_object(result_properties["disposition"])["anyOf"])
    disposition_values = _array(_object(disposition_any_of[0])["enum"])
    assert {item.value for item in LegalDisposition} == {
        _text(value) for value in disposition_values
    }
    assert {item.value for item in PredicateOperator} == _property_enum(
        definitions["rule_predicate"],
        "operator",
    )
    assert {item.value for item in GenerativeTask} == _property_enum(
        definitions["semantic_task_request"],
        "task",
    )
    assert {item.value for item in GenerativeTask} == _property_enum(
        definitions["semantic_decision"],
        "task",
    )
