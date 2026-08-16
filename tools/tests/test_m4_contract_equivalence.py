"""Independent JSON-contract oracle for M4 closed runtime code sets."""

from pathlib import Path
from typing import TYPE_CHECKING

from asklegal_contracts import parse_json_bytes
from asklegal_evidence_vault import ArtifactClass, VaultName
from asklegal_source_connectors import (
    AcquisitionConsequence,
    AuthenticationClass,
    HttpMethod,
    ObservationDisposition,
    ScraperResultCode,
    WatcherResultCode,
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


def _definitions() -> dict[str, JsonValue]:
    path = _CONTRACTS_ROOT / "schemas/source-domain.schema.json"
    raw = path.read_bytes()
    schema = _object(parse_json_bytes(raw, max_bytes=len(raw)))
    return _object(schema["$defs"])


def _property_enum(definition: JsonValue, property_name: str) -> set[str]:
    properties = _object(_object(definition)["properties"])
    values = _array(_object(properties[property_name])["enum"])
    return {_text(value) for value in values}


def test_all_m4_python_codes_equal_the_normative_json_enums() -> None:
    """No M4 runtime code can drift from its versioned machine contract."""
    definitions = _definitions()
    assert {item.value for item in HttpMethod} == _property_enum(
        definitions["connector_request"],
        "method",
    )
    assert {item.value for item in AuthenticationClass} == _property_enum(
        definitions["connector_request"],
        "authentication_class",
    )
    assert {item.value for item in WatcherResultCode} == _property_enum(
        definitions["watcher_result"],
        "result_code",
    )
    assert {item.value for item in ScraperResultCode} == _property_enum(
        definitions["scraper_result"],
        "result_code",
    )
    assert {item.value for item in VaultName} == _property_enum(
        definitions["vault_object_receipt"],
        "vault_role",
    )
    assert {item.value for item in ArtifactClass} == _property_enum(
        definitions["evidence_object"],
        "artifact_class",
    )
    assert {item.value for item in ObservationDisposition} == _property_enum(
        definitions["acquisition_outcome"],
        "disposition",
    )
    assert {item.value for item in AcquisitionConsequence} == _property_enum(
        definitions["acquisition_outcome"],
        "downstream_authorization",
    )
