"""M5 executable Source Rulebook Package conformance."""

from __future__ import annotations

import shutil
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from asklegal_contracts import SchemaRegistry, canonicalize, fingerprint, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_legal_desks import (
    HK_ORDINANCES_SCOPE_ID,
    HKEX_REGULATORY_SOURCE_IDS,
    ActivationRecord,
    LoadedRulebook,
    PartitionReleaseConsequenceResult,
    ProcessingSubject,
    ReadinessState,
    RulebookError,
    RulebookErrorCode,
    RulebookLifecycle,
    RuleEngine,
    load_rulebook_package,
    prove_hk_baseline_change,
    prove_hk_baseline_disposition,
    prove_hk_baseline_evidence,
    prove_hk_baseline_history,
    prove_hk_baseline_identity,
    prove_hk_baseline_inventory,
    prove_hk_baseline_limit,
    prove_hk_baseline_observation,
    prove_hk_baseline_ordered_path,
    prove_hk_baseline_record,
    prove_hk_baseline_release_accounting,
    prove_hk_baseline_review,
    prove_hk_baseline_state,
    prove_hk_current_cause,
    prove_hk_current_cessation,
    prove_hk_current_commencement,
    prove_hk_current_difference,
    prove_hk_current_disposition,
    prove_hk_current_event,
    prove_hk_current_evidence,
    prove_hk_current_observation,
    prove_hk_current_publication,
    prove_hk_current_record,
    prove_hk_current_release_accounting,
    prove_hk_current_text_event,
    prove_hk_known_stale_fallback,
    prove_hk_legislation_partition,
    prove_hk_reconstruction_execution,
    prove_hk_reconstruction_plan_semantic,
    prove_hk_reconstruction_plan_validation,
    prove_hk_reconstruction_reconciliation,
    prove_hk_reconstruction_report,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPOSITORY_ROOT / "packages/legal-desks/src/asklegal_legal_desks/_synthetic_package"
HK_PACKAGE_ROOT = (
    REPOSITORY_ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package"
)
HK_CASE_PACKAGE_ROOT = (
    REPOSITORY_ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_cases_package"
)
HK_REGULATORY_PACKAGE_ROOT = (
    REPOSITORY_ROOT / "packages/legal-desks/src/asklegal_legal_desks/_hk_regulatory_package"
)
CONTRACT_MANIFEST = REPOSITORY_ROOT / "contracts/package-manifest.json"
CONTRACTS_ROOT = REPOSITORY_ROOT / "contracts"
SCOPE_ID = f"rsc_{'3' * 48}"


def _contract_fingerprint() -> str:
    raw = CONTRACT_MANIFEST.read_bytes()
    return fingerprint(parse_json_bytes(raw, max_bytes=len(raw)))


def _load(
    root: Path = PACKAGE_ROOT,
    *,
    environment: str = "LOCAL_SYNTHETIC",
) -> LoadedRulebook:
    return load_rulebook_package(
        root,
        environment=environment,
        contract_set_fingerprint=_contract_fingerprint(),
        now="2026-08-16T00:00:00Z",
    )


def _load_hk(root: Path = HK_PACKAGE_ROOT) -> LoadedRulebook:
    return load_rulebook_package(
        root,
        environment="PRODUCTION",
        contract_set_fingerprint=_contract_fingerprint(),
        now="2026-08-17T00:00:00Z",
    )


def _load_cases(root: Path = HK_CASE_PACKAGE_ROOT) -> LoadedRulebook:
    return load_rulebook_package(
        root,
        environment="PRODUCTION",
        contract_set_fingerprint=_contract_fingerprint(),
        now="2026-08-24T00:00:00Z",
    )


def _load_hk_regulatory(root: Path = HK_REGULATORY_PACKAGE_ROOT) -> LoadedRulebook:
    return load_rulebook_package(
        root,
        environment="PRODUCTION",
        contract_set_fingerprint=_contract_fingerprint(),
        now="2026-08-24T00:00:00Z",
    )


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _json(path: Path) -> dict[str, JsonValue]:
    raw = path.read_bytes()
    return _object(parse_json_bytes(raw, max_bytes=len(raw)))


def _write(path: Path, value: JsonValue) -> None:
    path.write_bytes(canonicalize(value) + b"\n")


def _rehash(root: Path) -> None:
    manifest = _json(root / "package.json")
    entries = _array(manifest["files"])
    for raw_entry in entries:
        entry = _object(raw_entry)
        raw = (root / _text(entry["path"])).read_bytes()
        entry["byte_size"] = len(raw)
        entry["fingerprint"] = f"sha256:{sha256(raw).hexdigest()}"
    source_raw = (root / "sources/source-universe.json").read_bytes()
    manifest["source_universe_fingerprint"] = f"sha256:{sha256(source_raw).hexdigest()}"
    projection = dict(manifest)
    projection.pop("package_fingerprint")
    canonical_projection = canonicalize(checked_json_value(projection))
    manifest["package_fingerprint"] = f"sha256:{sha256(canonical_projection).hexdigest()}"
    _write(root / "package.json", manifest)


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(PACKAGE_ROOT, target)
    return target


def _copy_hk(tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(HK_PACKAGE_ROOT, target)
    return target


def _activation(package: LoadedRulebook) -> ActivationRecord:
    return ActivationRecord(
        f"wae_{'8' * 48}",
        package.manifest.package_id,
        package.manifest.package_fingerprint,
        "legal-processing-build-1",
        _contract_fingerprint(),
        "sha256:" + "9" * 64,
        tuple(profile.profile_id for profile in package.semantic_profiles),
        package.attestation_ids[0],
        (SCOPE_ID,),
        "LOCAL_SYNTHETIC",
        "2026-08-16T00:00:00Z",
    )


def _subject(*facts: tuple[str, str]) -> ProcessingSubject:
    return ProcessingSubject(
        f"wki_{'a' * 48}",
        SCOPE_ID,
        f"obs_{'b' * 48}",
        f"snp_{'c' * 48}",
        (f"art_{'d' * 48}",),
        ("SOURCE_CONTENT",),
        "NONE",
        facts,
        "sha256:" + "e" * 64,
    )


def test_reserved_package_loads_with_complete_exact_inventory() -> None:
    package = _load()
    assert package.manifest.jurisdiction == "ZZZ"
    assert package.manifest.material_family == "TEST_LEGAL_MATERIAL"
    assert len(package.sources) == 2
    assert len(package.rules) == 4
    assert tuple(profile.task for profile in package.semantic_profiles) == (
        "GAZETTE_EVENT_ANALYSIS",
        "GAZETTE_EVENT_CHALLENGE",
    )
    assert package.fixture_ids == (
        "ZZZ-DET-CREATE-001",
        "ZZZ-DET-UNCERTAIN-001",
        "ZZZ-SEM-GAZETTE-001",
    )


def test_hk_legislation_readiness_package_is_exact_non_executable_and_honest() -> None:
    SchemaRegistry.from_contracts_root(CONTRACTS_ROOT).validate(
        _json(HK_PACKAGE_ROOT / "package.json"),
        "schemas/processing-domain.schema.json#/$defs/executable_rulebook_package",
    )
    package = _load_hk()
    assert package.manifest.jurisdiction == "HK"
    assert package.manifest.material_family == "LEGISLATION"
    assert package.manifest.environment == "PRODUCTION"
    assert len(package.sources) == 14
    assert package.rules == ()
    assert package.semantic_profiles == ()
    assert package.fixture_ids == (
        "HKLEG-BASE-CHANGE-FIX-001",
        "HKLEG-BASE-CHANGE-FIX-002",
        "HKLEG-BASE-CHANGE-FIX-003",
        "HKLEG-BASE-CHANGE-FIX-004",
        "HKLEG-BASE-CHANGE-FIX-005",
        "HKLEG-BASE-CHANGE-FIX-006",
        "HKLEG-BASE-CHANGE-FIX-007",
        "HKLEG-BASE-DISP-FIX-001",
        "HKLEG-BASE-DISP-FIX-002",
        "HKLEG-BASE-DISP-FIX-003",
        "HKLEG-BASE-DISP-FIX-004",
        "HKLEG-BASE-DISP-FIX-005",
        "HKLEG-BASE-DISP-FIX-006",
        "HKLEG-BASE-DISP-FIX-007",
        "HKLEG-BASE-EVID-FIX-001",
        "HKLEG-BASE-EVID-FIX-002",
        "HKLEG-BASE-EVID-FIX-003",
        "HKLEG-BASE-EVID-FIX-004",
        "HKLEG-BASE-EVID-FIX-005",
        "HKLEG-BASE-HIST-FIX-001",
        "HKLEG-BASE-HIST-FIX-002",
        "HKLEG-BASE-HIST-FIX-003",
        "HKLEG-BASE-HIST-FIX-004",
        "HKLEG-BASE-HIST-FIX-005",
        "HKLEG-BASE-HIST-FIX-006",
        "HKLEG-BASE-ID-FIX-001",
        "HKLEG-BASE-ID-FIX-002",
        "HKLEG-BASE-ID-FIX-003",
        "HKLEG-BASE-ID-FIX-004",
        "HKLEG-BASE-ID-FIX-005",
        "HKLEG-BASE-INV-FIX-001",
        "HKLEG-BASE-INV-FIX-002",
        "HKLEG-BASE-INV-FIX-003",
        "HKLEG-BASE-INV-FIX-004",
        "HKLEG-BASE-LIMIT-FIX-001",
        "HKLEG-BASE-LIMIT-FIX-002",
        "HKLEG-BASE-LIMIT-FIX-003",
        "HKLEG-BASE-LIMIT-FIX-004",
        "HKLEG-BASE-LIMIT-FIX-005",
        "HKLEG-BASE-OBS-FIX-001",
        "HKLEG-BASE-OBS-FIX-002",
        "HKLEG-BASE-OBS-FIX-003",
        "HKLEG-BASE-OBS-FIX-004",
        "HKLEG-BASE-OBS-FIX-005",
        "HKLEG-BASE-REC-FIX-001",
        "HKLEG-BASE-REC-FIX-002",
        "HKLEG-BASE-REC-FIX-003",
        "HKLEG-BASE-REC-FIX-004",
        "HKLEG-BASE-REC-FIX-005",
        "HKLEG-BASE-REC-FIX-006",
        "HKLEG-BASE-REL-FIX-001",
        "HKLEG-BASE-REL-FIX-002",
        "HKLEG-BASE-REL-FIX-003",
        "HKLEG-BASE-REL-FIX-004",
        "HKLEG-BASE-REL-FIX-005",
        "HKLEG-BASE-REL-FIX-006",
        "HKLEG-BASE-REL-FIX-007",
        "HKLEG-BASE-REVIEW-FIX-001",
        "HKLEG-BASE-REVIEW-FIX-002",
        "HKLEG-BASE-REVIEW-FIX-003",
        "HKLEG-BASE-REVIEW-FIX-004",
        "HKLEG-BASE-REVIEW-FIX-005",
        "HKLEG-BASE-STATE-FIX-001",
        "HKLEG-BASE-STATE-FIX-002",
        "HKLEG-BASE-STATE-FIX-003",
        "HKLEG-BASE-STATE-FIX-004",
        "HKLEG-BASE-STATE-FIX-005",
        "HKLEG-BASE-STATE-FIX-006",
        "HKLEG-BASE-STATE-FIX-007",
        "HKLEG-CURRENT-CAUSE-FIX-001",
        "HKLEG-CURRENT-CAUSE-FIX-002",
        "HKLEG-CURRENT-CAUSE-FIX-003",
        "HKLEG-CURRENT-CAUSE-FIX-004",
        "HKLEG-CURRENT-CAUSE-FIX-005",
        "HKLEG-CURRENT-CAUSE-FIX-006",
        "HKLEG-CURRENT-CESSATION-FIX-001",
        "HKLEG-CURRENT-CESSATION-FIX-002",
        "HKLEG-CURRENT-CESSATION-FIX-003",
        "HKLEG-CURRENT-CESSATION-FIX-004",
        "HKLEG-CURRENT-CESSATION-FIX-005",
        "HKLEG-CURRENT-CESSATION-FIX-006",
        "HKLEG-CURRENT-CESSATION-FIX-007",
        "HKLEG-CURRENT-CESSATION-FIX-008",
        "HKLEG-CURRENT-CESSATION-FIX-009",
        "HKLEG-CURRENT-CESSATION-FIX-010",
        "HKLEG-CURRENT-CESSATION-FIX-011",
        "HKLEG-CURRENT-CESSATION-FIX-012",
        "HKLEG-CURRENT-CESSATION-FIX-013",
        "HKLEG-CURRENT-CESSATION-FIX-014",
        "HKLEG-CURRENT-COMMENCE-FIX-001",
        "HKLEG-CURRENT-COMMENCE-FIX-002",
        "HKLEG-CURRENT-COMMENCE-FIX-003",
        "HKLEG-CURRENT-COMMENCE-FIX-004",
        "HKLEG-CURRENT-COMMENCE-FIX-005",
        "HKLEG-CURRENT-COMMENCE-FIX-006",
        "HKLEG-CURRENT-COMMENCE-FIX-007",
        "HKLEG-CURRENT-COMMENCE-FIX-008",
        "HKLEG-CURRENT-COMMENCE-FIX-009",
        "HKLEG-CURRENT-COMMENCE-FIX-010",
        "HKLEG-CURRENT-COMMENCE-FIX-011",
        "HKLEG-CURRENT-COMMENCE-FIX-012",
        "HKLEG-CURRENT-DIFF-FIX-001",
        "HKLEG-CURRENT-DIFF-FIX-002",
        "HKLEG-CURRENT-DIFF-FIX-003",
        "HKLEG-CURRENT-DIFF-FIX-004",
        "HKLEG-CURRENT-DIFF-FIX-005",
        "HKLEG-CURRENT-DIFF-FIX-006",
        "HKLEG-CURRENT-DIFF-FIX-007",
        "HKLEG-CURRENT-DISP-FIX-001",
        "HKLEG-CURRENT-DISP-FIX-002",
        "HKLEG-CURRENT-DISP-FIX-003",
        "HKLEG-CURRENT-DISP-FIX-004",
        "HKLEG-CURRENT-DISP-FIX-005",
        "HKLEG-CURRENT-DISP-FIX-006",
        "HKLEG-CURRENT-DISP-FIX-007",
        "HKLEG-CURRENT-EVENT-FIX-001",
        "HKLEG-CURRENT-EVENT-FIX-002",
        "HKLEG-CURRENT-EVENT-FIX-003",
        "HKLEG-CURRENT-EVENT-FIX-004",
        "HKLEG-CURRENT-EVENT-FIX-005",
        "HKLEG-CURRENT-EVENT-FIX-006",
        "HKLEG-CURRENT-EVENT-FIX-007",
        "HKLEG-CURRENT-EVENT-FIX-008",
        "HKLEG-CURRENT-EVID-FIX-001",
        "HKLEG-CURRENT-EVID-FIX-002",
        "HKLEG-CURRENT-EVID-FIX-003",
        "HKLEG-CURRENT-EVID-FIX-004",
        "HKLEG-CURRENT-EVID-FIX-005",
        "HKLEG-CURRENT-EVID-FIX-006",
        "HKLEG-CURRENT-EVID-FIX-007",
        "HKLEG-CURRENT-EVID-FIX-008",
        "HKLEG-CURRENT-EVID-FIX-009",
        "HKLEG-CURRENT-OBS-FIX-001",
        "HKLEG-CURRENT-OBS-FIX-002",
        "HKLEG-CURRENT-OBS-FIX-003",
        "HKLEG-CURRENT-OBS-FIX-004",
        "HKLEG-CURRENT-OBS-FIX-005",
        "HKLEG-CURRENT-OBS-FIX-006",
        "HKLEG-CURRENT-PUB-FIX-001",
        "HKLEG-CURRENT-PUB-FIX-002",
        "HKLEG-CURRENT-PUB-FIX-003",
        "HKLEG-CURRENT-PUB-FIX-004",
        "HKLEG-CURRENT-PUB-FIX-005",
        "HKLEG-CURRENT-PUB-FIX-006",
        "HKLEG-CURRENT-PUB-FIX-007",
        "HKLEG-CURRENT-PUB-FIX-008",
        "HKLEG-CURRENT-PUB-FIX-009",
        "HKLEG-CURRENT-PUB-FIX-010",
        "HKLEG-CURRENT-PUB-FIX-011",
        "HKLEG-CURRENT-PUB-FIX-012",
        "HKLEG-CURRENT-PUB-FIX-013",
        "HKLEG-CURRENT-REC-FIX-001",
        "HKLEG-CURRENT-REC-FIX-002",
        "HKLEG-CURRENT-REC-FIX-003",
        "HKLEG-CURRENT-REC-FIX-004",
        "HKLEG-CURRENT-REC-FIX-005",
        "HKLEG-CURRENT-REC-FIX-006",
        "HKLEG-CURRENT-REC-FIX-007",
        "HKLEG-CURRENT-REC-FIX-008",
        "HKLEG-CURRENT-REL-FIX-001",
        "HKLEG-CURRENT-REL-FIX-002",
        "HKLEG-CURRENT-REL-FIX-003",
        "HKLEG-CURRENT-REL-FIX-004",
        "HKLEG-CURRENT-REL-FIX-005",
        "HKLEG-CURRENT-REL-FIX-006",
        "HKLEG-CURRENT-REL-FIX-007",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-001",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-002",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-003",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-004",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-005",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-006",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-007",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-008",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-009",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-010",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-011",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-012",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-013",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-014",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-015",
        "HKLEG-CURRENT-TEXT-EVENT-FIX-016",
        "HKLEG-KNOWN-STALE-FIX-001",
        "HKLEG-KNOWN-STALE-FIX-002",
        "HKLEG-KNOWN-STALE-FIX-003",
        "HKLEG-KNOWN-STALE-FIX-004",
        "HKLEG-KNOWN-STALE-FIX-005",
        "HKLEG-KNOWN-STALE-FIX-006",
        "HKLEG-KNOWN-STALE-FIX-007",
        "HKLEG-KNOWN-STALE-FIX-008",
        "HKLEG-KNOWN-STALE-FIX-009",
        "HKLEG-KNOWN-STALE-FIX-010",
        "HKLEG-KNOWN-STALE-FIX-011",
        "HKLEG-KNOWN-STALE-FIX-012",
        "HKLEG-RECON-EXEC-FIX-001",
        "HKLEG-RECON-EXEC-FIX-002",
        "HKLEG-RECON-EXEC-FIX-003",
        "HKLEG-RECON-EXEC-FIX-004",
        "HKLEG-RECON-EXEC-FIX-005",
        "HKLEG-RECON-EXEC-FIX-006",
        "HKLEG-RECON-EXEC-FIX-007",
        "HKLEG-RECON-EXEC-FIX-008",
        "HKLEG-RECON-EXEC-FIX-009",
        "HKLEG-RECON-EXEC-FIX-010",
        "HKLEG-RECON-EXEC-FIX-011",
        "HKLEG-RECON-EXEC-FIX-012",
        "HKLEG-RECON-EXEC-FIX-013",
        "HKLEG-RECON-ORP-FIX-001",
        "HKLEG-RECON-ORP-FIX-002",
        "HKLEG-RECON-ORP-FIX-003",
        "HKLEG-RECON-ORP-FIX-004",
        "HKLEG-RECON-ORP-FIX-005",
        "HKLEG-RECON-ORP-FIX-006",
        "HKLEG-RECON-ORP-FIX-007",
        "HKLEG-RECON-ORP-FIX-008",
        "HKLEG-RECON-ORP-FIX-009",
        "HKLEG-RECON-ORP-FIX-010",
        "HKLEG-RECON-ORP-FIX-011",
        "HKLEG-RECON-ORP-FIX-012",
        "HKLEG-RECON-ORP-FIX-013",
        "HKLEG-RECON-ORP-FIX-014",
        "HKLEG-RECON-ORP-FIX-015",
        "HKLEG-RECON-ORP-FIX-016",
        "HKLEG-RECON-ORP-FIX-017",
        "HKLEG-RECON-ORP-FIX-018",
        "HKLEG-RECON-ORP-FIX-019",
        "HKLEG-RECON-ORP-FIX-020",
        "HKLEG-RECON-ORP-FIX-021",
        "HKLEG-RECON-ORP-FIX-022",
        "HKLEG-RECON-PLAN-SEM-FIX-001",
        "HKLEG-RECON-PLAN-SEM-FIX-002",
        "HKLEG-RECON-PLAN-SEM-FIX-003",
        "HKLEG-RECON-PLAN-SEM-FIX-004",
        "HKLEG-RECON-PLAN-SEM-FIX-005",
        "HKLEG-RECON-PLAN-SEM-FIX-006",
        "HKLEG-RECON-PLAN-SEM-FIX-007",
        "HKLEG-RECON-PLAN-SEM-FIX-008",
        "HKLEG-RECON-PLAN-SEM-FIX-009",
        "HKLEG-RECON-PLAN-SEM-FIX-010",
        "HKLEG-RECON-PLAN-SEM-FIX-011",
        "HKLEG-RECON-PLAN-SEM-FIX-012",
        "HKLEG-RECON-PLAN-SEM-FIX-013",
        "HKLEG-RECON-PLAN-VAL-FIX-001",
        "HKLEG-RECON-PLAN-VAL-FIX-002",
        "HKLEG-RECON-PLAN-VAL-FIX-003",
        "HKLEG-RECON-PLAN-VAL-FIX-004",
        "HKLEG-RECON-PLAN-VAL-FIX-005",
        "HKLEG-RECON-PLAN-VAL-FIX-006",
        "HKLEG-RECON-PLAN-VAL-FIX-007",
        "HKLEG-RECON-PLAN-VAL-FIX-008",
        "HKLEG-RECON-PLAN-VAL-FIX-009",
        "HKLEG-RECON-PLAN-VAL-FIX-010",
        "HKLEG-RECON-PLAN-VAL-FIX-011",
        "HKLEG-RECON-PLAN-VAL-FIX-012",
        "HKLEG-RECON-PLAN-VAL-FIX-013",
        "HKLEG-RECON-PLAN-VAL-FIX-014",
        "HKLEG-RECON-PLAN-VAL-FIX-015",
        "HKLEG-RECON-PLAN-VAL-FIX-016",
        "HKLEG-RECON-PLAN-VAL-FIX-017",
        "HKLEG-RECON-PLAN-VAL-FIX-018",
        "HKLEG-RECON-PLAN-VAL-FIX-019",
        "HKLEG-RECON-PLAN-VAL-FIX-020",
        "HKLEG-RECON-PLAN-VAL-FIX-021",
        "HKLEG-RECON-RCN-FIX-001",
        "HKLEG-RECON-RCN-FIX-002",
        "HKLEG-RECON-RCN-FIX-003",
        "HKLEG-RECON-RCN-FIX-004",
        "HKLEG-RECON-RCN-FIX-005",
        "HKLEG-RECON-RCN-FIX-006",
        "HKLEG-RECON-RCN-FIX-007",
        "HKLEG-RECON-RCN-FIX-008",
        "HKLEG-RECON-RCN-FIX-009",
        "HKLEG-RECON-RCN-FIX-010",
        "HKLEG-RECON-RCN-FIX-011",
        "HKLEG-RECON-RCN-FIX-012",
        "HKLEG-RECON-REPORT-FIX-001",
        "HKLEG-RECON-REPORT-FIX-002",
    )
    assert package.evaluation_ids == ()
    assert package.attestation_ids == ()
    assert {scope.readiness for scope in package.scopes} == {ReadinessState.NOT_READY}
    ordinances = next(scope for scope in package.scopes if scope.scope_id == HK_ORDINANCES_SCOPE_ID)
    assert ordinances.ownership_keys == ("HK:LEGISLATION:HK-LEG-ORDINANCES",)
    assert "HKLEG_REAL_SOURCE_BYTES_MISSING" in ordinances.blocker_codes
    assert "HKLEG_NAMED_OWNER_ATTESTATION_MISSING" in ordinances.blocker_codes

    readiness = _json(HK_PACKAGE_ROOT / "contracts/readiness-contract.json")
    declared_rules = tuple(
        _text(value) for value in _array(readiness["offline_conformance_rule_ids"])
    )
    expected_rules = tuple(
        _text(_json(path)["rule_id"])
        for path in sorted((HK_PACKAGE_ROOT / "rules").glob("HKLEG-*.json"))
    )
    assert declared_rules == expected_rules
    assert (
        tuple(_text(value) for value in _array(readiness["offline_fixture_ids"]))
        == package.fixture_ids
    )

    with pytest.raises(RulebookError) as inactive:
        RuleEngine(RulebookLifecycle()).execute(
            package,
            ProcessingSubject(
                f"wki_{'1' * 48}",
                HK_ORDINANCES_SCOPE_ID,
                f"obs_{'2' * 48}",
                f"snp_{'3' * 48}",
                (f"art_{'4' * 48}",),
                ("SOURCE_CONTENT",),
                "NONE",
                (("change_kind", "CREATE"),),
                "sha256:" + "5" * 64,
            ),
        )
    assert inactive.value.code is RulebookErrorCode.PACKAGE_NOT_ACTIVE


def test_not_ready_real_package_may_declare_families_without_inventing_scopes(
    tmp_path: Path,
) -> None:
    root = _copy_hk(tmp_path)
    scope_document = _json(root / "scopes/release-scopes.json")
    scopes = _array(scope_document["scopes"])
    blocker_codes = sorted(
        {
            _text(code)
            for raw_scope in scopes
            for code in _array(_object(raw_scope)["blocker_codes"])
        }
    )
    scope_document["scopes"] = []
    scope_document["scope_families"] = checked_json_value(
        [
            {
                "family_id": "HK-CASE-CFA",
                "ownership_key_pattern": "HK-CASE-CFA-{DECISION_YEAR}",
                "required_source_ids": ["HK-LEG-HKEL-CURRENT-INVENTORY"],
                "concrete_scope_rule": "REQUIRES_EVIDENCED_INCLUSIVE_YEAR_BOUNDARY",
                "blocker_codes": blocker_codes,
            }
        ]
    )
    _write(root / "scopes/release-scopes.json", scope_document)
    manifest = _json(root / "package.json")
    manifest["scope_readiness"] = []
    _write(root / "package.json", manifest)
    _rehash(root)

    package = _load_hk(root)
    assert package.scopes == ()
    assert len(package.scope_families) == 1
    assert package.scope_families[0].family_id == "HK-CASE-CFA"
    assert package.rules == ()

    no_families = _copy_hk(tmp_path / "no-families")
    scope_document = _json(no_families / "scopes/release-scopes.json")
    scope_document["scopes"] = []
    _write(no_families / "scopes/release-scopes.json", scope_document)
    manifest = _json(no_families / "package.json")
    manifest["scope_readiness"] = []
    _write(no_families / "package.json", manifest)
    _rehash(no_families)
    with pytest.raises(RulebookError) as caught:
        _load_hk(no_families)
    assert caught.value.code is RulebookErrorCode.OVERLAPPING_SCOPES


def test_hk_cases_package_is_honestly_frozen_without_activation_authority() -> None:
    package = _load_cases()

    assert package.manifest.package_version == "0.13.0"
    assert package.manifest.jurisdiction == "HK"
    assert package.manifest.material_family == "CASES"
    assert package.manifest.environment == "PRODUCTION"
    assert package.scopes == ()
    assert tuple(family.family_id for family in package.scope_families) == (
        "HK-CASE-CA",
        "HK-CASE-CFA",
        "HK-CASE-CFI",
        "HK-CASE-CT",
        "HK-CASE-HKPC",
        "HK-CASE-HKSUPERIOR",
    )
    assert tuple(source.source_id for source in package.sources) == (
        "HK-CASE-COURT-REGISTRY",
        "HK-CASE-HKLII-DISCOVERY",
        "HK-CASE-JUDICIARY-JUDGMENT",
        "HK-CASE-JUDICIARY-LIBRARY",
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "HK-CASE-JUDICIARY-TRANSLATION",
        "HK-CASE-PRIVY-COUNCIL",
    )
    assert package.rules == ()
    assert package.semantic_profiles == ()
    assert package.fixture_ids == (
        "HKCASE-LIST-FIX-001",
        *(f"HKCASE-PROP-DET-ADM-{ordinal:03d}" for ordinal in range(1, 19)),
        *(f"HKCASE-PROP-DET-LED-{ordinal:03d}" for ordinal in range(1, 21)),
        *(f"HKCASE-PROP-DET-OUT-{ordinal:03d}" for ordinal in range(1, 17)),
        *(f"HKCASE-PROP-SEM-BND-{ordinal:03d}" for ordinal in range(1, 23)),
        *(f"HKCASE-PROP-SEM-CNT-{ordinal:03d}" for ordinal in range(1, 19)),
        *(f"HKCASE-PROP-SEM-MAT-{ordinal:03d}" for ordinal in range(1, 19)),
        *(f"HKCASE-PROP-SEM-RSK-{ordinal:03d}" for ordinal in range(1, 21)),
        *(f"HKCASE-TREAT-SEM-DIS-{ordinal:03d}" for ordinal in range(1, 14)),
        *(f"HKCASE-PROP-TASK-PREFLIGHT-{ordinal:03d}" for ordinal in range(1, 9)),
    )
    assert package.evaluation_ids == ()
    assert package.attestation_ids == ()
    assert package.manifest.scope_readiness == ()
    assert package.manifest.unresolved_policy_codes == (
        "HKCASE_BASELINE_UNBUILT",
        "HKCASE_CONCRETE_SCOPE_BOUNDARIES_UNADMITTED",
        "HKCASE_EVALUATIONS_UNADMITTED",
        "HKCASE_OFFICIAL_CONNECTORS_UNADMITTED",
        "HKCASE_ORIGINATING_FORMATS_UNADMITTED",
        "HKCASE_PROPOSITION_WORKFLOW_UNADMITTED",
        "HKCASE_TREATMENT_WORKFLOW_UNADMITTED",
    )


def test_hk_regulatory_package_freezes_two_scopes_without_serving_authority() -> None:
    package = _load_hk_regulatory()

    assert package.manifest.package_version == "0.14.0"
    assert package.manifest.jurisdiction == "HK"
    assert package.manifest.material_family == "REGULATORY_MATERIALS"
    assert package.manifest.environment == "PRODUCTION"
    assert tuple(source.source_id for source in package.sources) == (HKEX_REGULATORY_SOURCE_IDS)
    assert tuple(scope.ownership_keys for scope in package.scopes) == (
        ("HK:REGULATORY:HK-REG-HKEX-GEM",),
        ("HK:REGULATORY:HK-REG-HKEX-MAIN-BOARD",),
    )
    assert {scope.readiness for scope in package.scopes} == {ReadinessState.NOT_READY}
    assert all(scope.blocker_codes for scope in package.scopes)
    assert package.scope_families == ()
    assert package.rules == ()
    assert package.semantic_profiles == ()
    assert package.fixture_ids == (
        *(f"HKREG-DEC-BND-{ordinal:03d}" for ordinal in range(1, 31)),
        *(f"HKREG-DET-COV-{ordinal:03d}" for ordinal in range(1, 21)),
        *(f"HKREG-DET-IDN-{ordinal:03d}" for ordinal in range(1, 25)),
        *(f"HKREG-DET-PKG-{ordinal:03d}" for ordinal in range(1, 39)),
        *(f"HKREG-DET-PAR-{ordinal:03d}" for ordinal in range(1, 25)),
        *(f"HKREG-DET-RND-{ordinal:03d}" for ordinal in range(1, 36)),
        *(f"HKREG-DEC-SRC-{ordinal:03d}" for ordinal in range(1, 63)),
        *(f"HKREG-DEC-STA-{ordinal:03d}" for ordinal in range(1, 52)),
        "HKREG-CONTINUITY-FIX-001",
        "HKREG-EFFECTIVE-STATE-FIX-001",
        "HKREG-ENGLISH-RECORD-FIX-001",
        "HKREG-INV-FIX-001",
        "HKREG-RECORD-IDENTITY-FIX-001",
    )
    assert package.evaluation_ids == ()
    assert package.attestation_ids == ()
    assert len(package.manifest.unresolved_policy_codes) == 11
    assert "HKREG_EFFECTIVE_STATE_REAL_EVIDENCE_UNADMITTED" in (
        package.manifest.unresolved_policy_codes
    )


def test_hk_baseline_inventory_vertical_slice_is_exact_and_fail_closed() -> None:
    decisions = prove_hk_baseline_inventory(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == (
        "HKLEG-BASE-INV-FIX-001",
        "HKLEG-BASE-INV-FIX-002",
        "HKLEG-BASE-INV-FIX-003",
        "HKLEG-BASE-INV-FIX-004",
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "QUARANTINE",
        "BLOCK",
    )
    assert tuple(decision.coverage_effect for decision in decisions) == (
        "NONE",
        "COVERAGE_GAP",
        "COVERAGE_GAP",
        "COVERAGE_GAP",
    )
    assert decisions[0].accounted_object_ids == ("SYN-HKLEG-OBJ-001",)
    assert all(decision.unresolved_object_ids for decision in decisions[1:])

    package = _load_hk()
    ordinances = next(scope for scope in package.scopes if scope.scope_id == HK_ORDINANCES_SCOPE_ID)
    assert ordinances.readiness is ReadinessState.NOT_READY
    assert "HKLEG_EXECUTABLE_RULESET_INCOMPLETE" in ordinances.blocker_codes
    assert "HKLEG_DETERMINISTIC_FIXTURE_UNIVERSE_INCOMPLETE" in ordinances.blocker_codes


def test_hk_baseline_observation_slice_and_ordered_path_are_exact() -> None:
    decisions = prove_hk_baseline_observation(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == (
        "HKLEG-BASE-OBS-FIX-001",
        "HKLEG-BASE-OBS-FIX-002",
        "HKLEG-BASE-OBS-FIX-003",
        "HKLEG-BASE-OBS-FIX-004",
        "HKLEG-BASE-OBS-FIX-005",
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
    )
    assert tuple(decision.reason_code for decision in decisions) == (
        "HKLEG_BASE_OBSERVATION_FROZEN",
        "HKLEG_BASE_OBSERVATION_REQUIRED_SOURCE_UNAVAILABLE",
        "HKLEG_BASE_OBSERVATION_CUTOFF_MIXED",
        "HKLEG_BASE_OBSERVATION_LOCK_MISMATCH",
        "HKLEG_BASE_OBSERVATION_POST_CUTOFF_CHANGE",
    )
    assert decisions[0].next_action == "RUN_HKLEG_BASE_INV_001"
    assert all(decision.next_action != "RUN_HKLEG_BASE_INV_001" for decision in decisions[1:])
    assert prove_hk_baseline_ordered_path(HK_PACKAGE_ROOT) == (
        "HKLEG-BASE-OBS-001",
        "HKLEG-BASE-INV-001",
        "HKLEG-BASE-EVID-001",
        "HKLEG-BASE-STATE-001",
        "HKLEG-BASE-LIMIT-001",
        "HKLEG-BASE-ID-001",
        "HKLEG-BASE-DISP-001",
        "HKLEG-BASE-REC-001",
        "HKLEG-BASE-REL-001",
    )

    package = _load_hk()
    ordinances = next(scope for scope in package.scopes if scope.scope_id == HK_ORDINANCES_SCOPE_ID)
    assert ordinances.readiness is ReadinessState.NOT_READY


def test_hk_baseline_evidence_slice_is_bilingual_exact_and_fail_closed() -> None:
    decisions = prove_hk_baseline_evidence(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == (
        "HKLEG-BASE-EVID-FIX-001",
        "HKLEG-BASE-EVID-FIX-002",
        "HKLEG-BASE-EVID-FIX-003",
        "HKLEG-BASE-EVID-FIX-004",
        "HKLEG-BASE-EVID-FIX-005",
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "BLOCK",
        "QUARANTINE",
        "BLOCK",
    )
    assert tuple(decision.evidence_mode for decision in decisions) == (
        "VERIFIED",
        "ASSISTED",
        "NONE",
        "NONE",
        "NONE",
    )
    assert all(decision.next_action == "RUN_HKLEG_BASE_STATE_001" for decision in decisions[:2])
    assert all(decision.next_action != "RUN_HKLEG_BASE_STATE_001" for decision in decisions[2:])

    package = _load_hk()
    ordinances = next(scope for scope in package.scopes if scope.scope_id == HK_ORDINANCES_SCOPE_ID)
    assert ordinances.readiness is ReadinessState.NOT_READY


def test_hk_baseline_state_slice_is_exact_limited_and_fail_closed() -> None:
    decisions = prove_hk_baseline_state(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == (
        "HKLEG-BASE-STATE-FIX-001",
        "HKLEG-BASE-STATE-FIX-002",
        "HKLEG-BASE-STATE-FIX-003",
        "HKLEG-BASE-STATE-FIX-004",
        "HKLEG-BASE-STATE-FIX-005",
        "HKLEG-BASE-STATE-FIX-006",
        "HKLEG-BASE-STATE-FIX-007",
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
        "BLOCK",
        "BLOCK",
        "BLOCK",
    )
    assert tuple(decision.source_contract_review_required for decision in decisions) == (
        False,
        False,
        False,
        False,
        True,
        False,
        False,
    )
    assert decisions[0].present_state == "OPERATIVE_CURRENT"
    assert decisions[0].historical_assertion_scope == "PENDING_LIMIT_RULE"
    assert decisions[0].next_action == "RUN_HKLEG_BASE_LIMIT_001"
    assert all(decision.present_state == "UNRESOLVED" for decision in decisions[1:])
    assert all(decision.next_action != "RUN_HKLEG_BASE_LIMIT_001" for decision in decisions[1:])

    package = _load_hk()
    ordinances = next(scope for scope in package.scopes if scope.scope_id == HK_ORDINANCES_SCOPE_ID)
    assert ordinances.readiness is ReadinessState.NOT_READY


def test_hk_baseline_limit_slice_rejects_unsupported_history() -> None:
    decisions = prove_hk_baseline_limit(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == (
        "HKLEG-BASE-LIMIT-FIX-001",
        "HKLEG-BASE-LIMIT-FIX-002",
        "HKLEG-BASE-LIMIT-FIX-003",
        "HKLEG-BASE-LIMIT-FIX-004",
        "HKLEG-BASE-LIMIT-FIX-005",
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
    )
    assert decisions[0].historical_assertion_scope == "PRESENT_STATE_ONLY"
    assert decisions[0].next_action == "RUN_HKLEG_BASE_ID_001"
    assert all(decision.rejected_assertion_codes for decision in decisions[1:])
    assert all(
        decision.next_action == "REMOVE_UNSUPPORTED_HISTORICAL_ASSERTIONS"
        for decision in decisions[1:]
    )

    package = _load_hk()
    ordinances = next(scope for scope in package.scopes if scope.scope_id == HK_ORDINANCES_SCOPE_ID)
    assert ordinances.readiness is ReadinessState.NOT_READY


def test_hk_baseline_identity_slice_uses_only_register_owned_identity() -> None:
    decisions = prove_hk_baseline_identity(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == (
        "HKLEG-BASE-ID-FIX-001",
        "HKLEG-BASE-ID-FIX-002",
        "HKLEG-BASE-ID-FIX-003",
        "HKLEG-BASE-ID-FIX-004",
        "HKLEG-BASE-ID-FIX-005",
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "BLOCK",
        "BLOCK",
        "QUARANTINE",
    )
    assert decisions[0].identity_layers == (
        "LEGAL_ITEM",
        "OFFICIAL_VERSION",
        "LEGAL_LOCATION",
        "SEARCH_RECORD",
    )
    assert decisions[1].identity_layers == decisions[0].identity_layers
    assert {alias[0] for alias in decisions[1].preserved_aliases} == {
        "HKEL_NUMBER",
        "LEGACY_DISTILLATION_ID",
        "LEGACY_PINECONE_ID",
    }
    assert all(not decision.identity_layers for decision in decisions[2:])
    assert decisions[4].next_action == "RUN_HKLEG_BASE_REVIEW_001"

    package = _load_hk()
    ordinances = next(scope for scope in package.scopes if scope.scope_id == HK_ORDINANCES_SCOPE_ID)
    assert ordinances.readiness is ReadinessState.NOT_READY


def test_hk_baseline_disposition_slice_assigns_exactly_one_supported_result() -> None:
    decisions = prove_hk_baseline_disposition(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-BASE-DISP-FIX-{index:03d}" for index in range(1, 8)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "QUARANTINE",
        "BLOCK",
        "BLOCK",
    )
    assert tuple(decision.legal_disposition for decision in decisions[:5]) == (
        "SEARCHABLE_CURRENT",
        "WAITING_ROOM",
        "EVIDENCE_ONLY",
        "HISTORICAL",
        "QUARANTINE",
    )
    assert decisions[5].coverage_effect == "COVERAGE_GAP"
    assert decisions[5].next_action == "APPLY_HKLEG_CURRENT_EVENT_001"
    assert decisions[6].legal_disposition == "NOT_APPLICABLE"
    assert decisions[0].next_action == "RUN_HKLEG_BASE_REC_001"

    package = _load_hk()
    ordinances = next(scope for scope in package.scopes if scope.scope_id == HK_ORDINANCES_SCOPE_ID)
    assert ordinances.readiness is ReadinessState.NOT_READY


def test_hk_baseline_record_slice_builds_exact_bilingual_six_field_candidate() -> None:
    decisions = prove_hk_baseline_record(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-BASE-REC-FIX-{index:03d}" for index in range(1, 7)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "BLOCK",
        "BLOCK",
        "QUARANTINE",
        "BLOCK",
    )
    candidate = decisions[0].candidate_record
    assert candidate is not None
    SchemaRegistry.from_contracts_root(CONTRACTS_ROOT).validate(
        candidate,
        "schemas/serving-domain.schema.json#/$defs/serving_record",
    )
    metadata = _object(candidate["metadata"])
    assert tuple(sorted(metadata, key=str.encode)) == (
        "authority_note",
        "country",
        "jurisdiction",
        "source",
        "text",
        "type",
    )
    assert _text(metadata["text"]).startswith("[English — Authentic Text]\n")
    assert "\n\n[繁體中文 — 真確文本]\n" in _text(metadata["text"])
    assert metadata["authority_note"] == "None"
    assert decisions[0].serving_payload_fingerprint == (
        "sha256:1008160068a049c1ecc427d443c33d282b311fd055d61227adce248339674a04"
    )
    assert decisions[1].legal_disposition == "WAITING_ROOM"
    assert decisions[1].candidate_record is None
    assert all(decision.candidate_record is None for decision in decisions[1:])


def test_hk_baseline_release_accounting_is_complete_and_initial() -> None:
    decisions = prove_hk_baseline_release_accounting(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-BASE-REL-FIX-{index:03d}" for index in range(1, 8)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
    )
    assert decisions[0].accounted_object_ids == (
        "SYN-HKLEG-OBJ-001",
        "SYN-HKLEG-OBJ-002",
        "SYN-HKLEG-OBJ-003",
    )
    assert decisions[0].accounted_location_ids == (
        "SYN-HKLEG-LOC-001",
        "SYN-HKLEG-LOC-002",
        "SYN-HKLEG-LOC-003",
    )
    assert decisions[0].release_accounting_fingerprint == (
        "sha256:13a425c68884c1d61f9f701527ec8b62971e70c1a943dc61b09e2f3844bdf6e9"
    )
    assert decisions[0].next_action == "BUILD_CANDIDATE_CORPUS_RELEASE"
    assert all(decision.unresolved_ids for decision in decisions[1:])
    assert all(decision.release_accounting_fingerprint is None for decision in decisions[1:])


def test_hk_baseline_review_opens_only_one_bounded_material_question() -> None:
    decisions = prove_hk_baseline_review(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-BASE-REVIEW-FIX-{index:03d}" for index in range(1, 6)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
    )
    task = decisions[0].review_task
    assert task is not None
    assert task["permitted_fact_codes"] == ["IDENTITY_OR_CONTINUITY"]
    assert task["requested_source_ids"] == [
        "HK-LEG-HKEL-PAST-INVENTORY",
        "HK-LEG-HKEL-PAST-DATA",
    ]
    assert task["responsible_legal_desk"] == "HONG_KONG_LEGISLATION_LEGAL_DESK"
    assert decisions[0].next_action == "RUN_HKLEG_BASE_HIST_001"
    assert all(decision.review_task is None for decision in decisions[1:])


def test_hk_baseline_history_establishes_only_the_review_permitted_fact() -> None:
    decisions = prove_hk_baseline_history(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-BASE-HIST-FIX-{index:03d}" for index in range(1, 7)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "QUARANTINE",
        "BLOCK",
    )
    assert decisions[0].established_fact_code == "PRESENT_OPERATIVE_STATUS"
    assert decisions[0].next_action == "RESUME_BASELINE_DECISION"
    assert all(decision.established_fact_code is None for decision in decisions[1:])
    assert decisions[3].coverage_effect == "COVERAGE_GAP"
    assert decisions[3].unaffected_work_may_continue is False
    assert all(decision.unaffected_work_may_continue for decision in decisions[:3])
    assert all(decision.unaffected_work_may_continue for decision in decisions[4:])


def test_hk_baseline_change_preserves_one_cutoff_and_one_later_observation() -> None:
    decisions = prove_hk_baseline_change(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-BASE-CHANGE-FIX-{index:03d}" for index in range(1, 8)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
    )
    assert tuple(decision.baseline_action for decision in decisions[:3]) == (
        "CONTINUE_ORIGINAL",
        "ABANDON_AND_REFREEZE",
        "FINISH_ORIGINAL_THEN_UPDATE",
    )
    assert decisions[3].preserved_cutoff is None
    assert all(
        decision.preserved_cutoff == "2026-08-17T00:00:00Z"
        for decision in (*decisions[:3], *decisions[4:])
    )
    assert all(
        decision.new_observation_status == "RECORDED_SEPARATELY" for decision in decisions[1:3]
    )


def test_hk_current_observation_routes_silence_change_and_unavailability() -> None:
    decisions = prove_hk_current_observation(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-OBS-FIX-{index:03d}" for index in range(1, 7)
    )
    assert tuple(decision.rule_id for decision in decisions) == (
        "HKLEG-CURRENT-OBS-001",
        "HKLEG-CURRENT-OBS-002",
        "HKLEG-CURRENT-OBS-002",
        "HKLEG-CURRENT-OBS-003",
        "HKLEG-CURRENT-OBS-003",
        "HKLEG-CURRENT-OBS-002",
    )
    assert decisions[0].workflow_result == "SUPPORTED_NO_CHANGE"
    assert decisions[0].next_action == "REUSE_EXISTING_CORPUS_RELEASE"
    assert decisions[1].work_deduplication == "OPENED_NEW"
    assert decisions[2].work_deduplication == "DEDUPLICATED_EXISTING"
    assert decisions[3].coverage_effect == "COVERAGE_GAP"
    assert decisions[3].release_choice_required is True
    assert decisions[4].affected_object_ids == ("SYN-HKLEG-OBJ-002",)
    assert decisions[4].release_choice_required is False


def test_hk_current_evidence_selects_only_complete_official_bilingual_bundle() -> None:
    decisions = prove_hk_current_evidence(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-EVID-FIX-{index:03d}" for index in range(1, 10)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "BLOCK",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
        "BLOCK",
        "QUARANTINE",
    )
    assert tuple(decision.evidence_class for decision in decisions[:3]) == (
        "VERIFIED",
        "ASSISTED",
        "VERIFIED",
    )
    assert decisions[1].selected_version == "SYN-V2"
    assert decisions[3].coverage_effect == "COVERAGE_GAP"
    assert decisions[4].coverage_effect == "NONE"
    assert all(decision.evidence_class is None for decision in decisions[3:])
    assert all(
        decision.next_action == "QUARANTINE_AFFECTED_EVIDENCE" for decision in decisions[5:7]
    )


def test_hk_current_difference_classifies_observables_without_legal_inference() -> None:
    decisions = prove_hk_current_difference(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-DIFF-FIX-{index:03d}" for index in range(1, 8)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "BLOCK",
    )
    assert tuple(decision.difference_class for decision in decisions) == (
        "EXACT_UNCHANGED",
        "EXACT_UNCHANGED",
        "PAYLOAD_CHANGED",
        "MULTIPLE_OBSERVABLE_DIFFERENCES",
        "EVIDENCE_BUNDLE_CHANGED",
        "OBJECT_ADDED",
        None,
    )
    assert decisions[0].record_selection == "REUSE_ELIGIBLE"
    assert decisions[1].record_selection == "NONE"
    assert all(decision.identity_or_status_inference == "NONE" for decision in decisions)
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)


def test_hk_current_cause_requires_exact_assigned_evidence() -> None:
    decisions = prove_hk_current_cause(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-CAUSE-FIX-{index:03d}" for index in range(1, 7)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "QUARANTINE",
        "QUARANTINE",
        "BLOCK",
    )
    assert tuple(decision.cause_class for decision in decisions[:3]) == (
        "GAZETTE_EVENT",
        "EDITORIAL_RECORD",
        "NON_SERVING_TECHNICAL_REPUBLICATION",
    )
    assert decisions[5].source_contract_review_required is True
    assert all(
        decision.document()["identity_or_status_inference"] == "NONE" for decision in decisions
    )
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)


def test_hk_current_disposition_assigns_one_supported_state_or_fails_closed() -> None:
    decisions = prove_hk_current_disposition(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-DISP-FIX-{index:03d}" for index in range(1, 8)
    )
    assert tuple(decision.legal_disposition for decision in decisions) == (
        "SEARCHABLE_CURRENT",
        "WAITING_ROOM",
        "EVIDENCE_ONLY",
        "HISTORICAL",
        "QUARANTINE",
        "NOT_APPLICABLE",
        "NOT_APPLICABLE",
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "QUARANTINE",
        "BLOCK",
        "BLOCK",
    )
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)


def test_hk_current_record_reuses_only_exact_supported_payloads() -> None:
    decisions = prove_hk_current_record(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-REC-FIX-{index:03d}" for index in range(1, 9)
    )
    assert tuple(decision.record_action for decision in decisions) == (
        "REUSED",
        "CREATED",
        "CREATED",
        "NONE",
        "NONE",
        "NONE",
        "NONE",
        "NONE",
    )
    assert decisions[0].candidate_record is not None
    assert decisions[1].predecessor_record_id == "rec_" + "1" * 48
    assert decisions[5].processing_outcome == "QUARANTINE"
    assert decisions[6].next_action == "REUSE_PREDECESSOR_RECORD_ID"
    assert decisions[7].next_action == "OPEN_INITIAL_BASELINE"


def test_hk_current_release_accounting_is_complete_before_candidate_build() -> None:
    decisions = prove_hk_current_release_accounting(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-REL-FIX-{index:03d}" for index in range(1, 8)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "PASS",
    )
    assert decisions[0].coverage_effect == "COVERAGE_GAP"
    assert decisions[0].accounted_location_ids == ("location-1", "location-2")
    assert decisions[6].coverage_effect == "NONE"
    assert decisions[6].next_action == "BUILD_CANDIDATE_CORPUS_RELEASE"


def test_hk_current_event_routes_gap_without_constructing_a_record() -> None:
    decisions = prove_hk_current_event(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-EVENT-FIX-{index:03d}" for index in range(1, 9)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "BLOCK",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
    )
    assert tuple(decision.selection_result for decision in decisions[:4]) == (
        "RECONSTRUCTION_PLAN_REQUIRED",
        "KNOWN_STALE_ANALYTICAL_CARRY_FORWARD_REQUIRED",
        "KNOWN_STALE_ANALYTICAL_CARRY_FORWARD_REQUIRED",
        "NO_RECORD_COVERAGE_GAP",
    )
    assert decisions[4].selection_result == "ORDINARY_CURRENT_BUNDLE_REQUIRED"
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)
    assert all(decision.event_fact_output == "LEGAL_STATUS_EVENT" for decision in decisions[:4])


def test_hk_known_stale_fallback_selects_only_exact_latest_hkel_text() -> None:
    decisions = prove_hk_known_stale_fallback(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-KNOWN-STALE-FIX-{index:03d}" for index in range(1, 13)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
        "QUARANTINE",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
    )
    assert decisions[0].selection_result == "KNOWN_STALE_ANALYTICAL_CARRY_FORWARD"
    assert decisions[1].fallback_selection is not None
    assert decisions[1].fallback_selection["base_evidence_class"] == "ASSISTED"
    assert decisions[1].fallback_selection["base_version_date"] == "2026-07-15"
    assert decisions[1].selection_ref() is not None
    assert decisions[2].processing_outcome == "PASS"
    assert decisions[2].selection_result == "NO_RECORD"
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)
    assert all(decision.document()["external_effects"] == "NONE" for decision in decisions)


def test_hk_current_commencement_establishes_exact_operative_and_pending_locations() -> None:
    decisions = prove_hk_current_commencement(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-COMMENCE-FIX-{index:03d}" for index in range(1, 13)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
    )
    assert decisions[2].legal_disposition == "WAITING_ROOM"
    assert decisions[6].effective_date is None
    assert decisions[7].operative_location_ids == ("section-1", "section-2")
    assert decisions[7].pending_location_ids == ("section-3",)
    assert decisions[8].operative_location_ids == ("section-1",)
    assert decisions[8].pending_location_ids == ("section-2", "section-3")
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)


def test_hk_current_cessation_preserves_exact_post_event_state_and_identity_limits() -> None:
    decisions = prove_hk_current_cessation(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-CESSATION-FIX-{index:03d}" for index in range(1, 15)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "QUARANTINE",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
    )
    assert decisions[0].post_event_operative_location_ids == ()
    assert decisions[1].post_event_operative_location_ids == ("section-1", "section-3")
    assert decisions[2].event_operative_at_cutoff is False
    assert decisions[7].identity_effect == "REVIVAL_CONTINUITY_PROVED"
    assert decisions[8].post_event_ceased_location_ids == ("section-3",)
    assert decisions[10].event_fact_output == "NONE"
    assert all(decision.event_history_action == "APPEND_EVENT" for decision in decisions[:10])
    assert all(decision.event_history_action == "PRESERVE_UNCHANGED" for decision in decisions[10:])
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)


def test_hk_current_text_event_routes_without_constructing_resulting_text() -> None:
    decisions = prove_hk_current_text_event(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-TEXT-EVENT-FIX-{index:03d}" for index in range(1, 17)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
        "PASS",
        "PASS",
    )
    assert decisions[0].selection_result == "ORDINARY_CURRENT_BUNDLE_REQUIRED"
    assert decisions[1].coverage_effect == "COVERAGE_GAP"
    assert decisions[2].legal_disposition == "WAITING_ROOM"
    assert decisions[3].affected_location_ids == ("section-2",)
    assert decisions[6].cause_source_id == "HK-LEG-HKEL-EDITORIAL-RECORDS"
    assert all(decision.event_history_action == "APPEND_EVENT" for decision in decisions[:8])
    assert all(
        decision.event_history_action == "PRESERVE_UNCHANGED" for decision in decisions[8:14]
    )
    assert all(decision.event_history_action == "APPEND_EVENT" for decision in decisions[14:])
    assert decisions[14].reason_code == "HKLEG_CURRENT_TEXT_EVENT_EXPRESS_CORRECTION_PENDING"
    assert decisions[15].reason_code == "HKLEG_CURRENT_TEXT_EVENT_EDITORIAL_PENDING"
    assert all(decision.document()["official_version_output"] == "NONE" for decision in decisions)
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)


