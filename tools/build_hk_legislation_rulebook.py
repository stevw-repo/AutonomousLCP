"""Mechanically rebuild the frozen Hong Kong Legislation partial package."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, cast

import rfc8785

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package"

ROLES = {
    "attestations": "ATTESTATION",
    "catalogues": "CATALOGUE",
    "contracts": "CONTRACT",
    "evaluations": "EVALUATION",
    "expected": "EXPECTED_ARTIFACT",
    "profiles": "PROFILE",
    "renderers": "RENDERER",
    "rules": "RULES",
    "scopes": "SCOPE_REGISTRY",
    "sources": "SOURCE_UNIVERSE",
}

SCOPE_READINESS = (
    ("rsc_fa928755a873dbf8df5f4f2d333b672cd1d935af9bf99b95", "NOT_READY"),
    ("rsc_1cdf5a558e8286dadf84f819de1d48168d455cd457fcf30e", "NOT_READY"),
    ("rsc_4708261daa351aa91a1511674b94bced0a9c2eaa817770ea", "NOT_READY"),
)

FIXTURE_GROUPS = (
    (
        tuple(f"HKLEG-BASE-CHANGE-FIX-{index:03d}" for index in range(1, 8)),
        "asklegal.hk-legislation.baseline-change.fixtures",
        "catalogues/baseline-change-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-DISP-FIX-{index:03d}" for index in range(1, 8)),
        "asklegal.hk-legislation.baseline-disposition.fixtures",
        "catalogues/baseline-disposition-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-EVID-FIX-{index:03d}" for index in range(1, 6)),
        "asklegal.hk-legislation.baseline-evidence.fixtures",
        "catalogues/baseline-evidence-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-ID-FIX-{index:03d}" for index in range(1, 6)),
        "asklegal.hk-legislation.baseline-identity.fixtures",
        "catalogues/baseline-identity-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-HIST-FIX-{index:03d}" for index in range(1, 7)),
        "asklegal.hk-legislation.baseline-history.fixtures",
        "catalogues/baseline-history-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-INV-FIX-{index:03d}" for index in range(1, 5)),
        "asklegal.hk-legislation.baseline-inventory.fixtures",
        "catalogues/baseline-inventory-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-LIMIT-FIX-{index:03d}" for index in range(1, 6)),
        "asklegal.hk-legislation.baseline-limit.fixtures",
        "catalogues/baseline-limit-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-OBS-FIX-{index:03d}" for index in range(1, 6)),
        "asklegal.hk-legislation.baseline-observation.fixtures",
        "catalogues/baseline-observation-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-REC-FIX-{index:03d}" for index in range(1, 7)),
        "asklegal.hk-legislation.baseline-record.fixtures",
        "catalogues/baseline-record-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-REL-FIX-{index:03d}" for index in range(1, 8)),
        "asklegal.hk-legislation.baseline-release-accounting.fixtures",
        "catalogues/baseline-release-accounting-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-REVIEW-FIX-{index:03d}" for index in range(1, 6)),
        "asklegal.hk-legislation.baseline-review.fixtures",
        "catalogues/baseline-review-fixtures.json",
    ),
    (
        tuple(f"HKLEG-BASE-STATE-FIX-{index:03d}" for index in range(1, 8)),
        "asklegal.hk-legislation.baseline-state.fixtures",
        "catalogues/baseline-state-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-CAUSE-FIX-{index:03d}" for index in range(1, 7)),
        "asklegal.hk-legislation.current-cause.fixtures",
        "catalogues/current-cause-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-COMMENCE-FIX-{index:03d}" for index in range(1, 13)),
        "asklegal.hk-legislation.current-commencement.fixtures",
        "catalogues/current-commencement-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-CESSATION-FIX-{index:03d}" for index in range(1, 15)),
        "asklegal.hk-legislation.current-cessation.fixtures",
        "catalogues/current-cessation-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-TEXT-EVENT-FIX-{index:03d}" for index in range(1, 17)),
        "asklegal.hk-legislation.current-text-event.fixtures",
        "catalogues/current-text-event-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-DIFF-FIX-{index:03d}" for index in range(1, 8)),
        "asklegal.hk-legislation.current-difference.fixtures",
        "catalogues/current-difference-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-DISP-FIX-{index:03d}" for index in range(1, 8)),
        "asklegal.hk-legislation.current-disposition.fixtures",
        "catalogues/current-disposition-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-EVENT-FIX-{index:03d}" for index in range(1, 9)),
        "asklegal.hk-legislation.current-event.fixtures",
        "catalogues/current-event-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-EVID-FIX-{index:03d}" for index in range(1, 10)),
        "asklegal.hk-legislation.current-evidence.fixtures",
        "catalogues/current-evidence-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-OBS-FIX-{index:03d}" for index in range(1, 7)),
        "asklegal.hk-legislation.current-observation.fixtures",
        "catalogues/current-observation-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-PUB-FIX-{index:03d}" for index in range(1, 14)),
        "asklegal.hk-legislation.current-publication.fixtures",
        "catalogues/current-publication-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-REC-FIX-{index:03d}" for index in range(1, 9)),
        "asklegal.hk-legislation.current-record.fixtures",
        "catalogues/current-record-fixtures.json",
    ),
    (
        tuple(f"HKLEG-CURRENT-REL-FIX-{index:03d}" for index in range(1, 8)),
        "asklegal.hk-legislation.current-release-accounting.fixtures",
        "catalogues/current-release-accounting-fixtures.json",
    ),
    (
        tuple(f"HKLEG-RECON-PLAN-SEM-FIX-{index:03d}" for index in range(1, 14)),
        "asklegal.hk-legislation.reconstruction-plan-semantic.fixtures",
        "catalogues/reconstruction-plan-semantic-fixtures.json",
    ),
    (
        tuple(f"HKLEG-RECON-PLAN-VAL-FIX-{index:03d}" for index in range(1, 22)),
        "asklegal.hk-legislation.reconstruction-plan-validation.fixtures",
        "catalogues/reconstruction-plan-validation-fixtures.json",
    ),
    (
        tuple(f"HKLEG-RECON-EXEC-FIX-{index:03d}" for index in range(1, 14)),
        "asklegal.hk-legislation.reconstruction-execution.fixtures",
        "catalogues/reconstruction-execution-fixtures.json",
    ),
    (
        tuple(f"HKLEG-RECON-REPORT-FIX-{index:03d}" for index in range(1, 3)),
        "asklegal.hk-legislation.reconstruction-report.fixtures",
        "catalogues/reconstruction-report-fixtures.json",
    ),
    (
        tuple(f"HKLEG-KNOWN-STALE-FIX-{index:03d}" for index in range(1, 13)),
        "asklegal.hk-legislation.known-stale-fallback.fixtures",
        "catalogues/known-stale-fallback-fixtures.json",
    ),
    (
        tuple(f"HKLEG-RECON-RCN-FIX-{index:03d}" for index in range(1, 13)),
        "asklegal.hk-legislation.reconstruction-reconciliation.fixtures",
        "catalogues/reconstruction-reconciliation-fixtures.json",
    ),
    (
        tuple(f"HKLEG-RECON-ORP-FIX-{index:03d}" for index in range(1, 23)),
        "asklegal.hk-legislation.reconstruction-overlong-partition.fixtures",
        "catalogues/reconstruction-overlong-partition-fixtures.json",
    ),
)


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _role(path: str) -> str:
    if path.startswith("fixtures/deterministic/"):
        return "DETERMINISTIC_FIXTURE"
    if path.startswith("fixtures/semantic/"):
        return "SEMANTIC_FIXTURE"
    return ROLES[path.split("/", maxsplit=1)[0]]


def _write_json(path: Path, document: JsonValue) -> None:
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _refresh_fixture_locks() -> None:
    for fixture_ids, catalogue_id, catalogue_path in FIXTURE_GROUPS:
        entries: list[JsonValue] = []
        for fixture_id in fixture_ids:
            fixture_path = PACKAGE_ROOT / f"fixtures/deterministic/{fixture_id}.json"
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            input_key = "batch_input" if "batch_input" in fixture else "input"
            fixture["input_fingerprint"] = _fingerprint(
                rfc8785.dumps(cast("JsonValue", fixture[input_key]))
            )
            expected_path_text = fixture["expected_artifact"]["path"]
            expected_path = PACKAGE_ROOT / expected_path_text
            if fixture_id.startswith("HKLEG-RECON-PLAN-VAL-FIX-"):
                expected = json.loads(expected_path.read_text(encoding="utf-8"))
                candidate_plan = fixture["input"]["candidate_plan"]
                candidate_fingerprint = (
                    _fingerprint(rfc8785.dumps(cast("JsonValue", candidate_plan)))
                    if isinstance(candidate_plan, dict)
                    else None
                )
                expected["candidate_plan_fingerprint"] = candidate_fingerprint
                if expected["plan_validation_result"] == "VALIDATED":
                    expected["validated_reconstruction_plan_fingerprint"] = candidate_fingerprint
                _write_json(expected_path, cast("JsonValue", expected))
            expected_fingerprint = _fingerprint(expected_path.read_bytes())
            fixture["expected_artifact"]["fingerprint"] = expected_fingerprint
            _write_json(fixture_path, cast("JsonValue", fixture))
            entries.append(
                {
                    "fixture_id": fixture_id,
                    "path": fixture_path.relative_to(PACKAGE_ROOT).as_posix(),
                    "fixture_fingerprint": _fingerprint(fixture_path.read_bytes()),
                    "expected_path": expected_path_text,
                    "expected_fingerprint": expected_fingerprint,
                }
            )
        catalogue: JsonValue = {
            "catalogue_id": catalogue_id,
            "version": "1.0.0",
            "status": "FROZEN_PARTIAL",
            "accepted_complete_universe": False,
            "fixtures": entries,
        }
        _write_json(PACKAGE_ROOT / catalogue_path, catalogue)


def _refresh_readiness_contract() -> None:
    """Bind readiness reporting to every frozen offline rule and fixture."""
    rule_ids: list[str] = []
    for path in sorted((PACKAGE_ROOT / "rules").glob("HKLEG-*.json")):
        document = cast("dict[str, JsonValue]", json.loads(path.read_text(encoding="utf-8")))
        rule_id = document.get("rule_id")
        if not isinstance(rule_id, str):
            message = "rule_id"
            raise TypeError(message)
        rule_ids.append(rule_id)
    fixture_ids = sorted(fixture_id for group, _, _ in FIXTURE_GROUPS for fixture_id in group)
    readiness = cast(
        "JsonValue",
        {
            "contract_id": "asklegal.hk-legislation-readiness-package",
            "contract_version": "1.0.0",
            "lifecycle_state": "NOT_READY",
            "execution_authority": "NONE",
            "offline_conformance_rule_ids": rule_ids,
            "offline_fixture_ids": fixture_ids,
            "accepted_complete_conformance_universe": False,
            "activation_forbidden": True,
            "external_source_access": "NOT_PERFORMED",
            "real_source_bytes_included": False,
        },
    )
    _write_json(PACKAGE_ROOT / "contracts/readiness-contract.json", readiness)


def build_manifest() -> dict[str, JsonValue]:
    """Build the deterministic manifest for a non-activatable partial package."""
    _refresh_fixture_locks()
    _refresh_readiness_contract()
    files: list[JsonValue] = []
    for path in sorted(PACKAGE_ROOT.rglob("*"), key=lambda item: item.as_posix().encode()):
        if not path.is_file() or path.name == "package.json":
            continue
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        raw = path.read_bytes()
        files.append(
            {
                "byte_size": len(raw),
                "fingerprint": _fingerprint(raw),
                "path": relative,
                "role": _role(relative),
            }
        )
    contract_manifest = json.loads((ROOT / "contracts/package-manifest.json").read_text())
    contract_fingerprint = _fingerprint(rfc8785.dumps(contract_manifest))
    document: dict[str, JsonValue] = {
        "schema_id": "asklegal.executable-source-rulebook-package",
        "schema_version": "1.0.0",
        "package_id": "rbp_866fd2858e653370aec45ffa71b551942fbc33e1b8c440ca",
        "package_version": "0.41.0",
        "package_fingerprint": "PENDING",
        "jurisdiction": "HK",
        "environment": "PRODUCTION",
        "material_family": "LEGISLATION",
        "legal_desk_owner": "UNASSIGNED_HONG_KONG_LEGISLATION_LEGAL_DESK",
        "effective_cutoff": "2026-08-17T00:00:00Z",
        "predecessor": None,
        "contract_locks": [contract_fingerprint],
        "code_locks": ["asklegal-legal-desks==0.1.0", "asklegal-processing==0.1.0"],
        "source_universe_fingerprint": _fingerprint(
            (PACKAGE_ROOT / "sources/source-universe.json").read_bytes()
        ),
        "scope_readiness": [
            {"scope_id": scope_id, "state": state} for scope_id, state in SCOPE_READINESS
        ],
        "unresolved_policy_codes": ["HKLEG_INSTRUMENTS_AND_OTHERS_REVIEW_REQUIRED"],
        "impact_declaration": (
            "FROZEN_PARTIAL_BASELINE_OBSERVATION_INVENTORY_EVIDENCE_STATE_LIMIT_IDENTITY_"
            "DISPOSITION_RECORD_RELEASE_ACCOUNTING_TARGETED_REVIEW_AND_HISTORY_"
            "POST_CUTOFF_CHANGE_"
            "ORDINARY_CURRENT_OBSERVATION_"
            "ORDINARY_CURRENT_RECORD_"
            "ORDINARY_CURRENT_RELEASE_ACCOUNTING_"
            "ORDINARY_CURRENT_EVIDENCE_"
            "ORDINARY_CURRENT_DIFFERENCE_"
            "ORDINARY_CURRENT_DISPOSITION_"
            "ORDINARY_CURRENT_CAUSE_"
            "ORDINARY_CURRENT_COMMENCEMENT_"
            "ORDINARY_CURRENT_CESSATION_AND_REVIVAL_"
            "ORDINARY_CURRENT_PUBLICATION_AND_ENACTMENT_"
            "ORDINARY_CURRENT_TEXT_CHANGING_EVENT_"
            "ORDINARY_CURRENT_EVENT_"
            "RECONSTRUCTION_PLAN_SEMANTIC_DECISION_AND_CHALLENGE_"
            "DETERMINISTIC_RECONSTRUCTION_PLAN_VALIDATION_"
            "CANONICAL_SOURCE_TREE_AND_ORDINARY_BILINGUAL_RENDERER_"
            "DETERMINISTIC_CANONICAL_RECONSTRUCTION_EXECUTION_"
            "IMMUTABLE_RECONSTRUCTION_ARTIFACT_AND_EXECUTION_REPORT_"
            "DETERMINISTIC_KNOWN_STALE_FALLBACK_SELECTION_"
            "DETERMINISTIC_LATER_HKEL_RECONCILIATION_"
            "SOURCE_NEUTRAL_RECURSIVE_BILINGUAL_SERVING_PARTITION_"
            "CONFORMANCE_ONLY_"
            "NO_PROCESSING_ACTIVATION_OR_PRODUCTION_AUTHORITY"
        ),
        "minimum_engine_version": "1.0.0",
        "files": files,
    }
    projection = dict(document)
    projection.pop("package_fingerprint")
    document["package_fingerprint"] = _fingerprint(rfc8785.dumps(cast("JsonValue", projection)))
    return document


def main() -> None:
    """Write stable display bytes; the manifest fingerprint uses canonical JSON."""
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    (PACKAGE_ROOT / "package.json").write_text(
        json.dumps(build_manifest(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
