"""The ordered raw bytes -> schema -> typed-boundary proof path."""

from pydantic import ValidationError

from asklegal_contracts.errors import ContractErrorCode, ContractViolation
from asklegal_contracts.models import ServingRecordBoundary
from asklegal_contracts.schemas import SchemaRegistry
from asklegal_contracts.strict_json import parse_json_bytes

SERVING_RECORD_SCHEMA = "schemas/serving-domain.schema.json#/$defs/serving_record"


def parse_serving_record(
    raw: bytes,
    *,
    max_bytes: int,
    schema_registry: SchemaRegistry,
) -> ServingRecordBoundary:
    """Apply the normative order without Pydantic parsing the raw JSON."""
    value = parse_json_bytes(raw, max_bytes=max_bytes)
    schema_registry.validate(value, SERVING_RECORD_SCHEMA)
    try:
        return ServingRecordBoundary.model_validate(value, strict=True)
    except ValidationError as error:
        raise ContractViolation(ContractErrorCode.TYPE_BINDING_INVALID) from error