def test_hk_current_publication_classifies_facts_without_inferring_legal_effect() -> None:
    decisions = prove_hk_current_publication(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-CURRENT-PUB-FIX-{index:03d}" for index in range(1, 14)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "BLOCK",
        "BLOCK",
        "QUARANTINE",
        "BLOCK",
        "QUARANTINE",
        "BLOCK",
    )
    assert decisions[0].publication_fact_output == "ORDINANCE_ENACTMENT_AND_PUBLICATION"
    assert decisions[1].gazette_issue_kind == "EXTRAORDINARY"
    assert decisions[1].reason_code == decisions[0].reason_code
    assert decisions[3].publication_fact_output == "NOTICE_PUBLICATION"
    assert decisions[5].publication_fact_output == "EXCLUDED_BILL_INVENTORY"
    assert decisions[6].publication_fact_output == "DISCOVERY_ONLY"
    assert decisions[12].next_action == "RESOLVE_PUBLICATION_EVIDENCE"
    assert all(decision.document()["commencement_output"] == "NONE" for decision in decisions)
    assert all(decision.document()["legal_effect_output"] == "NONE" for decision in decisions)
    assert all(decision.document()["identity_output"] == "NONE" for decision in decisions)
    assert all(decision.document()["official_version_output"] == "NONE" for decision in decisions)
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)


