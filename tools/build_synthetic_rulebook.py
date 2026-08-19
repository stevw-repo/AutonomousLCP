"""Mechanically rebuild the reserved M5 synthetic package manifest."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, cast

import rfc8785

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "packages/legal-desks/src/asklegal_legal_desks/_synthetic_package"

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


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _role(path: str) -> str:
    if path.startswith("fixtures/deterministic/"):
        return "DETERMINISTIC_FIXTURE"
    if path.startswith("fixtures/semantic/"):
        return "SEMANTIC_FIXTURE"
    return ROLES[path.split("/", maxsplit=1)[0]]


def build_manifest() -> dict[str, JsonValue]:
    """Build one deterministic root manifest excluding itself."""
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
        "package_id": "rbp_777777777777777777777777777777777777777777777777",
        "package_version": "1.0.0",
        "package_fingerprint": "PENDING",
        "jurisdiction": "ZZZ",
        "environment": "LOCAL_SYNTHETIC",
        "material_family": "TEST_LEGAL_MATERIAL",
        "legal_desk_owner": "TEST_FIXTURE_OWNER",
        "effective_cutoff": "2026-08-16T00:00:00Z",
        "predecessor": None,
        "contract_locks": [contract_fingerprint],
        "code_locks": ["asklegal-legal-desks==0.1.0", "asklegal-processing==0.1.0"],
        "source_universe_fingerprint": _fingerprint(
            (PACKAGE_ROOT / "sources/source-universe.json").read_bytes()
        ),
        "scope_readiness": [
            {
                "scope_id": "rsc_333333333333333333333333333333333333333333333333",
                "state": "ATTESTED_INACTIVE",
            }
        ],
        "unresolved_policy_codes": [],
        "impact_declaration": "TEST_ONLY_INITIAL_PACKAGE_NO_REAL_SCOPE_IMPACT",
        "minimum_engine_version": "1.0.0",
        "files": files,
    }
    projection = dict(document)
    projection.pop("package_fingerprint")
    document["package_fingerprint"] = _fingerprint(rfc8785.dumps(cast("JsonValue", projection)))
    return document


def main() -> None:
    """Write stable human-readable bytes; authority is the canonical fingerprint."""
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    (PACKAGE_ROOT / "package.json").write_text(
        json.dumps(build_manifest(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
