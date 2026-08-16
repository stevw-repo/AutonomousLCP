"""Tests for offline schema resolution and ordered typed binding."""

from pathlib import Path

import pytest
from asklegal_contracts import (
    ContractErrorCode,
    ContractViolation,
    SchemaRegistry,
    ServingRecordBoundary,
    parse_json_bytes,
    parse_serving_record,
)
from asklegal_contracts.json_types import JsonValue
from pydantic import ValidationError

from .conftest import CONTRACTS_ROOT

type JsonObject = dict[str, JsonValue]

POSITIVE_RECORD = CONTRACTS_ROOT / "fixtures/XCF-POSITIVE-001/input.json"
NEGATIVE_RECORD = CONTRACTS_ROOT / "fixtures/XCF-NEGATIVE-001/input.json"


def _reference(ref_type: str, prefix: str, digit: str) -> JsonObject:
    return {
        "ref_type": ref_type,
        "ref_id": f"{prefix}_{digit * 48}",
        "fingerprint": f"sha256:{digit * 64}",
    }


def _contract_reference(digit: str) -> JsonObject:
    return {
        "contract_id": "synthetic-policy",
        "version": "1.0.0",
        "fingerprint": f"sha256:{digit * 64}",
    }


def test_every_repository_schema_loads_into_the_closed_registry(
    schema_registry: SchemaRegistry,
) -> None:
    """Construction checks every local Draft 2020-12 schema before use."""
    value = parse_json_bytes(POSITIVE_RECORD.read_bytes(), max_bytes=2_000)
    schema_registry.validate(
        value,
        "schemas/serving-domain.schema.json#/$defs/serving_record",
    )


def test_external_and_unknown_schema_references_fail_closed(
    schema_registry: SchemaRegistry,
) -> None:
    """Validation never performs implicit HTTP or filesystem retrieval."""
    with pytest.raises(ContractViolation) as external:
        schema_registry.validate({}, "https://example.invalid/schema.json")
    assert external.value.code is ContractErrorCode.SCHEMA_REFERENCE_FORBIDDEN

    with pytest.raises(ContractViolation) as unknown:
        schema_registry.validate({}, "schemas/not-present.schema.json")
    assert unknown.value.code is ContractErrorCode.UNKNOWN_SCHEMA


def test_schema_rejects_the_forbidden_seventh_metadata_field(
    schema_registry: SchemaRegistry,
) -> None:
    """The normative schema closes the six-field serving envelope."""
    value = parse_json_bytes(NEGATIVE_RECORD.read_bytes(), max_bytes=2_000)
    with pytest.raises(ContractViolation) as captured:
        schema_registry.validate(
            value,
            "schemas/serving-domain.schema.json#/$defs/serving_record",
        )
    assert captured.value.code is ContractErrorCode.SCHEMA_INVALID


def test_ordered_pipeline_binds_only_after_schema_validation(
    schema_registry: SchemaRegistry,
) -> None:
    """Raw bytes follow strict parse, schema, then strict Pydantic binding."""
    record = parse_serving_record(
        POSITIVE_RECORD.read_bytes(),
        max_bytes=2_000,
        schema_registry=schema_registry,
    )
    assert isinstance(record, ServingRecordBoundary)
    assert record.metadata.jurisdiction == "SYN"


def test_boundary_model_is_strict_closed_and_frozen(
    schema_registry: SchemaRegistry,
) -> None:
    """Pydantic cannot coerce, extend, or mutate the typed boundary."""
    with pytest.raises(ValidationError):
        ServingRecordBoundary.model_validate(
            {
                "id": 1,
                "metadata": {
                    "text": "x",
                    "country": "x",
                    "jurisdiction": "x",
                    "type": "x",
                    "source": "x",
                    "authority_note": "x",
                },
            },
            strict=True,
        )

    record = parse_serving_record(
        POSITIVE_RECORD.read_bytes(),
        max_bytes=2_000,
        schema_registry=schema_registry,
    )
    with pytest.raises(ValidationError):
        record.id = "rec_ffffffffffffffffffffffffffffffffffffffffffffffff"