def test_hk_reconstruction_plan_semantic_gate_never_creates_a_plan_or_text() -> None:
    decisions = prove_hk_reconstruction_plan_semantic(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-RECON-PLAN-SEM-FIX-{index:03d}" for index in range(1, 14)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "QUARANTINE",
        "BLOCK",
        "QUARANTINE",
        "QUARANTINE",
        "BLOCK",
    )
    assert tuple(decision.reason_code for decision in decisions) == (
        "HKLEG_RECON_PLAN_SEMANTIC_CANDIDATE_CONFIRMED",
        "HKLEG_RECON_PLAN_SEMANTIC_PROFILE_NOT_ADMITTED",
        "HKLEG_RECON_PLAN_SEMANTIC_DECISION_RESULT_MISSING",
        "HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_RESULT_MISSING",
        "HKLEG_RECON_PLAN_SEMANTIC_DECISION_CONTRACT_INVALID",
        "HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_CONTRACT_INVALID",
        "HKLEG_RECON_PLAN_SEMANTIC_EVIDENCE_BINDING_INCOMPLETE",
        "HKLEG_RECON_PLAN_SEMANTIC_UNSUPPORTED_OPERATION",
        "HKLEG_RECON_PLAN_SEMANTIC_FINAL_TEXT_OVERREACH",
        "HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_OBJECTION",
        "HKLEG_RECON_PLAN_SEMANTIC_CHALLENGE_UNRESOLVED",
        "HKLEG_RECON_PLAN_SEMANTIC_RESULT_CONFLICT",
        "HKLEG_RECON_PLAN_SEMANTIC_DETERMINISTIC_PRECHECK_FAILED",
    )
    assert decisions[0].candidate_output == "UNTRUSTED_STRUCTURED_PLAN_CANDIDATE"
    assert decisions[0].deterministic_precheck_result == "PASS"
    assert all(decision.candidate_output == "NONE" for decision in decisions[1:])
    assert decisions[-1].deterministic_precheck_result == "FAIL"
    for decision in decisions:
        document = decision.document()
        assert document["executable_plan_output"] == "NONE"
        assert document["reconstructed_text_output"] == "NONE"
        assert document["operation_execution"] == "NONE"
        assert document["record_output"] == "NONE"
        assert document["external_effects"] == "NONE"


