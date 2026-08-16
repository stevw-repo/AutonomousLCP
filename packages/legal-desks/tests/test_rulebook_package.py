"""M5 executable Source Rulebook Package conformance."""

from __future__ import annotations

import shutil
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from asklegal_contracts import canonicalize, fingerprint, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_legal_desks import (
    ActivationRecord,
    LoadedRulebook,
    ProcessingSubject,
    RulebookError,
    RulebookErrorCode,
    RulebookLifecycle,
    RuleEngine,
    load_rulebook_package,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPOSITORY_ROOT / "packages/legal-desks/src/asklegal_legal_desks/_synthetic_package"
CONTRACT_MANIFEST = REPOSITORY_ROOT / "contracts/package-manifest.json"
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
