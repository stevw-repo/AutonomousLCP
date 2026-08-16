"""Preloaded, network-disabled Draft 2020-12 schema validation."""

from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import urldefrag

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable
from referencing.jsonschema import DRAFT202012, Schema

from asklegal_contracts.errors import ContractErrorCode, ContractViolation
from asklegal_contracts.json_types import JsonValue
from asklegal_contracts.strict_json import parse_json_bytes

type SchemaObject = dict[str, JsonValue]


class SchemaRegistry:
    """A closed in-memory registry containing only repository schema bytes."""

    _resources: Registry[Schema]
    _ids_by_path: dict[str, str]

    def __init__(self, resources: Registry[Schema], ids_by_path: dict[str, str]) -> None:
        """Store an already closed resource registry and path map."""
        self._resources = resources
        self._ids_by_path = dict(ids_by_path)

    @classmethod
    def from_contracts_root(cls, contracts_root: Path) -> SchemaRegistry:
        """Load and check every local schema before the registry can be used."""
        schema_root = contracts_root / "schemas"
        resources: Registry[Schema] = Registry()
        ids_by_path: dict[str, str] = {}
        for path in sorted(schema_root.glob("*.schema.json")):
            parsed = parse_json_bytes(path.read_bytes(), max_bytes=2_000_000)
            if not isinstance(parsed, dict):
                raise ContractViolation(ContractErrorCode.SCHEMA_INVALID)
            schema: SchemaObject = parsed
            schema_id = schema.get("$id")
            if not isinstance(schema_id, str):
                raise ContractViolation(ContractErrorCode.SCHEMA_INVALID)
            if not schema_id.startswith("https://contracts.asklegal.local/v1/"):
                raise ContractViolation(ContractErrorCode.SCHEMA_REFERENCE_FORBIDDEN)
            try:
                Draft202012Validator.check_schema(schema)
                resource: Resource[Schema] = Resource.from_contents(
                    cast("Schema", schema),
                    default_specification=DRAFT202012,
                )
            except (SchemaError, TypeError, ValueError) as error:
                raise ContractViolation(ContractErrorCode.SCHEMA_INVALID) from error
            resources = resources.with_resource(schema_id, resource)
            ids_by_path[f"schemas/{path.name}"] = schema_id
        return cls(resources, ids_by_path)

    def _absolute_reference(self, schema_ref: str) -> str:
        resource, fragment = urldefrag(schema_ref)
        if resource.startswith(("http:", "https:")):
            if not resource.startswith("https://contracts.asklegal.local/v1/"):
                raise ContractViolation(ContractErrorCode.SCHEMA_REFERENCE_FORBIDDEN)
            absolute = resource
        else:
            normalized = PurePosixPath(resource).as_posix()
            if normalized.startswith("/") or ".." in PurePosixPath(normalized).parts:
                raise ContractViolation(ContractErrorCode.SCHEMA_REFERENCE_FORBIDDEN)
            absolute = self._ids_by_path.get(normalized, "")
            if not absolute:
                raise ContractViolation(ContractErrorCode.UNKNOWN_SCHEMA)
        return f"{absolute}#{fragment}" if fragment else absolute

    def validate(self, value: JsonValue, schema_ref: str) -> None:
        """Validate against one admitted schema reference without retrieval."""
        absolute_reference = self._absolute_reference(schema_ref)
        wrapper: SchemaObject = {"$ref": absolute_reference}
        validator = Draft202012Validator(
            wrapper,
            registry=self._resources,
            format_checker=FormatChecker(),
        )
        try:
            # jsonschema exposes Any here; this adapter narrows it and tests both outcomes.
            iter_errors = cast(
                "Callable[[object], Iterator[ValidationError]]",
                validator.iter_errors,  # pyright: ignore[reportUnknownMemberType]
            )
            first_error = next(iter_errors(value), None)
        except (NoSuchResource, Unresolvable) as error:
            raise ContractViolation(ContractErrorCode.UNKNOWN_SCHEMA) from error
        if first_error is not None:
            location = "$" + "".join(f"[{part!r}]" for part in first_error.absolute_path)
            raise ContractViolation(ContractErrorCode.SCHEMA_INVALID, location)