def test_hk_reconstruction_plan_validation_is_complete_and_effect_free() -> None:
    decisions = prove_hk_reconstruction_plan_validation(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-RECON-PLAN-VAL-FIX-{index:03d}" for index in range(1, 22)
    )
    assert tuple(decision.processing_outcome for decision in decisions) == (
        "PASS",
        "PASS",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "QUARANTINE",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
        "BLOCK",
    )
    assert tuple(decision.reason_code for decision in decisions) == (
        "HKLEG_RECON_PLAN_VALIDATED",
        "HKLEG_RECON_PLAN_VALIDATED",
        "HKLEG_RECON_PLAN_CANDIDATE_MISSING",
        "HKLEG_RECON_PLAN_CONTRACT_INVALID",
        "HKLEG_RECON_PLAN_UNKNOWN_OPERATION",
        "HKLEG_RECON_PLAN_SEMANTIC_CANDIDATE_MISMATCH",
        "HKLEG_RECON_PLAN_LEGAL_DESK_DECISION_NOT_ACCEPTED",
        "HKLEG_RECON_PLAN_BASE_NOT_LATEST_ELIGIBLE",
        "HKLEG_RECON_PLAN_CHAIN_INCOMPLETE",
        "HKLEG_RECON_PLAN_EVENT_ORDER_UNRESOLVED",
        "HKLEG_RECON_PLAN_APPLICABILITY_UNRESOLVED",
        "HKLEG_RECON_PLAN_DEPENDENCY_CLOSURE_INCOMPLETE",
        "HKLEG_RECON_PLAN_OVERLAP",
        "HKLEG_RECON_PLAN_SOURCE_UNIT_OWNERSHIP_INCOMPLETE",
        "HKLEG_RECON_PLAN_LANGUAGE_EVIDENCE_INCOMPLETE",
        "HKLEG_RECON_PLAN_BILINGUAL_RESULT_MISMATCH",
        "HKLEG_RECON_PLAN_OPERATION_INVENTORY_INVALID",
        "HKLEG_RECON_PLAN_OPERATION_EVENT_BINDING_INCOMPLETE",
        "HKLEG_RECON_PLAN_ATOMIC_GROUP_INCOMPLETE",
        "HKLEG_RECON_PLAN_UNDECLARED_INPUT",
        "HKLEG_RECON_PLAN_DETERMINISTIC_REVALIDATION_FAILED",
    )
    assert tuple(decision.validated_operation_count for decision in decisions[:2]) == (2, 1)
    assert all(decision.plan_validation_result == "VALIDATED" for decision in decisions[:2])
    assert all(decision.plan_validation_result == "NONE" for decision in decisions[2:])
    assert decisions[4].source_contract_review_required is True
    for decision in decisions:
        document = decision.document()
        assert document["operation_execution"] == "NONE"
        assert document["reconstructed_text_output"] == "NONE"
        assert document["record_output"] == "NONE"
        assert document["external_effects"] == "NONE"


