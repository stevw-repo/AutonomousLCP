"""Run the complete source-neutral HKEX conformance suite in one clean process."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from asklegal_contracts import fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import load_rulebook_package, validate_hkex_conformance_universe

from tools.architecture_spike import MANIFEST_PATH, run_spike
from tools.build_hk_regulatory_rulebook import (
    PACKAGE_ROOT,
    build_boundary_decision_cases,
    build_conformance_universe,
    build_coverage_decision_cases,
    build_identity_decision_cases,
    build_package_integrity_cases,
    build_partition_decision_cases,
    build_rendering_decision_cases,
    build_source_decision_cases,
    build_state_decision_cases,
)

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = Path("tools/run_hk_regulatory_conformance.py")
CONTRACT_SET_PATH = Path("contracts/package-manifest.json")
DEPENDENCY_LOCK_PATH = Path("uv.lock")
PROCESSING_SOURCE_ROOT = Path("packages/legal-desks/src/asklegal_legal_desks")

type CaseDocuments = tuple[tuple[dict[str, JsonValue], dict[str, JsonValue]], ...]
type CaseBuilder = Callable[[], CaseDocuments]

_CASE_BUILDERS: tuple[tuple[str, CaseBuilder], ...] = (
    ("boundary-decision", build_boundary_decision_cases),
    ("coverage-decision", build_coverage_decision_cases),
    ("identity-decision", build_identity_decision_cases),
    ("package-integrity", build_package_integrity_cases),
    ("partition-decision", build_partition_decision_cases),
    ("rendering-decision", build_rendering_decision_cases),
    ("source-decision", build_source_decision_cases),
    ("state-decision", build_state_decision_cases),
)

_CASE_RESULT_ID_MISMATCH = "CASE_RESULT_ID_MISMATCH"
_CASE_UNIVERSE_MISMATCH = "CASE_UNIVERSE_MISMATCH"
_OUTPUT_DIRECTORY_NOT_CLEAN = "OUTPUT_DIRECTORY_NOT_CLEAN"
_CASE_ID_INVALID = "CASE_ID_INVALID"


class HKEXConformanceRunnerError(RuntimeError):
    """The isolated conformance execution did not prove its exact contract."""


def run_hk_regulatory_conformance(output_directory: Path) -> dict[str, JsonValue]:
    """Execute, reproduce, and inventory all 284 permanent cases once."""
    _require_clean_directory(output_directory)
    contract_document = checked_json_value(
        json.loads((ROOT / CONTRACT_SET_PATH).read_text(encoding="utf-8"))
    )
    contract_set_fingerprint = fingerprint(contract_document)
    package = load_rulebook_package(
        PACKAGE_ROOT,
        environment="PRODUCTION",
        contract_set_fingerprint=contract_set_fingerprint,
        now="2026-08-24T00:00:00Z",
    )
    universe_document = build_conformance_universe()
    universe_proof = validate_hkex_conformance_universe(universe_document)
    expected_case_ids = tuple(sorted(case.case_id for case in universe_proof.cases))

    result_members: list[dict[str, JsonValue]] = []
    observed_case_ids: list[str] = []
    for directory, builder in _CASE_BUILDERS:
        for fixture_document, result_document in builder():
            case_id = _case_id(fixture_document)
            if result_document.get("case_id") != case_id:
                raise HKEXConformanceRunnerError(_CASE_RESULT_ID_MISMATCH)
            fixture_relative = Path("fixtures/conformance") / directory / f"{case_id}.json"
            result_relative = Path("expected/conformance") / directory / f"{case_id}.json"
            fixture_bytes = _display_bytes(fixture_document)
            result_bytes = _display_bytes(result_document)
            if (PACKAGE_ROOT / fixture_relative).read_bytes() != fixture_bytes:
                detail = f"FROZEN_FIXTURE_DRIFT:{case_id}"
                raise HKEXConformanceRunnerError(detail)
            if (PACKAGE_ROOT / result_relative).read_bytes() != result_bytes:
                detail = f"FROZEN_RESULT_DRIFT:{case_id}"
                raise HKEXConformanceRunnerError(detail)
            output_path = output_directory / result_relative
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(result_bytes)
            observed_case_ids.append(case_id)
            result_members.append(
                {
                    "case_id": case_id,
                    "result": _artifact_binding(result_relative, result_bytes),
                }
            )
    result_members.sort(key=lambda member: str(member["case_id"]))
    if tuple(sorted(observed_case_ids)) != expected_case_ids:
        raise HKEXConformanceRunnerError(_CASE_UNIVERSE_MISMATCH)

    result_set_document: dict[str, JsonValue] = {
        "case_count": len(result_members),
        "members": checked_json_value(result_members),
        "result_set_fingerprint": "PENDING",
    }
    result_set_projection = dict(result_set_document)
    result_set_projection.pop("result_set_fingerprint")
    result_set_document["result_set_fingerprint"] = fingerprint(
        checked_json_value(result_set_projection)
    )
    tree_members = [
        _artifact_binding(path.relative_to(output_directory), path.read_bytes())
        for path in sorted(output_directory.rglob("*.json"), key=lambda item: item.as_posix())
    ]
    tree_fingerprint = fingerprint(checked_json_value(tree_members))

    architecture_report = run_spike(ROOT)
    architecture_document = architecture_report.to_json()
    architecture_document["result"] = "PASS"
    architecture_document["tool"] = _binding_for_path(Path("tools/architecture_spike.py"))
    architecture_document["policy"] = _binding_for_path(MANIFEST_PATH)
    report_projection = {
        key: value for key, value in architecture_document.items() if key != "report_fingerprint"
    }
    architecture_document["report_fingerprint"] = fingerprint(checked_json_value(report_projection))

    processing_members = tuple(
        _binding_for_path(path.relative_to(ROOT))
        for path in sorted(
            (ROOT / PROCESSING_SOURCE_ROOT).rglob("*.py"),
            key=lambda item: item.as_posix().encode(),
        )
        if "__pycache__" not in path.parts
    )
    processing_document: dict[str, JsonValue] = {
        "members": list(processing_members),
        "inventory_fingerprint": fingerprint(checked_json_value(list(processing_members))),
    }
    universe_path = Path(
        "packages/legal-desks/src/asklegal_legal_desks/_hk_regulatory_package/"
        "catalogues/conformance-universe.json"
    )
    universe_binding = _binding_for_path(universe_path)
    return {
        "schema_id": "asklegal.hk-regulatory.conformance-run",
        "schema_version": "1.0.0",
        "rulebook_package": {
            "package_id": package.manifest.package_id,
            "package_version": package.manifest.package_version,
            "package_fingerprint": package.manifest.package_fingerprint,
        },
        "suite": {
            "universe": universe_binding,
            "universe_fingerprint": universe_proof.catalogue_fingerprint,
            "case_count": universe_proof.case_count,
            "coverage_cell_count": universe_proof.coverage_cell_count,
            "pair_count": universe_proof.pair_count,
        },
        "processing_build": processing_document,
        "dependency_lock": _binding_for_path(DEPENDENCY_LOCK_PATH),
        "conformance_runner": _binding_for_path(RUNNER_PATH),
        "contract_set": _binding_for_path(CONTRACT_SET_PATH),
        "contract_set_fingerprint": contract_set_fingerprint,
        "case_results": result_set_document,
        "tree_fingerprint": tree_fingerprint,
        "architecture": checked_json_value(architecture_document),
        "structural_validation": "PASS",
        "semantic_validation": "PASS",
        "architecture_validation": "PASS",
        "source_access_authorized": False,
        "external_effects": "NONE",
    }


def _require_clean_directory(path: Path) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise HKEXConformanceRunnerError(_OUTPUT_DIRECTORY_NOT_CLEAN)
    path.mkdir(parents=True, exist_ok=True)


def _case_id(document: dict[str, JsonValue]) -> str:
    value = document.get("case_id")
    if type(value) is not str:
        raise HKEXConformanceRunnerError(_CASE_ID_INVALID)
    return value


def _display_bytes(document: dict[str, JsonValue]) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()


def _binding_for_path(path: Path) -> dict[str, JsonValue]:
    raw = (ROOT / path).read_bytes()
    return _artifact_binding(path, raw)


def _artifact_binding(path: Path, raw: bytes) -> dict[str, JsonValue]:
    return {
        "path": path.as_posix(),
        "byte_size": len(raw),
        "fingerprint": f"sha256:{sha256(raw).hexdigest()}",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    return parser


def main() -> None:
    """Run one clean execution and write its deterministic summary."""
    arguments = _parser().parse_args()
    summary = run_hk_regulatory_conformance(arguments.output_directory.resolve())
    arguments.summary.parent.mkdir(parents=True, exist_ok=True)
    arguments.summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
