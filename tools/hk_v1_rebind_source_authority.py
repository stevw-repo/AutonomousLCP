"""Rebind retained user-attested source authority to current two-family identities.

This command is a local, no-network preparation step.  It preserves the exact
retained permission and terms evidence, narrows selected sources to the accepted
Cases/Legislation V1 set, and refreshes only repository-owned Matrix, register,
and endpoint identities.  It does not convert user-reported evidence into a
publisher-issued permission or authorize source execution by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Never, TypeIs, cast
from urllib.parse import urlsplit

_ROOT = Path(__file__).resolve().parents[1]
_MATRIX = Path("packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json")
_REGISTERS = {
    "CASES": Path(
        "packages/source-connectors/src/asklegal_source_connectors/hk_cases_source_register.json"
    ),
    "LEGISLATION": Path(
        "packages/source-connectors/src/asklegal_source_connectors/"
        "hk_legislation_source_register.json"
    ),
    "REGULATORY": Path(
        "packages/source-connectors/src/asklegal_source_connectors/"
        "hk_regulatory_source_register.json"
    ),
}
_SELECTED = {
    "CASES": frozenset({"HK-CASE-HKLII-DISCOVERY", "HK-CASE-JUDICIARY-LRS-INVENTORY"}),
    "LEGISLATION": frozenset(
        {
            "HK-LEG-BASIC-LAW-PORTAL",
            "HK-LEG-GLD-EGAZETTE",
            "HK-LEG-HKEL-CURRENT-DATA",
            "HK-LEG-HKEL-CURRENT-INVENTORY",
            "HK-LEG-HKEL-EDITORIAL-RECORDS",
            "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        }
    ),
}
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_CUTOFF = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00$")
_MAX_BYTES = 4_194_304
_INPUT_INVALID = "SOURCE_AUTHORITY_INPUT_INVALID"
_FINGERPRINT_INVALID = "SOURCE_AUTHORITY_FINGERPRINT_INVALID"
_REGISTER_INVALID = "SOURCE_REGISTER_INVALID"
_SCOPE_EXPANSION = "SOURCE_AUTHORITY_SCOPE_EXPANSION_FORBIDDEN"
_TERMS_MISSING = "SOURCE_AUTHORITY_TERMS_EVIDENCE_MISSING"
_OUTPUT_INVALID = "SOURCE_AUTHORITY_OUTPUT_INVALID"
_OUTPUT_CONFLICT = "SOURCE_AUTHORITY_OUTPUT_CONFLICT"
_OUTPUT_READBACK = "SOURCE_AUTHORITY_OUTPUT_READBACK_FAILED"


class SourceAuthorityRebindError(ValueError):
    """One fail-closed local authority-rebinding error."""


def _object(value: object) -> TypeIs[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    candidate = cast("dict[object, object]", value)
    return all(type(key) is str for key in candidate)


def _fail(code: str) -> Never:
    raise SourceAuthorityRebindError(code)


def _objects(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        _fail(_INPUT_INVALID)
    candidate = cast("list[object]", value)
    if any(not _object(item) for item in candidate):
        _fail(_INPUT_INVALID)
    return cast("list[dict[str, object]]", candidate)


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        _fail(_INPUT_INVALID)
    candidate = cast("list[object]", value)
    if any(type(item) is not str for item in candidate):
        _fail(_INPUT_INVALID)
    return cast("list[str]", candidate)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _load(path: Path, *, require_canonical: bool = True) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > _MAX_BYTES:
            _fail(_INPUT_INVALID)
        value: object = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceAuthorityRebindError(_INPUT_INVALID) from error
    if not _object(value) or (require_canonical and _canonical(value) != raw):
        _fail(_INPUT_INVALID)
    return value


def _verified_document(path: Path, *, require_canonical: bool = True) -> dict[str, object]:
    document = _load(path, require_canonical=require_canonical)
    declared = document.get("fingerprint")
    unsigned = dict(document)
    unsigned.pop("fingerprint", None)
    actual = f"sha256:{hashlib.sha256(_canonical(unsigned)).hexdigest()}"
    if type(declared) is not str or declared != actual:
        _fail(_FINGERPRINT_INVALID)
    return document


def _source_map(register: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for source in _objects(register.get("sources")):
        source_id = source.get("source_id")
        if type(source_id) is not str or source_id in result:
            _fail(_REGISTER_INVALID)
        result[source_id] = source
    return result


def _endpoint_map(register: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for endpoint in _objects(register.get("endpoints")):
        endpoint_id = endpoint.get("endpoint_id")
        if type(endpoint_id) is not str or endpoint_id in result:
            _fail(_REGISTER_INVALID)
        result[endpoint_id] = endpoint
    return result


def _claim(endpoint: dict[str, object]) -> dict[str, object]:
    endpoint_id = endpoint.get("endpoint_id")
    url = endpoint.get("url")
    methods = _strings(endpoint.get("methods"))
    if type(endpoint_id) is not str or type(url) is not str or not methods:
        _fail(_REGISTER_INVALID)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        _fail(_REGISTER_INVALID)
    return {
        "endpoint_id": endpoint_id,
        "host": parsed.netloc,
        "method": methods[0],
        "path": parsed.path + (f"?{parsed.query}" if parsed.query else ""),
        "procedure_id": endpoint_id,
        "redirect_policy": "NO_REDIRECT",
    }


def _permission_by_source(
    manifest: dict[str, object],
) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    permissions: dict[str, dict[str, object]] = {}
    by_source: dict[str, str] = {}
    for permission in _objects(manifest.get("publisher_permissions")):
        permission_id = permission.get("permission_id")
        reference = permission.get("reference")
        if type(permission_id) is not str or permission_id in permissions or not _object(reference):
            _fail(_INPUT_INVALID)
        permissions[permission_id] = permission
        for source_id in _strings(permission.get("source_ids")):
            if source_id in by_source and by_source[source_id] != permission_id:
                _fail(_INPUT_INVALID)
            by_source[source_id] = permission_id
    return by_source, permissions


def rebind_source_authority(  # noqa: C901 - exact closed reconstruction stays auditable here.
    retained_manifest: Path,
    observation_cutoff: str,
    *,
    repository_root: Path = _ROOT,
) -> dict[str, object]:
    """Return one current, narrowed, canonicalizable authority document."""
    source = _verified_document(retained_manifest)
    if (
        source.get("scope") != "HK_V1_SOURCE_ADMISSION_PREFLIGHT"
        or source.get("provenance") != "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING"
        or _CUTOFF.fullmatch(observation_cutoff) is None
    ):
        _fail(_INPUT_INVALID)
    try:
        cutoff = datetime.fromisoformat(observation_cutoff)
    except ValueError as error:
        raise SourceAuthorityRebindError(_INPUT_INVALID) from error
    if cutoff.utcoffset() != timedelta(hours=8):
        _fail(_INPUT_INVALID)

    matrix = _verified_document(repository_root / _MATRIX, require_canonical=False)
    registers = {
        family: _verified_document(repository_root / relative, require_canonical=False)
        for family, relative in _REGISTERS.items()
    }
    permission_for, original_permissions = _permission_by_source(source)
    terms = {item.get("host"): item for item in _objects(source.get("terms"))}
    if any(type(host) is not str for host in terms):
        _fail(_INPUT_INVALID)

    selected: list[dict[str, object]] = []
    permission_facts: dict[str, dict[str, set[str]]] = {}
    required_hosts: set[str] = set()
    for family in ("CASES", "LEGISLATION"):
        sources = _source_map(registers[family])
        endpoints = _endpoint_map(registers[family])
        for source_id in sorted(_SELECTED[family]):
            registered = sources.get(source_id)
            permission_id = permission_for.get(source_id)
            if registered is None or permission_id not in original_permissions:
                _fail(_SCOPE_EXPANSION)
            endpoint_ids = _strings(registered.get("endpoint_ids"))
            claims = [_claim(endpoints[endpoint_id]) for endpoint_id in endpoint_ids]
            selected.append(
                {
                    "family": family,
                    "source_id": source_id,
                    "endpoints": claims,
                    "publisher_permission_id": permission_id,
                }
            )
            facts = permission_facts.setdefault(
                permission_id, {"source_ids": set(), "hosts": set(), "procedure_ids": set()}
            )
            facts["source_ids"].add(source_id)
            for claim in claims:
                facts["hosts"].add(cast("str", claim["host"]))
                facts["procedure_ids"].add(cast("str", claim["procedure_id"]))
                required_hosts.add(cast("str", claim["host"]))

    narrowed_permissions: list[dict[str, object]] = []
    for permission_id in sorted(permission_facts):
        facts = permission_facts[permission_id]
        narrowed_permissions.append(
            {
                "permission_id": permission_id,
                "source_ids": sorted(facts["source_ids"]),
                "hosts": sorted(facts["hosts"]),
                "procedure_ids": sorted(facts["procedure_ids"]),
                "reference": original_permissions[permission_id]["reference"],
            }
        )
    if required_hosts - set(cast("dict[str, object]", terms)):
        _fail(_TERMS_MISSING)

    register_bindings = [
        {
            "family": family,
            "register_id": registers[family]["register_id"],
            "register_version": registers[family]["register_version"],
            "fingerprint": registers[family]["fingerprint"],
        }
        for family in ("LEGISLATION", "CASES", "REGULATORY")
    ]
    source_fp = cast("str", source["fingerprint"])
    seed = _canonical(
        {
            "retained_authority": source_fp,
            "observation_cutoff": observation_cutoff,
            "matrix_fingerprint": matrix["fingerprint"],
            "registers": register_bindings,
        }
    )
    unsigned: dict[str, object] = {
        "schema_version": "1.0.0",
        "authority_id": "hka_" + hashlib.sha256(seed).hexdigest()[:48],
        "scope": "HK_V1_SOURCE_ADMISSION_PREFLIGHT",
        "provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "effective_date": source["effective_date"],
        "expires_on": source["expires_on"],
        "matrix": {"revision": matrix["revision"], "fingerprint": matrix["fingerprint"]},
        "registers": register_bindings,
        "selected_sources": selected,
        "publisher_permissions": narrowed_permissions,
        "user_reports": source["user_reports"],
        "terms": [terms[host] for host in sorted(required_hosts)],
        "observation_window": {
            "start": (cutoff - timedelta(days=1))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .isoformat(),
            "end": observation_cutoff,
            "cutoff": observation_cutoff,
            "timezone": "Asia/Hong_Kong",
        },
        "credentials": source["credentials"],
        "sessions": source["sessions"],
    }
    return {
        **unsigned,
        "fingerprint": f"sha256:{hashlib.sha256(_canonical(unsigned)).hexdigest()}",
    }


def publish_source_authority(document: dict[str, object], output: Path) -> bool:
    """Create or replay one exact local manifest; refuse overwrite and symlinks."""
    if not output.is_absolute() or output.is_symlink() or output.name in {"", ".", ".."}:
        _fail(_OUTPUT_INVALID)
    raw = _canonical(document)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output.exists():
        if output.is_file() and not output.is_symlink() and output.read_bytes() == raw:
            return True
        _fail(_OUTPUT_CONFLICT)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            temporary.chmod(0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
    except OSError as error:
        raise SourceAuthorityRebindError(_OUTPUT_INVALID) from error
    if output.read_bytes() != raw:
        _fail(_OUTPUT_READBACK)
    return False


def main() -> None:
    """Run the local-only rebind and emit one sanitized canonical report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-authority", required=True, type=Path)
    parser.add_argument("--observation-cutoff", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        document = rebind_source_authority(
            arguments.retained_authority.resolve(strict=True),
            arguments.observation_cutoff,
        )
        replayed = publish_source_authority(document, arguments.output)
    except (OSError, SourceAuthorityRebindError) as error:
        sys.stdout.write(_canonical({"result": "NOT_READY", "code": str(error)}).decode() + "\n")
        raise SystemExit(2) from None
    sys.stdout.write(
        _canonical(
            {
                "result": "READY",
                "authority_fingerprint": document["fingerprint"],
                "families": ["CASES", "LEGISLATION"],
                "replayed": replayed,
            }
        ).decode()
        + "\n"
    )


if __name__ == "__main__":
    main()