def test_hk_reconstruction_execution_is_exact_atomic_and_effect_free() -> None:
    results = prove_hk_reconstruction_execution(HK_PACKAGE_ROOT)
    assert tuple(result.processing_outcome for result in results) == (
        *("PASS" for _ in range(8)),
        *("BLOCK" for _ in range(5)),
    )
    assert tuple(result.reason_code for result in results) == (
        *("RECONSTRUCTION_OPERATIONS_PROVISIONALLY_COMPLETE" for _ in range(8)),
        "RECONSTRUCTION_BEFORE_STATE_MISMATCH",
        "RECONSTRUCTION_FINAL_TREE_MISMATCH",
        "RECONSTRUCTION_SOURCE_UNIT_INVENTORY_MISMATCH",
        "RECONSTRUCTION_BILINGUAL_ALIGNMENT_MISMATCH",
        "RECONSTRUCTION_RENDERER_UNSUPPORTED",
    )
    for result in results:
        document = result.document()
        assert document["execution_report_output"] == "NONE"
        assert document["reconstructed_artifact_output"] == "NONE"
        assert document["record_output"] == "NONE"
        assert document["external_effects"] == "NONE"
    assert all(
        operation.atomic_group_result == "ROLLED_BACK"
        for result in results[8:12]
        for operation in result.operation_results
        if operation.result == "APPLIED"
    )


