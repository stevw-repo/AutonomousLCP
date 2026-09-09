"""Focused no-network proofs for current two-family source-authority rebinding."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest

from tools.hk_v1_rebind_source_authority import (
    SourceAuthorityRebindError,
    publish_source_authority,
    rebind_source_authority,
)
from tools.hk_v1_source_admission import preflight

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
REGISTERS = {
    "CASES": ROOT
    / "packages/source-connectors/src/asklegal_source_connectors/hk_cases_source_register.json",
    "LEGISLATION": ROOT / "packages/source-connectors/src/asklegal_source_connectors/"
    "hk_legislation_source_register.json",
    "REGULATORY": ROOT / "packages/source-connectors/src/asklegal_source_connectors/"
    "hk_regulatory_source_register.json",
}
SELECTED = {
    "CASES": {"HK-CASE-HKLII-DISCOVERY", "HK-CASE-JUDICIARY-LRS-INVENTORY"},
    "LEGISLATION": {
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
    },
}


def _load(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_bytes())
    assert type(value) is dict
    return cast("dict[str, object]", value)


def _reference(label: str, scope: str) -> dict[str, object]:
    return {
        "vault": "PRIMARY",
        "logical_key": f"hk-v1/{label}",
        "version_id": "v" + "a" * 64,
        "fingerprint": "sha256:" + "a" * 64,
        "byte_length": 1,
        "publisher": "ASKLEGAL_USER_ATTESTATION",
        "scope": scope,
        "effective_date": "2026-01-01",
        "expires_on": "NO_EXPIRY",
        "provenance": "USER_REPORTED",
    }


def _retained_manifest(path: Path) -> Path:
    matrix = _load(MATRIX)
    selected: list[dict[str, object]] = []
    source_ids: set[str] = set()
    hosts: set[str] = set()
    procedure_ids: set[str] = set()
    bindings: list[dict[str, object]] = []
    for family in ("LEGISLATION", "CASES", "REGULATORY"):
        register = _load(REGISTERS[family])
        bindings.append(
            {
                "family": family,
                "register_id": register["register_id"],
                "register_version": register["register_version"],
                "fingerprint": register["fingerprint"],
            }
        )
        if family not in SELECTED:
            continue
        endpoints: dict[object, dict[str, object]] = {}
        for raw in cast("list[object]", register["endpoints"]):
            item = cast("dict[str, object]", raw)
            endpoints[item["endpoint_id"]] = item
        for raw in cast("list[object]", register["sources"]):
            source = cast("dict[str, object]", raw)
            source_id = cast("str", source["source_id"])
            if source_id not in SELECTED[family]:
                continue
            claims: list[dict[str, object]] = []
            for endpoint_id in cast("list[str]", source["endpoint_ids"]):
                endpoint = endpoints[endpoint_id]
                parsed = urlsplit(cast("str", endpoint["url"]))
                claim: dict[str, object] = {
                    "endpoint_id": endpoint_id,
                    "host": parsed.netloc,
                    "method": cast("list[str]", endpoint["methods"])[0],
                    "path": parsed.path + (f"?{parsed.query}" if parsed.query else ""),
                    "procedure_id": endpoint_id,
                    "redirect_policy": "NO_REDIRECT",
                }
                claims.append(claim)
                hosts.add(parsed.netloc)
                procedure_ids.add(endpoint_id)
            source_ids.add(source_id)
            selected.append(
                {
                    "family": family,
                    "source_id": source_id,
                    "endpoints": claims,
                    "publisher_permission_id": "pp_" + "1" * 48,
                }
            )
    unsigned: dict[str, object] = {
        "schema_version": "1.0.0",
        "authority_id": "hka_" + "1" * 48,
        "scope": "HK_V1_SOURCE_ADMISSION_PREFLIGHT",
        "provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "effective_date": "2026-01-01",
        "expires_on": "NO_EXPIRY",
        "matrix": {"revision": "OLD", "fingerprint": "sha256:" + "0" * 64},
        "registers": bindings,
        "selected_sources": selected,
        "publisher_permissions": [
            {
                "permission_id": "pp_" + "1" * 48,
                "source_ids": sorted(source_ids),
                "hosts": sorted(hosts),
                "procedure_ids": sorted(procedure_ids),
                "reference": _reference("authority", "READ_ONLY_SOURCE_ADMISSION"),
            }
        ],
        "user_reports": [
            {"report_id": "usr_" + "1" * 48, "reference": _reference("report", "REPORT")}
        ],
        "terms": [
            {
                "host": host,
                "state": "ALREADY_ACCEPTED_WITH_EVIDENCE",
                "terms_reference": _reference(f"terms/{index}", "PUBLISHER_TERMS_EVIDENCE"),
                "acceptance_evidence": _reference(
                    f"acceptance/{index}", "PUBLISHER_TERMS_EVIDENCE"
                ),
            }
            for index, host in enumerate(sorted(hosts))
        ],
        "observation_window": {
            "start": "2026-01-01T00:00:00+08:00",
            "end": "2026-01-02T00:00:00+08:00",
            "cutoff": "2026-01-02T00:00:00+08:00",
            "timezone": "Asia/Hong_Kong",
        },
        "credentials": [],
        "sessions": [],
    }
    unsigned["matrix"] = {"revision": "OLD", "fingerprint": matrix["fingerprint"]}
    document = {
        **unsigned,
        "fingerprint": "sha256:"
        + hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    return path


def test_rebind_narrows_to_current_two_family_identity_and_preflights(tmp_path: Path) -> None:
    """Only current two-family bindings remain; policy blockers stay visible."""
    retained = _retained_manifest(tmp_path / "retained.json")
    current = rebind_source_authority(retained, "2026-09-08T12:00:00+08:00")
    output = tmp_path / "current.json"
    output.write_bytes(json.dumps(current, sort_keys=True, separators=(",", ":")).encode())

    assert {
        item["family"] for item in cast("list[dict[str, object]]", current["selected_sources"])
    } == {
        "CASES",
        "LEGISLATION",
    }
    report = preflight(
        authority_manifest=output,
        matrix=MATRIX,
        output_root=ROOT / "var/hk-v1/source-admission/task10-preflight",
        repository_root=ROOT,
    )
    assert report["missing_codes"] == [
        "MATRIX_RIGHTS_ADMISSION_MISSING",
        "MATRIX_TECHNICAL_ADMISSION_MISSING",
        "SOURCE_BLOCKERS_PRESENT",
        "SOURCE_OPERATIONAL_ADMISSION_MISSING",
    ]


def test_rebind_is_deterministic_and_publish_replays_without_overwrite(tmp_path: Path) -> None:
    """Same retained evidence and cutoff replay exact bytes without replacement."""
    retained = _retained_manifest(tmp_path / "retained.json")
    first = rebind_source_authority(retained, "2026-09-08T12:00:00+08:00")
    second = rebind_source_authority(retained, "2026-09-08T12:00:00+08:00")
    output = tmp_path / "state/current.json"

    assert first == second
    assert publish_source_authority(first, output) is False
    assert publish_source_authority(second, output) is True
    output.write_text("drift", encoding="utf-8")
    with pytest.raises(SourceAuthorityRebindError, match="OUTPUT_CONFLICT"):
        publish_source_authority(second, output)


def test_rebind_refuses_source_scope_expansion_and_symlink_output(tmp_path: Path) -> None:
    """Rebinding cannot add unproven source rights or escape through a symlink."""
    retained = _retained_manifest(tmp_path / "retained.json")
    value = json.loads(retained.read_bytes())
    permission = cast("list[dict[str, object]]", value["publisher_permissions"])[0]
    permission["source_ids"] = ["HK-LEG-GLD-EGAZETTE"]
    unsigned = dict(value)
    unsigned.pop("fingerprint")
    value["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    retained.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())

    with pytest.raises(SourceAuthorityRebindError, match="SCOPE_EXPANSION_FORBIDDEN"):
        rebind_source_authority(retained, "2026-09-08T12:00:00+08:00")

    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(SourceAuthorityRebindError, match="OUTPUT_INVALID"):
        publish_source_authority({"a": 1}, link)
