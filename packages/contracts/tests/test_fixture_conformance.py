"""Python reproduction of every implementation-neutral synthetic fixture."""

from pathlib import Path

import pytest
from asklegal_contracts import (
    ContractErrorCode,
    ContractViolation,
    SchemaRegistry,
    canonicalize,
    fingerprint,
    parse_json_bytes,
)
from asklegal_contracts.json_types import JsonValue

from .conftest import CONTRACTS_ROOT

type JsonObject = dict[str, JsonValue]


def _object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _load(path: Path) -> JsonValue:
    raw = path.read_bytes()
    return parse_json_bytes(raw, max_bytes=max(len(raw), 1))


def _result(
    result_code: str,
    failure_codes: list[JsonValue],
    reason_codes: list[JsonValue],
    **extra: JsonValue,
) -> JsonObject:
    result: JsonObject = {
        "result_code": result_code,
        "failure_codes": failure_codes,
        "reason_codes": reason_codes,
    }
    result.update(extra)
    return result


def _all_same(items: list[JsonValue], fields: tuple[str, ...]) -> bool:
    if len(items) < 2:
        return False
    first = _object(items[0])
    for item in items[1:]:
        candidate = _object(item)
        if any(candidate.get(field) != first.get(field) for field in fields):
            return False
    return True


def _fixture_result(fixture: JsonObject, registry: SchemaRegistry) -> JsonObject:
    operation = _text(fixture["operation"])
    input_path = CONTRACTS_ROOT / _text(fixture["input_path"])
    if operation == "PARSE_JSON":
        try:
            _load(input_path)
        except ContractViolation as error:
            failure = (
                "FAILURE_NON_CANONICAL"
                if error.code is ContractErrorCode.NON_CANONICAL_JSON
                else "FAILURE_MALFORMED_JSON"
            )
            return _result("BLOCK", [failure], [])
        return _result("PASS", [], ["VALIDATION_COMPLETE"])

    input_value = _load(input_path)
    if operation == "SCHEMA_VALIDATE":
        try:
            registry.validate(input_value, _text(fixture["schema_ref"]))
        except ContractViolation as error:
            assert error.code is ContractErrorCode.SCHEMA_INVALID
            return _result("BLOCK", ["FAILURE_SCHEMA_INVALID"], [])
        return _result("PASS", [], ["SCHEMA_VALID", "VALIDATION_COMPLETE"])

    input_object = _object(input_value)
    if operation == "TRANSITION_CHECK":
        machine = _object(_load(CONTRACTS_ROOT / _text(fixture["state_machine_ref"])))
        allowed = any(
            _object(transition).get("from") == input_object.get("from")
            and _object(transition).get("to") == input_object.get("to")
            for transition in _array(machine["allowed_transitions"])
        )
        if allowed:
            return _result("PASS", [], ["TRANSITION_ALLOWED"])
        return _result(
            "BLOCK",
            ["FAILURE_FORBIDDEN_TRANSITION"],
            ["TRANSITION_UNLISTED"],
        )

    if operation == "RETRY_CHECK":
        exact = _all_same(
            _array(input_object["attempts"]),
            ("idempotency_key", "input_fingerprint"),
        )
        if exact:
            return _result("PASS", [], ["EXACT_REPLAY", "RETRY_INPUT_UNCHANGED"])
        return _result("BLOCK", ["FAILURE_RETRY_INPUT_CHANGED"], [])

    if operation == "IDEMPOTENCY_CHECK":
        exact = _all_same(
            _array(input_object["registrations"]),
            ("object_id", "input_fingerprint"),
        )
        if exact:
            return _result("PASS", [], ["EXACT_REPLAY"])
        return _result("BLOCK", ["FAILURE_ID_COLLISION"], [])

    if operation == "CANONICALIZE":
        documents = _array(input_object["documents"])
        canonical_documents = [canonicalize(document) for document in documents]
        if len(set(canonical_documents)) != 1:
            return _result("BLOCK", ["FAILURE_REPRODUCIBILITY"], [])
        canonical = canonical_documents[0]
        return _result(
            "PASS",
            [],
            ["VALIDATION_COMPLETE"],
            canonical_json=canonical.decode("utf-8"),
            fingerprint=fingerprint(documents[0]),
        )

    pytest.fail(f"Unsupported fixture operation: {operation}")


def test_python_reproduces_every_current_fixture(schema_registry: SchemaRegistry) -> None:
    """All nineteen Node-oracle fixture results are byte-equivalent in Python."""
    catalogue = _object(_load(CONTRACTS_ROOT / "fixtures/catalogue.json"))
    entries = _array(catalogue["fixtures"])
    assert len(entries) == 19
    for entry_value in entries:
        entry = _object(entry_value)
        fixture = _object(_load(CONTRACTS_ROOT / _text(entry["path"])))
        registry_ref = _text(catalogue["fixture_schema_ref"])
        schema_registry.validate(fixture, registry_ref)
        actual = _fixture_result(fixture, schema_registry)
        expected = _load(CONTRACTS_ROOT / _text(fixture["expected_path"]))
        assert canonicalize(actual) == canonicalize(expected), _text(fixture["fixture_id"])
