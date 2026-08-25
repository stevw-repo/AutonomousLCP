"""External immutable ADR 0074 HKEX conformance-attestation proofs."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import fingerprint, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_CONFORMANCE_ATTESTATION_RULE_ID,
    HKEX_CONFORMANCE_CASE_RESULT_COUNT,
    HKEXConformanceArtifactBinding,
    HKEXConformanceAttestationError,
    HKEXConformanceAttestationOutcome,
    HKEXConformanceAttestationReason,
    evaluate_hkex_conformance_attestation,
    hkex_conformance_attestation_from_document,
    validate_hkex_conformance_universe,
)
from jsonschema import Draft202012Validator

from tools.architecture_spike import run_spike
from tools.build_hk_regulatory_attestation import build_hkex_conformance_attestation

ROOT = Path(__file__).resolve().parents[3]
BUNDLE_ROOT = ROOT / "packages/legal-desks/conformance/hk-regulatory"
PACKAGE_ROOT = ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_regulatory_package"
ATTESTATION_PATH = BUNDLE_ROOT / "attestations/HKREG-CONFORMANCE-ATTESTATION-001.json"
EXPECTED_PATH = BUNDLE_ROOT / "expected/HKREG-CONFORMANCE-ATTESTATION-001.json"
ATTESTATION_SCHEMA_PATH = BUNDLE_ROOT / "contracts/hkex-conformance-attestation.schema.json"
RESULT_SCHEMA_PATH = BUNDLE_ROOT / "contracts/hkex-conformance-attestation-result.schema.json"
RULE_PATH = BUNDLE_ROOT / "rules/HKREG-CONFORMANCE-ATTESTATION-001.json"


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def test_external_attestation_validates_and_grants_only_build_compatibility() -> None:
    document = _document(ATTESTATION_PATH)
    expected = _document(EXPECTED_PATH)
    attestation_schema = _document(ATTESTATION_SCHEMA_PATH)
    result_schema = _document(RESULT_SCHEMA_PATH)
    for schema in (attestation_schema, result_schema):
        Draft202012Validator.check_schema(schema)
    _validator(attestation_schema).validate(document)
    _validator(result_schema).validate(expected)

    attestation = hkex_conformance_attestation_from_document(document)
    result = evaluate_hkex_conformance_attestation(attestation, attestation.evidence)
    assert result.document() == expected
    assert result.outcome is HKEXConformanceAttestationOutcome.VALID
    assert result.reason is (
        HKEXConformanceAttestationReason.COMPLETE_SOURCE_NEUTRAL_BUILD_COMPATIBILITY
    )
    assert result.build_compatibility_valid is True
    assert result.source_access_authorized is False
    assert result.release_creation_authorized is False
    assert result.approval_authorized is False
    assert result.pinecone_authorized is False
    assert result.deployment_authorized is False
    assert result.activation_authorized is False
    assert result.external_effects == "NONE"


def test_attestation_binds_current_package_suite_build_lock_runner_and_contracts() -> None:
    attestation = hkex_conformance_attestation_from_document(_document(ATTESTATION_PATH))
    evidence = attestation.evidence
    manifest = _document(PACKAGE_ROOT / "package.json")
    assert evidence.rulebook_package.package_id == manifest["package_id"]
    assert evidence.rulebook_package.package_version == "0.14.0"
    assert evidence.rulebook_package.package_fingerprint == manifest["package_fingerprint"]

    universe_path = ROOT / evidence.suite.universe.path
    _assert_binding(evidence.suite.universe.path, evidence.suite.universe)
    universe = _json_object(parse_json_bytes(universe_path.read_bytes(), max_bytes=500_000))
    proof = validate_hkex_conformance_universe(universe)
    assert evidence.suite.universe_fingerprint == proof.catalogue_fingerprint
    assert (
        evidence.suite.case_count,
        evidence.suite.coverage_cell_count,
        evidence.suite.pair_count,
    ) == (284, 284, 57)

    for member in evidence.processing_build.members:
        _assert_binding(member.path, member)
    processing_projection = [member.document() for member in evidence.processing_build.members]
    assert evidence.processing_build.inventory_fingerprint == fingerprint(
        checked_json_value(processing_projection)
    )
    for binding in (
        evidence.dependency_lock,
        evidence.conformance_runner,
        evidence.contract_set,
        evidence.architecture.tool,
        evidence.architecture.policy,
    ):
        _assert_binding(binding.path, binding)
    contract_document = checked_json_value(
        json.loads((ROOT / evidence.contract_set.path).read_text(encoding="utf-8"))
    )
    assert evidence.contract_set_fingerprint == fingerprint(contract_document)


def test_complete_case_result_inventory_is_exact_and_reproducible() -> None:
    evidence = hkex_conformance_attestation_from_document(_document(ATTESTATION_PATH)).evidence
    results = evidence.case_results
    assert len(results.members) == HKEX_CONFORMANCE_CASE_RESULT_COUNT == 284
    assert len({member.case_id for member in results.members}) == 284
    assert len({member.result.path for member in results.members}) == 284
    for member in results.members:
        _assert_binding(member.result.path, member.result, root=PACKAGE_ROOT)
        result_document = _document(PACKAGE_ROOT / member.result.path)
        assert result_document["case_id"] == member.case_id

    result_projection: dict[str, JsonValue] = {
        "case_count": 284,
        "members": [member.document() for member in results.members],
    }
    assert results.result_set_fingerprint == fingerprint(checked_json_value(result_projection))
    tree_projection = [
        member.result.document()
        for member in sorted(results.members, key=lambda item: item.result.path)
    ]
    reproduction = evidence.reproducibility
    first, second = reproduction.runs
    assert reproduction.byte_identical is True
    assert first.result_set_fingerprint == second.result_set_fingerprint
    assert first.result_set_fingerprint == results.result_set_fingerprint
    assert first.tree_fingerprint == second.tree_fingerprint
    assert first.tree_fingerprint == fingerprint(checked_json_value(tree_projection))


def test_architecture_report_is_current_exact_and_successful() -> None:
    architecture = hkex_conformance_attestation_from_document(
        _document(ATTESTATION_PATH)
    ).evidence.architecture
    current = run_spike(ROOT).to_json()
    assert architecture.result == "PASS"
    assert architecture.applications == current["applications"]
    assert architecture.packages == current["packages"]
    assert architecture.dependency_edges == current["dependency_edges"]
    assert architecture.capability_ports == current["capability_ports"]
    assert architecture.policy_fingerprint == current["policy_fingerprint"]
    report_projection = architecture.document()
    report_projection.pop("report_fingerprint")
    assert architecture.report_fingerprint == fingerprint(checked_json_value(report_projection))


def test_stale_or_partial_binding_is_rejected_without_compatibility() -> None:
    current = hkex_conformance_attestation_from_document(_document(ATTESTATION_PATH))
    candidate_document = deepcopy(_document(ATTESTATION_PATH))
    evidence = _json_object(candidate_document["evidence"])
    dependency_lock = _json_object(evidence["dependency_lock"])
    dependency_lock["fingerprint"] = "sha256:" + "0" * 64
    candidate = hkex_conformance_attestation_from_document(candidate_document)

    result = evaluate_hkex_conformance_attestation(candidate, current.evidence)
    assert result.outcome is HKEXConformanceAttestationOutcome.INVALID
    assert result.reason is (HKEXConformanceAttestationReason.DEPENDENCY_LOCK_BINDING_MISMATCH)
    assert result.build_compatibility_valid is False
    assert result.external_effects == "NONE"


def test_changed_result_set_is_rejected_without_partial_pass() -> None:
    current = hkex_conformance_attestation_from_document(_document(ATTESTATION_PATH))
    candidate_document = deepcopy(_document(ATTESTATION_PATH))
    evidence = _json_object(candidate_document["evidence"])
    case_results = _json_object(evidence["case_results"])
    first_member = _json_object(_json_array(case_results["members"])[0])
    result_binding = _json_object(first_member["result"])
    result_binding["fingerprint"] = "sha256:" + "1" * 64
    candidate = hkex_conformance_attestation_from_document(candidate_document)

    result = evaluate_hkex_conformance_attestation(candidate, current.evidence)
    assert result.outcome is HKEXConformanceAttestationOutcome.INVALID
    assert result.reason is (HKEXConformanceAttestationReason.CASE_RESULT_INVENTORY_MISMATCH)


def test_authority_overreach_and_external_effect_claim_fail_closed() -> None:
    current = hkex_conformance_attestation_from_document(_document(ATTESTATION_PATH))
    for field, value, expected_reason in (
        (
            "source_access_authorized",
            True,
            HKEXConformanceAttestationReason.AUTHORITY_OVERREACH,
        ),
        (
            "real_source_evaluation",
            True,
            HKEXConformanceAttestationReason.AUTHORITY_OVERREACH,
        ),
        (
            "external_effects",
            "PRESENT",
            HKEXConformanceAttestationReason.EXTERNAL_EFFECT_CLAIM,
        ),
    ):
        candidate_document = deepcopy(_document(ATTESTATION_PATH))
        candidate_document[field] = value
        candidate = hkex_conformance_attestation_from_document(candidate_document)
        result = evaluate_hkex_conformance_attestation(candidate, current.evidence)
        assert result.outcome is HKEXConformanceAttestationOutcome.INVALID
        assert result.reason is expected_reason
        assert result.build_compatibility_valid is False


def test_strict_decoder_rejects_unknown_missing_and_malformed_fields() -> None:
    unknown = deepcopy(_document(ATTESTATION_PATH))
    unknown["unexpected"] = True
    missing = deepcopy(_document(ATTESTATION_PATH))
    missing.pop("final_result")
    malformed = deepcopy(_document(ATTESTATION_PATH))
    malformed["attestation_id"] = "latest"
    for candidate in (unknown, missing, malformed):
        with pytest.raises(HKEXConformanceAttestationError):
            hkex_conformance_attestation_from_document(candidate)


def test_attestation_stays_external_and_has_no_self_fingerprint_cycle() -> None:
    document = _document(ATTESTATION_PATH)
    attestation = hkex_conformance_attestation_from_document(document)
    bound_paths = {
        attestation.evidence.suite.universe.path,
        *(member.path for member in attestation.evidence.processing_build.members),
        attestation.evidence.dependency_lock.path,
        attestation.evidence.conformance_runner.path,
        attestation.evidence.contract_set.path,
        *(member.result.path for member in attestation.evidence.case_results.members),
        attestation.evidence.architecture.tool.path,
        attestation.evidence.architecture.policy.path,
    }
    assert not any(path.startswith("packages/legal-desks/conformance/") for path in bound_paths)
    assert not tuple((PACKAGE_ROOT / "attestations").glob("*.json"))
    assert _document(RULE_PATH)["granted_capabilities"] == ["BUILD_COMPATIBILITY"]
    assert document["rule_id"] == HKEX_CONFORMANCE_ATTESTATION_RULE_ID


def test_generated_attestation_bundle_reproduces_from_two_new_clean_runs() -> None:
    attestation, result = build_hkex_conformance_attestation()
    assert attestation == _document(ATTESTATION_PATH)
    assert result == _document(EXPECTED_PATH)


def _assert_binding(
    path: str,
    binding: HKEXConformanceArtifactBinding,
    *,
    root: Path = ROOT,
) -> None:
    raw = (root / path).read_bytes()
    assert binding.byte_size == len(raw)
    assert binding.fingerprint == f"sha256:{sha256(raw).hexdigest()}"


def _document(path: Path) -> dict[str, JsonValue]:
    return _json_object(parse_json_bytes(path.read_bytes(), max_bytes=2_000_000))


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _json_array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)