def test_contracts_path_argument_is_not_implicitly_discovered(tmp_path: Path) -> None:
    """An empty caller-supplied root cannot fall back to the repository."""
    (tmp_path / "schemas").mkdir()
    registry = SchemaRegistry.from_contracts_root(tmp_path)
    with pytest.raises(ContractViolation) as captured:
        registry.validate({}, "schemas/common.schema.json")
    assert captured.value.code is ContractErrorCode.UNKNOWN_SCHEMA


def test_approval_v1_1_has_no_independent_expiry(
    schema_registry: SchemaRegistry,
) -> None:
    """The amended Approval is single-use and manifest-bound, not TTL-bound."""
    approval: JsonObject = {
        "schema_id": "asklegal.approval-decision",
        "schema_version": "1.1.0",
        "approval_id": f"apr_{'1' * 48}",
        "decision_time": "2026-08-16T01:00:00Z",
        "promotion_manifest_ref": _reference("PROMOTION_MANIFEST", "pmn", "2"),
        "decision": "APPROVED",
        "reviewer_identity_ref": _reference("ACTOR", "act", "3"),
        "authority_evidence_ref": _reference("EVIDENCE", "evi", "4"),
        "reason": "Complete synthetic package reviewed",
        "valid_from": "2026-08-16T01:00:00Z",
        "expected_base_serving_state_ref": _reference("SERVING_STATE", "srv", "5"),
        "validity_condition_refs": [_contract_reference("6")],
        "governance_policy_state": "CONFIGURED",
        "immutable": True,
    }
    schema_ref = "schemas/promotion-domain.schema.json#/$defs/approval_decision"
    schema_registry.validate(approval, schema_ref)

    legacy = dict(approval)
    legacy["schema_version"] = "1.0.0"
    legacy["valid_until"] = "2026-08-16T05:00:00Z"
    with pytest.raises(ContractViolation) as captured:
        schema_registry.validate(legacy, schema_ref)
    assert captured.value.code is ContractErrorCode.SCHEMA_INVALID


def test_coverage_status_v1_1_binds_verification_refs_and_warning(
    schema_registry: SchemaRegistry,
) -> None:
    """Each scope exposes exact evidence and a status-matched warning code."""
    scope_status: JsonObject = {
        "release_scope_ref": _reference("RELEASE_SCOPE", "rsc", "1"),
        "status": "KNOWN_GAP",
        "last_verified_at": "2026-08-16T01:00:00Z",
        "coverage_gap_refs": [_reference("COVERAGE_GAP", "cgp", "2")],
        "quarantine_refs": [],
        "source_failure_refs": [],
        "warning_code": "COVERAGE_KNOWN_GAP",
    }
    manifest: JsonObject = {
        "schema_id": "asklegal.coverage-status-manifest",
        "schema_version": "1.1.0",
        "coverage_status_manifest_id": f"csm_{'3' * 48}",
        "created_at": "2026-08-16T01:00:00Z",
        "observation_cutoff": "2026-08-16T00:00:00Z",
        "serving_state_id": f"srv_{'4' * 48}",
        "coverage_gap_refs": [_reference("COVERAGE_GAP", "cgp", "2")],
        "quarantine_refs": [],
        "source_failure_refs": [],
        "scope_statuses": [scope_status],
        "immutable": True,
    }
    schema_ref = "schemas/corpus-domain.schema.json#/$defs/coverage_status_manifest"
    schema_registry.validate(manifest, schema_ref)

    wrong_warning = dict(manifest)
    wrong_scope = dict(scope_status)
    wrong_scope["warning_code"] = "NO_COVERAGE_WARNING"
    wrong_warning["scope_statuses"] = [wrong_scope]
    with pytest.raises(ContractViolation) as captured:
        schema_registry.validate(wrong_warning, schema_ref)
    assert captured.value.code is ContractErrorCode.SCHEMA_INVALID

    legacy = dict(manifest)
    legacy["signature_policy_state"] = "CONFIGURED"
    with pytest.raises(ContractViolation) as captured:
        schema_registry.validate(legacy, schema_ref)
    assert captured.value.code is ContractErrorCode.SCHEMA_INVALID