def test_hk_recursive_bilingual_partition_package_is_exact_and_effect_free() -> None:
    results = prove_hk_legislation_partition(HK_PACKAGE_ROOT)

    assert len(results) == 22
    assert tuple(result.reason.value for result in results) == (
        "PASS_UNSPLIT",
        "LOCATIONS_PROCESSED_SEPARATELY",
        "PASS_PARTITIONED",
        "PASS_PARTITIONED",
        "PASS_PARTITIONED",
        "PASS_PARTITIONED",
        "PASS_PARTITIONED",
        "PASS_UNSPLIT",
        "PASS_PARTITIONED",
        "PASS_PARTITIONED",
        "PASS_PARTITIONED",
        "PASS_PARTITIONED",
        "PASS_PARTITIONED",
        "SOURCE_UNIT_COVERAGE_DEFECT",
        "SOURCE_UNIT_COVERAGE_DEFECT",
        "SMALLEST_DEPENDENT_BRANCH_OVER_LIMIT",
        "SMALLEST_DEPENDENT_BRANCH_OVER_LIMIT",
        "BILINGUAL_ALIGNMENT_MISMATCH",
        "SOURCE_LOCATION_OWNERSHIP_DEFECT",
        "PASS_PARTITIONED",
        "SOURCE_CONTRACT_REVIEW_REQUIRED",
        "EXPLICIT_UNSAFE_NEW_VERSION_CONSEQUENCE",
    )
    assert all(result.canonical_bytes == canonicalize(result.document()) for result in results)
    assert all(
        result.document()["search_record_output"] == "NONE"
        and result.document()["external_effects"] == "NONE"
        for result in results
    )
    batch = results[1]
    assert batch.parts == ()
    assert batch.document()["cross_location_combination"] == "FORBIDDEN"
    assert len(_array(batch.document()["location_results"])) == 2
    assert results[5].parts[0].primary_partition_node_ids == ("partition_paragraph_1",)
    nested_nodes = tuple(
        node_id for part in results[6].parts for node_id in part.primary_partition_node_ids
    )
    assert "nested_subparagraph_1a" in nested_nodes
    assert results[8].parts[-1].dependency_alignment_group_ids == ("align_heading",)
    assert all(not part.dependency_alignment_group_ids for part in results[9].parts)
    assert all(
        part.dependency_alignment_group_ids == ("align_table_headers",)
        for part in results[10].parts
    )
    note_part = next(
        part for part in results[11].parts if "align_note_1" in part.primary_alignment_group_ids
    )
    assert note_part.primary_partition_node_ids == ("partition_paragraph_1",)
    assert note_part.primary_alignment_group_ids == ("align_body_1", "align_note_1")
    assert results[13].disposition.value == "BLOCK"
    assert results[14].disposition.value == "BLOCK"
    assert results[15].coverage_gap_required is True
    assert results[16].coverage_gap_required is True
    assert results[17].coverage_gap_required is True
    assert results[18].disposition.value == "BLOCK"
    assert results[18].reason.value == "SOURCE_LOCATION_OWNERSHIP_DEFECT"
    consequence = results[21]
    assert isinstance(consequence, PartitionReleaseConsequenceResult)
    assert consequence.release_action == "NO_NEW_DESIRED_STATE"
    assert consequence.routing_action == "RETAIN_PREVIOUS_VERIFIED_TARGET"
    assert consequence.document()["predecessor_retirement"] == "FORBIDDEN"


