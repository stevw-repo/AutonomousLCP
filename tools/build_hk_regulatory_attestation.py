"""Build the external immutable HKEX Rulebook Conformance Attestation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKEX_CONFORMANCE_ATTESTATION_CONTRACT_VERSION,
    HKEX_CONFORMANCE_ATTESTATION_KIND,
    HKEX_CONFORMANCE_ATTESTATION_RULE_ID,
    HKEX_CONFORMANCE_CASE_RESULT_COUNT,
    HKEXConformanceAttestationOutcome,
    evaluate_hkex_conformance_attestation,
    hkex_conformance_attestation_evidence_from_document,
    seal_hkex_conformance_attestation,
)

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = ROOT / "packages/legal-desks/conformance/hk-regulatory"
ATTESTATION_PATH = BUNDLE_ROOT / "attestations/HKREG-CONFORMANCE-ATTESTATION-001.json"
EXPECTED_PATH = BUNDLE_ROOT / "expected/HKREG-CONFORMANCE-ATTESTATION-001.json"
ATTESTATION_SCHEMA_PATH = BUNDLE_ROOT / "contracts/hkex-conformance-attestation.schema.json"
RESULT_SCHEMA_PATH = BUNDLE_ROOT / "contracts/hkex-conformance-attestation-result.schema.json"
RULE_PATH = BUNDLE_ROOT / "rules/HKREG-CONFORMANCE-ATTESTATION-001.json"

_FINGERPRINT_SCHEMA: dict[str, JsonValue] = {
    "type": "string",
    "pattern": "^sha256:[0-9a-f]{64}$",
}
_ARTIFACT_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["path", "byte_size", "fingerprint"],
    "properties": {
        "path": {
            "type": "string",
            "minLength": 1,
            "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*\\\\)[^/]+(?:/[^/]+)*$",
        },
        "byte_size": {"type": "integer", "minimum": 1},
        "fingerprint": _FINGERPRINT_SCHEMA,
    },
}

_RUN_SUMMARY_CONTRACT = "RUN_SUMMARY_CONTRACT"
_ISOLATED_RUN_MISMATCH = "ISOLATED_RUN_MISMATCH"
_RUN_DID_NOT_PASS = "RUN_DID_NOT_PASS"
_EXPECTED_OBJECT = "EXPECTED_OBJECT"


class HKEXAttestationBuildError(RuntimeError):
    """Two clean executions did not produce one exact successful proof."""


def build_hkex_conformance_attestation() -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """Execute the suite twice and return the attestation and validation result."""
    with TemporaryDirectory(prefix="asklegal-hkreg-attestation-") as temporary:
        temporary_root = Path(temporary)
        first = _isolated_run(temporary_root, 1)
        second = _isolated_run(temporary_root, 2)
    _require_equal_run_bindings(first, second)
    case_results = _object(first["case_results"])
    run_one = {
        "run_id": "ISOLATED_RUN_1",
        "case_count": case_results["case_count"],
        "result_set_fingerprint": case_results["result_set_fingerprint"],
        "tree_fingerprint": first["tree_fingerprint"],
    }
    run_two = {
        "run_id": "ISOLATED_RUN_2",
        "case_count": _object(second["case_results"])["case_count"],
        "result_set_fingerprint": _object(second["case_results"])["result_set_fingerprint"],
        "tree_fingerprint": second["tree_fingerprint"],
    }
    evidence_document: dict[str, JsonValue] = {
        "rulebook_package": first["rulebook_package"],
        "suite": first["suite"],
        "processing_build": first["processing_build"],
        "dependency_lock": first["dependency_lock"],
        "conformance_runner": first["conformance_runner"],
        "contract_set": first["contract_set"],
        "contract_set_fingerprint": first["contract_set_fingerprint"],
        "case_results": first["case_results"],
        "reproducibility": {
            "isolated_run_count": 2,
            "runs": [run_one, run_two],
            "byte_identical": True,
        },
        "architecture": first["architecture"],
    }
    evidence = hkex_conformance_attestation_evidence_from_document(evidence_document)
    attestation = seal_hkex_conformance_attestation(evidence)
    result = evaluate_hkex_conformance_attestation(attestation, evidence)
    if result.outcome is not HKEXConformanceAttestationOutcome.VALID:
        raise HKEXAttestationBuildError(result.reason.value)
    return attestation.document(), result.document()


def build_attestation_schema() -> dict[str, JsonValue]:
    """Return the strict closed external-attestation JSON Schema."""
    package_binding = _closed(
        ["package_id", "package_version", "package_fingerprint"],
        {
            "package_id": {"type": "string", "minLength": 1},
            "package_version": {"type": "string", "minLength": 1},
            "package_fingerprint": _FINGERPRINT_SCHEMA,
        },
    )
    suite_binding = _closed(
        [
            "universe",
            "universe_fingerprint",
            "case_count",
            "coverage_cell_count",
            "pair_count",
        ],
        {
            "universe": _ARTIFACT_SCHEMA,
            "universe_fingerprint": _FINGERPRINT_SCHEMA,
            "case_count": {"const": 284},
            "coverage_cell_count": {"const": 284},
            "pair_count": {"const": 57},
        },
    )
    artifact_set = _closed(
        ["members", "inventory_fingerprint"],
        {
            "members": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": _ARTIFACT_SCHEMA,
            },
            "inventory_fingerprint": _FINGERPRINT_SCHEMA,
        },
    )
    case_result = _closed(
        ["case_id", "result"],
        {
            "case_id": {
                "type": "string",
                "pattern": "^HKREG-(?:DEC|DET)-[A-Z]{3}-[0-9]{3}$",
            },
            "result": _ARTIFACT_SCHEMA,
        },
    )
    case_results = _closed(
        ["case_count", "members", "result_set_fingerprint"],
        {
            "case_count": {"const": 284},
            "members": {
                "type": "array",
                "minItems": 284,
                "maxItems": 284,
                "uniqueItems": True,
                "items": case_result,
            },
            "result_set_fingerprint": _FINGERPRINT_SCHEMA,
        },
    )
    run = _closed(
        ["run_id", "case_count", "result_set_fingerprint", "tree_fingerprint"],
        {
            "run_id": {"enum": ["ISOLATED_RUN_1", "ISOLATED_RUN_2"]},
            "case_count": {"const": 284},
            "result_set_fingerprint": _FINGERPRINT_SCHEMA,
            "tree_fingerprint": _FINGERPRINT_SCHEMA,
        },
    )
    reproducibility = _closed(
        ["isolated_run_count", "runs", "byte_identical"],
        {
            "isolated_run_count": {"const": 2},
            "runs": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "prefixItems": [
                    {"allOf": [run, {"properties": {"run_id": {"const": "ISOLATED_RUN_1"}}}]},
                    {"allOf": [run, {"properties": {"run_id": {"const": "ISOLATED_RUN_2"}}}]},
                ],
                "items": False,
            },
            "byte_identical": {"const": True},
        },
    )
    architecture = _closed(
        [
            "tool",
            "policy",
            "applications",
            "packages",
            "dependency_edges",
            "capability_ports",
            "policy_fingerprint",
            "report_fingerprint",
            "result",
        ],
        {
            "tool": _ARTIFACT_SCHEMA,
            "policy": _ARTIFACT_SCHEMA,
            "applications": {"type": "integer", "minimum": 1},
            "packages": {"type": "integer", "minimum": 1},
            "dependency_edges": {"type": "integer", "minimum": 1},
            "capability_ports": {"type": "integer", "minimum": 1},
            "policy_fingerprint": _FINGERPRINT_SCHEMA,
            "report_fingerprint": _FINGERPRINT_SCHEMA,
            "result": {"const": "PASS"},
        },
    )
    evidence = _closed(
        [
            "rulebook_package",
            "suite",
            "processing_build",
            "dependency_lock",
            "conformance_runner",
            "contract_set",
            "contract_set_fingerprint",
            "case_results",
            "reproducibility",
            "architecture",
        ],
        {
            "rulebook_package": package_binding,
            "suite": suite_binding,
            "processing_build": artifact_set,
            "dependency_lock": _ARTIFACT_SCHEMA,
            "conformance_runner": _ARTIFACT_SCHEMA,
            "contract_set": _ARTIFACT_SCHEMA,
            "contract_set_fingerprint": _FINGERPRINT_SCHEMA,
            "case_results": case_results,
            "reproducibility": reproducibility,
            "architecture": architecture,
        },
    )
    root = _closed(
        [
            "schema_id",
            "schema_version",
            "attestation_id",
            "attestation_kind",
            "jurisdiction",
            "material_family",
            "rule_id",
            "evidence",
            "final_result",
            "capability_claims",
            "real_source_evaluation",
            "source_access_authorized",
            "release_creation_authorized",
            "approval_authorized",
            "pinecone_authorized",
            "deployment_authorized",
            "activation_authorized",
            "external_effects",
        ],
        {
            "schema_id": {"const": "asklegal.hk-regulatory.conformance-attestation"},
            "schema_version": {"const": HKEX_CONFORMANCE_ATTESTATION_CONTRACT_VERSION},
            "attestation_id": {"type": "string", "pattern": "^rba_[0-9a-f]{48}$"},
            "attestation_kind": {"const": HKEX_CONFORMANCE_ATTESTATION_KIND},
            "jurisdiction": {"const": "HK"},
            "material_family": {"const": "REGULATORY_MATERIALS"},
            "rule_id": {"const": HKEX_CONFORMANCE_ATTESTATION_RULE_ID},
            "evidence": evidence,
            "final_result": {"const": "PASS"},
            "capability_claims": {"const": ["BUILD_COMPATIBILITY"]},
            "real_source_evaluation": {"const": False},
            "source_access_authorized": {"const": False},
            "release_creation_authorized": {"const": False},
            "approval_authorized": {"const": False},
            "pinecone_authorized": {"const": False},
            "deployment_authorized": {"const": False},
            "activation_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        },
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://ask.legal/schemas/hkex-conformance-attestation.schema.json",
        "title": "External HKEX Regulatory Rulebook Conformance Attestation",
        **root,
    }


def build_result_schema() -> dict[str, JsonValue]:
    """Return the closed successful compatibility-result schema."""
    root = _closed(
        [
            "schema_id",
            "schema_version",
            "rule_id",
            "attestation_id",
            "outcome",
            "reason",
            "build_compatibility_valid",
            "source_access_authorized",
            "release_creation_authorized",
            "approval_authorized",
            "pinecone_authorized",
            "deployment_authorized",
            "activation_authorized",
            "external_effects",
        ],
        {
            "schema_id": {"const": "asklegal.hk-regulatory.conformance-attestation-result"},
            "schema_version": {"const": HKEX_CONFORMANCE_ATTESTATION_CONTRACT_VERSION},
            "rule_id": {"const": HKEX_CONFORMANCE_ATTESTATION_RULE_ID},
            "attestation_id": {"type": "string", "pattern": "^rba_[0-9a-f]{48}$"},
            "outcome": {"const": "VALID"},
            "reason": {"const": "COMPLETE_SOURCE_NEUTRAL_BUILD_COMPATIBILITY"},
            "build_compatibility_valid": {"const": True},
            "source_access_authorized": {"const": False},
            "release_creation_authorized": {"const": False},
            "approval_authorized": {"const": False},
            "pinecone_authorized": {"const": False},
            "deployment_authorized": {"const": False},
            "activation_authorized": {"const": False},
            "external_effects": {"const": "NONE"},
        },
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://ask.legal/schemas/hkex-conformance-attestation-result.schema.json",
        "title": "HKEX Regulatory conformance compatibility result",
        **root,
    }


def build_rule_document() -> dict[str, JsonValue]:
    """Declare the exact non-authorizing consequence of a valid attestation."""
    return {
        "schema_id": "asklegal.hk-regulatory.conformance-attestation-rule",
        "schema_version": HKEX_CONFORMANCE_ATTESTATION_CONTRACT_VERSION,
        "rule_id": HKEX_CONFORMANCE_ATTESTATION_RULE_ID,
        "attestation_path": ("attestations/HKREG-CONFORMANCE-ATTESTATION-001.json"),
        "required_case_count": HKEX_CONFORMANCE_CASE_RESULT_COUNT,
        "required_isolated_run_count": 2,
        "required_terminal_result": "PASS",
        "granted_capabilities": ["BUILD_COMPATIBILITY"],
        "real_source_evaluation": False,
        "source_access_authorized": False,
        "release_creation_authorized": False,
        "approval_authorized": False,
        "pinecone_authorized": False,
        "deployment_authorized": False,
        "activation_authorized": False,
        "external_effects": "NONE",
    }


def _isolated_run(temporary_root: Path, ordinal: int) -> dict[str, JsonValue]:
    output = temporary_root / f"run-{ordinal}"
    summary = temporary_root / f"run-{ordinal}-summary.json"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.run_hk_regulatory_conformance",
            "--output-directory",
            str(output),
            "--summary",
            str(summary),
        ],
        cwd=ROOT,
        check=True,
    )
    document = checked_json_value(json.loads(summary.read_text(encoding="utf-8")))
    return _object(document)


def _require_equal_run_bindings(first: dict[str, JsonValue], second: dict[str, JsonValue]) -> None:
    stable_keys = {
        "rulebook_package",
        "suite",
        "processing_build",
        "dependency_lock",
        "conformance_runner",
        "contract_set",
        "contract_set_fingerprint",
        "case_results",
        "tree_fingerprint",
        "architecture",
        "structural_validation",
        "semantic_validation",
        "architecture_validation",
        "source_access_authorized",
        "external_effects",
    }
    if set(first) != stable_keys | {"schema_id", "schema_version"} or set(second) != set(first):
        raise HKEXAttestationBuildError(_RUN_SUMMARY_CONTRACT)
    if first != second:
        raise HKEXAttestationBuildError(_ISOLATED_RUN_MISMATCH)
    if (
        first["structural_validation"] != "PASS"
        or first["semantic_validation"] != "PASS"
        or first["architecture_validation"] != "PASS"
        or first["source_access_authorized"] is not False
        or first["external_effects"] != "NONE"
    ):
        raise HKEXAttestationBuildError(_RUN_DID_NOT_PASS)


def _closed(required: list[str], properties: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": checked_json_value(required),
        "properties": properties,
    }


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise HKEXAttestationBuildError(_EXPECTED_OBJECT)
    return value


def _write(path: Path, document: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    """Write the complete external conformance-attestation bundle."""
    attestation, result = build_hkex_conformance_attestation()
    _write(ATTESTATION_SCHEMA_PATH, build_attestation_schema())
    _write(RESULT_SCHEMA_PATH, build_result_schema())
    _write(RULE_PATH, build_rule_document())
    _write(ATTESTATION_PATH, attestation)
    _write(EXPECTED_PATH, result)


if __name__ == "__main__":
    main()
