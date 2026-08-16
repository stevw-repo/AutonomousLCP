"""Independent JSON-contract oracle for M2 command and effect objects."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING

from asklegal_contracts import parse_json_bytes
from asklegal_domain import (
    ApplicationCode,
    CommandEnvelope,
    CommandPayload,
    CommandResult,
    CommandResultCode,
    CommandSubmissionResolutionCode,
    DeclaredCompensation,
    DestinationClass,
    EffectCancelledDetail,
    EffectCapability,
    EffectFinalFailureDetail,
    EffectIntent,
    EffectReceipt,
    EffectReceiptStatus,
    EffectSuccessDetail,
    EffectType,
    EffectUnknownDetail,
    FailureCode,
    NoCompensation,
    ReferenceType,
    RetryClass,
    StopCondition,
)

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


def _operation_definitions() -> dict[str, JsonValue]:
    path = _CONTRACTS_ROOT / "schemas/operation-domain.schema.json"
    raw = path.read_bytes()
    schema = _object(parse_json_bytes(raw, max_bytes=len(raw)))
    return _object(schema["$defs"])


def _common_definitions() -> dict[str, JsonValue]:
    path = _CONTRACTS_ROOT / "schemas/common.schema.json"
    raw = path.read_bytes()
    schema = _object(parse_json_bytes(raw, max_bytes=len(raw)))
    return _object(schema["$defs"])


def _enum(definition: dict[str, JsonValue]) -> set[str]:
    return {_text(value) for value in _array(definition["enum"])}


def _property_enum(definition: dict[str, JsonValue], property_name: str) -> set[str]:
    properties = _object(definition["properties"])
    return _enum(_object(properties[property_name]))


def _required(definition: dict[str, JsonValue], *constant_fields: str) -> set[str]:
    required = {_text(value) for value in _array(definition["required"])}
    return required - set(constant_fields)


def test_all_closed_python_codes_equal_the_normative_json_enums() -> None:
    """Every Python code set must equal its independent JSON contract enum."""
    definitions = _operation_definitions()
    common = _common_definitions()
    reference = _object(_object(common["reference"])["properties"])

    assert {item.value for item in ReferenceType} == _enum(_object(reference["ref_type"]))
    assert {item.value for item in FailureCode} == _enum(_object(common["failure_code"]))
    assert {item.value for item in CommandResultCode} == _enum(
        _object(definitions["command_result_code"]),
    )
    assert {item.value for item in CommandSubmissionResolutionCode} == _enum(
        _object(definitions["command_submission_resolution_code"]),
    )
    assert {item.value for item in EffectType} == _enum(_object(definitions["effect_type"]))

    intent = _object(definitions["effect_intent"])
    assert {item.value for item in ApplicationCode} == _property_enum(
        intent,
        "owning_application",
    )
    assert {item.value for item in EffectCapability} == _property_enum(
        intent,
        "required_capability",
    )
    assert {item.value for item in DestinationClass} == _property_enum(
        intent,
        "destination_class",
    )
    assert {item.value for item in RetryClass} == _property_enum(intent, "retry_class")
    stop_conditions = _object(_object(intent["properties"])["stop_conditions"])
    assert {item.value for item in StopCondition} == _enum(_object(stop_conditions["items"]))

    receipt = _object(definitions["effect_receipt"])
    assert {item.value for item in EffectReceiptStatus} == _property_enum(
        receipt,
        "terminal_status",
    )


def test_python_object_fields_equal_every_normative_required_field() -> None:
    """Every domain dataclass must carry every non-constant required field."""
    definitions = _operation_definitions()
    immutable_constants = ("schema_id", "schema_version", "immutable")

    assert {field.name for field in fields(CommandPayload)} == _required(
        _object(definitions["command_payload"]),
    )
    assert {field.name for field in fields(CommandEnvelope)} == _required(
        _object(definitions["command_envelope"]),
        *immutable_constants,
    )
    assert {field.name for field in fields(CommandResult)} == _required(
        _object(definitions["command_result"]),
        *immutable_constants,
    )
    assert {field.name for field in fields(EffectIntent)} == _required(
        _object(definitions["effect_intent"]),
        *immutable_constants,
    )
    assert {field.name for field in fields(EffectReceipt)} == _required(
        _object(definitions["effect_receipt"]),
        *immutable_constants,
    )

    assert {field.name for field in fields(NoCompensation)} == _required(
        _object(definitions["no_compensation"]),
        "mode",
    )
    assert {field.name for field in fields(DeclaredCompensation)} == _required(
        _object(definitions["declared_compensation"]),
        "mode",
    )
    assert {field.name for field in fields(EffectSuccessDetail)} == _required(
        _object(definitions["effect_success_detail"]),
        "detail_type",
    )
    assert {field.name for field in fields(EffectFinalFailureDetail)} == _required(
        _object(definitions["effect_final_failure_detail"]),
        "detail_type",
    )
    assert {field.name for field in fields(EffectCancelledDetail)} == _required(
        _object(definitions["effect_cancelled_detail"]),
        "detail_type",
    )
    assert {field.name for field in fields(EffectUnknownDetail)} == _required(
        _object(definitions["effect_unknown_detail"]),
        "detail_type",
        "reconciliation_required",
    )