def test_hk_reconstruction_artifact_and_report_are_exact_and_effect_free() -> None:
    reports = prove_hk_reconstruction_report(HK_PACKAGE_ROOT)
    assert tuple(report.document()["processing_outcome"] for report in reports) == (
        "PASS",
        "BLOCK",
    )
    assert tuple(report.document()["selection_consequence"] for report in reports) == (
        "RECONSTRUCTION",
        "NO_RECORD",
    )
    assert all(report.document()["external_effects"] == "NONE" for report in reports)


def test_hk_later_hkel_reconciliation_is_complete_and_valid_hkel_first() -> None:
    decisions = prove_hk_reconstruction_reconciliation(HK_PACKAGE_ROOT)
    assert tuple(decision.fixture_id for decision in decisions) == tuple(
        f"HKLEG-RECON-RCN-FIX-{index:03d}" for index in range(1, 13)
    )
    assert tuple(decision.next_state for decision in decisions) == (
        "AWAITING_HKEL_CONSOLIDATION",
        "HKEL_CANDIDATE_OBSERVED",
        "AWAITING_HKEL_CONSOLIDATION",
        "MATCH_CONFIRMED",
        "MATCH_CONFIRMED",
        "COMPARISON_DEFERRED",
        "MISMATCH_CONFIRMED",
        "MISMATCH_CONFIRMED",
        "HKEL_CANDIDATE_OBSERVED",
        "SUSPENDED_PENDING_REVALIDATION",
        "REVALIDATED",
        "SUPERSEDED_BY_HKEL",
    )
    assert decisions[2].comparison_class == "HKEL_CANDIDATE_INVALID"
    assert decisions[5].serving_consequence == "SELECT_ORDINARY_HKEL_WHEN_APPROVED"
    assert decisions[8].processing_outcome == "BLOCK"
    assert decisions[11].comparison_class == "MATERIAL_MISMATCH"
    assert decisions[11].serving_consequence == "ORDINARY_HKEL_SELECTED"
    assert all(decision.document()["artifact_mutation"] == "NONE" for decision in decisions)
    assert all(decision.document()["record_output"] == "NONE" for decision in decisions)
    assert all(decision.document()["external_effects"] == "NONE" for decision in decisions)


def test_hk_baseline_inventory_fixture_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-INV-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-inventory-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_inventory(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_evidence_fixture_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-EVID-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-evidence-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_evidence(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_state_fixture_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-STATE-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-state-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_state(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_limit_fixture_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-LIMIT-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-limit-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_limit(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_identity_fixture_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-ID-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-identity-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_identity(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_disposition_fixture_schema_and_locks_reject_drift(
    tmp_path: Path,
) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-DISP-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-disposition-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_disposition(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_record_fixture_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-REC-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-record-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_record(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_release_accounting_schema_and_locks_reject_drift(
    tmp_path: Path,
) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-REL-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-release-accounting-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_release_accounting(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_review_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-REVIEW-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-review-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_review(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_history_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-HIST-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-history-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_history(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_baseline_change_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-BASE-CHANGE-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/baseline-change-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_baseline_change(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_observation_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-OBS-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-observation-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_observation(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_evidence_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-EVID-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-evidence-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_evidence(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_difference_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-DIFF-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-difference-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_difference(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_cause_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-CAUSE-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-cause-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_cause(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_commencement_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-COMMENCE-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-commencement-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_commencement(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_cessation_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-CESSATION-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-cessation-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_cessation(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_text_event_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-TEXT-EVENT-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-text-event-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_text_event(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_publication_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-PUB-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-publication-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_publication(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_reconstruction_plan_semantic_schema_and_locks_reject_drift(
    tmp_path: Path,
) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-RECON-PLAN-SEM-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/reconstruction-plan-semantic-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_reconstruction_plan_semantic(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_reconstruction_plan_validation_schema_and_locks_reject_drift(
    tmp_path: Path,
) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-RECON-PLAN-VAL-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/reconstruction-plan-validation-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_reconstruction_plan_validation(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_reconstruction_execution_schema_and_locks_reject_drift(
    tmp_path: Path,
) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-RECON-EXEC-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/reconstruction-execution-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_reconstruction_execution(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_partition_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-RECON-ORP-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/reconstruction-overlong-partition-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_legislation_partition(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_reconstruction_report_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-RECON-REPORT-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/reconstruction-report-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_reconstruction_report(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_event_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-EVENT-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-event-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_event(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_disposition_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-DISP-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-disposition-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_disposition(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_record_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-REC-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-record-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_record(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_hk_current_release_schema_and_locks_reject_drift(tmp_path: Path) -> None:
    root = _copy_hk(tmp_path)
    fixture_path = root / "fixtures/deterministic/HKLEG-CURRENT-REL-FIX-001.json"
    fixture = _json(fixture_path)
    fixture["unexpected"] = "FORBIDDEN"
    _write(fixture_path, fixture)

    catalogue_path = root / "catalogues/current-release-accounting-fixtures.json"
    catalogue = _json(catalogue_path)
    entries = _array(catalogue["fixtures"])
    _object(entries[0])["fixture_fingerprint"] = (
        f"sha256:{sha256(fixture_path.read_bytes()).hexdigest()}"
    )
    _write(catalogue_path, catalogue)
    _rehash(root)

    with pytest.raises(RulebookError) as caught:
        prove_hk_current_release_accounting(root)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH


def test_not_ready_blockers_and_ready_proof_inventory_are_enforced(tmp_path: Path) -> None:
    missing_blocker = _copy_hk(tmp_path / "missing-blocker")
    scopes_document = _json(missing_blocker / "scopes/release-scopes.json")
    scopes = _array(scopes_document["scopes"])
    _object(scopes[0])["blocker_codes"] = []
    _write(missing_blocker / "scopes/release-scopes.json", scopes_document)
    _rehash(missing_blocker)
    with pytest.raises(RulebookError) as blockers:
        _load_hk(missing_blocker)
    assert blockers.value.code is RulebookErrorCode.CONTRACT_MISMATCH

    unknown_blocker = _copy_hk(tmp_path / "unknown-blocker")
    scopes_document = _json(unknown_blocker / "scopes/release-scopes.json")
    scopes = _array(scopes_document["scopes"])
    blocker_codes = _array(_object(scopes[0])["blocker_codes"])
    blocker_codes.append("HKLEG_UNDECLARED_BLOCKER")
    _write(unknown_blocker / "scopes/release-scopes.json", scopes_document)
    _rehash(unknown_blocker)
    with pytest.raises(RulebookError) as unknown:
        _load_hk(unknown_blocker)
    assert unknown.value.code is RulebookErrorCode.UNKNOWN_CODE

    false_attestation = _copy_hk(tmp_path / "false-attestation")
    scopes_document = _json(false_attestation / "scopes/release-scopes.json")
    scopes = _array(scopes_document["scopes"])
    _object(scopes[0])["readiness"] = "ATTESTED_INACTIVE"
    _object(scopes[0])["blocker_codes"] = []
    _write(false_attestation / "scopes/release-scopes.json", scopes_document)
    manifest = _json(false_attestation / "package.json")
    manifest["legal_desk_owner"] = "NAMED_HONG_KONG_LEGISLATION_LEGAL_DESK"
    readiness = _array(manifest["scope_readiness"])
    _object(readiness[0])["state"] = "ATTESTED_INACTIVE"
    _write(false_attestation / "package.json", manifest)
    _rehash(false_attestation)
    with pytest.raises(RulebookError) as proofs:
        _load_hk(false_attestation)
    assert proofs.value.code is RulebookErrorCode.CONTRACT_MISMATCH


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("missing", RulebookErrorCode.INVENTORY_MISMATCH),
        ("extra", RulebookErrorCode.INVENTORY_MISMATCH),
        ("drift", RulebookErrorCode.FINGERPRINT_DRIFT),
    ],
)
def test_missing_extra_and_drift_are_rejected(
    tmp_path: Path,
    mutation: str,
    expected: RulebookErrorCode,
) -> None:
    root = _copy(tmp_path)
    if mutation == "missing":
        (root / "expected/candidate.json").unlink()
    elif mutation == "extra":
        _write(root / "rules/undeclared.json", {})
    else:
        _write(root / "rules/terminal-rules.json", {"rules": []})
    with pytest.raises(RulebookError) as caught:
        _load(root)
    assert caught.value.code is expected


def test_unknown_code_overlap_incomplete_source_and_fixture_leakage_fail_closed(
    tmp_path: Path,
) -> None:
    mutations = (
        ("unknown", RulebookErrorCode.UNKNOWN_CODE),
        ("overlap", RulebookErrorCode.OVERLAPPING_SCOPES),
        ("source", RulebookErrorCode.INCOMPLETE_SOURCE_INVENTORY),
        ("leakage", RulebookErrorCode.EVALUATION_LEAKAGE),
    )
    for name, expected in mutations:
        root = _copy(tmp_path / name)
        if name == "unknown":
            document = _json(root / "rules/terminal-rules.json")
            rules = _array(document["rules"])
            _object(rules[0])["disposition"] = "GUESS"
            _write(root / "rules/terminal-rules.json", document)
        elif name == "overlap":
            document = _json(root / "scopes/release-scopes.json")
            scopes = _array(document["scopes"])
            duplicate = dict(_object(scopes[0]))
            duplicate["scope_id"] = f"rsc_{'4' * 48}"
            scopes.append(duplicate)
            _write(root / "scopes/release-scopes.json", document)
            manifest = _json(root / "package.json")
            readiness = _array(manifest["scope_readiness"])
            readiness.append({"scope_id": f"rsc_{'4' * 48}", "state": "ATTESTED_INACTIVE"})
            _write(root / "package.json", manifest)
        elif name == "source":
            document = _json(root / "sources/source-universe.json")
            document["complete"] = False
            _write(root / "sources/source-universe.json", document)
        else:
            document = _json(root / "evaluations/gazette-event-evaluation.json")
            document["protected_reference_fingerprints"] = ["sha256:" + "3" * 64]
            _write(root / "evaluations/gazette-event-evaluation.json", document)
        _rehash(root)
        with pytest.raises(RulebookError) as caught:
            _load(root)
        assert caught.value.code is expected


def test_floating_and_expired_profiles_and_environment_misuse_are_rejected(tmp_path: Path) -> None:
    floating = _copy(tmp_path / "floating")
    document = _json(floating / "profiles/semantic-profiles.json")
    profiles = _array(document["profiles"])
    _object(profiles[0])["model_version"] = "latest"
    _write(floating / "profiles/semantic-profiles.json", document)
    _rehash(floating)
    with pytest.raises(RulebookError) as caught:
        _load(floating)
    assert caught.value.code is RulebookErrorCode.CONTRACT_MISMATCH

    with pytest.raises(RulebookError) as expired:
        load_rulebook_package(
            PACKAGE_ROOT,
            environment="LOCAL_SYNTHETIC",
            contract_set_fingerprint=_contract_fingerprint(),
            now="2031-01-01T00:00:00Z",
        )
    assert expired.value.code is RulebookErrorCode.EXPIRED_PROFILE
    with pytest.raises(RulebookError) as environment:
        _load(environment="PRODUCTION")
    assert environment.value.code is RulebookErrorCode.ENVIRONMENT_MISUSE


def test_activation_is_exact_and_stale_or_suspended_scope_cannot_execute() -> None:
    package = _load()
    lifecycle = RulebookLifecycle()
    activation = _activation(package)
    lifecycle.activate(
        package,
        activation,
        current_contract_set_fingerprint=_contract_fingerprint(),
        current_engine_build="legal-processing-build-1",
    )
    engine = RuleEngine(lifecycle)
    result = engine.execute(package, _subject(("change_kind", "CREATE")))
    assert result.processing_result == "SUCCEEDED"
    assert result.rule_id == "ZZZ-TEST-CREATE-001"

    lifecycle.suspend(package.manifest.package_fingerprint, SCOPE_ID)
    with pytest.raises(RulebookError) as suspended:
        engine.execute(package, _subject(("change_kind", "CREATE")))
    assert suspended.value.code is RulebookErrorCode.PACKAGE_NOT_ACTIVE

    stale = replace(activation, engine_build="changed-build")
    with pytest.raises(RulebookError) as caught:
        RulebookLifecycle().activate(
            package,
            stale,
            current_contract_set_fingerprint=_contract_fingerprint(),
            current_engine_build="legal-processing-build-1",
        )
    assert caught.value.code is RulebookErrorCode.STALE_ACTIVATION


def test_rule_execution_is_total_ambiguity_safe_and_byte_reproducible(tmp_path: Path) -> None:
    package = _load()
    lifecycle = RulebookLifecycle()
    lifecycle.activate(
        package,
        _activation(package),
        current_contract_set_fingerprint=_contract_fingerprint(),
        current_engine_build="legal-processing-build-1",
    )
    engine = RuleEngine(lifecycle)
    subject = _subject(("unknown", "fact"))
    blocked = engine.execute(package, subject)
    assert blocked.failure_code == "RULEBOOK_NON_TOTAL"
    assert blocked.candidate_artifact_refs == ()

    first = engine.execute(package, _subject(("change_kind", "CREATE")))
    second = engine.execute(package, _subject(("change_kind", "CREATE")))
    assert first == second
    assert engine.canonical_result(first) == engine.canonical_result(second)

    ambiguous_root = _copy(tmp_path)
    document = _json(ambiguous_root / "rules/terminal-rules.json")
    rules = _array(document["rules"])
    duplicate = dict(_object(rules[0]))
    duplicate["rule_id"] = "ZZZ-TEST-CREATE-002"
    rules.append(duplicate)
    _write(ambiguous_root / "rules/terminal-rules.json", document)
    _rehash(ambiguous_root)
    ambiguous_package = _load(ambiguous_root)
    ambiguous_lifecycle = RulebookLifecycle()
    ambiguous_lifecycle.activate(
        ambiguous_package,
        _activation(ambiguous_package),
        current_contract_set_fingerprint=_contract_fingerprint(),
        current_engine_build="legal-processing-build-1",
    )
    ambiguous = RuleEngine(ambiguous_lifecycle).execute(
        ambiguous_package,
        _subject(("change_kind", "CREATE")),
    )
    assert ambiguous.failure_code == "RULEBOOK_AMBIGUOUS"
    assert ambiguous.candidate_artifact_refs == ()
