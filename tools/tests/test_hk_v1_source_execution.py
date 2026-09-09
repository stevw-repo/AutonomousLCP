"""Authentic transport-bound source execution with deterministic local doubles."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import urllib.response
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from http.client import HTTPMessage
from io import BytesIO
from multiprocessing import get_context
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event as ProcessEvent
from pathlib import Path
from types import TracebackType
from typing import IO, TYPE_CHECKING, ClassVar, NoReturn, Self, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest
from asklegal_source_connectors import OfficialEndpointContract, basic_law_authentic
from asklegal_source_connectors.hkel_gazette import CAPABILITY_CLAIM

import tools.hk_v1_source_admission as admission
import tools.hk_v1_source_execution as execution
from tools.hk_v1_judiciary_policy import (
    execution_policy,
    execution_policy_fingerprint,
    recognized_execution_policy,
    retry_eligible,
)
from tools.hk_v1_source_admission import ExecutionAuthorization
from tools.hk_v1_source_execution import (
    CapturedResponse,
    HkelSessionCapture,
    HkelSessionStage,
    execute_source_family,
)
from tools.tests.hkex_role_aware_candidate import candidate_hkex_endpoints

if TYPE_CHECKING:
    from asklegal_source_connectors.hk_judiciary_authentic import JudiciaryYearResultPage

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_JUDICIARY_MAINTENANCE_BODY = (
    b'<HEAD>\n\t\t\t\t\t\t<SCRIPT language="JavaScript"> \n\t\t\t\t\t\t<!--\n'
    b"\t\t\t\t\t\tfunction redirectmaintenance()\n\t\t\t\t\t\t{\n"
    b'\t\t\t\t\t\ttop.location="http://www.judiciary.hk/maintenance";\n'
    b"\t\t\t\t\t\t}\n\t\t\t\t\t\tsetTimeout('redirectmaintenance()',0);\n"
    b"\t\t\t\t\t\t//--> \n\t\t\t\t\t\t</SCRIPT> \n\t\t\t\t\t\t</HEAD>"
)
_HISTORICAL_HKEL_FIXTURE = (
    REPOSITORY_ROOT / "tools/tests/fixtures/historical_hkel_basic_law_replay.json"
)
_HKEL_CONFIGURATION_ACTION = "https://www.elegislation.gov.hk/checkconfig/submitClientConfig.do"
_HKEL_CONFIGURATION_GET = (
    "https://www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?applicationId=RA001"
)
_HKEL_CLIENT_CHECK_URL = "https://www.elegislation.gov.hk/client-check?" + urlencode(
    CAPABILITY_CLAIM
)
_HKEL_CLIENT_CHECK_COORDINATE = "https://www.elegislation.gov.hk/client-check"
_HKEL_SESSION_GET_URLS = frozenset(
    {
        "https://www.elegislation.gov.hk/copyright",
        "https://www.elegislation.gov.hk/editorialrecord",
        "https://www.elegislation.gov.hk/importantnotices",
        "https://www.elegislation.gov.hk/terms",
    }
)
_BASIC_LAW_CONSTITUTION_ROOT = "https://www.basiclaw.gov.hk/en/constitution/index.html"
_BASIC_LAW_TEXT_ROOT = "https://www.basiclaw.gov.hk/en/basiclaw/index.html"
_BASIC_LAW_MEMBER_URLS = (
    "https://www.basiclaw.gov.hk/en/constitution/preamble.html",
    "https://www.basiclaw.gov.hk/en/constitution/chapter1.html",
    "https://www.basiclaw.gov.hk/en/constitution/chapter2.html",
    "https://www.basiclaw.gov.hk/en/constitution/chapter3.html",
    "https://www.basiclaw.gov.hk/en/constitution/chapter4.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/decree.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/preamble.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter1.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter2.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter3.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter4.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter5.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter6.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter7.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter8.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/chapter9.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/annex1.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/annex2.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/annex3.html",
    "https://www.basiclaw.gov.hk/en/basiclaw/annex-instrument.html",
)


def _basic_law_content_fixture(url: str) -> bytes:
    """Build independently labelled structural HTML for one exact content URL."""
    contract_path = Path(basic_law_authentic.__file__).with_name("basic_law_content_structure.json")
    identity = basic_law_authentic.read_basic_law_structure_contract(contract_path)[url]
    substantial_content = (
        "Synthetic autonomous content changes independently of the structural identity."
    )
    return (
        f"<!doctype html><html><head><title>{identity.title}</title></head>"
        f"<body><main>{substantial_content}</main></body></html>"
    ).encode()


def _install_synthetic_basic_law_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind the execution double's text-free structure without altering production data."""
    identities: dict[str, object] = {}
    for url in _BASIC_LAW_MEMBER_URLS:
        body = _basic_law_content_fixture(url)
        content = basic_law_authentic._ContentIdentityParser()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        content.feed(body.decode())
        title = " ".join(content.title_text)
        structure = basic_law_authentic._TextFreeStructureParser()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        structure.feed(body.decode())
        projection = basic_law_authentic._structure_projection(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            structure,
            url=url,
            title=title,
        )
        identities[url] = basic_law_authentic._BasicLawStructureIdentity(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            title,
            basic_law_authentic._sha256(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                basic_law_authentic._canonical_json(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                    projection
                )
            ),
        )
    monkeypatch.setattr(basic_law_authentic, "_default_structure_contract", lambda: identities)


def _synthetic_basic_law_contract_sitecustomize() -> str:
    """Install the matching synthetic structural contract in a CLI child."""
    return """import asklegal_source_connectors.basic_law_authentic as basic_law_authentic
from pathlib import Path

contract_path = Path(basic_law_authentic.__file__).with_name("basic_law_content_structure.json")
identities = {}
for url, identity in basic_law_authentic.read_basic_law_structure_contract(contract_path).items():
    body = (
        f"<!doctype html><html><head><title>{identity.title}</title></head>"
        "<body><main>Synthetic autonomous content changes independently "
        "of the structural identity.</main></body></html>"
    ).encode()
    content = basic_law_authentic._ContentIdentityParser()
    content.feed(body.decode())
    title = " ".join(content.title_text)
    structure = basic_law_authentic._TextFreeStructureParser()
    structure.feed(body.decode())
    projection = basic_law_authentic._structure_projection(structure, url=url, title=title)
    identities[url] = basic_law_authentic._BasicLawStructureIdentity(
        title,
        basic_law_authentic._sha256(basic_law_authentic._canonical_json(projection)),
    )
basic_law_authentic._default_structure_contract = lambda: identities
"""


_DUE_SOURCE_IDS = frozenset(
    {
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-CASE-HKLII-DISCOVERY",
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "HK-REG-HKEX-FEES-RULES",
        "HK-REG-HKEX-REGULATORY-FORMS",
        "HK-REG-HKEX-RULE-UPDATES",
        "HK-REG-HKEX-RULEBOOK-CATALOGUE",
    }
)


def _reference(label: str, *, scope: str) -> dict[str, object]:
    return {
        "vault": "PRIMARY",
        "logical_key": f"hk-v1/task-7/{label}",
        "version_id": "v" + "a" * 64,
        "fingerprint": "sha256:" + "a" * 64,
        "byte_length": 1,
        "publisher": "user-attested-publisher-authority-pending-document",
        "scope": scope,
        "effective_date": "1997-01-01",
        "expires_on": "NO_EXPIRY",
        "provenance": "USER_REPORTED",
    }


def _authority(tmp_path: Path, *, cutoff: str = "2026-08-27T22:52:09+08:00") -> Path:
    matrix_path = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    register_root = REPOSITORY_ROOT / "packages/source-connectors/src/asklegal_source_connectors"
    register_specs = (
        ("LEGISLATION", register_root / "hk_legislation_source_register.json"),
        ("CASES", register_root / "hk_cases_source_register.json"),
        ("REGULATORY", register_root / "hk_regulatory_source_register.json"),
    )
    matrix = cast("dict[str, object]", json.loads(matrix_path.read_bytes()))
    registers: list[dict[str, object]] = []
    selected_sources: list[dict[str, object]] = []
    permissions: list[dict[str, object]] = []
    terms_by_host: dict[str, dict[str, object]] = {}
    for family, register_path in register_specs:
        register = cast("dict[str, object]", json.loads(register_path.read_bytes()))
        registers.append(
            {
                "family": family,
                "register_id": register["register_id"],
                "register_version": register["register_version"],
                "fingerprint": register["fingerprint"],
            }
        )
        endpoints = {
            cast("str", item["endpoint_id"]): cast("dict[str, object]", item)
            for item in cast("list[object]", register["endpoints"])
            if type(item) is dict
        }
        for raw_source in cast("list[object]", register["sources"]):
            if type(raw_source) is not dict:
                continue
            source = cast("dict[str, object]", raw_source)
            source_id = cast("str", source["source_id"])
            if source_id not in _DUE_SOURCE_IDS:
                continue
            claims: list[dict[str, object]] = []
            for endpoint_id in cast("list[str]", source["endpoint_ids"]):
                endpoint = endpoints[endpoint_id]
                parsed = urlsplit(cast("str", endpoint["url"]))
                host = cast("str", parsed.hostname)
                claims.append(
                    {
                        "endpoint_id": endpoint_id,
                        "host": host,
                        "method": cast("list[str]", endpoint["methods"])[0],
                        "path": parsed.path + (f"?{parsed.query}" if parsed.query else ""),
                        "procedure_id": endpoint_id,
                        "redirect_policy": "NO_REDIRECT",
                    }
                )
                terms_by_host.setdefault(
                    host,
                    {
                        "host": host,
                        "state": "ALREADY_ACCEPTED_WITH_EVIDENCE",
                        "terms_reference": _reference(
                            f"{host}-terms", scope="PUBLISHER_TERMS_EVIDENCE"
                        ),
                        "acceptance_evidence": _reference(
                            f"{host}-terms-acceptance", scope="PUBLISHER_TERMS_EVIDENCE"
                        ),
                    },
                )
            permission_id = "pp_" + hashlib.sha256(source_id.encode()).hexdigest()
            selected_sources.append(
                {
                    "family": family,
                    "source_id": source_id,
                    "endpoints": claims,
                    "publisher_permission_id": permission_id,
                }
            )
            permissions.append(
                {
                    "permission_id": permission_id,
                    "source_ids": [source_id],
                    "hosts": sorted({cast("str", claim["host"]) for claim in claims}),
                    "procedure_ids": sorted(
                        {cast("str", claim["procedure_id"]) for claim in claims}
                    ),
                    "reference": _reference(
                        f"{source_id}-permission", scope="READ_ONLY_SOURCE_ADMISSION"
                    ),
                }
            )
    cutoff_time = datetime.fromisoformat(cutoff)
    document: dict[str, object] = {
        "schema_version": "1.0.0",
        "authority_id": "hka_000000000000000000000000000000000000000000000007",
        "scope": "HK_V1_SOURCE_ADMISSION_PREFLIGHT",
        "provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "effective_date": "1997-01-01",
        "expires_on": "NO_EXPIRY",
        "matrix": {"revision": matrix["revision"], "fingerprint": matrix["fingerprint"]},
        "registers": registers,
        "selected_sources": sorted(
            selected_sources, key=lambda item: cast("str", item["source_id"])
        ),
        "publisher_permissions": sorted(
            permissions, key=lambda item: cast("str", item["permission_id"])
        ),
        "user_reports": [
            {
                "report_id": "usr_000000000000000000000000000000000000000000000007",
                "reference": _reference("controller-ruling", scope="READ_ONLY_SOURCE_ADMISSION"),
            }
        ],
        "terms": [terms_by_host[host] for host in sorted(terms_by_host)],
        "observation_window": {
            "start": (cutoff_time - timedelta(days=1)).isoformat(),
            "end": cutoff,
            "cutoff": cutoff,
            "timezone": "Asia/Hong_Kong",
        },
        "credentials": [],
        "sessions": [],
    }
    document["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    path = tmp_path / "authority.json"
    path.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return path


def _replace_authority_identity(path: Path) -> str:
    """Create a second valid authority binding without changing its observation cutoff."""
    document = cast("dict[str, object]", json.loads(path.read_bytes()))
    document["authority_id"] = "hka_000000000000000000000000000000000000000000000008"
    document.pop("fingerprint")
    fingerprint = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    document["fingerprint"] = fingerprint
    path.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return fingerprint


def _replace_authority_identity_with_current_cases_register(path: Path) -> str:
    """Issue a synthetic child authority against current Matrix and Cases identities."""
    document = cast("dict[str, object]", json.loads(path.read_bytes()))
    matrix = cast(
        "dict[str, object]",
        json.loads(
            (
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ).read_bytes()
        ),
    )
    cases_register = cast(
        "dict[str, object]",
        json.loads(
            (
                REPOSITORY_ROOT
                / "packages/source-connectors/src/asklegal_source_connectors"
                / "hk_cases_source_register.json"
            ).read_bytes()
        ),
    )
    document["authority_id"] = "hka_000000000000000000000000000000000000000000000008"
    document["matrix"] = {
        "revision": matrix["revision"],
        "fingerprint": matrix["fingerprint"],
    }
    registers = cast("list[dict[str, object]]", document["registers"])
    cases_binding = next(item for item in registers if item["family"] == "CASES")
    for key in ("register_id", "register_version", "fingerprint"):
        cases_binding[key] = cases_register[key]
    document.pop("fingerprint")
    fingerprint = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    document["fingerprint"] = fingerprint
    path.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return fingerprint


def _historical_hkel_authority(
    tmp_path: Path, *, cutoff: str = "2026-08-27T22:52:09+08:00"
) -> Path:
    """Create the exact synthetic register-2026-08-28.2 HKEL transition binding."""
    path = _authority(tmp_path, cutoff=cutoff)
    document = cast("dict[str, object]", json.loads(path.read_bytes()))
    for raw_register in cast("list[object]", document["registers"]):
        register = cast("dict[str, object]", raw_register)
        if register["family"] == "LEGISLATION":
            register["register_version"] = "2026-08-28.2"
            register["fingerprint"] = (
                "sha256:4ab32818f0b273307503e28d7158cd877c52432ab0c7ca39eb7de4ad5a30160f"
            )
    current_content_ids = {f"sep_{value:048x}" for value in range(0x57, 0x69)}
    for raw_source in cast("list[object]", document["selected_sources"]):
        source = cast("dict[str, object]", raw_source)
        if source["source_id"] == "HK-LEG-BASIC-LAW-PORTAL":
            source["endpoints"] = [
                item
                for item in cast("list[dict[str, object]]", source["endpoints"])
                if item["endpoint_id"] not in current_content_ids
            ]
    for raw_permission in cast("list[object]", document["publisher_permissions"]):
        permission = cast("dict[str, object]", raw_permission)
        if permission["source_ids"] == ["HK-LEG-BASIC-LAW-PORTAL"]:
            permission["procedure_ids"] = [
                item
                for item in cast("list[str]", permission["procedure_ids"])
                if item not in current_content_ids
            ]
    document.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    path.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return path


def _install_tracked_historical_hkel_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, object]]:
    """Materialize the tracked inert old-writer fixture into one isolated test vault."""
    fixture = cast("dict[str, object]", json.loads(_HISTORICAL_HKEL_FIXTURE.read_bytes()))
    cutoff = cast("str", fixture["observation_cutoff"])
    authority = _historical_hkel_authority(tmp_path, cutoff=cutoff)
    authority_document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "tracked-historical-hkel"
    )
    endpoints: list[dict[str, object]] = []
    for raw_endpoint in cast("list[object]", fixture["endpoints"]):
        item = cast("dict[str, object]", raw_endpoint)
        body = cast("str", item["body_utf8"]).encode()
        fingerprint = "sha256:" + hashlib.sha256(body).hexdigest()
        object_key = f"objects/{fingerprint.removeprefix('sha256:')}.bin"
        object_path = output / object_key
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_bytes(body)
        endpoint = {
            "body_fingerprint": fingerprint,
            "byte_length": len(body),
            "endpoint_id": item["endpoint_id"],
            "endpoint_version": item["endpoint_version"],
            "media_type": item["media_type"],
            "method": item["method"],
            "object_key": object_key,
            "requested_url": item["requested_url"],
            "status": item["status"],
            "terminal_code": "CAPTURED",
        }
        if item["endpoint_id"] == "sep_000000000000000000000000000000000000000000000056":
            document = cast("dict[str, object]", json.loads(body))
            comparison = json.dumps(
                document["stable"], sort_keys=True, separators=(",", ":")
            ).encode()
            endpoint["comparison_fingerprint"] = "sha256:" + hashlib.sha256(comparison).hexdigest()
        endpoints.append(endpoint)
    report: dict[str, object] = {
        "attempt_id": fixture["attempt_id"],
        "authority_manifest_fingerprint": authority_document["fingerprint"],
        "authority_provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "change_state": "FIRST_OBSERVATION",
        "endpoint_counts": {"CAPTURED": len(endpoints)},
        "endpoints": endpoints,
        "observation_cutoff": cutoff,
        "predecessor_attempt_id": None,
        "readback_verified": True,
        "result": "EVIDENCE_CAPTURED_INCOMPLETE",
        "source_family": "HKEL",
        "source_procedures": fixture["source_procedures"],
    }
    report_path = output / "attempts" / cast("str", fixture["attempt_id"]) / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return authority, output, report


def _install_judiciary_attempt_a_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy the one retained Judiciary attempt A into a disposable replay vault."""
    authority = tmp_path / "judiciary-attempt-a-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-28-basic-law-20-attempt-b.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-a"
    )
    shutil.copytree(
        REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-a",
        output,
    )
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260828a/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_b_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy the immutable attempt-B contract-drift observation into a disposable vault."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-b-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-b.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-b"
    )
    shutil.copytree(
        REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-b",
        output,
    )
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830b/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_c_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy the immutable attempt-C broad-result observation into a disposable vault."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-c-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-c.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-c"
    )
    shutil.copytree(
        REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-c",
        output,
    )
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830c/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_d_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy the immutable attempt-D filtered-result observation into a disposable vault."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-d-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-d.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-d"
    )
    shutil.copytree(
        REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-d",
        output,
    )
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830d/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_e_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy the immutable attempt-E page-two observation into a disposable vault."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-e-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-e.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-e"
    )
    shutil.copytree(
        REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-e",
        output,
    )
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830e/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_f_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy immutable Attempt F into a disposable vault for exact replay tests."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-f-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-f.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-f"
    )
    shutil.copytree(
        REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-f",
        output,
    )
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830f/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_g_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy immutable Attempt G into a disposable vault for exact replay tests."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-g-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-g.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-g"
    )
    shutil.copytree(
        REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-g",
        output,
    )
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830g/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_h_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy immutable Attempt H into a disposable vault for exact replay tests."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-h-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-h.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-h"
    )
    shutil.copytree(REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-h", output)
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830h/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_i_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy immutable Attempt I into a disposable vault for exact replay tests."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-i-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-i.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-i"
    )
    shutil.copytree(REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-i", output)
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830i/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_j_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy immutable Attempt J into a disposable vault for exact replay tests."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-j-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-j.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-j"
    )
    shutil.copytree(REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-j", output)
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830j/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_k_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Copy immutable Attempt K into a disposable vault for exact replay tests."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / "judiciary-attempt-k-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-30-judiciary-attempt-k.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-k"
    )
    shutil.copytree(REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-k", output)
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260830k/report.json").read_bytes()
        ),
    )
    return authority, output, report


def _install_judiciary_attempt_fixture(
    tmp_path: Path, suffix: str
) -> tuple[Path, Path, dict[str, object]]:
    """Copy one frozen Judiciary attempt to a disposable replay root."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    authority = tmp_path / f"judiciary-attempt-{suffix}-authority.json"
    source_root = (
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / ("judiciary-attempt-p" if suffix in {"q", "s"} else f"judiciary-attempt-{suffix}")
    )
    date_fragment = "2026-08-31" if suffix in {"n", "o", "p", "q", "s"} else "2026-08-30"
    attempt_date = "20260831" if suffix in {"n", "o", "p", "q", "s"} else "20260830"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / f"authority-user-attested-live-{date_fragment}-judiciary-attempt-{suffix}.json",
        authority,
    )
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / f"judiciary-attempt-{suffix}"
    )

    def exclude_later_lineage(directory: str, names: list[str]) -> list[str]:
        if suffix not in {"p", "q", "s"}:
            return []
        if Path(directory).name == "attempts":
            allowed = {"judiciary-live-baseline-20260831p"}
            if suffix == "q":
                allowed.add("judiciary-live-baseline-20260831q")
            if suffix == "s":
                allowed.update(
                    {
                        "judiciary-live-baseline-20260831q",
                        "judiciary-live-baseline-20260831r",
                        "judiciary-live-baseline-20260831s",
                    }
                )
            return [name for name in names if name not in allowed]
        return []

    shutil.copytree(source_root, output, ignore=exclude_later_lineage)
    report = cast(
        "dict[str, object]",
        json.loads(
            (
                output / f"attempts/judiciary-live-baseline-{attempt_date}{suffix}/report.json"
            ).read_bytes()
        ),
    )
    return authority, output, report


def test_current_judiciary_form_107_maps_only_to_result_106() -> None:
    """Current aggregate overlap semantics advance without changing older mappings."""
    assert execution._judiciary_result_contract_version("1.0.5") == "1.0.4"  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    assert execution._judiciary_result_contract_version("1.0.6") == "1.0.5"  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    assert execution._judiciary_result_contract_version("1.0.7") == "1.0.6"  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    assert execution._judiciary_result_contract_version("1.0.8") == "1.0.7"  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    assert execution._judiciary_result_contract_version("1.0.9") == "1.0.8"  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    assert execution._judiciary_result_contract_version("1.0.10") == "1.0.9"  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    assert execution._judiciary_result_contract_version("1.0.11") == "1.0.10"  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    assert execution._judiciary_result_contract_version("1.0.12") == "1.0.11"  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    assert execution._judiciary_result_contract_version("1.0.13") == "1.0.12"  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def _mutated_hkel_authorization(
    authority: Path,
    output: Path,
    *,
    cutoff: str = "2026-08-27T22:52:09+08:00",
) -> ExecutionAuthorization:
    """Model an attacker-mutated current binding for the explicit rejection test."""
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    current = execution.authorize_execution(
        authority_manifest=authority,
        matrix=matrix,
        output_root=output,
        source_family="HKEL",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
    )
    current_only_basic_law = {
        *(
            url
            for url in _BASIC_LAW_MEMBER_URLS
            if url
            not in {
                "https://www.basiclaw.gov.hk/en/basiclaw/annex3.html",
                "https://www.basiclaw.gov.hk/en/basiclaw/annex-instrument.html",
            }
        ),
    }
    return replace(
        current,
        allowed_urls=tuple(
            url
            for url in current.allowed_urls
            if url != _HKEL_CLIENT_CHECK_URL and url not in current_only_basic_law
        ),
    )


def test_module_cli_execute_uses_canonical_authorization_without_network(
    tmp_path: Path,
) -> None:
    """The prescribed ``-m`` command reaches a terminal without split class identity."""
    cutoff = "2026-08-27T22:52:09+08:00"
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff=cutoff)
    terminal_fixture = execute_source_family(
        authority_manifest=authority,
        source_family="GLD",
        output_root=output,
        attempt_id="module-cli-terminal",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"", status=503),
    )
    assert terminal_fixture["result"] == "SOURCE_OUTAGE"
    probe = tmp_path / "external-opener-used"
    child_site = tmp_path / "child-site"
    child_site.mkdir()
    (child_site / "sitecustomize.py").write_text(
        """import os
import socket
import urllib.request
from pathlib import Path

def _deny_external_effect(*args, **kwargs):
    Path(os.environ["ASKLEGAL_FIX4_EXTERNAL_PROBE"]).write_text("attempted")
    raise AssertionError("external opener or network reached")

urllib.request.OpenerDirector.open = _deny_external_effect
socket.create_connection = _deny_external_effect
socket.getaddrinfo = _deny_external_effect
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(child_site)
        if not existing_pythonpath
        else os.pathsep.join((str(child_site), existing_pythonpath))
    )
    environment["ASKLEGAL_FIX4_EXTERNAL_PROBE"] = str(probe)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.hk_v1_source_admission",
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "GLD",
            "--attempt-id",
            "module-cli-terminal",
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 1
    assert result.stderr == b""
    report = cast("dict[str, object]", json.loads(result.stdout))
    assert report["result"] == "SOURCE_OUTAGE"
    assert report["readback_verified"] is True
    assert not probe.exists()


def test_module_cli_fresh_terminal_closes_session_and_exits_promptly_offline(
    tmp_path: Path,
) -> None:
    """A fresh bounded ``python -m`` run writes its report, closes, and needs no signal."""
    cutoff = "2026-08-27T22:52:09+08:00"
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "fresh-process"
    )
    authority = _authority(tmp_path, cutoff=cutoff)
    close_probe = tmp_path / "transport-closed"
    child_site = tmp_path / "fresh-child-site"
    child_site.mkdir()
    (child_site / "sitecustomize.py").write_text(
        """import http.cookiejar
import os
import urllib.error
import urllib.request
from pathlib import Path

_clear = http.cookiejar.CookieJar.clear

def _offline(*args, **kwargs):
    raise urllib.error.URLError("deterministic offline transport")

def _observed_clear(self, domain=None, path=None, name=None):
    Path(os.environ["ASKLEGAL_FIX5_CLOSE_PROBE"]).write_text("closed")
    return _clear(self, domain, path, name)

urllib.request.OpenerDirector.open = _offline
http.cookiejar.CookieJar.clear = _observed_clear
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(child_site)
        if not existing_pythonpath
        else os.pathsep.join((str(child_site), existing_pythonpath))
    )
    environment["ASKLEGAL_FIX5_CLOSE_PROBE"] = str(close_probe)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    started = time.monotonic()

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.hk_v1_source_admission",
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "HKEL",
            "--attempt-id",
            "module-cli-fresh-terminal",
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=10,
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 1
    assert result.stderr == b""
    report = cast("dict[str, object]", json.loads(result.stdout))
    assert report["result"] == "SOURCE_OUTAGE"
    assert report["readback_verified"] is True
    assert close_probe.read_text() == "closed"
    assert elapsed < 5
    retained = cast(
        "dict[str, object]",
        json.loads((output / "attempts/module-cli-fresh-terminal/report.json").read_bytes()),
    )
    assert retained == report


def test_archive_accounting_releases_full_bodies_before_source_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only ZIP signatures survive immutable write/readback into parser accounting."""

    class BoundedArchiveTransport(_ConfiguredHkelTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if url.endswith(".zip"):
                body = b"PK\x03\x04" + b"x" * 262_144
                return CapturedResponse(200, "application/zip", body[: max_bytes + 1], url)
            return super().get(url=url, max_bytes=max_bytes)

    original = cast(
        "Callable[[str, dict[str, bytes], dict[str, str]], list[dict[str, object]]]",
        execution.__dict__["_source_procedures"],
    )
    observed = False

    def inspect_bodies(
        source_family: str, bodies: dict[str, bytes], terminals: dict[str, str]
    ) -> list[dict[str, object]]:
        nonlocal observed
        if source_family == "HKEL":
            observed = True
            assert all(len(bodies[f"sep_{value:048x}"]) == 4 for value in range(0xA, 0x16))
        return original(source_family, bodies, terminals)

    monkeypatch.setattr(execution, "_source_procedures", inspect_bodies)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "archive-release"
    )

    report = execute_source_family(
        authority_manifest=_authority(tmp_path),
        source_family="HKEL",
        output_root=output,
        attempt_id="archive-release",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=BoundedArchiveTransport(),
    )

    assert observed
    assert report["readback_verified"] is True


def test_forged_authorization_lookalike_fails_before_transport(
    tmp_path: Path,
) -> None:
    """Matching fields cannot substitute for the canonical authorization class."""

    @dataclass(frozen=True, slots=True)
    class ForgedAuthorization:
        authority_manifest_fingerprint: str
        source_family: str
        source_ids: tuple[str, ...]
        observation_cutoff: str
        allowed_urls: tuple[str, ...]

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    canonical = execution.authorize_execution(
        authority_manifest=authority,
        matrix=matrix,
        output_root=output,
        source_family="GLD",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
    )
    forged = ForgedAuthorization(
        canonical.authority_manifest_fingerprint,
        canonical.source_family,
        canonical.source_ids,
        canonical.observation_cutoff,
        canonical.allowed_urls,
    )
    transport = TransportProbe()

    with pytest.raises(ValueError, match="EXECUTION_AUTHORIZATION_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="GLD",
            output_root=output,
            attempt_id="forged-authorization",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=transport,
            authorization=cast("ExecutionAuthorization", forged),
            matrix_path=matrix,
        )

    assert transport.calls == 0


@dataclass
class _Transport:
    body: bytes
    status: int = 200

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        body = self.body
        final_url: str | None = None
        if url == ("https://legalref.judiciary.hk/lrs/common/index.jsp?target=newjudgments&lan=en"):
            final_url = "https://legalref.judiciary.hk/lrs/common/ju/newjudgments.jsp"
        if self.status == 200 and len(body) <= max_bytes:
            if "isadvsearch=1" in url and "year=" not in url:
                body = b"""<form method="get" action="search_result_form.jsp">
                  <select name="database"><option value="JU">JU</option></select>
                  <select name="court"><option value="FA">FA</option><option value="CA">CA</option>
                  <option value="HC">HC</option><option value="CT">CT</option>
                  <option value="DC">DC</option><option value="FC">FC</option>
                  <option value="LD">LD</option><option value="OT">OT</option></select>
                  <input name="txtSearch3"><input name="year"><input name="page">
                </form>"""
            elif "year=" in url:
                body = b"<p>0 results / 1 pages</p>"
        return CapturedResponse(
            status=self.status,
            media_type="text/html",
            body=body[: max_bytes + 1],
            final_url=final_url,
        )


class _FakeHTTPResponse:
    """Minimal context-managed urllib response with bounded read behavior."""

    def __init__(
        self,
        body: bytes,
        *,
        url: str,
        status: int = 200,
        media_type: str = "text/html",
    ) -> None:
        self._body = body
        self.url = url
        self.status = status
        self.headers = HTTPMessage()
        self.headers["Content-Type"] = media_type

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


class _FakeOpener:
    """Controlled no-network opener for the real urllib transport composition."""

    def __init__(
        self,
        *,
        get_body: bytes,
        post_body: bytes | None = None,
        post_status: int = 200,
    ) -> None:
        self.get_body = get_body
        self.post_body = get_body if post_body is None else post_body
        self.post_status = post_status
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, *, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 30
        self.requests.append(request)
        if request.method == "POST":
            return _FakeHTTPResponse(
                self.post_body,
                url=request.full_url,
                status=self.post_status,
            )
        final_url = (
            _HKEL_CONFIGURATION_GET
            if request.full_url == "https://www.elegislation.gov.hk/terms"
            else request.full_url
        )
        return _FakeHTTPResponse(self.get_body, url=final_url)


def _fake_opener_factory(opener: _FakeOpener) -> Callable[..., _FakeOpener]:
    """Return a fully typed build_opener replacement for strict test checking."""

    def build(*_handlers: object) -> _FakeOpener:
        return opener

    return build


class _RedirectingHttpsHandler(urllib.request.BaseHandler):
    """No-network HTTPS handler that still exercises urllib's redirect machinery."""

    handler_order = 100

    def __init__(
        self,
        *,
        redirect_target: str,
        post_redirect_target: str | None = None,
        post_redirect_status: int = 302,
        post_followup_redirect_target: str | None = None,
    ) -> None:
        self.redirect_target = redirect_target
        self.post_redirect_target = post_redirect_target
        self.post_redirect_status = post_redirect_status
        self.post_followup_redirect_target = post_followup_redirect_target
        self.requests: list[tuple[str, str]] = []
        self.config_get_count = 0

    def https_open(self, request: urllib.request.Request) -> urllib.response.addinfourl:
        method = request.get_method()
        self.requests.append((method, request.full_url))
        headers = HTTPMessage()
        status = 200
        body = b"configured"
        if request.full_url == "https://www.elegislation.gov.hk/terms":
            status = 302
            headers["Location"] = self.redirect_target
            body = b"redirect"
        elif request.full_url == _HKEL_CONFIGURATION_GET:
            self.config_get_count += 1
            if self.config_get_count > 1 and self.post_followup_redirect_target is not None:
                status = 302
                headers["Location"] = self.post_followup_redirect_target
                body = b"redirect"
            else:
                body = _HKEL_CONFIGURATION_FORM
        elif request.full_url == _HKEL_CONFIGURATION_ACTION and method == "POST":
            if self.post_redirect_target is not None:
                status = self.post_redirect_status
                headers["Location"] = self.post_redirect_target
                body = b"redirect"
        elif request.full_url != _HKEL_CONFIGURATION_ACTION:
            raise AssertionError((method, request.full_url))
        headers["Content-Type"] = "text/html"
        response = _RedirectResponse(BytesIO(body), headers, request.full_url, status)
        response.msg = "Found" if status == 302 else "OK"
        return response


class _RedirectResponse(urllib.response.addinfourl):
    """Typed urllib test response carrying the error-processor reason field."""

    msg: str


@pytest.mark.parametrize(
    "target",
    [
        "https://legalref.judiciary.hk/lrs/common/ju/newjudgments.jsp",
        "https://legalref.judiciary.hk/lrs/common/ju/newjudgments.jsp?x=1",
        "http://legalref.judiciary.hk/lrs/common/ju/newjudgments.jsp",
        "https://legalref.judiciary.hk:444/lrs/common/ju/newjudgments.jsp",
        "https://evil.example/lrs/common/ju/newjudgments.jsp",
        "https://legalref.judiciary.hk/lrs/common/ju/%2e%2e/newjudgments.jsp",
    ],
)
def test_judiciary_redirect_handler_allows_only_the_exact_session_transition(target: str) -> None:
    """Changing target/query/scheme/port/host/path must fail before a follow-up request."""
    entry = "https://legalref.judiciary.hk/lrs/common/index.jsp?target=newjudgments&lan=en"
    final = "https://legalref.judiciary.hk/lrs/common/ju/newjudgments.jsp"
    handler = _confining_redirect_handler(frozenset({entry, final}))
    request = urllib.request.Request(entry, method="GET")
    headers = HTTPMessage()
    response = _RedirectResponse(BytesIO(b"redirect"), headers, entry, 302)

    if target == final:
        redirected = handler.redirect_request(request, response, 302, "Found", headers, target)
        assert redirected is not None
        assert redirected.full_url == final
        assert redirected.get_method() == "GET"
    else:
        with pytest.raises(urllib.error.HTTPError, match="REDIRECT_NOT_ADMITTED"):
            handler.redirect_request(request, response, 302, "Found", headers, target)


def _real_opener_factory(
    opener: urllib.request.OpenerDirector,
) -> Callable[..., urllib.request.OpenerDirector]:
    """Return a typed build_opener replacement around a real no-network director."""

    def build(*_handlers: object) -> urllib.request.OpenerDirector:
        return opener

    return build


def _confining_redirect_handler(
    allowed_urls: frozenset[str],
) -> urllib.request.HTTPRedirectHandler:
    """Construct the private production boundary without a private static reference."""
    factory = cast(
        "Callable[[frozenset[str]], urllib.request.HTTPRedirectHandler]",
        execution.__dict__["_ConfiningRedirectHandler"],
    )
    return factory(allowed_urls)


_HKEL_CONFIGURATION_FORM = b"""<form method="post" action="/checkconfig/submitClientConfig.do">
<input type="hidden" name="applicationId" value="RA001">
<input type="hidden" name="branchCode" value="hkel">
<input type="hidden" name="jvmVendor" value="publisher-vendor">
<input type="hidden" name="jvmVersion" value="publisher-version">
<input type="hidden" name="javascriptEnabled" value="false">
<input type="hidden" name="cookieEnabled" value="false">
<input type="hidden" name="appletLoadFailed" value="false">
<input type="hidden" name="isIpv4Verified" value="false">
<input type="hidden" name="isIpv6Verified" value="true">
<input type="hidden" name="language" value="en">
<input type="hidden" name="country" value="HK">
<input type="hidden" name="_CSRF_TOKEN" value="short-lived-site-token">
</form>"""
_HKEL_LIST_URLS = (
    "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_en.xml",
    "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_zh-Hant.xml",
    "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_zh-Hans.xml",
    "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_en.json",
    "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_zh-Hant.json",
    "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_zh-Hans.json",
)
_HKEL_DATA_URLS = (
    "https://resource.data.one.gov.hk/doj/data/hkel_c_leg_cap_1_cap_300_en.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_leg_cap_301_cap_600_en.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_leg_cap_601_cap_end_en.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_instruments_en.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_leg_cap_1_cap_300_zh-Hant.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_leg_cap_301_cap_600_zh-Hant.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_leg_cap_601_cap_end_zh-Hant.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_instruments_zh-Hant.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_leg_cap_1_cap_300_zh-Hans.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_leg_cap_301_cap_600_zh-Hans.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_leg_cap_601_cap_end_zh-Hans.zip",
    "https://resource.data.one.gov.hk/doj/data/hkel_c_instruments_zh-Hans.zip",
)


class _ConfiguredHkelTransport:
    """Serve source-shaped DATA.GOV, Basic Law, and configured HKeL session bytes."""

    def __init__(self) -> None:
        self.configured = False
        self.urls: list[str] = []

    def configure_hkel_session(self, *, url: str, max_bytes: int) -> HkelSessionCapture:
        assert max_bytes > 0
        self.urls.append(url)
        self.configured = True
        if url == _HKEL_CLIENT_CHECK_URL:
            return HkelSessionCapture(
                HkelSessionStage(
                    "CONFIG_GET",
                    "NOT_ATTEMPTED",
                    0,
                    "application/octet-stream",
                    None,
                    0,
                    attempted=False,
                ),
                HkelSessionStage(
                    "CONFIG_PARSE",
                    "NOT_ATTEMPTED",
                    0,
                    "application/octet-stream",
                    None,
                    0,
                    attempted=False,
                ),
                HkelSessionStage(
                    "CONFIG_POST",
                    "NOT_ATTEMPTED",
                    0,
                    "application/octet-stream",
                    None,
                    0,
                    attempted=False,
                ),
                HkelSessionStage(
                    "CAPABILITY_GET",
                    "CAPTURED",
                    200,
                    "text/html",
                    _HKEL_CLIENT_CHECK_URL,
                    349,
                ),
            )
        return HkelSessionCapture(
            HkelSessionStage(
                "CONFIG_GET", "CAPTURED", 200, "text/html", _HKEL_CONFIGURATION_GET, 400
            ),
            HkelSessionStage(
                "CONFIG_PARSE",
                "CAPTURED",
                200,
                "text/html",
                _HKEL_CONFIGURATION_GET,
                400,
                configuration_action=_HKEL_CONFIGURATION_ACTION,
                configuration_field_count=12,
                anti_forgery_control_present=True,
            ),
            HkelSessionStage(
                "CONFIG_POST",
                "CAPTURED",
                200,
                "text/html",
                _HKEL_CONFIGURATION_ACTION,
                57,
            ),
        )

    def get(  # noqa: C901, PLR0912 - one deterministic double serves every fixture role.
        self, *, url: str, max_bytes: int
    ) -> CapturedResponse:
        self.urls.append(url)
        if "package_show?id=hk-doj-hkel-list" in url:
            body = json.dumps(
                {
                    "success": True,
                    "result": {
                        "name": "hk-doj-hkel-list-of-legislation-current",
                        "resources": [{"url": item} for item in _HKEL_LIST_URLS],
                    },
                }
            ).encode()
        elif "package_show?id=hk-doj-hkel-legislation-current" in url:
            body = json.dumps(
                {
                    "success": True,
                    "result": {
                        "name": "hk-doj-hkel-legislation-current",
                        "resources": [{"url": item} for item in _HKEL_DATA_URLS],
                    },
                }
            ).encode()
        elif url.endswith(("hkel_list_c_all_en.xml", "hkel_list_c_all_zh-Hant.xml")):
            language = "zh-Hant" if url.endswith("zh-Hant.xml") else "en"
            body = (
                f'<Listing lang="{language}" pointOfTime="c" legislationType="ALL">'
                "<Chapter><CapNo>1</CapNo></Chapter></Listing>"
            ).encode()
        elif url.endswith(".zip"):
            body = b"PK\x03\x04authentic current-data archive"
        elif url.endswith(".pdf"):
            body = b"%PDF-1.7\nauthentic specification"
        elif url.endswith("/en/index/index.html"):
            body = (
                b'<a href="../constitution/index.html">Constitution</a>'
                b'<a href="../basiclaw/index.html">Basic Law</a>'
            )
        elif url == _BASIC_LAW_CONSTITUTION_ROOT:
            body = b"".join(
                f'<a href="{member.rsplit("/", 1)[-1]}">member</a>'.encode()
                for member in _BASIC_LAW_MEMBER_URLS[:5]
            )
        elif url == _BASIC_LAW_TEXT_ROOT:
            body = b"".join(
                f'<a href="{member.rsplit("/", 1)[-1]}">member</a>'.encode()
                for member in _BASIC_LAW_MEMBER_URLS[5:]
            )
        elif url in _BASIC_LAW_MEMBER_URLS:
            body = _basic_law_content_fixture(url)
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], url)
        elif "basiclaw.gov.hk" in url:
            body = b"<html>official Basic Law portal page</html>"
        elif url.endswith("/copyright"):
            if not self.configured:
                return CapturedResponse(403, "text/html", b"", url)
            body = (
                b"Copyright Policy April 2026 mass replication product/database reproduction "
                b"attribution version non-endorsement indemnity third-party rights"
            )
        elif url.endswith("/terms"):
            body = b"Terms of Use last reviewed April 2026 automatic extraction"
        elif (
            "elegislation.gov.hk" in url
            and not self.configured
            and url.endswith(("/editorialrecord", "/importantnotices"))
        ):
            return CapturedResponse(403, "text/html", b"", url)
        else:
            body = b"<html>configured official source artifact</html>"
        return CapturedResponse(200, "application/octet-stream", body[: max_bytes + 1], url)


class _DirectConfiguredHkelTransport(_ConfiguredHkelTransport):
    """Serve the current direct capability check and remember only request locators."""

    def configure_hkel_session(self, *, url: str, max_bytes: int) -> HkelSessionCapture:
        assert url == _HKEL_CLIENT_CHECK_URL
        assert max_bytes > 0
        self.urls.append(url)
        self.configured = True
        return HkelSessionCapture(
            HkelSessionStage(
                "CONFIG_GET",
                "NOT_ATTEMPTED",
                0,
                "application/octet-stream",
                None,
                0,
                attempted=False,
            ),
            HkelSessionStage(
                "CONFIG_PARSE",
                "NOT_ATTEMPTED",
                0,
                "application/octet-stream",
                None,
                0,
                attempted=False,
            ),
            HkelSessionStage(
                "CONFIG_POST",
                "NOT_ATTEMPTED",
                0,
                "application/octet-stream",
                None,
                0,
                attempted=False,
            ),
            HkelSessionStage(
                "CAPABILITY_GET",
                "CAPTURED",
                200,
                "text/html",
                _HKEL_CLIENT_CHECK_URL,
                349,
            ),
        )


def _current_judiciary_form_body() -> bytes:
    day_options = "".join(
        ['<option value="" selected></option>']
        + [f'<option value="{value}"></option>' for value in range(32)]
    )
    month_options = "".join(
        ['<option value="" selected></option>']
        + [f'<option value="{value}"></option>' for value in range(13)]
    )
    courts = "".join(
        f'<option value="{code}" selected>{code}</option>'
        for code in ("FA", "CA", "HC", "CT", "DC", "FC", "LD", "OT")
    )
    return f"""<form name="frm_search" id="frm_search" method="get" action=""
      onsubmit="javascript:return FORM_SUBMIT(this);">
      <input type="hidden" name="isadvsearch" value="1">
      <input type="checkbox" name="stem" value="1" checked>
      <input type="hidden" name="txtselectopt3" value="5">
      <input type="checkbox" name="selall2" value="1" checked>
      <input type="checkbox" name="selallct" value="1" checked>
      <select name="selDatabase2" multiple="" multiple>
        <option value="JU" selected>JU</option><option value="RV" selected>RV</option>
        <option value="RS" selected>RS</option><option value="PD" selected>PD</option>
      </select>
      <select name="selSchct" multiple="" multiple>{courts}</select>
      <input type="hidden" name="txtSearch3" value="">
      <select name="day1">{day_options}</select>
      <select name="month">{month_options}</select>
      <select name="year"><option value="" selected></option><option value="0"></option></select>
    </form>
    <form method="post" action="later-submit.jsp"><input name="page"></form>
    <form method="post" action="other-submit.jsp"><input name="database"></form>""".encode()


def _current_judiciary_result_body(
    *, year: int, reported_pages: int, rows: tuple[tuple[int, str], ...]
) -> bytes:
    return _current_judiciary_paginated_result_body(
        year=year,
        page=1,
        reported_results=len(rows),
        reported_pages=reported_pages,
        rows=rows,
    )


def _current_judiciary_paginated_result_body(  # noqa: PLR0913 - exact page fixture fields.
    *,
    year: int,
    page: int,
    reported_results: int,
    reported_pages: int,
    rows: tuple[tuple[int, str], ...],
    row_types: dict[int, str] | None = None,
    optional_frame_ids: frozenset[int] = frozenset(),
) -> bytes:
    assert all(decision_date.endswith(f"/{year}") for _dis_id, decision_date in rows), year
    rendered: list[str] = []
    for dis_id, decision_date in rows:
        result_type = (row_types or {}).get(dis_id, "JU")
        strict_class_shape = result_type in {"RS", "RV"}
        first_class = ' class="searchfont result-caseno"' if strict_class_shape else ""
        second_class = " class=searchfont" if strict_class_shape else ""
        optional_frame = (
            '<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
            f'AH=S&DIS={dis_id}&QS=%2B&TP={result_type}" '
            'target="_top" class=default >frame</a>'
            if dis_id in optional_frame_ids
            else ""
        )
        rendered.append(
            "<tr><td>n</td><td>"
            f"<script>var temp{dis_id}='DIS={dis_id}&QS=%2B&TP={result_type}';</script>"
            f"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'+temp{dis_id});\""
            f"{first_class}>entry</a>"
            f"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'+temp{dis_id});\""
            f"{second_class}>entry</a>{optional_frame}</td><td>{decision_date}</td></tr>"
        )
    rendered_rows = "".join(rendered)
    next_link = (
        f"<a href=\"javascript:pagesubmit('{page + 1}',this.form)\">next</a>"
        if page < reported_pages
        else ""
    )
    post_page_control = f'<input type="hidden" name="page" value="{page}">' if page > 1 else ""
    return (
        '<form name="frm_search" id="frm_search" method="get" action="" '
        'onsubmit="javascript:return FORM_SUBMIT(this);">'
        '<select name="selSchct" multiple="" multiple></select>'
        '<select name="selDatabase2" multiple="" multiple></select>'
        f'<span id="searchresult-total">{reported_results}</span>'
        f'<span id="searchresult-totalpages">{reported_pages}</span>'
        f'<input type="hidden" name="page" value="{page}">'
        f'{next_link}<table id="table">{rendered_rows}</table>{next_link}</form>'
        f'<form method="post" name="org_value" action="">{post_page_control}</form>'
        f'<form method="post" name="org_value" action="">{post_page_control}</form>'
    ).encode()


def _attempt_s_direct_word_result_body() -> bytes:
    """Project Attempt S's direct-Word shape onto the small current result fixture."""
    original = (
        b"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'+temp2);\">entry</a>"
        b"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'+temp2);\">entry</a>"
    )
    replacement = (
        b"<a href=\"javascript:judpop1('/doc/judg/word/vetted/other/en/1997/sanitized.doc');\">"
        b"entry</a>"
        b'<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
        b'AH=S&DIS=2&QS=%2B&TP=JU" target="_top" class=default >frame</a>'
    )
    body = _current_judiciary_paginated_result_body(
        year=1997,
        page=1,
        reported_results=2,
        reported_pages=1,
        rows=((2, "01/07/1997"), (3, "02/07/1997")),
    )
    assert body.count(original) == 1
    return body.replace(original, replacement, 1)


class _JudiciaryTransport:
    """Serve one complete two-year baseline through exact generated GET locators."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        self.urls.append(url)
        if url == ("https://legalref.judiciary.hk/lrs/common/index.jsp?target=newjudgments&lan=en"):
            body = b"<html>current signal through session entry</html>"
            return CapturedResponse(
                200,
                "text/html",
                body[: max_bytes + 1],
                "https://legalref.judiciary.hk/lrs/common/ju/newjudgments.jsp",
            )
        if "isadvsearch=1" in url and "year=" not in url:
            body = _current_judiciary_form_body()
        elif "year=1997" in url:
            body = (
                _current_judiciary_result_body(
                    year=1997,
                    reported_pages=1,
                    rows=((1, "30/06/1997"), (2, "01/07/1997")),
                )
                if "txtselectopt3=5&day1=&month=" in url
                else b"<html>year controls missing</html>"
            )
        elif "year=1998" in url:
            body = (
                _current_judiciary_result_body(
                    year=1998,
                    reported_pages=1,
                    rows=((3, "02/01/1998"),),
                )
                if "txtselectopt3=5&day1=&month=" in url
                else b"<html>year controls missing</html>"
            )
        elif "DIS=" in url:
            body = b"<html><main>full inert judgment body</main></html>"
        else:
            body = b"<html>current signal</html>"
        return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)


class _JudiciaryContractChangedTransport(_JudiciaryTransport):
    """Expose a reachable but contract-invalid result page."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=" in url:
            body = b"<html>publisher changed the result contract</html>"
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryUnsupportedPaginationTransport(_JudiciaryTransport):
    """Advertise a second page without claiming a publisher query grammar for it."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            body = _current_judiciary_result_body(
                year=1997,
                reported_pages=2,
                rows=((2, "01/07/1997"),),
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciarySequentialPaginationTransport(_JudiciaryTransport):
    """Serve two retained pages before accepting any derived judgment locator."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            if "&page=2" in url:
                body = _current_judiciary_paginated_result_body(
                    year=1997,
                    page=2,
                    reported_results=11,
                    reported_pages=2,
                    rows=((1011, "11/07/1997"),),
                )
            else:
                body = _current_judiciary_paginated_result_body(
                    year=1997,
                    page=1,
                    reported_results=11,
                    reported_pages=2,
                    rows=tuple((1000 + day, f"{day:02d}/07/1997") for day in range(1, 11)),
                )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryBoundaryOverlapTransport(_JudiciaryTransport):
    """Serve one exact last-row/first-row overlap and count every detail effect."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            rows = (
                ((1010, "10/07/1997"),)
                if "&page=2" in url
                else tuple((1000 + day, f"{day:02d}/07/1997") for day in range(1, 11))
            )
            body = _current_judiciary_paginated_result_body(
                year=1997,
                page=2 if "&page=2" in url else 1,
                reported_results=11,
                reported_pages=2,
                rows=rows,
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryIdentityRepeatTransport(_JudiciaryTransport):
    """Serve stable same-page/interior/triplicate repeats in both listing passes."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            body = _current_judiciary_result_body(
                year=1997,
                reported_pages=1,
                rows=(
                    (2, "01/07/1997"),
                    (2, "01/07/1997"),
                    (3, "02/07/1997"),
                    (2, "01/07/1997"),
                    (4, "03/07/1997"),
                ),
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryRsTransport(_JudiciaryTransport):
    """Serve one stable exact RS row in both passes."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            body = _current_judiciary_paginated_result_body(
                year=1997,
                page=1,
                reported_results=2,
                reported_pages=1,
                rows=((2, "01/07/1997"), (3, "02/07/1997")),
                row_types={2: "RS"},
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryRsSecondPassFlipTransport(_JudiciaryRsTransport):
    """Change one RS locator to JU only in the verification pass."""

    def __init__(self, *, out_of_scope: bool = False) -> None:
        super().__init__()
        self.year_requests = 0
        self.out_of_scope = out_of_scope

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            self.year_requests += 1
            body = _current_judiciary_paginated_result_body(
                year=1997,
                page=1,
                reported_results=2,
                reported_pages=1,
                rows=(
                    (2, "30/06/1997" if self.out_of_scope else "01/07/1997"),
                    (3, "02/07/1997"),
                ),
                row_types={2: "RS"} if self.year_requests == 1 else None,
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryRvTransport(_JudiciaryTransport):
    """Serve one stable exact RV row in both passes."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            body = _current_judiciary_paginated_result_body(
                year=1997,
                page=1,
                reported_results=2,
                reported_pages=1,
                rows=((2, "01/07/1997"), (3, "02/07/1997")),
                row_types={2: "RV"},
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryTypedOptionalFrameTransport(_JudiciaryTransport):
    """Serve stable exact RS and RV third frames in both listing passes."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            body = _current_judiciary_paginated_result_body(
                year=1997,
                page=1,
                reported_results=2,
                reported_pages=1,
                rows=((2, "01/07/1997"), (4, "02/07/1997")),
                row_types={2: "RS", 4: "RV"},
                optional_frame_ids=frozenset({2, 4}),
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryAttemptSDirectWordTransport(_JudiciaryTransport):
    """Serve one stable direct-Word row while retaining only the canonical detail effect."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            return CapturedResponse(200, "text/html", _attempt_s_direct_word_result_body(), None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryRvSecondPassFlipTransport(_JudiciaryRvTransport):
    """Change one RV locator to JU only in the verification pass."""

    def __init__(self, *, out_of_scope: bool = False) -> None:
        super().__init__()
        self.year_requests = 0
        self.out_of_scope = out_of_scope

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            self.year_requests += 1
            body = _current_judiciary_paginated_result_body(
                year=1997,
                page=1,
                reported_results=2,
                reported_pages=1,
                rows=(
                    (2, "30/06/1997" if self.out_of_scope else "01/07/1997"),
                    (3, "02/07/1997"),
                ),
                row_types={2: "RV"} if self.year_requests == 1 else None,
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciarySecondPassAccountingDriftTransport(_JudiciaryTransport):
    """Keep the unique map stable while changing raw/reported duplicate slots."""

    def __init__(self) -> None:
        super().__init__()
        self.year_requests = 0

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            self.year_requests += 1
            rows = (
                (
                    (2, "01/07/1997"),
                    (2, "01/07/1997"),
                    (3, "02/07/1997"),
                    (4, "03/07/1997"),
                )
                if self.year_requests == 1
                else (
                    (2, "01/07/1997"),
                    (2, "01/07/1997"),
                    (3, "02/07/1997"),
                    (2, "01/07/1997"),
                    (4, "03/07/1997"),
                )
            )
            body = _current_judiciary_result_body(
                year=1997,
                reported_pages=1,
                rows=rows,
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciarySecondPassPageCountDriftTransport(_JudiciaryTransport):
    """Keep the unique map stable while adding one repeated slot and page."""

    def __init__(self) -> None:
        super().__init__()
        self.year_requests = 0

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            self.year_requests += 1
            base_rows = tuple((1000 + day, f"{day:02d}/07/1997") for day in range(1, 11))
            verification = self.year_requests > 1
            page = 2 if "&page=2" in url else 1
            body = _current_judiciary_paginated_result_body(
                year=1997,
                page=page,
                reported_results=11 if verification else 10,
                reported_pages=2 if verification else 1,
                rows=((1010, "10/07/1997"),) if page == 2 else base_rows,
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciarySecondPassDriftTransport(_JudiciarySequentialPaginationTransport):
    """Change one valid identity only when the verification pass reaches page two."""

    def __init__(self) -> None:
        super().__init__()
        self.year_requests = 0

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.year_requests += 1
            if self.year_requests == 4:
                self.urls.append(url)
                body = _current_judiciary_paginated_result_body(
                    year=1997,
                    page=2,
                    reported_results=11,
                    reported_pages=2,
                    rows=((1012, "11/07/1997"),),
                )
                return CapturedResponse(200, "text/html", body[: max_bytes + 1], url)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciarySecondPassParserDriftTransport(_JudiciarySequentialPaginationTransport):
    """Return invalid markup only for verification page two."""

    def __init__(self) -> None:
        super().__init__()
        self.year_requests = 0

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.year_requests += 1
            if self.year_requests == 4:
                self.urls.append(url)
                body = b"<html>verification result contract changed</html>"
                return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryOutOfScopeSecondPassDriftTransport(_JudiciaryTransport):
    """Change only one cutoff-excluded identity between the two valid passes."""

    def __init__(self) -> None:
        super().__init__()
        self.year_requests = 0

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url:
            self.urls.append(url)
            self.year_requests += 1
            body = _current_judiciary_result_body(
                year=1997,
                reported_pages=1,
                rows=(
                    (1 if self.year_requests == 1 else 9, "30/06/1997"),
                    (2, "01/07/1997"),
                ),
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryLaterYearSecondPassDriftTransport(_JudiciaryTransport):
    """Change only the second 1998 listing after a stable 1997 listing."""

    def __init__(self) -> None:
        super().__init__()
        self.year_1998_requests = 0

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1998" in url:
            self.urls.append(url)
            self.year_1998_requests += 1
            body = _current_judiciary_result_body(
                year=1998,
                reported_pages=1,
                rows=((3 if self.year_1998_requests == 1 else 4, "02/01/1998"),),
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciaryCrossYearDuplicateTransport(_JudiciaryTransport):
    """Expose one stable DIS identity in two independently valid year partitions."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "year=1997" in url or "year=1998" in url:
            self.urls.append(url)
            year = 1997 if "year=1997" in url else 1998
            body = _current_judiciary_result_body(
                year=year,
                reported_pages=1,
                rows=((2, f"02/01/{year}"),),
            )
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _JudiciarySearchFormContractChangedTransport(_JudiciaryTransport):
    """Expose a retained advanced-search form that cannot bind the year procedure."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "isadvsearch=1" in url and "year=" not in url:
            body = b'<form method="get" action="search_result_form.jsp"><input name="year"></form>'
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


@dataclass
class _JudiciaryClock:
    """Deterministic monotonic clock/sleeper pair for bounded-observation tests."""

    value: float = 0.0
    sleeps: list[float] = field(default_factory=lambda: cast("list[float]", []))

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class _BlockingJudiciaryTransport(_JudiciaryTransport):
    """Hold one real child execution at its first transport boundary."""

    def __init__(self, started: ProcessEvent, release: ProcessEvent) -> None:
        super().__init__()
        self._started = started
        self._release = release

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        self._started.set()
        if not self._release.wait(timeout=30):
            message = "timed out waiting to release blocking transport"
            raise AssertionError(message)
        return super().get(url=url, max_bytes=max_bytes)


def _execute_blocked_judiciary_process(  # noqa: PLR0913, PLR0917
    authority: str,
    output: str,
    cutoff: str,
    attempt_id: str,
    started: ProcessEvent,
    release: ProcessEvent,
    results: Queue[tuple[str, object]],
) -> None:
    """Execute one public source attempt in a separate process for exclusivity proof."""
    clock = _JudiciaryClock()
    try:
        report = execute_source_family(
            authority_manifest=Path(authority),
            source_family="JUDICIARY",
            output_root=Path(output),
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_BlockingJudiciaryTransport(started, release),
            judiciary_clock=clock.monotonic,
            judiciary_sleeper=clock.sleep,
        )
    except Exception as error:  # noqa: BLE001  # pragma: no cover - child result asserts it.
        results.put(("error", (type(error).__name__, str(error))))
    else:
        results.put(("ok", report))


def test_concurrent_same_root_and_attempt_fails_before_clock_sleep_or_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second process cannot perform any effect for an already-running attempt identity."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "cross-process-attempt-claim"
    )
    attempt_id = "cross-process-same-attempt"
    lock_root = tmp_path / "runtime-attempt-locks"
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(lock_root))
    context = get_context("fork")
    started = context.Event()
    release = context.Event()
    results: Queue[tuple[str, object]] = context.Queue()
    first = context.Process(
        target=_execute_blocked_judiciary_process,
        args=(str(authority), str(output), cutoff, attempt_id, started, release, results),
    )
    first.start()
    clock_calls: list[str] = []
    sleep_calls: list[float] = []
    transport_calls: list[str] = []

    def exploding_clock() -> float:
        clock_calls.append("called")
        message = "second execution reached its clock"
        raise AssertionError(message)

    def exploding_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        message = "second execution reached its sleeper"
        raise AssertionError(message)

    class ExplodingTransport:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            transport_calls.append(url)
            raise AssertionError((url, max_bytes))

    try:
        assert started.wait(timeout=15), "first process did not reach blocking transport"
        with pytest.raises(ValueError, match=r"^SOURCE_ATTEMPT_IN_PROGRESS$"):
            execute_source_family(
                authority_manifest=authority,
                source_family="JUDICIARY",
                output_root=output,
                attempt_id=attempt_id,
                observation_cutoff=cutoff,
                repository_root=REPOSITORY_ROOT,
                transport=ExplodingTransport(),
                judiciary_clock=exploding_clock,
                judiciary_sleeper=exploding_sleep,
            )
        assert clock_calls == []
        assert sleep_calls == []
        assert transport_calls == []
    finally:
        release.set()
        first.join(timeout=30)
        if first.is_alive():
            first.terminate()
            first.join(timeout=10)

    assert first.exitcode == 0
    assert results.get(timeout=5)[0] == "ok"


def test_cli_reports_concurrent_attempt_as_stable_pre_effect_result(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The losing CLI claims before authorization, replay probing, or transport."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "cli-cross-process-attempt-claim"
    )
    attempt_id = "cli-cross-process-same-attempt"
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(tmp_path / "runtime-attempt-locks"))
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    current_authorization = admission.authorize_execution(
        authority_manifest=authority,
        matrix=matrix,
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
    )
    context = get_context("fork")
    started = context.Event()
    release = context.Event()
    results: Queue[tuple[str, object]] = context.Queue()
    first = context.Process(
        target=_execute_blocked_judiciary_process,
        args=(str(authority), str(output), cutoff, attempt_id, started, release, results),
    )
    first.start()
    authorization_calls: list[str] = []
    report_probe_calls: list[Path] = []
    transport_construction: list[frozenset[str]] = []
    transport_calls: list[str] = []
    close_calls: list[str] = []

    class ExplodingCliTransport:
        def __init__(self, *, allowed_redirect_urls: frozenset[str]) -> None:
            transport_construction.append(allowed_redirect_urls)

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            transport_calls.append(url)
            raise AssertionError((url, max_bytes))

        def close(self) -> None:
            close_calls.append("closed")

    try:
        assert started.wait(timeout=15), "first process did not reach blocking transport"
        report_path = output / "attempts" / attempt_id / "report.json"
        original_is_file = Path.is_file

        def unavailable_current_authorization(**_arguments: object) -> ExecutionAuthorization:
            authorization_calls.append("authorize_execution")
            message = "EXECUTION_NOT_AUTHORIZED:CURRENT_TEST_REJECTION"
            raise ValueError(message)

        def retained_authorization(**_arguments: object) -> ExecutionAuthorization:
            authorization_calls.append("authorize_retained_replay")
            return current_authorization

        def recording_is_file(path: Path) -> bool:
            if path == report_path:
                report_probe_calls.append(path)
                return True
            return original_is_file(path)

        monkeypatch.setattr(admission, "authorize_execution", unavailable_current_authorization)
        monkeypatch.setattr(admission, "authorize_retained_replay", retained_authorization)
        monkeypatch.setattr(Path, "is_file", recording_is_file)
        monkeypatch.setattr(execution, "UrllibReadOnlyTransport", ExplodingCliTransport)
        exit_code = admission.main(
            [
                "--authority-manifest",
                str(authority),
                "--matrix",
                str(matrix),
                "--mode",
                "execute",
                "--source-family",
                "JUDICIARY",
                "--attempt-id",
                attempt_id,
                "--observation-cutoff",
                cutoff,
                "--output-root",
                str(output),
            ]
        )
        captured = capfd.readouterr()
        assert exit_code == 2
        assert captured.err == ""
        assert json.loads(captured.out) == {
            "attempt_id": attempt_id,
            "execute_authorized": False,
            "result": "SOURCE_ATTEMPT_IN_PROGRESS",
            "source_attempted": False,
        }
        assert authorization_calls == []
        assert report_probe_calls == []
        assert transport_construction == []
        assert transport_calls == []
        assert close_calls == []
    finally:
        release.set()
        first.join(timeout=30)
        if first.is_alive():
            first.terminate()
            first.join(timeout=10)

    assert first.exitcode == 0
    assert results.get(timeout=5)[0] == "ok"


def test_process_death_releases_claim_and_stale_filename_cannot_block_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An OS-released claim is reusable even though its private runtime file persists."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "process-death-attempt-claim"
    )
    attempt_id = "process-death-same-attempt"
    lock_root = tmp_path / "runtime-attempt-locks"
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(lock_root))
    context = get_context("fork")
    started = context.Event()
    release = context.Event()
    results: Queue[tuple[str, object]] = context.Queue()
    first = context.Process(
        target=_execute_blocked_judiciary_process,
        args=(str(authority), str(output), cutoff, attempt_id, started, release, results),
    )
    first.start()
    assert started.wait(timeout=15), "first process did not reach blocking transport"
    first.terminate()
    first.join(timeout=10)
    assert not first.is_alive()
    assert not (output / "attempts" / attempt_id / "report.json").exists()

    clock = _JudiciaryClock()
    report = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_JudiciaryTransport(),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["attempt_id"] == attempt_id
    lock_files = list(lock_root.iterdir())
    assert len(lock_files) == 1
    assert lock_files[0].is_file()
    assert not lock_files[0].is_symlink()
    assert lock_files[0].stat().st_mode & 0o777 == 0o600


def test_execution_exception_releases_attempt_claim_for_clean_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ordinary executor exception cannot strand the exact attempt identity."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "exception-release-attempt-claim"
    )
    attempt_id = "exception-release-same-attempt"
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(tmp_path / "runtime-locks"))

    with pytest.raises(
        execution.PredecessorValidationError, match=r"^PREDECESSOR_ATTEMPT_INVALID$"
    ):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=attempt_id,
            predecessor_attempt_id="missing-predecessor",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=cast("execution.ReadOnlySourceTransport", pytest.fail),
        )

    clock = _JudiciaryClock()
    report = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_JudiciaryTransport(),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    assert report["attempt_id"] == attempt_id


@pytest.mark.parametrize("identity_difference", ["canonical-root", "attempt-id"])
def test_different_attempt_identity_does_not_contend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identity_difference: str,
) -> None:
    """Changing either identity coordinate permits independent source execution."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    base = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "different-root-attempt-claim"
    )
    first_output = base / "first"
    second_output = base / "second" if identity_difference == "canonical-root" else first_output
    first_attempt_id = "first-attempt-identity"
    second_attempt_id = (
        first_attempt_id if identity_difference == "canonical-root" else "second-attempt-identity"
    )
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(tmp_path / "runtime-attempt-locks"))
    context = get_context("fork")
    started = context.Event()
    release = context.Event()
    results: Queue[tuple[str, object]] = context.Queue()
    first = context.Process(
        target=_execute_blocked_judiciary_process,
        args=(
            str(authority),
            str(first_output),
            cutoff,
            first_attempt_id,
            started,
            release,
            results,
        ),
    )
    first.start()
    try:
        assert started.wait(timeout=15), "first process did not reach blocking transport"
        clock = _JudiciaryClock()
        second = execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=second_output,
            attempt_id=second_attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_JudiciaryTransport(),
            judiciary_clock=clock.monotonic,
            judiciary_sleeper=clock.sleep,
        )
        assert second["attempt_id"] == second_attempt_id
    finally:
        release.set()
        first.join(timeout=30)
        if first.is_alive():
            first.terminate()
            first.join(timeout=10)

    assert first.exitcode == 0
    assert results.get(timeout=5)[0] == "ok"
    assert (first_output / "attempts" / first_attempt_id / "report.json").is_file()
    assert (second_output / "attempts" / second_attempt_id / "report.json").is_file()


@pytest.mark.parametrize("hostile_kind", ["symlink", "file", "public-directory"])
def test_hostile_runtime_lock_root_fails_closed_before_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hostile_kind: str,
) -> None:
    """A replaceable or ambiguously permissioned runtime root never controls execution."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / f"hostile-runtime-{hostile_kind}"
    )
    lock_root = tmp_path / "runtime-attempt-locks"
    if hostile_kind == "symlink":
        target = tmp_path / "runtime-target"
        target.mkdir(mode=0o700)
        lock_root.symlink_to(target, target_is_directory=True)
    elif hostile_kind == "file":
        lock_root.write_bytes(b"not a directory")
    else:
        lock_root.mkdir(mode=0o755)
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(lock_root))
    clock_calls: list[str] = []
    transport_calls: list[str] = []

    def exploding_clock() -> float:
        clock_calls.append("called")
        message = "unsafe runtime root reached its clock"
        raise AssertionError(message)

    class ExplodingTransport:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            transport_calls.append(url)
            raise AssertionError((url, max_bytes))

    with pytest.raises(ValueError, match=r"^SOURCE_ATTEMPT_LOCK_UNSAFE$"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=f"hostile-runtime-{hostile_kind}",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=ExplodingTransport(),
            judiciary_clock=exploding_clock,
            judiciary_sleeper=lambda _seconds: pytest.fail("unsafe runtime root reached sleeper"),
        )

    assert clock_calls == []
    assert transport_calls == []
    assert not output.exists()


@pytest.mark.parametrize("overlap_kind", ["equal", "descendant", "resolved-alias"])
def test_runtime_lock_root_overlap_with_evidence_is_rejected_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overlap_kind: str,
) -> None:
    """No lexical or resolved runtime lock root may enter the evidence tree."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / f"runtime-evidence-overlap-{overlap_kind}"
    )
    output.mkdir(parents=True, mode=0o700)
    output.chmod(0o700)
    (output / "retained-marker.bin").write_bytes(b"retained bytes must not change")
    if overlap_kind == "equal":
        lock_root = output
    elif overlap_kind == "descendant":
        lock_root = output / "runtime-attempt-locks"
    else:
        nested = output / "nested"
        nested.mkdir(mode=0o700)
        alias = tmp_path / "evidence-alias"
        alias.symlink_to(output, target_is_directory=True)
        lock_root = alias / "nested" / "runtime-attempt-locks"
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(lock_root))

    def exact_tree() -> tuple[tuple[object, ...], ...]:
        paths = (output, *sorted(output.rglob("*")))
        return tuple(
            (
                "." if path == output else path.relative_to(output).as_posix(),
                stat.S_IFMT(path.lstat().st_mode),
                stat.S_IMODE(path.lstat().st_mode),
                path.lstat().st_size,
                path.lstat().st_mtime_ns,
                path.read_bytes() if path.is_file() else None,
            )
            for path in paths
        )

    before = exact_tree()
    with pytest.raises(ValueError, match=r"^SOURCE_ATTEMPT_LOCK_UNSAFE$"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=f"runtime-evidence-overlap-{overlap_kind}",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=cast("execution.ReadOnlySourceTransport", pytest.fail),
            judiciary_clock=lambda: pytest.fail("overlapping runtime root reached clock"),
            judiciary_sleeper=lambda _seconds: pytest.fail(
                "overlapping runtime root reached sleeper"
            ),
        )
    assert exact_tree() == before


def test_cold_tempdir_selection_cannot_probe_or_mutate_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selecting the trusted runtime base is read-only even for hostile TMPDIR."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "cold-tempdir-evidence-root"
    )
    output.mkdir(parents=True, mode=0o700)
    output.chmod(0o700)
    marker = output / "retained-marker.bin"
    marker.write_bytes(b"cold temp selection must not touch evidence")
    attempt_id = "cold-tempdir-evidence-root"
    report_path = output / "attempts" / attempt_id / "report.json"
    monkeypatch.delenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", raising=False)
    monkeypatch.setenv("TMPDIR", str(output))
    monkeypatch.setattr(tempfile, "tempdir", None)
    authorization_calls: list[str] = []
    report_probe_calls: list[Path] = []
    transport_calls: list[str] = []
    clock_calls: list[str] = []
    sleep_calls: list[float] = []
    original_is_file = Path.is_file

    def forbidden_authorization(**_arguments: object) -> ExecutionAuthorization:
        authorization_calls.append("called")
        pytest.fail("hostile TMPDIR reached authorization")

    def recording_is_file(path: Path) -> bool:
        if path == report_path:
            report_probe_calls.append(path)
        return original_is_file(path)

    class ExplodingTransport:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            transport_calls.append(url)
            raise AssertionError((url, max_bytes))

    def exploding_clock() -> float:
        clock_calls.append("called")
        message = "hostile TMPDIR reached clock"
        raise AssertionError(message)

    def exploding_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        message = "hostile TMPDIR reached sleeper"
        raise AssertionError(message)

    def closure() -> tuple[tuple[object, ...], ...]:
        paths = (output, *sorted(output.rglob("*")))
        return tuple(
            (
                "." if path == output else path.relative_to(output).as_posix(),
                stat.S_IFMT(path.lstat().st_mode),
                stat.S_IMODE(path.lstat().st_mode),
                path.lstat().st_size,
                path.lstat().st_mtime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
            )
            for path in paths
        )

    monkeypatch.setattr(execution, "authorize_execution", forbidden_authorization)
    monkeypatch.setattr(execution, "authorize_retained_replay", forbidden_authorization)
    monkeypatch.setattr(Path, "is_file", recording_is_file)
    before = closure()
    with pytest.raises(ValueError, match=r"^SOURCE_ATTEMPT_LOCK_UNSAFE$"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=ExplodingTransport(),
            judiciary_clock=exploding_clock,
            judiciary_sleeper=exploding_sleep,
        )
    assert closure() == before
    assert tuple(output.iterdir()) == (marker,)
    assert authorization_calls == []
    assert report_probe_calls == []
    assert transport_calls == []
    assert clock_calls == []
    assert sleep_calls == []


def test_intermediate_runtime_alias_cannot_retarget_into_evidence_before_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every component is pinned without symlink traversal before any lock-root mutation."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "runtime-intermediate-retarget"
    )
    output_nested = output / "nested"
    output_nested.mkdir(parents=True, mode=0o700)
    output_nested.chmod(0o700)
    (output / "retained-marker.bin").write_bytes(b"retained bytes must not change")
    safe_target = tmp_path / "safe-runtime-target"
    safe_nested = safe_target / "nested"
    safe_nested.mkdir(parents=True, mode=0o700)
    safe_nested.chmod(0o700)
    alias = tmp_path / "runtime-parent-alias"
    alias.symlink_to(safe_target, target_is_directory=True)
    lock_root = alias / "nested" / "runtime-attempt-locks"
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(lock_root))

    def tree_bytes(root: Path) -> tuple[tuple[object, ...], ...]:
        paths = (root, *sorted(root.rglob("*")))
        return tuple(
            (
                "." if path == root else path.relative_to(root).as_posix(),
                stat.S_IFMT(path.lstat().st_mode),
                stat.S_IMODE(path.lstat().st_mode),
                path.lstat().st_size,
                path.lstat().st_mtime_ns,
                path.read_bytes() if path.is_file() else None,
            )
            for path in paths
        )

    output_before = tree_bytes(output)
    safe_before = tree_bytes(safe_target)
    alias_before = (alias.lstat().st_mtime_ns, alias.readlink())
    original_resolve = Path.resolve

    def retarget_after_resolution(path: Path, *, strict: bool = False) -> Path:
        resolved = original_resolve(path, strict=strict)
        if path == lock_root:
            alias.unlink()
            alias.symlink_to(output, target_is_directory=True)
        return resolved

    monkeypatch.setattr(Path, "resolve", retarget_after_resolution)
    with pytest.raises(ValueError, match=r"^SOURCE_ATTEMPT_LOCK_UNSAFE$"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="runtime-intermediate-retarget",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=cast("execution.ReadOnlySourceTransport", pytest.fail),
            judiciary_clock=lambda: pytest.fail("retargeted runtime alias reached clock"),
            judiciary_sleeper=lambda _seconds: pytest.fail(
                "retargeted runtime alias reached sleeper"
            ),
        )
    assert tree_bytes(output) == output_before
    assert tree_bytes(safe_target) == safe_before
    assert (alias.lstat().st_mtime_ns, alias.readlink()) == alias_before


@pytest.mark.parametrize(
    "hostile_kind", ["symlink", "directory", "permissive-file", "fifo", "wrong-owner"]
)
def test_hostile_attempt_lock_entry_fails_closed_before_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hostile_kind: str,
) -> None:
    """Only one private, owned regular lock inode may coordinate an attempt."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / f"hostile-lock-entry-{hostile_kind}"
    )
    attempt_id = f"hostile-lock-entry-{hostile_kind}"
    lock_root = tmp_path / "runtime-attempt-locks"
    lock_root.mkdir(mode=0o700)
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(lock_root))
    identity = json.dumps(
        {"attempt_id": attempt_id, "output_root": str(output.resolve(strict=False))},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    lock_path = lock_root / f"{hashlib.sha256(identity).hexdigest()}.lock"
    if hostile_kind == "symlink":
        victim = tmp_path / "victim"
        victim.write_bytes(b"must remain untouched")
        lock_path.symlink_to(victim)
    elif hostile_kind == "directory":
        lock_path.mkdir(mode=0o700)
    elif hostile_kind == "permissive-file":
        lock_path.write_bytes(b"")
        lock_path.chmod(0o644)
    elif hostile_kind == "fifo":
        os.mkfifo(lock_path, mode=0o600)
    else:
        original_fstat = execution.os.fstat

        def wrong_regular_owner(descriptor: int) -> os.stat_result:
            details = original_fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                return details
            fields = list(details)
            fields[4] = details.st_uid + 1
            return os.stat_result(fields)

        monkeypatch.setattr(execution.os, "fstat", wrong_regular_owner)
    transport_calls: list[str] = []

    class ExplodingTransport:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            transport_calls.append(url)
            raise AssertionError((url, max_bytes))

    with pytest.raises(ValueError, match=r"^SOURCE_ATTEMPT_LOCK_UNSAFE$"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=ExplodingTransport(),
            judiciary_clock=lambda: pytest.fail("hostile lock entry reached clock"),
            judiciary_sleeper=lambda _seconds: pytest.fail("hostile lock entry reached sleeper"),
        )

    assert transport_calls == []
    assert not output.exists()
    if hostile_kind == "symlink":
        assert (tmp_path / "victim").read_bytes() == b"must remain untouched"


def test_replaceable_runtime_parent_fails_closed_before_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-sticky public parent cannot replace the otherwise-private runtime root."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "replaceable-runtime-parent"
    )
    public_parent = tmp_path / "public-parent"
    public_parent.mkdir()
    public_parent.chmod(0o777)
    monkeypatch.setenv(
        "ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(public_parent / "runtime-attempt-locks")
    )

    with pytest.raises(ValueError, match=r"^SOURCE_ATTEMPT_LOCK_UNSAFE$"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="replaceable-runtime-parent",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=cast("execution.ReadOnlySourceTransport", pytest.fail),
            judiciary_clock=lambda: pytest.fail("replaceable parent reached clock"),
            judiciary_sleeper=lambda _seconds: pytest.fail("replaceable parent reached sleeper"),
        )

    assert not output.exists()


def test_released_attempt_replays_exact_report_without_effect_or_evidence_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A terminal report is replayed byte-exactly after claim release with no lock in evidence."""
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "released-attempt-replay"
    )
    attempt_id = "released-attempt-replay"
    lock_root = tmp_path / "runtime-attempt-locks"
    monkeypatch.setenv("ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT", str(lock_root))
    clock = _JudiciaryClock()
    written = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_JudiciaryTransport(),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    before = {
        path.relative_to(output).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mode & 0o777,
            path.stat().st_mtime_ns,
        )
        for path in output.rglob("*")
        if path.is_file()
    }
    clock_calls: list[str] = []
    transport_calls: list[str] = []

    def exploding_clock() -> float:
        clock_calls.append("called")
        message = "exact replay reached its clock"
        raise AssertionError(message)

    class ExplodingTransport:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            transport_calls.append(url)
            raise AssertionError((url, max_bytes))

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ExplodingTransport(),
        judiciary_clock=exploding_clock,
        judiciary_sleeper=lambda _seconds: pytest.fail("exact replay reached sleeper"),
    )
    after = {
        path.relative_to(output).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mode & 0o777,
            path.stat().st_mtime_ns,
        )
        for path in output.rglob("*")
        if path.is_file()
    }

    assert replayed == written
    assert after == before
    assert clock_calls == []
    assert transport_calls == []
    assert not any(path.suffix == ".lock" for path in output.rglob("*"))
    assert len(list(lock_root.glob("*.lock"))) == 1


class _TimedJudiciaryTransport(_JudiciaryTransport):
    """Expose transport-start instants without changing the real fixture responses."""

    def __init__(self, clock: _JudiciaryClock) -> None:
        super().__init__()
        self._clock = clock
        self.starts: list[float] = []

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        self.starts.append(self._clock.value)
        return super().get(url=url, max_bytes=max_bytes)


_HKEX_MAIN_UPDATE_PDF = (
    "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_154_Attachment.pdf"
)
_HKEX_GEM_UPDATE_PDF = (
    "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_87_Attachment.pdf"
)


class _HKEXTransport:
    """Serve exact catalogue, static complete artifacts, and dynamic role members."""

    _ROOTS = (
        "main-board-listing-rules",
        "gem-listing-rules",
        "main-board-regulatory-forms",
        "gem-regulatory-forms",
        "main-board-fees-rules",
        "gem-fees-rules",
        "amendments-main-board-listing-rules",
        "amendments-gem-listing-rules",
    )
    _ENTIRE: ClassVar[dict[str, str]] = {
        "main-board-regulatory-forms": "6189",
        "gem-regulatory-forms": "6189",
        "main-board-fees-rules": "6192",
        "gem-fees-rules": "6192",
        "amendments-main-board-listing-rules": "2",
        "amendments-gem-listing-rules": "49",
    }

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        self.urls.append(url)
        if "www.hkex.com.hk/Listing/Rules" in url:
            body = b"".join(
                f'<a href="https://en-rules.hkex.com.hk/rulebook/{root}">{root}</a>'.encode()
                for root in self._ROOTS
            )
        elif url in {
            _HKEX_MAIN_UPDATE_PDF,
            _HKEX_GEM_UPDATE_PDF,
            "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/consol_mb.pdf",
            "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/consol_gem.pdf",
        }:
            body = b"%PDF-1.7\nauthentic bounded fixture"
        elif url.endswith(".pdf"):
            body = b"<html>publisher locator not found</html>"
            return CapturedResponse(404, "text/html", body[: max_bytes + 1], None)
        elif url == "https://en-rules.hkex.com.hk/entiresection/2":
            body = f'<a href="{_HKEX_MAIN_UPDATE_PDF}">Update 154</a>'.encode()
        elif url == "https://en-rules.hkex.com.hk/entiresection/49":
            body = f'<a href="{_HKEX_GEM_UPDATE_PDF}">Update 87</a>'.encode()
        else:
            matched = next((root for root in self._ENTIRE if url.endswith(root)), None)
            if matched is None:
                body = b"<html>captured complete section or member</html>"
            else:
                entire = self._ENTIRE[matched]
                body = (
                    f'<a href="/entiresection/{entire}">Entire Section</a>'
                    f'<a href="/rulebook/{matched}-member-1">Member</a>'
                ).encode()
        return CapturedResponse(200, "application/octet-stream", body[: max_bytes + 1], None)


class _HKEXContractChangedTransport(_HKEXTransport):
    """Keep every request reachable while changing the catalogue contract."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if "www.hkex.com.hk/Listing/Rules" in url:
            body = b"<html>publisher changed the catalogue</html>"
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], None)
        return super().get(url=url, max_bytes=max_bytes)


class _BasicLawContractChangedTransport(_ConfiguredHkelTransport):
    """Keep the HKeL family reachable while changing the Basic Law root contract."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if url == _BASIC_LAW_CONSTITUTION_ROOT:
            body = b"<html>publisher changed the Basic Law membership contract</html>"
            return CapturedResponse(200, "text/html", body[: max_bytes + 1], url)
        return super().get(url=url, max_bytes=max_bytes)


class _BasicLawMemberOutageTransport(_ConfiguredHkelTransport):
    """Keep the root parseable but fail one exact generated member request."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if url == "https://www.basiclaw.gov.hk/en/constitution/chapter2.html":
            return CapturedResponse(503, "text/html", b"unavailable", url)
        return super().get(url=url, max_bytes=max_bytes)


class _BasicLawArbitraryBodyTransport(_ConfiguredHkelTransport):
    """Return reachable non-HTML bytes for one exact required content member."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if url == "https://www.basiclaw.gov.hk/en/constitution/chapter2.html":
            return CapturedResponse(200, "application/octet-stream", b"not html", url)
        return super().get(url=url, max_bytes=max_bytes)


class _HkelArchiveOutageTransport(_ConfiguredHkelTransport):
    """Keep catalogues valid but fail one declared current-data archive."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if url.endswith("hkel_c_leg_cap_1_cap_300_en.zip"):
            return CapturedResponse(503, "application/zip", b"unavailable", url)
        return super().get(url=url, max_bytes=max_bytes)


def _items(report: dict[str, object], key: str) -> list[dict[str, object]]:
    raw = cast("list[object]", report[key])
    return [cast("dict[str, object]", item) for item in raw]


def test_hkex_fake_returns_http_404_for_an_unknown_pdf() -> None:
    """The source double must keep stale or fabricated PDF locators fail-visible."""
    response = _HKEXTransport().get(
        url="https://en-rules.hkex.com.hk/sites/default/files/net_file_store/unknown.pdf",
        max_bytes=16_777_216,
    )

    assert response.status == 404
    assert response.body.startswith(b"<html>")


@pytest.mark.parametrize(
    (
        "authority_name",
        "output_name",
        "attempt_id",
        "report_sha256",
        "expected_result",
        "observation_cutoff",
    ),
    [
        (
            "authority-user-attested-live-2026-09-01-hkex-baseline.json",
            "authentic-baseline-20260901a",
            "hkex-live-baseline-20260901a",
            "d04259b54ce71e5d7fec2f26de667006cfcb55a93e2d2b78617637a7604e966c",
            "SOURCE_OUTAGE",
            "2026-09-01T15:33:35+08:00",
        ),
        (
            "authority-user-attested-live-2026-09-01-hkex-baseline-b.json",
            "authentic-baseline-20260901b",
            "hkex-live-baseline-20260901b",
            "0e24ae06367796bfc8a8581f4538c3d8c16f9fdc7b169dd6c45e4544194b186e",
            "SOURCE_OUTAGE",
            "2026-09-01T15:33:35+08:00",
        ),
        (
            "authority-user-attested-live-2026-09-01-hkex-baseline-c.json",
            "authentic-baseline-20260901c",
            "hkex-live-baseline-20260901c",
            "74b8cfa325b6bfcc98c652d3ec413761a0792aebdf8d564bbe506719be294f75",
            "SOURCE_CONTRACT_CHANGED",
            "2026-09-01T15:33:35+08:00",
        ),
        (
            "authority-user-attested-live-2026-09-02-hkex-role-aware-baseline.json",
            "authentic-baseline-20260902a",
            "hkex-live-role-aware-20260902a",
            "38adea701dd4c7334c7b31af94519b0780248563248ff55ada87ed8bf3e6f9e4",
            "SOURCE_CONTRACT_CHANGED",
            "2026-09-02T09:51:30+08:00",
        ),
        (
            "authority-user-attested-live-2026-09-02-hkex-role-aware-baseline-b.json",
            "authentic-baseline-20260902b",
            "hkex-live-role-aware-20260902b",
            "0ba08e5868921fc7da0685187fd75d5246d062932cd2369ad0836ac7da6d2686",
            "SOURCE_CONTRACT_CHANGED",
            "2026-09-02T10:03:57+08:00",
        ),
    ],
    ids=[
        "authority-803-attempt-a",
        "authority-804-attempt-b",
        "authority-805-attempt-c",
        "authority-806-role-aware-root-contract-stop",
        "authority-807-role-aware-location-stop",
    ],
)
def test_exact_hkex_retained_attempt_replays_with_zero_effects(  # noqa: PLR0913, PLR0917
    authority_name: str,
    output_name: str,
    attempt_id: str,
    report_sha256: str,
    expected_result: str,
    observation_cutoff: str,
) -> None:
    """Each frozen HKEX report replays only under its exact retained binding."""
    base = REPOSITORY_ROOT / "var/hk-v1/source-admission"
    authority = base / authority_name
    output = base / "hkex" / output_name
    report_path = output / "attempts" / attempt_id / "report.json"

    def snapshot() -> dict[str, tuple[object, ...]]:
        paths = [output, *sorted(output.rglob("*"))]
        result: dict[str, tuple[object, ...]] = {}
        for path in paths:
            relative = "." if path == output else path.relative_to(output).as_posix()
            metadata = path.lstat()
            body_sha256 = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            result[relative] = (
                stat.S_IFMT(metadata.st_mode),
                stat.S_IMODE(metadata.st_mode),
                metadata.st_size,
                metadata.st_mtime_ns,
                body_sha256,
            )
        return result

    class ExplodingTransport:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            raise AssertionError((url, max_bytes))

    expected_bytes = report_path.read_bytes()
    assert hashlib.sha256(expected_bytes).hexdigest() == report_sha256
    expected = cast("dict[str, object]", json.loads(expected_bytes))
    before = snapshot()
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=(
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        output_root=output,
        source_family="HKEX",
        observation_cutoff=observation_cutoff,
        attempt_id=attempt_id,
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=observation_cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ExplodingTransport(),
        authorization=authorization,
        hkex_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        hkex_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleeper")),
    )

    assert replayed == expected
    assert replayed["result"] == expected_result
    assert snapshot() == before


def test_public_hkex_replay_derives_exact_806_parser_exception_from_its_pin() -> None:
    """The exact 806 report replays without a caller-supplied historical capability."""
    base = REPOSITORY_ROOT / "var/hk-v1/source-admission/hkex/authentic-baseline-20260902a"
    report_path = base / "attempts/hkex-live-role-aware-20260902a/report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    pin = execution.historical_hkex_replay_pin("hkex-live-role-aware-20260902a")

    replayed = execution.replay_hkex_role_aware_report(
        report,
        output_root=base,
        endpoints=pin.endpoints,
    )

    assert replayed == report


def test_public_hkex_replay_rejects_an_unbound_legacy_exception_argument() -> None:
    """A direct caller cannot grant the Authority-806-only parser exception."""
    base = REPOSITORY_ROOT / "var/hk-v1/source-admission/hkex/authentic-baseline-20260902a"
    report_path = base / "attempts/hkex-live-role-aware-20260902a/report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    forged = copy.deepcopy(report)
    forged["authority_manifest_fingerprint"] = "sha256:" + "0" * 64
    pin = execution.historical_hkex_replay_pin("hkex-live-role-aware-20260902a")
    public_replay = cast("Callable[..., object]", execution.replay_hkex_role_aware_report)

    with pytest.raises(TypeError):
        public_replay(
            forged,
            output_root=base,
            endpoints=pin.endpoints,
            historical_root_contract_changed=True,
        )


def test_execution_distinguishes_no_change_truncation_outage_and_restart(tmp_path: Path) -> None:
    """Every material terminal state remains distinct and an exact retry is immutable."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="2026-08-27T12:00:00+08:00")

    def execute(
        attempt_id: str, transport: _Transport, predecessor: str | None = None
    ) -> dict[str, object]:
        clock = _JudiciaryClock()
        return execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor,
            observation_cutoff="2026-08-27T12:00:00+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=transport,
            judiciary_clock=clock.monotonic,
            judiciary_sleeper=clock.sleep,
        )

    first = execute("first", _Transport(b"same"))
    unchanged = execute("second", _Transport(b"same"), "first")
    truncated = execute("truncated", _Transport(b"x" * 20_000_000), "second")
    outage = execute("outage", _Transport(b"", status=503), "truncated")
    restarted = execute("first", _Transport(b"different"))

    assert first["change_state"] == "FIRST_OBSERVATION"
    assert unchanged["change_state"] == "NO_CHANGE_OBSERVED"
    assert truncated["result"] == "TRUNCATED_RESPONSE"
    assert outage["result"] == "SOURCE_OUTAGE"
    assert restarted == first


def test_change_state_uses_explicit_immediate_predecessor_for_a_b_a(tmp_path: Path) -> None:
    """Run three must compare A to run two's B, never the first lexicographic A."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)

    first = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="run-a-one",
        predecessor_attempt_id=None,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"A"),
    )
    second = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="run-b-two",
        predecessor_attempt_id="run-a-one",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"B"),
    )
    third = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="run-a-three",
        predecessor_attempt_id="run-b-two",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"A"),
    )

    assert first["change_state"] == "FIRST_OBSERVATION"
    assert second["change_state"] == "CHANGED_OBSERVED"
    assert third["change_state"] == "CHANGED_OBSERVED"
    assert third["predecessor_attempt_id"] == "run-b-two"


def test_new_authority_binding_starts_a_new_baseline_in_the_same_vault(tmp_path: Path) -> None:
    """A valid report from another authority lineage cannot force or seed a predecessor."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "new-authority-baseline"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    previous = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="old-authority-baseline",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"old-authority"),
    )
    replacement_fingerprint = _replace_authority_identity(authority)

    current = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="new-authority-baseline",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"new-authority"),
    )

    assert previous["authority_manifest_fingerprint"] != replacement_fingerprint
    assert current["authority_manifest_fingerprint"] == replacement_fingerprint
    assert current["predecessor_attempt_id"] is None
    assert current["change_state"] == "FIRST_OBSERVATION"


def test_compatible_unconsumed_report_requires_predecessor_before_transport(
    tmp_path: Path,
) -> None:
    """Omitting the current lineage tip is rejected before any source request."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "compatible-predecessor-required"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="compatible-lineage-tip",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"tip"),
    )
    probe = TransportProbe()

    with pytest.raises(ValueError, match="PREDECESSOR_ATTEMPT_REQUIRED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id="missing-compatible-predecessor",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0


def test_malformed_foreign_binding_report_is_not_silently_ignored(tmp_path: Path) -> None:
    """Filtering another lineage cannot turn a malformed retained report into a baseline."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "malformed-foreign-binding"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="foreign-report-before-corruption",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"foreign"),
    )
    report_path = output / "attempts/foreign-report-before-corruption/report.json"
    malformed = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    malformed.pop("authority_manifest_fingerprint")
    report_path.write_text(json.dumps(malformed, sort_keys=True, separators=(",", ":")))
    _replace_authority_identity(authority)
    probe = TransportProbe()

    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id="baseline-after-malformed-foreign-report",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-provenance",
        "missing-readback",
        "false-readback",
        "missing-object-key",
        "escaped-object-key",
        "malformed-requested-url",
        "duplicate-endpoint-id",
        "malformed-counts",
        "malformed-procedures",
        "malformed-result",
        "malformed-change-state",
    ],
)
def test_every_foreign_report_must_match_the_closed_retained_report_contract(  # noqa: C901
    tmp_path: Path, mutation: str
) -> None:
    """A malformed foreign report cannot be ignored before a new baseline transport call."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / mutation
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_id = "foreign-contract-source"
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"foreign-contract"),
    )
    report_path = output / "attempts" / attempt_id / "report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    endpoints = _items(report, "endpoints")
    procedures = _items(report, "source_procedures")
    if mutation == "unknown-provenance":
        report["authority_provenance"] = "USER_REPORTED"
    elif mutation == "missing-readback":
        report.pop("readback_verified")
    elif mutation == "false-readback":
        report["readback_verified"] = False
    elif mutation == "missing-object-key":
        endpoints[0].pop("object_key")
    elif mutation == "escaped-object-key":
        endpoints[0]["object_key"] = "objects/../../foreign-object.bin"
    elif mutation == "malformed-requested-url":
        endpoints[0]["requested_url"] = "https://example.invalid:not-a-port/artifact"
    elif mutation == "duplicate-endpoint-id":
        duplicate = dict(endpoints[0])
        endpoints.append(duplicate)
        counts = cast("dict[str, int]", report["endpoint_counts"])
        code = cast("str", duplicate["terminal_code"])
        counts[code] += 1
    elif mutation == "malformed-counts":
        report["endpoint_counts"] = {"CAPTURED": True}
    elif mutation == "malformed-procedures":
        procedures[0]["declared_member_count"] = -1
    elif mutation == "malformed-result":
        report["result"] = "UNSUPPORTED_RESULT"
    else:
        report["change_state"] = "UNSUPPORTED_CHANGE_STATE"
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    _replace_authority_identity(authority)
    probe = TransportProbe()
    new_attempt_id = f"new-baseline-after-{mutation}"

    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id=new_attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0
    assert not (output / "attempts" / new_attempt_id / "report.json").exists()


@pytest.mark.parametrize(
    "mutation",
    ["escaped-path", "missing-object", "altered-bytes", "altered-length", "altered-fingerprint"],
)
def test_explicit_predecessor_objects_are_reread_before_transport(
    tmp_path: Path, mutation: str
) -> None:
    """A predecessor cannot seed comparison from missing, escaped, or altered evidence."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / mutation
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    predecessor_id = "predecessor-object-source"
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=predecessor_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"predecessor-object"),
    )
    report_path = output / "attempts" / predecessor_id / "report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    endpoint = _items(report, "endpoints")[0]
    object_path = output / cast("str", endpoint["object_key"])
    if mutation == "escaped-path":
        endpoint["object_key"] = "objects/../../authority.json"
    elif mutation == "missing-object":
        object_path.unlink()
    elif mutation == "altered-bytes":
        object_path.write_bytes(b"altered-predecessor-object")
    elif mutation == "altered-length":
        endpoint["byte_length"] = cast("int", endpoint["byte_length"]) + 1
    else:
        false_fingerprint = "sha256:" + "f" * 64
        false_key = "objects/" + "f" * 64 + ".bin"
        (output / false_key).write_bytes(object_path.read_bytes())
        endpoint["body_fingerprint"] = false_fingerprint
        endpoint["object_key"] = false_key
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    probe = TransportProbe()
    attempt_id = f"after-{mutation}"

    expected_code = (
        "PREDECESSOR_REPORT_MALFORMED"
        if mutation == "escaped-path"
        else "PREDECESSOR_EVIDENCE_READBACK_INVALID"
    )
    with pytest.raises(ValueError, match=expected_code):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0
    assert not (output / "attempts" / attempt_id / "report.json").exists()


def test_explicit_hkel_predecessor_comparison_fingerprint_is_recomputed(
    tmp_path: Path,
) -> None:
    """HKeL session comparison state is recomputed from the retained sanitized object."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "comparison-fingerprint"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    predecessor_id = "hkel-comparison-source"
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEL",
        output_root=output,
        attempt_id=predecessor_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_ConfiguredHkelTransport(),
    )
    report_path = output / "attempts" / predecessor_id / "report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    comparison_endpoint = next(
        item for item in _items(report, "endpoints") if "comparison_fingerprint" in item
    )
    comparison_endpoint["comparison_fingerprint"] = "sha256:" + "e" * 64
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    probe = TransportProbe()
    attempt_id = "after-altered-comparison"

    with pytest.raises(ValueError, match="PREDECESSOR_EVIDENCE_READBACK_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEL",
            output_root=output,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0
    assert not (output / "attempts" / attempt_id / "report.json").exists()


def test_explicit_predecessor_from_another_authority_is_rejected_before_transport(
    tmp_path: Path,
) -> None:
    """A new authority baseline cannot explicitly inherit an old authority's evidence."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "explicit-foreign-predecessor"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="old-authority-tip",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"old"),
    )
    _replace_authority_identity(authority)
    probe = TransportProbe()

    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id="new-authority-with-old-predecessor",
            predecessor_attempt_id="old-authority-tip",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0


def test_consumed_predecessor_cannot_fork_and_exact_replay_never_calls_transport(
    tmp_path: Path,
) -> None:
    """Lineage remains single-tip while an exact completed attempt stays replayable."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "fork-and-replay"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    first = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="lineage-first",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"first"),
    )
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="lineage-second",
        predecessor_attempt_id="lineage-first",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"second"),
    )
    replay_probe = TransportProbe()
    replay = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="lineage-first",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=replay_probe,
    )
    fork_probe = TransportProbe()

    with pytest.raises(ValueError, match="PREDECESSOR_ATTEMPT_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id="forbidden-lineage-fork",
            predecessor_attempt_id="lineage-first",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=fork_probe,
        )

    assert replay == first
    assert replay_probe.calls == 0
    assert fork_probe.calls == 0


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("result", "PREDECESSOR_REPORT_MALFORMED"),
        ("counts", "PREDECESSOR_REPORT_MALFORMED"),
        ("procedures", "PREDECESSOR_REPORT_MALFORMED"),
        ("readback", "PREDECESSOR_REPORT_MALFORMED"),
        ("change-state", "PREDECESSOR_REPORT_MALFORMED"),
        ("object", "PREDECESSOR_EVIDENCE_READBACK_INVALID"),
        ("path", "PREDECESSOR_REPORT_MALFORMED"),
        ("url", "PREDECESSOR_REPORT_MALFORMED"),
    ],
)
def test_exact_restart_revalidates_the_canonical_report_and_retained_objects(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Exact-attempt replay cannot bypass report, URL, object, or result validation."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / mutation
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_id = f"exact-restart-{mutation}"
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"retained-exact-restart"),
    )
    report_path = output / "attempts" / attempt_id / "report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    endpoints = _items(report, "endpoints")
    if mutation == "result":
        # Direct regression for the reviewed false-success path.
        report["result"] = "COMPLETE"
    elif mutation == "counts":
        counts = cast("dict[str, int]", report["endpoint_counts"])
        code = cast("str", endpoints[0]["terminal_code"])
        counts[code] += 1
    elif mutation == "procedures":
        _items(report, "source_procedures")[0]["source_id"] = "HK-REG-NOT-DECLARED"
    elif mutation == "readback":
        report["readback_verified"] = False
    elif mutation == "change-state":
        report["change_state"] = "CHANGED_OBSERVED"
    elif mutation == "object":
        object_path = output / cast("str", endpoints[0]["object_key"])
        object_path.write_bytes(b"altered-exact-restart-object")
    elif mutation == "path":
        endpoints[0]["object_key"] = "objects/../../authority.json"
    else:
        endpoints[0]["requested_url"] = "https://not-authorized.invalid/forged"
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    probe = TransportProbe()

    with pytest.raises(execution.PredecessorValidationError, match=expected_code):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0
    assert report_path.exists()
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    exit_code = admission.main(
        [
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "HKEX",
            "--attempt-id",
            attempt_id,
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ]
    )

    captured = capfd.readouterr()
    assert exit_code == 2
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "attempt_id": attempt_id,
        "execute_authorized": True,
        "result": expected_code,
        "source_attempted": False,
    }
    assert set((output / "attempts").iterdir()) == {report_path.parent}


def test_module_cli_forged_complete_exact_restart_is_closed_and_nonzero(
    tmp_path: Path,
) -> None:
    """The real module CLI cannot turn a forged retained result into exit zero."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "module-cli-forged-complete"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_id = "module-cli-forged-complete"
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"retained-incomplete"),
    )
    report_path = output / "attempts" / attempt_id / "report.json"
    forged = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    assert forged["result"] != "COMPLETE"
    forged["result"] = "COMPLETE"
    forged_bytes = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
    report_path.write_bytes(forged_bytes)
    probe = tmp_path / "forged-restart-external-transport-used"
    child_site = tmp_path / "forged-restart-child-site"
    child_site.mkdir()
    (child_site / "sitecustomize.py").write_text(
        """import os
import socket
import urllib.request
from pathlib import Path

def _deny_external_effect(*args, **kwargs):
    Path(os.environ["ASKLEGAL_FIX10_EXTERNAL_PROBE"]).write_text("attempted")
    raise AssertionError("external transport reached")

urllib.request.OpenerDirector.open = _deny_external_effect
socket.create_connection = _deny_external_effect
socket.getaddrinfo = _deny_external_effect
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(child_site)
        if not existing_pythonpath
        else os.pathsep.join((str(child_site), existing_pythonpath))
    )
    environment["ASKLEGAL_FIX10_EXTERNAL_PROBE"] = str(probe)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.hk_v1_source_admission",
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "HKEX",
            "--attempt-id",
            attempt_id,
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 2
    assert result.stderr == b""
    assert json.loads(result.stdout) == {
        "attempt_id": attempt_id,
        "execute_authorized": True,
        "result": "PREDECESSOR_REPORT_MALFORMED",
        "source_attempted": False,
    }
    assert report_path.read_bytes() == forged_bytes
    assert not probe.exists()


def test_coordinated_gld_writer_claim_forgery_is_rederived_from_retained_bytes(
    tmp_path: Path,
) -> None:
    """Coherent stored CAPTURED/COMPLETE claims cannot override retained GLD challenge facts."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "coordinated-gld-forgery"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_id = "coordinated-gld-forgery"
    written = execute_source_family(
        authority_manifest=authority,
        source_family="GLD",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"challenge-not-traversed"),
    )
    assert written["result"] == "CHALLENGE_AUTHORITY_REQUIRED"
    report_path = output / "attempts" / attempt_id / "report.json"
    forged = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    endpoints = _items(forged, "endpoints")
    for endpoint in endpoints:
        endpoint["terminal_code"] = "CAPTURED"
    forged["endpoint_counts"] = {"CAPTURED": len(endpoints)}
    forged["source_procedures"] = [
        {
            "declared_member_count": len(endpoints),
            "source_id": "HK-LEG-GLD-EGAZETTE",
            "terminal_code": "COMPLETE",
        }
    ]
    forged["result"] = "COMPLETE"
    forged_bytes = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
    report_path.write_bytes(forged_bytes)
    direct_probe = TransportProbe()

    with pytest.raises(
        execution.PredecessorValidationError,
        match="PREDECESSOR_REPORT_MALFORMED",
    ):
        execute_source_family(
            authority_manifest=authority,
            source_family="GLD",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=direct_probe,
        )

    assert direct_probe.calls == 0
    assert report_path.read_bytes() == forged_bytes

    external_probe = tmp_path / "coordinated-gld-external-transport-used"
    child_site = tmp_path / "coordinated-gld-child-site"
    child_site.mkdir()
    (child_site / "sitecustomize.py").write_text(
        """import os
import socket
import urllib.request
from pathlib import Path

def _deny_external_effect(*args, **kwargs):
    Path(os.environ["ASKLEGAL_FIX11_EXTERNAL_PROBE"]).write_text("attempted")
    raise AssertionError("external transport reached")

urllib.request.OpenerDirector.open = _deny_external_effect
socket.create_connection = _deny_external_effect
socket.getaddrinfo = _deny_external_effect
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(child_site)
        if not existing_pythonpath
        else os.pathsep.join((str(child_site), existing_pythonpath))
    )
    environment["ASKLEGAL_FIX11_EXTERNAL_PROBE"] = str(external_probe)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.hk_v1_source_admission",
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "GLD",
            "--attempt-id",
            attempt_id,
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 2
    assert result.stderr == b""
    assert json.loads(result.stdout) == {
        "attempt_id": attempt_id,
        "execute_authorized": True,
        "result": "PREDECESSOR_REPORT_MALFORMED",
        "source_attempted": False,
    }
    assert report_path.read_bytes() == forged_bytes
    assert not external_probe.exists()


@pytest.mark.parametrize("source_family", ["HKEL", "JUDICIARY", "HKEX"])
def test_every_parser_family_rederives_coordinated_complete_claims_from_retained_bytes(
    tmp_path: Path,
    source_family: str,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Parser/procedure COMPLETE claims must match the retained source bytes that produced them."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / source_family.lower()
    )
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_id = f"{source_family.lower()}-coordinated-forgery"
    writer_transport: object = {
        "HKEL": _BasicLawContractChangedTransport(),
        "JUDICIARY": _JudiciaryContractChangedTransport(),
        "HKEX": _HKEXContractChangedTransport(),
    }[source_family]
    written = execute_source_family(
        authority_manifest=authority,
        source_family=source_family,
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=cast("execution.ReadOnlySourceTransport", writer_transport),
    )
    assert written["result"] != "COMPLETE"
    report_path = output / "attempts" / attempt_id / "report.json"
    forged = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    endpoints = _items(forged, "endpoints")
    for endpoint in endpoints:
        endpoint["terminal_code"] = "CAPTURED"
    forged["endpoint_counts"] = {"CAPTURED": len(endpoints)}
    for procedure in _items(forged, "source_procedures"):
        procedure["terminal_code"] = "COMPLETE"
    forged["result"] = "COMPLETE"
    forged_bytes = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
    report_path.write_bytes(forged_bytes)
    probe = TransportProbe()

    with pytest.raises(
        execution.PredecessorValidationError,
        match="PREDECESSOR_REPORT_MALFORMED",
    ):
        execute_source_family(
            authority_manifest=authority,
            source_family=source_family,
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0
    assert report_path.read_bytes() == forged_bytes
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    exit_code = admission.main(
        [
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            source_family,
            "--attempt-id",
            attempt_id,
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ]
    )
    captured = capfd.readouterr()
    assert exit_code == 2
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "attempt_id": attempt_id,
        "execute_authorized": True,
        "result": "PREDECESSOR_REPORT_MALFORMED",
        "source_attempted": False,
    }


def _mutate_dynamic_replay_url(  # noqa: C901
    source_family: str, mutation: str, report: dict[str, object]
) -> None:
    """Apply one literal hostile locator mutation without using production builders."""
    endpoints = _items(report, "endpoints")
    prefix = {
        "JUDICIARY_YEAR": "judiciary-year-",
        "JUDICIARY_DIS": "judiciary-dis-",
        "HKEX": "hkex-member-",
    }[source_family]
    endpoint = next(
        item for item in endpoints if cast("str", item["endpoint_id"]).startswith(prefix)
    )
    original = cast("str", endpoint["requested_url"])
    parsed = urlsplit(original)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if mutation == "wrong-path":
        changed = urlunsplit((parsed.scheme, parsed.netloc, "/not-rulebook/member", "", ""))
    elif mutation.startswith("missing-"):
        name = mutation.removeprefix("missing-")
        pairs = [(key, value) for key, value in pairs if key != name]
        changed = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), ""))
    elif mutation.startswith("extra-"):
        changed = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode([*pairs, ("extra", "1")]), "")
        )
    elif mutation.startswith("duplicate-"):
        name = mutation.removeprefix("duplicate-")
        value = next(value for key, value in pairs if key == name)
        changed = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode([*pairs, (name, value)]), "")
        )
    elif mutation.startswith("wrong-"):
        name = mutation.removeprefix("wrong-")
        changed = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode([(key, "wrong" if key == name else value) for key, value in pairs]),
                "",
            )
        )
    elif mutation == "encoded-path":
        changed = urlunsplit((parsed.scheme, parsed.netloc, "/rulebook/%2e%2e/member", "", ""))
    elif mutation == "traversal-path":
        changed = urlunsplit((parsed.scheme, parsed.netloc, "/rulebook/../member", "", ""))
    elif mutation == "userinfo":
        changed = urlunsplit((parsed.scheme, f"user@{parsed.netloc}", parsed.path, "", ""))
    elif mutation == "port":
        changed = urlunsplit((parsed.scheme, f"{parsed.netloc}:444", parsed.path, "", ""))
    else:
        raise AssertionError(mutation)
    endpoint["requested_url"] = changed
    if source_family == "HKEX":
        endpoint["endpoint_id"] = "hkex-member-" + hashlib.sha256(changed.encode()).hexdigest()[:24]


@pytest.mark.parametrize(
    ("source_kind", "mutation"),
    [
        ("JUDICIARY_YEAR", "missing-stem"),
        ("JUDICIARY_YEAR", "extra-control"),
        ("JUDICIARY_YEAR", "duplicate-year"),
        ("JUDICIARY_YEAR", "wrong-selallct"),
        ("JUDICIARY_YEAR", "wrong-txtSearch3"),
        ("JUDICIARY_DIS", "missing-DIS"),
        ("JUDICIARY_DIS", "missing-QS"),
        ("JUDICIARY_DIS", "missing-TP"),
        ("JUDICIARY_DIS", "extra-control"),
        ("JUDICIARY_DIS", "duplicate-DIS"),
        ("JUDICIARY_DIS", "wrong-QS"),
    ],
)
def test_dynamic_replay_locators_use_the_exact_authentic_source_grammar(
    tmp_path: Path,
    source_kind: str,
    mutation: str,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Missing, extra, duplicate, or widened locator facts reject before transport."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    source_family = "JUDICIARY"
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / f"{source_kind.lower()}-{mutation.lower()}"
    )
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_id = "hostile-" + hashlib.sha256(f"{source_kind}:{mutation}".encode()).hexdigest()[:24]
    writer_transport: object = _JudiciaryTransport()
    execute_source_family(
        authority_manifest=authority,
        source_family=source_family,
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=cast("execution.ReadOnlySourceTransport", writer_transport),
    )
    report_path = output / "attempts" / attempt_id / "report.json"
    forged = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    _mutate_dynamic_replay_url(source_kind, mutation, forged)
    forged_bytes = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
    report_path.write_bytes(forged_bytes)
    probe = TransportProbe()

    with pytest.raises(
        execution.PredecessorValidationError,
        match="PREDECESSOR_REPORT_MALFORMED",
    ):
        execute_source_family(
            authority_manifest=authority,
            source_family=source_family,
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0
    assert report_path.read_bytes() == forged_bytes
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    exit_code = admission.main(
        [
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            source_family,
            "--attempt-id",
            attempt_id,
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ]
    )
    captured = capfd.readouterr()
    assert exit_code == 2
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "attempt_id": attempt_id,
        "execute_authorized": True,
        "result": "PREDECESSOR_REPORT_MALFORMED",
        "source_attempted": False,
    }
    assert set((output / "attempts").iterdir()) == {report_path.parent}


def test_exact_restart_revalidates_its_complete_predecessor_evidence_chain(
    tmp_path: Path,
) -> None:
    """A replay with a predecessor rereads that predecessor before returning."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "exact-predecessor-readback"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    predecessor_id = "exact-replay-predecessor"
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=predecessor_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"predecessor-bytes"),
    )
    attempt_id = "exact-replay-successor"
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=attempt_id,
        predecessor_attempt_id=predecessor_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"successor-bytes"),
    )
    predecessor_report = cast(
        "dict[str, object]",
        json.loads((output / "attempts" / predecessor_id / "report.json").read_bytes()),
    )
    predecessor_object = output / cast(
        "str", _items(predecessor_report, "endpoints")[0]["object_key"]
    )
    predecessor_object.write_bytes(b"altered-predecessor-before-exact-replay")
    probe = TransportProbe()

    with pytest.raises(
        execution.PredecessorValidationError,
        match="PREDECESSOR_EVIDENCE_READBACK_INVALID",
    ):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0


def test_exact_restart_recomputes_change_state_from_verified_lineage_objects(
    tmp_path: Path,
) -> None:
    """A stored successor cannot relabel changed retained objects as no-change."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "exact-change-state"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    predecessor_id = "change-state-predecessor"
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=predecessor_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"state-a"),
    )
    attempt_id = "change-state-successor"
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=attempt_id,
        predecessor_attempt_id=predecessor_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"state-b"),
    )
    report_path = output / "attempts" / attempt_id / "report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    assert report["change_state"] == "CHANGED_OBSERVED"
    report["change_state"] = "NO_CHANGE_OBSERVED"
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))

    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_Transport(b"must-not-be-used"),
        )


@pytest.mark.parametrize("source_family", ["GLD", "HKEL", "JUDICIARY", "HKEX"])
def test_every_family_writer_report_remains_valid_for_exact_zero_transport_replay(
    tmp_path: Path, source_family: str
) -> None:
    """The unified restart validator accepts every family writer's own report."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / source_family.lower()
    )
    cutoff = "1998-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_id = f"{source_family.lower()}-writer-replay"
    writer_transport: object = {
        "GLD": _Transport(b"writer-compatible"),
        "HKEL": _ConfiguredHkelTransport(),
        "JUDICIARY": _JudiciaryTransport(),
        "HKEX": _HKEXTransport(),
    }[source_family]
    written = execute_source_family(
        authority_manifest=authority,
        source_family=source_family,
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=cast("execution.ReadOnlySourceTransport", writer_transport),
    )
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family=source_family,
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )

    assert replayed == written
    assert probe.calls == 0


def test_get_only_hkel_writer_replay_is_byte_identical_across_hash_seeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent optional session stages never change replay control flow or CLI bytes."""
    _install_synthetic_basic_law_contract(monkeypatch)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "get-only-hkel-hash-seeds"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_id = "get-only-hkel-writer-replay"
    written = execute_source_family(
        authority_manifest=authority,
        source_family="HKEL",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_DirectConfiguredHkelTransport(),
    )
    assert not any(
        cast("str", endpoint["endpoint_id"]).startswith("hkel-session-")
        for endpoint in _items(written, "endpoints")
    )
    assert any(
        endpoint["endpoint_id"] == "sep_000000000000000000000000000000000000000000000056"
        for endpoint in _items(written, "endpoints")
    )
    external_probe = tmp_path / "get-only-hkel-external-transport-used"
    child_site = tmp_path / "get-only-hkel-child-site"
    child_site.mkdir()
    (child_site / "sitecustomize.py").write_text(
        _synthetic_basic_law_contract_sitecustomize()
        + """import os
import socket
import urllib.request
from pathlib import Path

def _deny_external_effect(*args, **kwargs):
    Path(os.environ["ASKLEGAL_FIX12_EXTERNAL_PROBE"]).write_text("attempted")
    raise AssertionError("external transport reached")

urllib.request.OpenerDirector.open = _deny_external_effect
socket.create_connection = _deny_external_effect
socket.getaddrinfo = _deny_external_effect
""",
        encoding="utf-8",
    )
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    command = [
        sys.executable,
        "-m",
        "tools.hk_v1_source_admission",
        "--authority-manifest",
        str(authority),
        "--matrix",
        str(matrix),
        "--mode",
        "execute",
        "--source-family",
        "HKEL",
        "--attempt-id",
        attempt_id,
        "--observation-cutoff",
        cutoff,
        "--output-root",
        str(output),
    ]
    results: list[subprocess.CompletedProcess[bytes]] = []
    for seed in ("0", "1", "4", "7"):
        environment = dict(os.environ)
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(child_site)
            if not existing_pythonpath
            else os.pathsep.join((str(child_site), existing_pythonpath))
        )
        environment["ASKLEGAL_FIX12_EXTERNAL_PROBE"] = str(external_probe)
        environment["PYTHONHASHSEED"] = seed
        results.append(
            subprocess.run(  # noqa: S603
                command,
                cwd=REPOSITORY_ROOT,
                env=environment,
                check=False,
                capture_output=True,
                timeout=30,
            )
        )

    assert {result.returncode for result in results} == {0}
    assert {result.stderr for result in results} == {b""}
    assert len({result.stdout for result in results}) == 1
    assert json.loads(results[0].stdout) == written
    assert not external_probe.exists()


def test_module_cli_predecessor_failure_is_sanitized_and_makes_no_attempt_report(
    tmp_path: Path,
) -> None:
    """The real module CLI reports a pre-effect lineage error without traceback or effect."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "module-cli-predecessor-failure"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="existing-compatible-tip",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"tip"),
    )
    probe = tmp_path / "external-transport-used"
    child_site = tmp_path / "predecessor-child-site"
    child_site.mkdir()
    (child_site / "sitecustomize.py").write_text(
        """import os
import socket
import urllib.request
from pathlib import Path

def _deny_external_effect(*args, **kwargs):
    Path(os.environ["ASKLEGAL_FIX8_EXTERNAL_PROBE"]).write_text("attempted")
    raise AssertionError("external transport reached")

urllib.request.OpenerDirector.open = _deny_external_effect
socket.create_connection = _deny_external_effect
socket.getaddrinfo = _deny_external_effect
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(child_site)
        if not existing_pythonpath
        else os.pathsep.join((str(child_site), existing_pythonpath))
    )
    environment["ASKLEGAL_FIX8_EXTERNAL_PROBE"] = str(probe)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.hk_v1_source_admission",
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "HKEX",
            "--attempt-id",
            "module-cli-missing-predecessor",
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 2
    assert result.stderr == b""
    assert json.loads(result.stdout) == {
        "attempt_id": "module-cli-missing-predecessor",
        "execute_authorized": True,
        "result": "PREDECESSOR_ATTEMPT_REQUIRED",
        "source_attempted": False,
    }
    assert not probe.exists()
    assert not (output / "attempts/module-cli-missing-predecessor/report.json").exists()


def test_module_cli_predecessor_readback_failure_is_sanitized_and_pre_effect(
    tmp_path: Path,
) -> None:
    """The new evidence-readback code is closed CLI output with no source attempt."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "module-cli-predecessor-readback"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    predecessor_id = "cli-readback-predecessor"
    report = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id=predecessor_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"cli-readback"),
    )
    object_key = cast("str", _items(report, "endpoints")[0]["object_key"])
    (output / object_key).write_bytes(b"altered-before-cli")
    probe = tmp_path / "cli-readback-external-transport-used"
    child_site = tmp_path / "cli-readback-child-site"
    child_site.mkdir()
    (child_site / "sitecustomize.py").write_text(
        """import os
import socket
import urllib.request
from pathlib import Path

def _deny_external_effect(*args, **kwargs):
    Path(os.environ["ASKLEGAL_FIX9_EXTERNAL_PROBE"]).write_text("attempted")
    raise AssertionError("external transport reached")

urllib.request.OpenerDirector.open = _deny_external_effect
socket.create_connection = _deny_external_effect
socket.getaddrinfo = _deny_external_effect
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(child_site)
        if not existing_pythonpath
        else os.pathsep.join((str(child_site), existing_pythonpath))
    )
    environment["ASKLEGAL_FIX9_EXTERNAL_PROBE"] = str(probe)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    attempt_id = "module-cli-readback-failure"

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.hk_v1_source_admission",
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "HKEX",
            "--attempt-id",
            attempt_id,
            "--predecessor-attempt-id",
            predecessor_id,
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 2
    assert result.stderr == b""
    assert json.loads(result.stdout) == {
        "attempt_id": attempt_id,
        "execute_authorized": True,
        "result": "PREDECESSOR_EVIDENCE_READBACK_INVALID",
        "source_attempted": False,
    }
    assert not probe.exists()
    assert not (output / "attempts" / attempt_id / "report.json").exists()


def test_cli_never_labels_an_ordinary_same_text_value_error_as_pre_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the predecessor validator's typed failures may claim no source attempt."""
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "ordinary-same-text-error"
    )
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    same_text_error = "PREDECESSOR_ATTEMPT_REQUIRED"

    def ordinary_failure(**_kwargs: object) -> dict[str, object]:
        raise ValueError(same_text_error)

    monkeypatch.setattr(execution, "execute_source_family", ordinary_failure)

    with pytest.raises(ValueError, match="PREDECESSOR_ATTEMPT_REQUIRED"):
        admission.main(
            [
                "--authority-manifest",
                str(authority),
                "--matrix",
                str(matrix),
                "--mode",
                "execute",
                "--source-family",
                "HKEX",
                "--attempt-id",
                "ordinary-same-text-error",
                "--observation-cutoff",
                cutoff,
                "--output-root",
                str(output),
            ]
        )


def test_judiciary_current_frames_remain_incomplete_until_content_is_versioned(
    tmp_path: Path,
) -> None:
    """Exact current frame locators are evidence, not an unproved full-body completion claim."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    transport = _JudiciaryTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1998-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-baseline",
        observation_cutoff="1998-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    procedures = {item["source_id"]: item for item in _items(report, "source_procedures")}
    assert procedures["HK-CASE-JUDICIARY-LRS-INVENTORY"] == {
        "declared_member_count": 2,
        "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "terminal_code": "INCOMPLETE",
    }
    assert report["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"

    assert any("year=1997" in url for url in transport.urls)
    assert any("year=1998" in url for url in transport.urls)
    assert not any("DIS=1" in url for url in transport.urls)
    assert any("DIS=2" in url for url in transport.urls)
    assert any("DIS=3" in url for url in transport.urls)
    dynamic_urls = [url for url in transport.urls if "year=" in url or "DIS=" in url]
    assert "year=1997" in dynamic_urls[0]
    assert "year=1998" in dynamic_urls[1]
    assert dynamic_urls[2] == dynamic_urls[0]
    assert dynamic_urls[3] == dynamic_urls[1]
    assert all("DIS=" in url for url in dynamic_urls[4:])
    assert procedures["HK-CASE-HKLII-DISCOVERY"] == {
        "declared_member_count": 1,
        "source_id": "HK-CASE-HKLII-DISCOVERY",
        "terminal_code": "COMPLETE",
    }


def test_judiciary_enumerates_every_advertised_page_before_any_judgment_fetch(
    tmp_path: Path,
) -> None:
    """All listing pages are retained before any detail-frame transport effect."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "sequential-pagination"
    )
    transport = _JudiciarySequentialPaginationTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-sequential-pagination",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    dynamic_urls = [url for url in transport.urls if "year=1997" in url or "DIS=" in url]
    listing_url_prefix = (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
        "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
        "selallct=1&stem=1&txtselectopt3=5&day1=&month=&txtSearch3=%2F%2F1997&"
        "year=1997&page="
    )
    assert dynamic_urls[:4] == [
        f"{listing_url_prefix}1",
        f"{listing_url_prefix}2",
        f"{listing_url_prefix}1",
        f"{listing_url_prefix}2",
    ]
    assert all("DIS=" in url for url in dynamic_urls[4:])
    assert len(dynamic_urls[4:]) == 11
    procedures = {item["source_id"]: item for item in _items(report, "source_procedures")}
    assert procedures["HK-CASE-JUDICIARY-LRS-INVENTORY"] == {
        "declared_member_count": 11,
        "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "terminal_code": "INCOMPLETE",
    }
    assert report["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"

    @dataclass(slots=True)
    class ReplayProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_probe = ReplayProbe()
    replayed = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-sequential-pagination",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_probe,
    )
    assert replayed == report
    assert replay_probe.calls == 0


def test_judiciary_fetches_one_detail_per_unique_adjacent_boundary_identity(
    tmp_path: Path,
) -> None:
    """Eleven listing slots with one exact boundary overlap produce ten detail effects."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "boundary-overlap"
    )
    transport = _JudiciaryBoundaryOverlapTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-boundary-overlap",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    detail_urls = [url for url in transport.urls if "DIS=" in url]
    assert len(detail_urls) == 10
    assert sum("DIS=1010" in url for url in detail_urls) == 1
    procedures = {item["source_id"]: item for item in _items(report, "source_procedures")}
    assert procedures["HK-CASE-JUDICIARY-LRS-INVENTORY"] == {
        "declared_member_count": 10,
        "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "terminal_code": "INCOMPLETE",
    }
    assert report["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"


def test_judiciary_fetches_each_stable_repeated_identity_once_after_two_passes(
    tmp_path: Path,
) -> None:
    """Repeated listing slots never duplicate a detail effect after full-map equality."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "identity-repeat"
    )
    transport = _JudiciaryIdentityRepeatTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-identity-repeat",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    detail_urls = [url for url in transport.urls if "DIS=" in url]
    assert len(detail_urls) == 3
    assert sum("DIS=2" in url for url in detail_urls) == 1
    dynamic_ids = [
        cast("str", endpoint["endpoint_id"])
        for endpoint in _items(report, "endpoints")
        if cast("str", endpoint["endpoint_id"]).startswith("judiciary-")
    ]
    assert dynamic_ids == [
        "judiciary-year-1997-page-1",
        "judiciary-year-1997-verification-page-1",
        "judiciary-dis-2",
        "judiciary-dis-3",
        "judiciary-dis-4",
    ]


def test_judiciary_fetches_one_exact_source_advertised_rs_detail_after_two_passes(
    tmp_path: Path,
) -> None:
    """A stable exact RS mapping is requested once with its source type preserved."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "stable-rs"
    )
    transport = _JudiciaryRsTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-stable-rs",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    detail_urls = [url for url in transport.urls if "DIS=" in url]
    assert len(detail_urls) == 2
    assert sum(url.endswith("DIS=2&QS=%2B&TP=RS") for url in detail_urls) == 1
    assert report["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"


def test_judiciary_fetches_one_exact_source_advertised_rv_detail_after_two_passes(
    tmp_path: Path,
) -> None:
    """A stable exact RV mapping is requested once with its source type preserved."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "stable-rv"
    )
    transport = _JudiciaryRvTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-stable-rv",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    detail_urls = [url for url in transport.urls if "DIS=" in url]
    assert len(detail_urls) == 2, (
        report["result"],
        [
            (endpoint["endpoint_id"], endpoint["terminal_code"])
            for endpoint in _items(report, "endpoints")
        ],
    )
    assert sum(url.endswith("DIS=2&QS=%2B&TP=RV") for url in detail_urls) == 1
    assert report["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"


def test_judiciary_fetches_each_typed_optional_frame_detail_once_after_two_passes(
    tmp_path: Path,
) -> None:
    """Redundant third frames never duplicate canonical RS/RV detail effects."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "typed-optional-frames"
    )
    transport = _JudiciaryTypedOptionalFrameTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-typed-optional-frames",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    detail_urls = [url for url in transport.urls if "DIS=" in url]
    assert sum(url.endswith("DIS=2&QS=%2B&TP=RS") for url in detail_urls) == 1
    assert sum(url.endswith("DIS=4&QS=%2B&TP=RV") for url in detail_urls) == 1
    assert report["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"


def test_judiciary_attempt_s_direct_word_fetches_only_canonical_detail_once_after_two_passes(
    tmp_path: Path,
) -> None:
    """Presentation-only Word metadata never becomes a transport target."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "attempt-s-direct-word"
    )
    transport = _JudiciaryAttemptSDirectWordTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-attempt-s-direct-word",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert sum(url.endswith("DIS=2&QS=%2B&TP=JU") for url in transport.urls) == 1
    assert all("/doc/judg/word/" not in url for url in transport.urls)
    assert report["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"


@pytest.mark.parametrize("scope_case", ["IN_SCOPE", "CUTOFF_EXCLUDED"])
def test_judiciary_two_pass_rejects_jurv_locator_flip_before_details(
    tmp_path: Path,
    scope_case: str,
) -> None:
    """Full-map equality catches an RV source-type flip at every cutoff scope."""
    out_of_scope = scope_case == "CUTOFF_EXCLUDED"
    observation_cutoff = "1997-12-31T23:59:59+08:00"
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / f"rv-flip-{out_of_scope}"
    )
    transport = _JudiciaryRvSecondPassFlipTransport(out_of_scope=out_of_scope)
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff=observation_cutoff),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=f"judiciary-rv-flip-{str(out_of_scope).lower()}",
        observation_cutoff=observation_cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert not any("DIS=" in url for url in transport.urls)


@pytest.mark.parametrize(
    "scope_case",
    ["IN_SCOPE", "CUTOFF_EXCLUDED"],
)
def test_judiciary_two_pass_rejects_jurs_locator_flip_before_details(
    tmp_path: Path,
    scope_case: str,
) -> None:
    """Full-map equality catches a source-type flip at every cutoff scope."""
    out_of_scope = scope_case == "CUTOFF_EXCLUDED"
    observation_cutoff = "1997-12-31T23:59:59+08:00"
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / f"rs-flip-{out_of_scope}"
    )
    transport = _JudiciaryRsSecondPassFlipTransport(out_of_scope=out_of_scope)
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff=observation_cutoff),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=f"judiciary-rs-flip-{str(out_of_scope).lower()}",
        observation_cutoff=observation_cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert not any("DIS=" in url for url in transport.urls)


def test_judiciary_two_pass_rejects_raw_and_reported_accounting_drift(
    tmp_path: Path,
) -> None:
    """Equal unique maps cannot hide changed raw slots or publisher totals."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "accounting-drift"
    )
    transport = _JudiciarySecondPassAccountingDriftTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-accounting-drift",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert not any("DIS=" in url for url in transport.urls)
    assert [
        cast("str", endpoint["endpoint_id"])
        for endpoint in _items(report, "endpoints")
        if cast("str", endpoint["endpoint_id"]).startswith("judiciary-year-")
    ] == ["judiciary-year-1997-page-1", "judiciary-year-1997-verification-page-1"]


def test_judiciary_two_pass_rejects_page_count_drift_with_equal_unique_map(
    tmp_path: Path,
) -> None:
    """An added verification page cannot be hidden by one identical repeated identity."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "page-count-drift"
    )
    transport = _JudiciarySecondPassPageCountDriftTransport()
    clock = _JudiciaryClock()
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-page-count-drift",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert not any("DIS=" in url for url in transport.urls)


def test_judiciary_two_pass_full_mapping_drift_is_fail_visible_without_details(
    tmp_path: Path,
) -> None:
    """A valid second listing with one changed identity cannot authorize detail effects."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "two-pass-drift"
    )
    transport = _JudiciarySecondPassDriftTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-two-pass-drift",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert not any("DIS=" in url for url in transport.urls)
    dynamic = [
        item
        for item in _items(report, "endpoints")
        if cast("str", item["endpoint_id"]).startswith("judiciary-year-")
    ]
    assert len(dynamic) == 4
    assert all(item["terminal_code"] == "CAPTURED" for item in dynamic)
    procedures = {item["source_id"]: item for item in _items(report, "source_procedures")}
    assert procedures["HK-CASE-JUDICIARY-LRS-INVENTORY"] == {
        "declared_member_count": 0,
        "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "terminal_code": "SOURCE_CONTRACT_CHANGED",
    }
    assert report["result"] == "SOURCE_CONTRACT_CHANGED"


def test_judiciary_second_pass_parser_drift_labels_the_exact_page(tmp_path: Path) -> None:
    """A bad verification page is retained and only that page is contract-changed."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "two-pass-parser-drift"
    )
    clock = _JudiciaryClock()
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-two-pass-parser-drift",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_JudiciarySecondPassParserDriftTransport(),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    terminals = {
        cast("str", item["endpoint_id"]): item["terminal_code"]
        for item in _items(report, "endpoints")
    }
    assert terminals["judiciary-year-1997-page-1"] == "CAPTURED"
    assert terminals["judiciary-year-1997-page-2"] == "CAPTURED"
    assert terminals["judiciary-year-1997-verification-page-1"] == "CAPTURED"
    assert terminals["judiciary-year-1997-verification-page-2"] == "SOURCE_CONTRACT_CHANGED"
    assert not any(endpoint_id.startswith("judiciary-dis-") for endpoint_id in terminals)


def test_judiciary_two_pass_compares_cutoff_excluded_identities(tmp_path: Path) -> None:
    """Full-map equality includes rows that are excluded from downstream detail effects."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "out-of-scope-map-drift"
    )
    transport = _JudiciaryOutOfScopeSecondPassDriftTransport()
    clock = _JudiciaryClock()
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-out-of-scope-map-drift",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert not any("DIS=" in url for url in transport.urls)


def test_judiciary_all_years_are_verified_before_any_detail_effect(tmp_path: Path) -> None:
    """A later-year map drift blocks details derived from every earlier year."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "later-year-map-drift"
    )
    transport = _JudiciaryLaterYearSecondPassDriftTransport()
    clock = _JudiciaryClock()
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1998-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-later-year-map-drift",
        observation_cutoff="1998-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert not any("DIS=" in url for url in transport.urls)


def test_judiciary_cross_year_identity_duplicate_rejects_before_details(tmp_path: Path) -> None:
    """One identity cannot occupy two year partitions or produce duplicate effects."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "cross-year-duplicate"
    )
    transport = _JudiciaryCrossYearDuplicateTransport()
    clock = _JudiciaryClock()
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1998-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-cross-year-duplicate",
        observation_cutoff="1998-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert not any("DIS=" in url for url in transport.urls)

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    replayed = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1998-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-cross-year-duplicate",
        observation_cutoff="1998-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )
    assert replayed == report
    assert probe.calls == 0


@pytest.mark.parametrize("mutation", ["missing", "reordered", "wrong_url", "wrong_version"])
def test_judiciary_two_pass_replay_rejects_dynamic_chain_forgery(
    tmp_path: Path, mutation: str
) -> None:
    """Replay reconstructs the exact two chains instead of trusting retained endpoint order."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / mutation
    )
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    clock = _JudiciaryClock()
    report = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=f"judiciary-two-pass-forgery-{mutation.replace('_', '-')}",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_JudiciarySequentialPaginationTransport(),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    endpoints = cast("list[dict[str, object]]", report["endpoints"])
    verification = [
        index
        for index, endpoint in enumerate(endpoints)
        if "verification-page" in cast("str", endpoint["endpoint_id"])
    ]
    if mutation == "missing":
        endpoints.pop(verification[-1])
    elif mutation == "reordered":
        endpoints[verification[0]], endpoints[verification[1]] = (
            endpoints[verification[1]],
            endpoints[verification[0]],
        )
    elif mutation == "wrong_url":
        endpoints[verification[0]]["requested_url"] = (
            cast("str", endpoints[verification[0]]["requested_url"]) + "&page=2"
        )
    else:
        endpoints[verification[0]]["endpoint_version"] = "1.0.5"
    report_path = output / "attempts" / cast("str", report["attempt_id"]) / "report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=cast("str", report["attempt_id"]),
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


def test_judiciary_parser_drift_is_a_retained_fail_visible_terminal(tmp_path: Path) -> None:
    """A reachable changed result contract writes evidence and never escapes as an exception."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-contract-drift",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_JudiciaryContractChangedTransport(),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert _items(report, "source_procedures") == [
        {
            "declared_member_count": 1,
            "source_id": "HK-CASE-HKLII-DISCOVERY",
            "terminal_code": "COMPLETE",
        },
        {
            "declared_member_count": 0,
            "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
            "terminal_code": "INCOMPLETE",
        },
    ]


def test_judiciary_changed_later_page_retains_triggering_page_and_never_completes(
    tmp_path: Path,
) -> None:
    """A retained later page with wrong current-page state remains fail-visible."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    transport = _JudiciaryUnsupportedPaginationTransport()
    clock = _JudiciaryClock()

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-unsupported-pagination",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    trigger = next(
        item
        for item in _items(report, "endpoints")
        if item["endpoint_id"] == "judiciary-year-1997-page-2"
    )
    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert trigger["terminal_code"] == "SOURCE_CONTRACT_CHANGED"
    assert type(trigger["object_key"]) is str
    assert any("page=2" in url for url in transport.urls)
    assert _items(report, "source_procedures")[1]["terminal_code"] == "INCOMPLETE"


def _judiciary_search_form_drift_attempt(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """Write one disposable current-bound report stopped by the static form parser."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-search-form-drift"
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()
    report = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-search-form-drift",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_JudiciarySearchFormContractChangedTransport(),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    return authority, output, report


def test_judiciary_static_search_form_drift_replays_with_zero_transport_effects(
    tmp_path: Path,
) -> None:
    """The writer's retained static-form drift report must replay before any request."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _judiciary_search_form_drift_attempt(tmp_path)
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-search-form-drift",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )

    assert replayed == report
    assert probe.calls == 0


def test_judiciary_false_captured_search_form_without_dynamic_page_rejects_pre_effect(
    tmp_path: Path,
) -> None:
    """A forged complete static trace cannot use parser drift to omit year evidence."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _judiciary_search_form_drift_attempt(tmp_path)
    endpoints = cast("list[dict[str, object]]", report["endpoints"])
    static_search = next(
        item for item in endpoints if cast("str", item["endpoint_id"]).endswith("204")
    )
    static_search["terminal_code"] = "CAPTURED"
    report["endpoint_counts"] = {"CAPTURED": len(endpoints)}
    procedures = cast("list[dict[str, object]]", report["source_procedures"])
    next(item for item in procedures if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY")[
        "terminal_code"
    ] = "COMPLETE"
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-search-form-drift/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    probe = TransportProbe()

    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-search-form-drift",
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0


def test_judiciary_request_starts_are_serial_and_two_seconds_apart(tmp_path: Path) -> None:
    """Removing the Judiciary request-start controller would permit a publisher burst."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    clock = _JudiciaryClock()
    transport = _TimedJudiciaryTransport(clock)

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-request-spacing",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"
    assert len(transport.starts) > 1
    assert all(
        later - earlier >= 2.0
        for earlier, later in zip(transport.starts, transport.starts[1:], strict=False)
    )


def test_judiciary_budget_stops_before_count_ceiling_next_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping the pre-transport count check would exceed the declared request ceiling."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 1, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    clock = _JudiciaryClock()
    transport = _TimedJudiciaryTransport(clock)

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-request-budget",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert len(transport.urls) == 1
    assert report["result"] == "OBSERVATION_BUDGET_EXHAUSTED"
    assert _items(report, "source_procedures")[1]["terminal_code"] == "BUDGET_EXHAUSTED"

    class ReplayTransport:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ReplayTransport()
    replay = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-request-budget",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replay == report
    assert replay_transport.calls == 0


def test_judiciary_stopped_replay_rereads_and_rejects_corrupt_retained_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skipping stopped evidence read-back would let a corrupt partial observation replay."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 1, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()
    written = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-corrupt-stopped-replay",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_TimedJudiciaryTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    endpoint = _items(written, "endpoints")[0]
    (output / cast("str", endpoint["object_key"])).write_bytes(b"corrupt")

    class ReplayTransport:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ReplayTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-corrupt-stopped-replay",
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=replay_transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert replay_transport.calls == 0


def test_judiciary_stopped_replay_rejects_dynamic_before_static_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial traversal evidence cannot claim a dynamic page before static prerequisites."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 5, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()
    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-dynamic-before-static",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_TimedJudiciaryTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    report_path = output / "attempts" / "judiciary-dynamic-before-static" / "report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    endpoints = cast("list[dict[str, object]]", report["endpoints"])
    assert endpoints[-1]["endpoint_id"] == "judiciary-year-1997-page-1"
    endpoints[-1], endpoints[-2] = endpoints[-2], endpoints[-1]
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    class ReplayTransport:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ReplayTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-dynamic-before-static",
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=replay_transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert replay_transport.calls == 0


def test_judiciary_stopped_replay_rejects_later_evidence_after_absent_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stopped dynamic trace cannot retain a later detail after omitting an earlier one."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 10, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1998-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()

    class Extra1997JudiciaryTransport(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if "year=1997" in url:
                self.starts.append(self._clock.value)
                self.urls.append(url)
                body = _current_judiciary_result_body(
                    year=1997,
                    reported_pages=1,
                    rows=(
                        (1, "30/06/1997"),
                        (20, "01/07/1997"),
                        (21, "02/07/1997"),
                    ),
                )
                return CapturedResponse(200, "text/html", body, None)
            return super().get(url=url, max_bytes=max_bytes)

    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-omitted-detail-with-later-evidence",
        observation_cutoff="1998-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=Extra1997JudiciaryTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    report_path = (
        output / "attempts" / "judiciary-omitted-detail-with-later-evidence" / "report.json"
    )
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    endpoints = cast("list[dict[str, object]]", report["endpoints"])
    report["endpoints"] = [
        endpoint for endpoint in endpoints if endpoint["endpoint_id"] != "judiciary-dis-20"
    ]
    report["endpoint_counts"] = {"CAPTURED": 9}
    stop = cast("dict[str, object]", report["observation_stop"])
    stop["code"] = "OBSERVATION_EXECUTION_FAILURE"
    stop["request_starts"] = 9
    stop["retained_response_bytes"] = sum(
        cast("int", endpoint["byte_length"]) for endpoint in report["endpoints"]
    )
    procedures = cast("list[dict[str, object]]", report["source_procedures"])
    procedures[1]["terminal_code"] = "OBSERVATION_EXECUTION_FAILURE"
    report["result"] = execution._derived_report_result(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        report["endpoint_counts"], procedures
    )
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    class ReplayTransport:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ReplayTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-omitted-detail-with-later-evidence",
            observation_cutoff="1998-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=replay_transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert replay_transport.calls == 0


@pytest.mark.parametrize("stop_before", ["detail", "page"])
def test_judiciary_stopped_replay_allows_the_next_unstarted_dynamic_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop_before: str
) -> None:
    """A stop immediately before the next required page or detail remains replayable."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 5, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()

    class TwoPageJudiciaryTransport(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if stop_before == "page" and "year=1997" in url and "page=1" in url:
                self.starts.append(self._clock.value)
                self.urls.append(url)
                body = (
                    b"<p>2 results / 2 pages</p><tr><td>01/07/1997</td>"
                    b'<td><a href="?DIS=2">new</a></td></tr>'
                )
                return CapturedResponse(200, "text/html", body, None)
            return super().get(url=url, max_bytes=max_bytes)

    attempt_id = "judiciary-stop-before-" + stop_before
    written = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=TwoPageJudiciaryTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    class ReplayTransport:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ReplayTransport()
    replay = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )

    assert replay == written
    assert replay_transport.calls == 0


@pytest.mark.parametrize("dynamic_state", ["complete", "failed"])
def test_judiciary_stopped_replay_rejects_completed_or_failed_dynamic_trace(
    tmp_path: Path, dynamic_state: str
) -> None:
    """A stop cannot relabel a completed or already terminal dynamic traversal."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()
    contract_changed = dynamic_state == "failed"
    attempt_id = "judiciary-stop-after-" + dynamic_state + "-dynamic"
    transport: _JudiciaryTransport = (
        _JudiciaryContractChangedTransport() if contract_changed else _JudiciaryTransport()
    )
    written = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    report_path = output / "attempts" / attempt_id / "report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    profile = execution._judiciary_observation_profile()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    endpoints = cast("list[dict[str, object]]", report["endpoints"])
    report["observation_stop"] = {
        "code": "OBSERVATION_EXECUTION_FAILURE",
        "profile": profile,
        "profile_fingerprint": execution._digest(execution._canonical(profile)),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        "request_starts": len(endpoints),
        "rejected_response_bytes": 0,
        "retained_response_bytes": sum(cast("int", item["byte_length"]) for item in endpoints),
        "elapsed_seconds": 0.0,
    }
    procedures = cast("list[dict[str, object]]", report["source_procedures"])
    procedures[1]["terminal_code"] = "OBSERVATION_EXECUTION_FAILURE"
    report["result"] = execution._derived_report_result(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        cast("dict[str, int]", report["endpoint_counts"]), procedures
    )
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    class ReplayTransport:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ReplayTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=replay_transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert written["result"] in {
        "EVIDENCE_CAPTURED_INCOMPLETE",
        "SOURCE_CONTRACT_CHANGED",
    }
    assert replay_transport.calls == 0


def test_judiciary_stopped_replay_rejects_a_self_consistent_weakened_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A smaller report-selected budget must not masquerade as the V1 profile."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 1, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()
    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-forged-stop-profile",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_TimedJudiciaryTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    report_path = output / "attempts" / "judiciary-forged-stop-profile" / "report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    stop = cast("dict[str, object]", report["observation_stop"])
    profile = cast("dict[str, object]", stop["profile"])
    profile["request_start_limit"] = 2
    stop["profile_fingerprint"] = execution._digest(execution._canonical(profile))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-forged-stop-profile",
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=_JudiciaryTransport(),
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )


def test_judiciary_stopped_replay_rejects_a_nonexhausted_request_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stop-code relabel must not turn an elapsed stop into a count-budget stop."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 2, raising=False)
    monkeypatch.setattr(execution, "_JUDICIARY_ELAPSED_SECONDS_LIMIT", 1.0, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()
    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-forged-request-stop",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_TimedJudiciaryTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    report_path = output / "attempts" / "judiciary-forged-request-stop" / "report.json"
    report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    stop = cast("dict[str, object]", report["observation_stop"])
    assert stop["code"] == "ELAPSED_TIME_BUDGET_EXHAUSTED"
    stop["code"] = "REQUEST_BUDGET_EXHAUSTED"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-forged-request-stop",
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=_JudiciaryTransport(),
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )


def test_judiciary_budget_stop_with_predecessor_never_reports_no_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Equal retained prefixes must not call two budget stops a no-change observation."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 1, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")

    def execute_budget_stop(attempt_id: str, predecessor: str | None = None) -> dict[str, object]:
        clock = _JudiciaryClock()
        return execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor,
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=_TimedJudiciaryTransport(clock),
            judiciary_clock=clock.monotonic,
            judiciary_sleeper=clock.sleep,
        )

    first = execute_budget_stop("judiciary-budget-predecessor-a")
    second = execute_budget_stop("judiciary-budget-predecessor-b", cast("str", first["attempt_id"]))

    assert first["result"] == "OBSERVATION_BUDGET_EXHAUSTED"
    assert second["result"] == "OBSERVATION_BUDGET_EXHAUSTED"
    assert second["change_state"] == "CHANGED_OBSERVED"


@pytest.mark.parametrize(
    ("stop_code", "procedure_terminal"),
    [
        ("REQUEST_BUDGET_EXHAUSTED", "BUDGET_EXHAUSTED"),
        ("OBSERVATION_EXECUTION_FAILURE", "OBSERVATION_EXECUTION_FAILURE"),
    ],
)
def test_judiciary_stopped_child_replays_with_zero_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stop_code: str,
    procedure_terminal: str,
) -> None:
    """Lineage replay must preserve the writer's bounded-child change-state rule."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 1, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")

    def execute_budget_stop(attempt_id: str, predecessor: str | None = None) -> dict[str, object]:
        clock = _JudiciaryClock()
        return execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor,
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=_TimedJudiciaryTransport(clock),
            judiciary_clock=clock.monotonic,
            judiciary_sleeper=clock.sleep,
        )

    first = execute_budget_stop("judiciary-lineage-budget-a")
    child = execute_budget_stop("judiciary-lineage-budget-b", cast("str", first["attempt_id"]))
    if stop_code != "REQUEST_BUDGET_EXHAUSTED":
        report_path = output / "attempts" / "judiciary-lineage-budget-b" / "report.json"
        child = cast("dict[str, object]", json.loads(report_path.read_bytes()))
        stop = cast("dict[str, object]", child["observation_stop"])
        stop["code"] = stop_code
        accounting = cast("dict[str, object]", child["observation_accounting"])
        accounting["stop_code"] = stop_code
        procedures = cast("list[dict[str, object]]", child["source_procedures"])
        procedures[1]["terminal_code"] = procedure_terminal
        child["result"] = execution._derived_report_result(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            cast("dict[str, int]", child["endpoint_counts"]), procedures
        )
        report_path.write_bytes(execution._canonical(child))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    class ReplayTransport:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ReplayTransport()
    replay = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-lineage-budget-b",
        predecessor_attempt_id=cast("str", first["attempt_id"]),
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )

    assert replay == child
    assert replay["change_state"] == "CHANGED_OBSERVED"
    assert replay_transport.calls == 0


def test_judiciary_retries_one_exact_transport_failure_and_retains_both_attempts(
    tmp_path: Path,
) -> None:
    """The initial normalized transport failure is evidence, not the final logical result."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    clock = _JudiciaryClock()

    class OneFailureTransport(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            _ = max_bytes
            self.starts.append(self._clock.value)
            self.urls.append(url)
            if len(self.urls) == 1:
                raise OSError
            return _JudiciaryTransport().get(url=url, max_bytes=max_bytes)

    transport = OneFailureTransport(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-one-transport-attempt",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] != "SOURCE_OUTAGE"
    failed_url = transport.urls[0]
    assert transport.urls.count(failed_url) == 2
    assert transport.starts[1] - transport.starts[0] >= 2.0
    attempts = _items(report, "transport_attempts")
    matching = [item for item in attempts if item["requested_url"] == failed_url]
    assert [item["attempt_number"] for item in matching] == [1, 2]
    assert [item["sequence"] for item in matching] == [1, 2]
    logical = next(
        item for item in _items(report, "endpoints") if item["requested_url"] == failed_url
    )
    assert logical["terminal_code"] == "CAPTURED"
    assert logical["body_fingerprint"] == matching[-1]["body_fingerprint"]


def test_judiciary_two_eligible_failures_are_one_final_outage_without_a_third_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second normalized failure is final evidence, never an unbounded retry loop."""
    registered_endpoints = execution._registered_endpoints  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def one_judiciary_endpoint(
        source_family: str,
        *,
        judiciary_endpoint_204_version: str | None = None,
        hkex_historical_attempt_id: str | None = None,
    ) -> tuple[object, ...]:
        endpoints = registered_endpoints(
            source_family,
            judiciary_endpoint_204_version=judiciary_endpoint_204_version,
            hkex_historical_attempt_id=hkex_historical_attempt_id,
        )
        return endpoints[:1] if source_family == "JUDICIARY" else endpoints

    monkeypatch.setattr(execution, "_registered_endpoints", one_judiciary_endpoint)
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class TwoFailures(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            _ = max_bytes
            self.starts.append(self._clock.value)
            self.urls.append(url)
            raise OSError

    transport = TwoFailures(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-two-outages",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    assert report["result"] == "SOURCE_OUTAGE"
    assert len(transport.urls) == 2
    assert transport.urls[0] == transport.urls[1]
    attempts = _items(report, "transport_attempts")
    first_url = transport.urls[0]
    first_attempts = [item for item in attempts if item["requested_url"] == first_url]
    assert [item["attempt_number"] for item in first_attempts] == [1, 2]
    first_logical = next(
        item for item in _items(report, "endpoints") if item["requested_url"] == first_url
    )
    assert first_logical["terminal_code"] == "OUTAGE"


def test_judiciary_exact_maintenance_outage_retries_once_then_continues(
    tmp_path: Path,
) -> None:
    """The exact publisher-maintenance sentinel is physical OUTAGE, then may recover."""
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class MaintenanceThenValid(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.starts.append(self._clock.value)
            self.urls.append(url)
            if len(self.urls) == 1:
                return CapturedResponse(200, "text/plain", _JUDICIARY_MAINTENANCE_BODY, url)
            return _JudiciaryTransport().get(url=url, max_bytes=max_bytes)

    transport = MaintenanceThenValid(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-maintenance-recovery",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    requested = transport.urls[0]
    matching = [
        item for item in _items(report, "transport_attempts") if item["requested_url"] == requested
    ]
    logical = next(
        item for item in _items(report, "endpoints") if item["requested_url"] == requested
    )
    assert execution_policy()["name"] == "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0"
    assert transport.urls[:2] == [requested, requested]
    assert transport.starts[1] - transport.starts[0] >= 2.0
    assert [item["terminal_code"] for item in matching] == ["OUTAGE", "CAPTURED"]
    assert logical["terminal_code"] == "CAPTURED"
    assert report["result"] != "SOURCE_OUTAGE"
    assert "http://www.judiciary.hk/maintenance" not in transport.urls


def test_judiciary_exact_server_error_retries_once_then_continues(
    tmp_path: Path,
) -> None:
    """An exact admitted publisher HTTP 500 is physical OUTAGE, then may recover."""
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class ServerErrorThenValid(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.starts.append(self._clock.value)
            self.urls.append(url)
            if len(self.urls) == 1:
                return CapturedResponse(
                    500,
                    "application/problem+json",
                    b'{"temporary":"publisher server error"}',
                    url,
                )
            return _JudiciaryTransport().get(url=url, max_bytes=max_bytes)

    transport = ServerErrorThenValid(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-server-error-recovery",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    requested = transport.urls[0]
    matching = [
        item for item in _items(report, "transport_attempts") if item["requested_url"] == requested
    ]
    logical = next(
        item for item in _items(report, "endpoints") if item["requested_url"] == requested
    )
    assert execution_policy()["name"] == "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0"
    assert transport.urls[:2] == [requested, requested]
    assert transport.starts[1] - transport.starts[0] >= 2.0
    assert [item["terminal_code"] for item in matching] == ["OUTAGE", "CAPTURED"]
    assert logical["terminal_code"] == "CAPTURED"
    assert report["result"] != "SOURCE_OUTAGE"


def test_judiciary_two_exact_server_errors_stop_without_a_third_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repeated admitted HTTP 500 is one logical outage with two physical attempts."""
    registered_endpoints = execution._registered_endpoints  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def one_judiciary_endpoint(
        source_family: str,
        *,
        judiciary_endpoint_204_version: str | None = None,
        hkex_historical_attempt_id: str | None = None,
    ) -> tuple[OfficialEndpointContract, ...]:
        endpoints = registered_endpoints(
            source_family,
            judiciary_endpoint_204_version=judiciary_endpoint_204_version,
            hkex_historical_attempt_id=hkex_historical_attempt_id,
        )
        return endpoints[:1] if source_family == "JUDICIARY" else endpoints

    monkeypatch.setattr(execution, "_registered_endpoints", one_judiciary_endpoint)
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class ServerErrorTwice(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            _ = max_bytes
            self.starts.append(self._clock.value)
            self.urls.append(url)
            return CapturedResponse(500, "text/html", b"publisher server error", url)

    transport = ServerErrorTwice(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-two-server-errors",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_OUTAGE"
    assert len(transport.urls) == 2
    assert transport.urls[0] == transport.urls[1]
    assert transport.starts[1] - transport.starts[0] >= 2.0
    attempts = _items(report, "transport_attempts")
    assert [item["attempt_number"] for item in attempts] == [1, 2]
    assert [item["terminal_code"] for item in attempts] == ["OUTAGE", "OUTAGE"]
    assert _items(report, "endpoints")[0]["terminal_code"] == "OUTAGE"


@pytest.mark.parametrize(
    ("redirect_rejected", "expected_terminal", "expected_result"),
    [
        (False, "TRUNCATED", "TRUNCATED_RESPONSE"),
        (True, "SOURCE_CONTRACT_CHANGED", "SOURCE_CONTRACT_CHANGED"),
    ],
)
def test_judiciary_truncated_server_error_is_final_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    redirect_rejected: bool,  # noqa: FBT001 - exact hostile fact is parameterized.
    expected_terminal: str,
    expected_result: str,
) -> None:
    """A server-error body beyond the request bound cannot enter the retry state."""
    registered_endpoints = execution._registered_endpoints  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def one_small_judiciary_endpoint(
        source_family: str,
        *,
        judiciary_endpoint_204_version: str | None = None,
        hkex_historical_attempt_id: str | None = None,
    ) -> tuple[OfficialEndpointContract, ...]:
        endpoints = registered_endpoints(
            source_family,
            judiciary_endpoint_204_version=judiciary_endpoint_204_version,
            hkex_historical_attempt_id=hkex_historical_attempt_id,
        )
        if source_family != "JUDICIARY":
            return endpoints
        return (replace(endpoints[0], max_bytes=8),)

    monkeypatch.setattr(execution, "_registered_endpoints", one_small_judiciary_endpoint)
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class TruncatedServerError(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.starts.append(self._clock.value)
            self.urls.append(url)
            assert max_bytes == 8
            return CapturedResponse(
                500,
                "text/html",
                b"123456789",
                url,
                redirect_rejected=redirect_rejected,
            )

    transport = TruncatedServerError(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-truncated-server-error",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert len(transport.urls) == 1
    attempts = _items(report, "transport_attempts")
    assert len(attempts) == 1
    assert attempts[0]["terminal_code"] == expected_terminal
    assert _items(report, "endpoints")[0]["terminal_code"] == expected_terminal
    assert report["result"] == expected_result

    class ExplodingReplay:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ExplodingReplay()
    replayed = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-truncated-server-error",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replayed == report
    assert replay_transport.calls == 0

    if redirect_rejected:
        return

    forged = cast("dict[str, object]", json.loads(execution._canonical(report)))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    forged_attempts = _items(forged, "transport_attempts")
    second = dict(forged_attempts[0])
    second["sequence"] = 2
    second["attempt_number"] = 2
    second["start_elapsed_seconds"] = 2.0
    cast("list[object]", forged["transport_attempts"]).append(second)
    accounting = cast("dict[str, object]", forged["observation_accounting"])
    accounting["request_starts"] = 2
    accounting["retained_response_bytes"] = 18
    accounting["elapsed_seconds"] = 2.0
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execution._validate_judiciary_retry_report(forged)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    report_path = output / "attempts/judiciary-truncated-server-error/report.json"
    report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-truncated-server-error",
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=replay_transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert replay_transport.calls == 0


def test_judiciary_two_exact_maintenance_outages_stop_without_third_or_body_follow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeated exact maintenance is one logical outage and never follows embedded script."""
    registered_endpoints = execution._registered_endpoints  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def one_judiciary_endpoint(
        source_family: str,
        *,
        judiciary_endpoint_204_version: str | None = None,
        hkex_historical_attempt_id: str | None = None,
    ) -> tuple[OfficialEndpointContract, ...]:
        endpoints = registered_endpoints(
            source_family,
            judiciary_endpoint_204_version=judiciary_endpoint_204_version,
            hkex_historical_attempt_id=hkex_historical_attempt_id,
        )
        return endpoints[:1] if source_family == "JUDICIARY" else endpoints

    monkeypatch.setattr(execution, "_registered_endpoints", one_judiciary_endpoint)
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class MaintenanceTwice(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            _ = max_bytes
            self.starts.append(self._clock.value)
            self.urls.append(url)
            return CapturedResponse(200, "text/plain", _JUDICIARY_MAINTENANCE_BODY, url)

    transport = MaintenanceTwice(clock)
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    report = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-maintenance-outage",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert report["result"] == "SOURCE_OUTAGE"
    assert len(transport.urls) == 2
    assert transport.urls[0] == transport.urls[1]
    assert transport.urls[0].startswith("https://")
    assert "http://www.judiciary.hk/maintenance" not in transport.urls
    assert [item["terminal_code"] for item in _items(report, "transport_attempts")] == [
        "OUTAGE",
        "OUTAGE",
    ]
    assert [item["terminal_code"] for item in _items(report, "endpoints")] == ["OUTAGE"]

    class NoReplayTransport:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = NoReplayTransport()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-maintenance-outage",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replayed == report
    assert replay_transport.calls == 0


def test_judiciary_maintenance_retry_obeys_request_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Maintenance eligibility cannot bypass the shared bounded-observation controller."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 1, raising=False)
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class MaintenanceOnce(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            _ = max_bytes
            self.starts.append(self._clock.value)
            self.urls.append(url)
            return CapturedResponse(200, "text/plain", _JUDICIARY_MAINTENANCE_BODY, url)

    transport = MaintenanceOnce(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-maintenance-budget",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert len(transport.urls) == 1
    assert [item["terminal_code"] for item in _items(report, "transport_attempts")] == ["OUTAGE"]
    assert _items(report, "endpoints") == []
    assert report["result"] == "OBSERVATION_BUDGET_EXHAUSTED"


@pytest.mark.parametrize(
    ("limit", "field"),
    [(1, "_JUDICIARY_REQUEST_START_LIMIT"), (1.0, "_JUDICIARY_ELAPSED_SECONDS_LIMIT")],
)
def test_judiciary_budget_before_retry_retains_only_the_eligible_first_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: float, field: str
) -> None:
    """Retry must use the ordinary controller rather than bypassing count/time ceilings."""
    monkeypatch.setattr(execution, field, limit, raising=False)
    attempt_id = (
        "judiciary-budget-before-retry-request"
        if field == "_JUDICIARY_REQUEST_START_LIMIT"
        else "judiciary-budget-before-retry-elapsed"
    )
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class OneFailure(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            _ = max_bytes
            self.starts.append(self._clock.value)
            self.urls.append(url)
            raise OSError

    transport = OneFailure(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    assert len(transport.urls) == 1
    assert len(_items(report, "transport_attempts")) == 1
    assert _items(report, "endpoints") == []
    assert report["result"] == "OBSERVATION_BUDGET_EXHAUSTED"
    accounting = cast("dict[str, object]", report["observation_accounting"])
    assert accounting["stop_code"] in {"REQUEST_BUDGET_EXHAUSTED", "ELAPSED_TIME_BUDGET_EXHAUSTED"}

    class ReplayProbe:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = ReplayProbe()
    replayed = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleeper")),
    )
    assert replayed == report
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("shape", "mutation"),
    [
        ("static", "id"),
        ("static", "version"),
        ("static", "url"),
        ("static", "max-bytes"),
        ("dynamic", "id"),
        ("dynamic", "version"),
        ("dynamic", "url"),
        ("dynamic", "max-bytes"),
    ],
)
def test_judiciary_retry_stopped_physical_group_must_bind_exact_next_request(  # noqa: C901
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, mutation: str
) -> None:
    """An eligible retained first attempt is bound to the exact blocked next request."""
    limit = 1 if shape == "static" else 5
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", limit, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / f"stopped-{shape}-{mutation}"
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()

    class FailureAtBlockedRequest(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if shape == "static" or "year=1997" in url:
                self.starts.append(self._clock.value)
                self.urls.append(url)
                raise OSError
            return super().get(url=url, max_bytes=max_bytes)

    attempt_id = f"judiciary-stopped-{shape}-{mutation}"
    written = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=FailureAtBlockedRequest(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    if shape == "static":
        assert _items(written, "endpoints") == []
    else:
        assert _items(written, "endpoints")
    report_path = output / "attempts" / attempt_id / "report.json"
    forged = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    stopped = _items(forged, "transport_attempts")[-1]
    if shape == "static":
        registered = execution._registered_endpoints("JUDICIARY")  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        alternate = registered[1]
        if mutation == "id":
            stopped["endpoint_id"] = alternate.endpoint_id
            stopped["endpoint_version"] = alternate.version
            stopped["requested_url"] = alternate.url
            stopped["max_bytes"] = alternate.max_bytes
        elif mutation == "version":
            stopped["endpoint_version"] = "9.9.9"
        elif mutation == "url":
            stopped["requested_url"] = alternate.url
        else:
            stopped["max_bytes"] = cast("int", stopped["max_bytes"]) - 1
    else:
        url = cast("str", stopped["requested_url"])
        changed_query = [
            (key, "2" if key == "page" else value) for key, value in parse_qsl(urlsplit(url).query)
        ]
        alternate_url = urlunsplit((*urlsplit(url)[:3], urlencode(changed_query), ""))
        if mutation == "id":
            stopped["endpoint_id"] = "judiciary-year-1997-page-2"
            stopped["requested_url"] = alternate_url
        elif mutation == "version":
            stopped["endpoint_version"] = "9.9.9"
        elif mutation == "url":
            stopped["requested_url"] = alternate_url
        else:
            stopped["max_bytes"] = cast("int", stopped["max_bytes"]) - 1
    report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    class ExplodingReplay:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = ExplodingReplay()
    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleeper")),
        )
    assert probe.calls == 0


def test_judiciary_byte_rejected_retry_is_not_retained_or_projected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second response crossing the byte ceiling cannot become a logical capture."""
    monkeypatch.setattr(execution, "_JUDICIARY_RETAINED_BYTE_LIMIT", 0, raising=False)
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class FailThenBody(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            _ = max_bytes
            self.starts.append(self._clock.value)
            self.urls.append(url)
            if len(self.urls) == 1:
                raise OSError
            return CapturedResponse(200, "text/html", b"second-body", url)

    transport = FailThenBody(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-byte-retry",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    assert len(transport.urls) == 2
    assert len(_items(report, "transport_attempts")) == 1
    assert _items(report, "endpoints") == []
    accounting = cast("dict[str, object]", report["observation_accounting"])
    assert accounting["request_starts"] == 2
    assert accounting["retained_response_bytes"] == 0
    assert accounting["rejected_response_bytes"] == len(b"second-body")


@pytest.mark.parametrize(
    "shape",
    [
        "no-retry-success",
        "retry-success",
        "double-outage",
        "request-stop",
        "elapsed-stop",
        "byte-rejected-stop",
    ],
)
def test_fresh_judiciary_schema_11_reports_replay_with_zero_effects(  # noqa: C901
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    """Every fresh schema-1.1 report shape replays byte- and metadata-identically."""
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / shape
    )
    clock = _JudiciaryClock()
    attempt_id = f"judiciary-schema11-{shape}"
    if shape == "request-stop":
        monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 1)
    elif shape == "elapsed-stop":
        monkeypatch.setattr(execution, "_JUDICIARY_ELAPSED_SECONDS_LIMIT", 1.0)
    elif shape == "byte-rejected-stop":
        monkeypatch.setattr(execution, "_JUDICIARY_RETAINED_BYTE_LIMIT", 0)

    class ShapeTransport(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.starts.append(self._clock.value)
            self.urls.append(url)
            if (
                shape in {"retry-success", "request-stop", "elapsed-stop", "byte-rejected-stop"}
                and len(self.urls) == 1
            ):
                raise OSError
            if (shape == "double-outage" and len(self.urls) <= 2) or shape in {
                "request-stop",
                "elapsed-stop",
            }:
                raise OSError
            if shape == "byte-rejected-stop" and len(self.urls) == 2:
                return CapturedResponse(200, "text/html", b"second-body", url)
            return _JudiciaryTransport().get(url=url, max_bytes=max_bytes)

    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    first = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=ShapeTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    expected_stop = {
        "request-stop": "REQUEST_BUDGET_EXHAUSTED",
        "elapsed-stop": "ELAPSED_TIME_BUDGET_EXHAUSTED",
        "byte-rejected-stop": "BYTE_BUDGET_EXHAUSTED",
    }.get(shape)
    if expected_stop is not None:
        assert (
            cast("dict[str, object]", first["observation_accounting"])["stop_code"] == expected_stop
        )
    if shape == "double-outage":
        assert first["result"] == "SOURCE_OUTAGE"

    def snapshot() -> dict[str, tuple[str, int, int, int]]:
        return {
            path.relative_to(output).as_posix(): (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_size,
                path.stat().st_mode,
                path.stat().st_mtime_ns,
            )
            for path in sorted(output.rglob("*"))
            if path.is_file()
        }

    before = snapshot()

    class ExplodingTransport:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            raise AssertionError((url, max_bytes))

    replay = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=ExplodingTransport(),
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleeper")),
    )
    assert replay == first
    assert snapshot() == before


@pytest.mark.parametrize(
    "response",
    [
        CapturedResponse(503, "application/octet-stream", b"", None),
        CapturedResponse(0, "application/octet-stream", b"nonempty", None),
        CapturedResponse(0, "text/plain", b"", None),
        CapturedResponse(0, "application/octet-stream", b"", "https://www.hklii.hk/en/cases"),
        CapturedResponse(0, "application/octet-stream", b"", None, redirect_rejected=True),
    ],
    ids=["status", "body", "media", "final-url", "redirect-rejected"],
)
def test_judiciary_only_the_exact_normalized_failure_is_retry_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, response: CapturedResponse
) -> None:
    """Changing any retry-eligibility field makes the first physical response final."""
    registered_endpoints = execution._registered_endpoints  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def one_judiciary_endpoint(
        source_family: str,
        *,
        judiciary_endpoint_204_version: str | None = None,
        hkex_historical_attempt_id: str | None = None,
    ) -> tuple[OfficialEndpointContract, ...]:
        endpoints = registered_endpoints(
            source_family,
            judiciary_endpoint_204_version=judiciary_endpoint_204_version,
            hkex_historical_attempt_id=hkex_historical_attempt_id,
        )
        return endpoints[:1] if source_family == "JUDICIARY" else endpoints

    monkeypatch.setattr(execution, "_registered_endpoints", one_judiciary_endpoint)
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class OneResponse(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            _ = max_bytes
            self.starts.append(self._clock.value)
            self.urls.append(url)
            return response

    transport = OneResponse(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-eligibility-" + response.media_type.replace("/", "-"),
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    assert len(transport.urls) == 1
    assert len(_items(report, "transport_attempts")) == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"status": False},
        {"status": 0.0},
        {"body": bytearray()},
        {"body": memoryview(b"")},
        {"media_type": b"application/octet-stream"},
        {"final_url": 0},
        {"redirect_rejected": 0},
    ],
)
def test_judiciary_retry_eligibility_is_runtime_type_exact(fields: dict[str, object]) -> None:
    """Adapter-malformed normalized facts cannot enter the retry state machine."""
    values: dict[str, object] = {
        "status": 0,
        "body": b"",
        "media_type": "application/octet-stream",
        "final_url": None,
        "redirect_rejected": False,
    }
    values.update(fields)
    assert retry_eligible(**values) is False  # type: ignore[arg-type]


def test_judiciary_exact_maintenance_tuple_is_retry_eligible() -> None:
    """Only the authentic bounded response at its exact requested HTTPS URL is eligible."""
    requested_url = "https://legalref.judiciary.hk/lrs/common/search/search_result.jsp?page=259"
    assert len(_JUDICIARY_MAINTENANCE_BODY) == 255
    assert hashlib.sha256(_JUDICIARY_MAINTENANCE_BODY).hexdigest() == (
        "39f0a4df3dc88efbd6216caeaa03dc9fd1acbed9e73a477508e86f7e4229594f"
    )
    assert retry_eligible(
        status=200,
        body=_JUDICIARY_MAINTENANCE_BODY,
        media_type="text/plain",
        final_url=requested_url,
        redirect_rejected=False,
        requested_url=requested_url,
    )


@pytest.mark.parametrize("status", [500, 502, 503, 504])
@pytest.mark.parametrize(
    ("body", "media_type"),
    [(b"", "text/html"), (b"bounded publisher error", "application/problem+json")],
)
def test_judiciary_closed_server_error_statuses_are_retry_eligible(
    status: int, body: bytes, media_type: str
) -> None:
    """Only the closed transient server/gateway status set admits any retained body/media."""
    requested_url = "https://legalref.judiciary.hk/lrs/common/search/search_result.jsp?page=259"
    assert retry_eligible(
        status=status,
        body=body,
        media_type=media_type,
        final_url=requested_url,
        redirect_rejected=False,
        requested_url=requested_url,
        max_bytes=len(body),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "status-400",
        "status-404",
        "status-429",
        "status-501",
        "status-505",
        "final-url-none",
        "final-url-drift",
        "redirect-rejected",
        "requested-http",
        "old-policy",
    ],
)
def test_judiciary_server_error_retry_rejects_every_boundary_variant(mutation: str) -> None:
    """Client errors, redirects, URL drift, non-HTTPS, and old policies remain final."""
    requested_url = "https://legalref.judiciary.hk/lrs/common/search/search_result.jsp?page=259"
    values: dict[str, object] = {
        "status": 500,
        "body": b"bounded publisher error",
        "media_type": "text/html",
        "final_url": requested_url,
        "redirect_rejected": False,
        "requested_url": requested_url,
        "max_bytes": len(b"bounded publisher error"),
    }
    if mutation.startswith("status-"):
        values["status"] = int(mutation.removeprefix("status-"))
    elif mutation == "final-url-none":
        values["final_url"] = None
    elif mutation == "final-url-drift":
        values["final_url"] = requested_url + "&changed=1"
    elif mutation == "redirect-rejected":
        values["redirect_rejected"] = True
    elif mutation == "requested-http":
        values["requested_url"] = requested_url.replace("https://", "http://")
        values["final_url"] = values["requested_url"]
    else:
        values["policy_name"] = "JUDICIARY_TRANSPORT_ATTEMPTS_1.1.0"
    assert retry_eligible(**values) is False  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "mutation",
    [
        "maximum-attempts-float",
        "redirect-integer",
        "status-float",
        "status-unknown",
        "status-order",
        "body-sentinel",
    ],
)
def test_judiciary_policy_120_recognition_is_canonical_and_type_exact(mutation: str) -> None:
    """A self-consistent fingerprint cannot make a mutated profile a recognized policy."""
    policy = execution_policy()
    assert recognized_execution_policy(policy, execution_policy_fingerprint()) == (
        "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0"
    )
    eligibility = cast("dict[str, object]", policy["retry_eligibility"])
    server_error = cast("dict[str, object]", eligibility["publisher_server_error"])
    statuses = cast("list[object]", server_error["statuses"])
    if mutation == "maximum-attempts-float":
        policy["maximum_attempts_per_logical_request"] = 2.0
    elif mutation == "redirect-integer":
        server_error["redirect_rejected"] = 0
    elif mutation == "status-float":
        statuses[0] = 500.0
    elif mutation == "status-unknown":
        statuses[0] = 501
    elif mutation == "status-order":
        statuses.reverse()
    else:
        server_error["body_byte_length"] = "ANY_BODY"
    fingerprint = "sha256:" + hashlib.sha256(execution._canonical(policy)).hexdigest()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    assert recognized_execution_policy(policy, fingerprint) is None


@pytest.mark.parametrize(
    "mutation",
    [
        "status",
        "media",
        "body-prefix",
        "body-suffix",
        "final-none",
        "final-other",
        "redirect",
        "requested-http",
        "body-http-target",
    ],
)
def test_judiciary_maintenance_retry_rejects_every_tuple_variant(mutation: str) -> None:
    """Near-maintenance pages remain ordinary fail-closed responses without retry."""
    requested_url = "https://legalref.judiciary.hk/lrs/common/search/search_result.jsp?page=259"
    values: dict[str, object] = {
        "status": 200,
        "body": _JUDICIARY_MAINTENANCE_BODY,
        "media_type": "text/plain",
        "final_url": requested_url,
        "redirect_rejected": False,
        "requested_url": requested_url,
    }
    if mutation == "status":
        values["status"] = 201
    elif mutation == "media":
        values["media_type"] = "text/html"
    elif mutation == "body-prefix":
        values["body"] = b" " + _JUDICIARY_MAINTENANCE_BODY[1:]
    elif mutation == "body-suffix":
        values["body"] = _JUDICIARY_MAINTENANCE_BODY + b"\n"
    elif mutation == "final-none":
        values["final_url"] = None
    elif mutation == "final-other":
        values["final_url"] = requested_url + "&changed=1"
    elif mutation == "redirect":
        values["redirect_rejected"] = True
    elif mutation == "requested-http":
        values["requested_url"] = requested_url.replace("https://", "http://")
        values["final_url"] = values["requested_url"]
    else:
        values["body"] = _JUDICIARY_MAINTENANCE_BODY.replace(
            b"http://www.judiciary.hk/maintenance",
            b"https://www.judiciary.hk/maintenanc",
        )
    assert retry_eligible(**values) is False  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("name", "endpoint_id", "second", "terminal"),
    [
        (
            "http-error",
            "sep_000000000000000000000000000000000000000000000201",
            CapturedResponse(503, "text/html", b"unavailable", None),
            "OUTAGE",
        ),
        (
            "empty-200",
            "sep_000000000000000000000000000000000000000000000201",
            CapturedResponse(200, "text/html", b"", None),
            "EMPTY_RESPONSE",
        ),
        (
            "truncated",
            "sep_000000000000000000000000000000000000000000000201",
            CapturedResponse(200, "text/html", b"x" * 8_388_609, None),
            "TRUNCATED",
        ),
        (
            "redirect-rejected",
            "sep_000000000000000000000000000000000000000000000201",
            CapturedResponse(200, "text/html", b"body", None, redirect_rejected=True),
            "SOURCE_CONTRACT_CHANGED",
        ),
        (
            "off-host-drift",
            "sep_000000000000000000000000000000000000000000000201",
            CapturedResponse(200, "text/html", b"body", "https://evil.invalid/redirect"),
            "SOURCE_CONTRACT_CHANGED",
        ),
    ],
)
def test_judiciary_second_attempt_is_final_for_all_terminal_outcomes(  # noqa: PLR0913, PLR0917
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    endpoint_id: str,
    second: CapturedResponse,
    terminal: str,
) -> None:
    """The retry is bounded even when its final evidence becomes a non-success terminal."""
    registered_endpoints = execution._registered_endpoints  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def selected_endpoint(
        source_family: str,
        *,
        judiciary_endpoint_204_version: str | None = None,
        hkex_historical_attempt_id: str | None = None,
    ) -> tuple[OfficialEndpointContract, ...]:
        endpoints = registered_endpoints(
            source_family,
            judiciary_endpoint_204_version=judiciary_endpoint_204_version,
            hkex_historical_attempt_id=hkex_historical_attempt_id,
        )
        return (
            tuple(item for item in endpoints if item.endpoint_id == endpoint_id)
            if source_family == "JUDICIARY"
            else endpoints
        )

    monkeypatch.setattr(execution, "_registered_endpoints", selected_endpoint)
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class FirstFailureThenFinal(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            _ = max_bytes
            self.starts.append(self._clock.value)
            self.urls.append(url)
            if len(self.urls) == 1:
                raise OSError
            return second

    transport = FirstFailureThenFinal(clock)
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=f"judiciary-final-{name}",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    assert len(transport.urls) == 2
    attempts = _items(report, "transport_attempts")
    assert [item["attempt_number"] for item in attempts] == [1, 2]
    assert len(_items(report, "endpoints")) == 1
    logical = _items(report, "endpoints")[0]
    assert logical["terminal_code"] == terminal
    assert logical["body_fingerprint"] == attempts[-1]["body_fingerprint"]


def test_judiciary_second_captured_search_form_is_parser_reclassified_without_third_start(
    tmp_path: Path,
) -> None:
    """A retry-success response may still be reclassified only by the strict form parser."""
    output = (
        REPOSITORY_ROOT / "var/test-hk-v1-source-execution" / tmp_path.parent.name / tmp_path.name
    )
    clock = _JudiciaryClock()

    class FirstFormFailure(_JudiciarySearchFormContractChangedTransport):
        form_calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if "isadvsearch=1" in url and "year=" not in url:
                self.form_calls += 1
                if self.form_calls == 1:
                    self.urls.append(url)
                    return CapturedResponse(0, "application/octet-stream", b"", None)
            return super().get(url=url, max_bytes=max_bytes)

    transport = FirstFormFailure()
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-retry-parser-drift",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    form_attempts = [
        item
        for item in _items(report, "transport_attempts")
        if "isadvsearch=1" in cast("str", item["requested_url"])
    ]
    assert transport.form_calls == 2
    assert [item["attempt_number"] for item in form_attempts] == [1, 2]
    logical = next(
        item
        for item in _items(report, "endpoints")
        if item["endpoint_id"] == form_attempts[-1]["endpoint_id"]
    )
    assert logical["terminal_code"] == "SOURCE_CONTRACT_CHANGED"


@pytest.mark.parametrize(
    "mutation",
    [
        "group-max-bytes",
        "forged-physical-terminal",
        "malformed-physical-final-url",
        "extra-logical-without-physical",
        "elapsed-before-last-start",
        "forged-stop-code",
    ],
)
def test_judiciary_retry_replay_rejects_physical_ledger_forgery_before_effects(
    tmp_path: Path, mutation: str
) -> None:
    """A physical ledger is an independently checkable replay boundary, not a hint."""
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / mutation
    )
    clock = _JudiciaryClock()

    class OneFailureTransport(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.starts.append(self._clock.value)
            self.urls.append(url)
            if len(self.urls) == 1:
                raise OSError
            return _JudiciaryTransport().get(url=url, max_bytes=max_bytes)

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-hostile-ledger",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=OneFailureTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    forged = cast("dict[str, object]", json.loads(execution._canonical(report)))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    attempts = _items(forged, "transport_attempts")
    accounting = cast("dict[str, object]", forged["observation_accounting"])
    if mutation == "group-max-bytes":
        attempts[1]["max_bytes"] = cast("int", attempts[1]["max_bytes"]) - 1
    elif mutation == "forged-physical-terminal":
        attempts[0]["terminal_code"] = "CAPTURED"
    elif mutation == "malformed-physical-final-url":
        attempts[0]["final_url"] = "not-a-url"
    elif mutation == "extra-logical-without-physical":
        logical = _items(forged, "endpoints")
        extra = dict(logical[-1])
        extra["endpoint_id"] = "judiciary-year-1997-page-999"
        cast("list[object]", forged["endpoints"]).append(extra)
        counts = cast("dict[str, int]", forged["endpoint_counts"])
        counts[cast("str", extra["terminal_code"])] += 1
    elif mutation == "elapsed-before-last-start":
        accounting["elapsed_seconds"] = 0.0
    else:
        forged["observation_stop"] = {
            "code": "REQUEST_BUDGET_EXHAUSTED",
            "elapsed_seconds": 0.0,
            "profile": execution._judiciary_observation_profile(),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            "profile_fingerprint": execution._digest(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
                execution._canonical(execution._judiciary_observation_profile())  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            ),
            "rejected_response_bytes": 0,
            "request_starts": len(attempts),
            "retained_response_bytes": sum(cast("int", item["byte_length"]) for item in attempts),
        }
        accounting["stop_code"] = "REQUEST_BUDGET_EXHAUSTED"

    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execution._validate_judiciary_retry_report(forged)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001


@pytest.mark.parametrize(
    "mutation",
    [
        "sequence-gap",
        "reordered-physical-groups",
        "stopped-group-not-final",
        "attempt-two-alone",
        "third-attempt",
        "noneligible-first-with-retry",
        "registered-max-bytes",
        "logical-final-mismatch",
        "policy-fingerprint",
        "policy-integer-as-float",
        "policy-boolean-as-integer",
        "accounting-rejected-without-stop",
        "accounting-elapsed-without-stop",
        "first-start-not-zero",
        "malformed-final-url",
        "missing-attempt-object",
        "attempt-object-key",
        "attempt-fingerprint",
        "attempt-byte-length",
        "corrupt-attempt-bytes",
        "dynamic-max-bytes",
    ],
)
def test_judiciary_retry_hostiles_reject_on_public_zero_effect_replay(  # noqa: C901, PLR0912, PLR0915
    tmp_path: Path, mutation: str
) -> None:
    """All retained-report forgeries are rejected before a replay can use an effect capability."""
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / mutation
    )
    clock = _JudiciaryClock()

    class OneFailureTransport(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.starts.append(self._clock.value)
            self.urls.append(url)
            if len(self.urls) == 1:
                raise OSError
            return _JudiciaryTransport().get(url=url, max_bytes=max_bytes)

    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    attempt_id = "judiciary-public-hostile"
    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=OneFailureTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    report_path = output / "attempts" / attempt_id / "report.json"
    forged = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    attempts = _items(forged, "transport_attempts")
    accounting = cast("dict[str, object]", forged["observation_accounting"])
    if mutation == "sequence-gap":
        attempts[1]["sequence"] = 3
    elif mutation == "reordered-physical-groups":
        first_group = attempts[:2]
        attempts[:3] = [attempts[2], *first_group]
        for sequence, item in enumerate(attempts, start=1):
            item["sequence"] = sequence
            item["start_elapsed_seconds"] = float((sequence - 1) * 2)
        accounting["elapsed_seconds"] = max(
            cast("float", accounting["elapsed_seconds"]),
            cast("float", attempts[-1]["start_elapsed_seconds"]),
        )
    elif mutation == "stopped-group-not-final":
        cast("list[object]", forged["transport_attempts"]).pop(1)
        first_logical = _items(forged, "endpoints").pop(0)
        counts = cast("dict[str, int]", forged["endpoint_counts"])
        counts[cast("str", first_logical["terminal_code"])] -= 1
        for sequence, item in enumerate(attempts, start=1):
            item["sequence"] = sequence
            item["start_elapsed_seconds"] = float((sequence - 1) * 2)
        profile = execution._judiciary_observation_profile()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        accounting["stop_code"] = "REQUEST_BUDGET_EXHAUSTED"
        accounting["request_starts"] = len(attempts)
        accounting["retained_response_bytes"] = sum(
            cast("int", item["byte_length"]) for item in attempts
        )
        accounting["elapsed_seconds"] = cast("float", attempts[-1]["start_elapsed_seconds"])
        forged["observation_stop"] = {
            "code": "REQUEST_BUDGET_EXHAUSTED",
            "elapsed_seconds": accounting["elapsed_seconds"],
            "profile": profile,
            "profile_fingerprint": execution._digest(execution._canonical(profile)),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            "rejected_response_bytes": 0,
            "request_starts": len(attempts),
            "retained_response_bytes": accounting["retained_response_bytes"],
        }
    elif mutation == "attempt-two-alone":
        cast("list[object]", forged["transport_attempts"]).pop(0)
        attempts[0]["attempt_number"] = 2
        attempts[0]["sequence"] = 1
    elif mutation == "third-attempt":
        third = dict(attempts[1])
        third["sequence"] = len(attempts) + 1
        third["attempt_number"] = 3
        cast("list[object]", forged["transport_attempts"]).append(third)
    elif mutation == "noneligible-first-with-retry":
        attempts[0]["status"] = 503
    elif mutation == "registered-max-bytes":
        for item in attempts[:2]:
            item["max_bytes"] = cast("int", item["max_bytes"]) - 1
    elif mutation == "logical-final-mismatch":
        _items(forged, "endpoints")[0]["requested_url"] = "https://www.hklii.hk/en/cases?forged=1"
    elif mutation == "policy-fingerprint":
        forged["execution_policy_fingerprint"] = "sha256:" + "f" * 64
    elif mutation == "policy-integer-as-float":
        policy = cast("dict[str, object]", forged["execution_policy"])
        policy["maximum_attempts_per_logical_request"] = 2.0
    elif mutation == "policy-boolean-as-integer":
        policy = cast("dict[str, object]", forged["execution_policy"])
        eligibility = cast("dict[str, object]", policy["retry_eligibility"])
        normalized = cast("dict[str, object]", eligibility["normalized_transport_failure"])
        normalized["redirect_rejected"] = 0
    elif mutation == "accounting-rejected-without-stop":
        accounting["rejected_response_bytes"] = 1
    elif mutation == "accounting-elapsed-without-stop":
        accounting["elapsed_seconds"] = 1_000_000.0
    elif mutation == "first-start-not-zero":
        attempts[0]["start_elapsed_seconds"] = 1.0
        attempts[1]["start_elapsed_seconds"] = 3.0
        accounting["elapsed_seconds"] = max(3.0, cast("float", accounting["elapsed_seconds"]))
    elif mutation == "malformed-final-url":
        attempts[0]["final_url"] = "https://legalref.judiciary.hk:444/not-valid"
    elif mutation == "missing-attempt-object":
        (output / cast("str", attempts[0]["object_key"])).unlink()
    elif mutation == "attempt-object-key":
        attempts[0]["object_key"] = "objects/" + "f" * 64 + ".bin"
    elif mutation == "attempt-fingerprint":
        attempts[0]["body_fingerprint"] = "sha256:" + "f" * 64
    elif mutation == "attempt-byte-length":
        attempts[0]["byte_length"] = 1
    elif mutation == "dynamic-max-bytes":
        dynamic = next(
            item
            for item in attempts
            if cast("str", item["endpoint_id"]).startswith("judiciary-year-")
        )
        # Keep the response physically CAPTURED: this must test binding to the
        # actual executor request ceiling, not merely terminal rederivation.
        dynamic["max_bytes"] = cast("int", dynamic["max_bytes"]) - 1
        logical = next(
            item
            for item in _items(forged, "endpoints")
            if item["endpoint_id"] == dynamic["endpoint_id"]
        )
        logical["requested_url"] = dynamic["requested_url"]
    else:
        (output / cast("str", attempts[0]["object_key"])).write_bytes(b"corrupted")
    report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    class ExplodingReplay:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = ExplodingReplay()
    expected_code = (
        "PREDECESSOR_EVIDENCE_READBACK_INVALID"
        if mutation in {"missing-attempt-object", "corrupt-attempt-bytes"}
        else "PREDECESSOR_REPORT_MALFORMED"
    )
    with pytest.raises(ValueError, match=expected_code):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleeper")),
        )
    assert probe.calls == 0


def test_judiciary_budget_rejects_a_response_that_crosses_retained_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing the pre-retention byte check would persist the response that exceeds 64 GiB."""
    fixture = _JudiciaryTransport()
    session_entry_body = fixture.get(
        url="https://legalref.judiciary.hk/lrs/common/index.jsp?target=newjudgments&lan=en",
        max_bytes=8_388_608,
    ).body
    first_body = fixture.get(
        url="https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?isadvsearch=1",
        max_bytes=16_777_216,
    ).body
    static_bytes = (
        2 * len(b"<html>current signal</html>") + len(session_entry_body) + len(first_body)
    )
    monkeypatch.setattr(execution, "_JUDICIARY_RETAINED_BYTE_LIMIT", static_bytes, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    clock = _JudiciaryClock()
    transport = _TimedJudiciaryTransport(clock)

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-byte-budget",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    endpoints = _items(report, "endpoints")
    assert len(transport.urls) == len(endpoints) + 1
    assert len(endpoints) == 4
    assert sum(cast("int", item["byte_length"]) for item in endpoints) == static_bytes
    assert report["result"] == "OBSERVATION_BUDGET_EXHAUSTED"


def test_judiciary_elapsed_budget_stops_before_next_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing elapsed-time enforcement would make the 72-hour observation unbounded."""
    monkeypatch.setattr(execution, "_JUDICIARY_ELAPSED_SECONDS_LIMIT", 1.0, raising=False)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    clock = _JudiciaryClock()
    transport = _TimedJudiciaryTransport(clock)

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-elapsed-budget",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert len(transport.urls) == 1
    assert report["result"] == "OBSERVATION_BUDGET_EXHAUSTED"


def test_judiciary_replay_does_not_sleep_or_call_transport(tmp_path: Path) -> None:
    """Moving the controller ahead of replay detection would create replay effects."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authority = _authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00")
    clock = _JudiciaryClock()
    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-replay-budget",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_TimedJudiciaryTransport(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    class ReplayTransport:
        calls = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ReplayTransport()
    replay = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-replay-budget",
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )

    assert replay["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"
    assert replay_transport.calls == 0


@pytest.mark.parametrize("failure", [RuntimeError("clock"), ValueError("sleeper")])
def test_judiciary_ordinary_clock_or_sleeper_failure_is_sanitized(
    tmp_path: Path, failure: Exception
) -> None:
    """Letting ordinary controller failures escape would leave an unreported partial attempt."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    clock = _JudiciaryClock()

    def failed_clock() -> float:
        if clock.value:
            raise failure
        return clock.value

    def failed_sleep(_seconds: float) -> None:
        raise failure

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-controller-failure-" + type(failure).__name__.lower(),
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_JudiciaryTransport(),
        judiciary_clock=failed_clock,
        judiciary_sleeper=failed_sleep,
    )

    assert report["result"] == "OBSERVATION_EXECUTION_FAILURE"


@pytest.mark.parametrize(
    ("clock_values", "case"),
    [((0.0, 0.0), "no-progress"), ((0.0, float("nan")), "non-finite"), ((0.0, -1.0), "backward")],
)
def test_judiciary_no_progress_or_invalid_clock_is_a_sanitized_failure(
    tmp_path: Path, clock_values: tuple[float, float], case: str
) -> None:
    """Accepting a no-op sleeper or invalid clock would violate the two-second start boundary."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    values = iter(clock_values)

    def clock() -> float:
        return next(values)

    transport = _JudiciaryTransport()
    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-clock-sanity-" + case,
        observation_cutoff="1997-12-31T23:59:59+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock,
        judiciary_sleeper=lambda _seconds: None,
    )

    assert report["result"] == "OBSERVATION_EXECUTION_FAILURE"
    assert len(transport.urls) == 1


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit()])
def test_judiciary_controller_base_exceptions_remain_visible(
    tmp_path: Path, failure: BaseException
) -> None:
    """Catching BaseException would hide explicit interruption and process termination."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    calls = 0

    def interrupted_clock() -> float:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise failure
        return 0.0

    with pytest.raises(type(failure)):
        execute_source_family(
            authority_manifest=_authority(tmp_path, cutoff="1997-12-31T23:59:59+08:00"),
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-base-exception-" + type(failure).__name__.lower(),
            observation_cutoff="1997-12-31T23:59:59+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=_JudiciaryTransport(),
            judiciary_clock=interrupted_clock,
            judiciary_sleeper=lambda _seconds: None,
        )


def test_hkel_configured_session_and_data_catalogues_complete_every_bound_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exact 5+15 portal membership completes with one request per unique content URL."""
    _install_synthetic_basic_law_contract(monkeypatch)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    transport = _ConfiguredHkelTransport()
    report = execute_source_family(
        authority_manifest=_authority(tmp_path),
        source_family="HKEL",
        output_root=output,
        attempt_id="hkel-configured-complete",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
    )

    assert transport.configured
    assert report["result"] == "COMPLETE"
    assert len(_items(report, "source_procedures")) == 5
    procedures = {
        cast("str", item["source_id"]): item for item in _items(report, "source_procedures")
    }
    assert procedures["HK-LEG-BASIC-LAW-PORTAL"] == {
        "declared_member_count": 20,
        "source_id": "HK-LEG-BASIC-LAW-PORTAL",
        "terminal_code": "COMPLETE",
    }
    assert all(item["terminal_code"] == "COMPLETE" for item in procedures.values())
    assert all(transport.urls.count(url) == 1 for url in _BASIC_LAW_MEMBER_URLS)
    assert transport.urls.count("https://www.basiclaw.gov.hk/en/basiclaw/annex3.html") == 1
    assert (
        transport.urls.count("https://www.basiclaw.gov.hk/en/basiclaw/annex-instrument.html") == 1
    )
    serialized = json.dumps(report, sort_keys=True)
    assert "CSRF" not in serialized
    assert "site-secret" not in serialized
    records = {item["endpoint_id"]: item for item in _items(report, "endpoints")}
    assert not any(str(endpoint_id).startswith("hkel-session-") for endpoint_id in records)
    capability = records["sep_000000000000000000000000000000000000000000000056"]
    assert capability["method"] == "GET"
    assert capability["requested_url"] == _HKEL_CLIENT_CHECK_COORDINATE
    assert capability["terminal_code"] == "CAPTURED"

    @dataclass(slots=True)
    class ReplayProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_probe = ReplayProbe()
    replayed = execute_source_family(
        authority_manifest=_authority(tmp_path),
        source_family="HKEL",
        output_root=output,
        attempt_id="hkel-configured-complete",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_probe,
    )
    assert replayed == report
    assert replay_probe.calls == 0


def test_basic_law_content_readback_defect_prevents_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retained content body must verify from storage before COMPLETE can be reported."""
    _install_synthetic_basic_law_contract(monkeypatch)
    content = _basic_law_content_fixture(_BASIC_LAW_MEMBER_URLS[0])
    content_name = hashlib.sha256(content).hexdigest() + ".bin"
    original_digest_file = execution.__dict__["_digest_file"]

    def corrupt_content_readback(path: Path) -> tuple[str, int]:
        fingerprint, byte_length = cast("Callable[[Path], tuple[str, int]]", original_digest_file)(
            path
        )
        if path.name == content_name:
            return "sha256:" + "0" * 64, byte_length
        return fingerprint, byte_length

    monkeypatch.setattr(execution, "_digest_file", corrupt_content_readback)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )

    with pytest.raises(execution.SourceEvidenceIntegrityError):
        execute_source_family(
            authority_manifest=_authority(tmp_path),
            source_family="HKEL",
            output_root=output,
            attempt_id="basic-law-content-readback-defect",
            observation_cutoff="2026-08-27T22:52:09+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=_ConfiguredHkelTransport(),
        )

    assert not (output / "attempts/basic-law-content-readback-defect/report.json").exists()


def test_mutated_current_authorization_cannot_select_historical_binding_pre_effect(
    tmp_path: Path,
) -> None:
    """Changing issued allowed URLs cannot turn a current authority into a legacy one."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "mutated-current-binding"
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    mutated = _mutated_hkel_authorization(authority, output, cutoff=cutoff)
    probe = TransportProbe()

    with pytest.raises(ValueError, match="EXECUTION_AUTHORIZATION_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEL",
            output_root=output,
            attempt_id="mutated-current-binding",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
            authorization=mutated,
        )

    assert probe.calls == 0


def test_tracked_historical_report_replays_under_its_frozen_binding(tmp_path: Path) -> None:
    """The tracked inert pre-20-member report replays without ignored vault state."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_tracked_historical_hkel_fixture(tmp_path)
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="HKEL",
        output_root=output,
        attempt_id="tracked-historical-hkel-replay",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )

    assert replayed == report
    assert probe.calls == 0


def test_genuine_historical_report_cannot_satisfy_current_binding(tmp_path: Path) -> None:
    """Current authority rejects the tracked two-root report before any transport."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    _old_authority, output, _report = _install_tracked_historical_hkel_fixture(tmp_path)
    cutoff = "2026-08-27T22:52:09+08:00"
    probe = TransportProbe()

    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=_authority(tmp_path, cutoff=cutoff),
            source_family="HKEL",
            output_root=output,
            attempt_id="tracked-historical-hkel-replay",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0


def test_coherent_historical_semantic_forgery_rejects_pre_effect(tmp_path: Path) -> None:
    """Old endpoint/count/procedure/result claims are never semantic replay inputs."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_tracked_historical_hkel_fixture(tmp_path)
    endpoints = _items(report, "endpoints")
    root = next(
        item
        for item in endpoints
        if item["endpoint_id"] == "sep_000000000000000000000000000000000000000000000050"
    )
    root["terminal_code"] = "OUTAGE"
    report["endpoint_counts"] = {"CAPTURED": 37, "OUTAGE": 1}
    report["result"] = "SOURCE_OUTAGE"
    basic_law = next(
        item
        for item in _items(report, "source_procedures")
        if item["source_id"] == "HK-LEG-BASIC-LAW-PORTAL"
    )
    basic_law["declared_member_count"] = 0
    report_path = output / "attempts/tracked-historical-hkel-replay/report.json"
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    probe = TransportProbe()

    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEL",
            output_root=output,
            attempt_id="tracked-historical-hkel-replay",
            observation_cutoff="2026-08-27T22:52:09+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0


def test_historical_report_hybrid_null_binding_rejects_pre_effect(tmp_path: Path) -> None:
    """Only omission identifies the exact legacy envelope; a new-key null is malformed."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_tracked_historical_hkel_fixture(tmp_path)
    report["execution_authorization_fingerprint"] = None
    report_path = output / "attempts/tracked-historical-hkel-replay/report.json"
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    probe = TransportProbe()

    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEL",
            output_root=output,
            attempt_id="tracked-historical-hkel-replay",
            observation_cutoff="2026-08-27T22:52:09+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0


def test_exact_judiciary_attempt_a_replays_with_zero_transport_effects(tmp_path: Path) -> None:
    """Only the retained 20260828a Judiciary report may use the old Cases binding."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_a_fixture(tmp_path)
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260828a",
        observation_cutoff="2026-08-28T22:20:23+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )

    assert replayed == report
    assert probe.calls == 0


def test_exact_judiciary_attempt_b_replays_with_zero_transport_effects(tmp_path: Path) -> None:
    """The versioned old 204 grammar replays only the exact immutable attempt-B report."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_b_fixture(tmp_path)
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830b",
        observation_cutoff="2026-08-30T07:18:07+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )

    assert replayed == report
    assert probe.calls == 0


def test_exact_judiciary_attempt_c_replays_with_zero_transport_effects(tmp_path: Path) -> None:
    """The frozen 1.0.1 form/result drift replays without adopting the current grammar."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_c_fixture(tmp_path)
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830c",
        observation_cutoff="2026-08-30T08:46:02+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )

    assert replayed == report
    assert probe.calls == 0


def test_exact_judiciary_attempt_d_replays_with_zero_transport_effects(tmp_path: Path) -> None:
    """The frozen 1.0.2/1.0.1 Attempt-D drift remains byte-exact and replay-only."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_d_fixture(tmp_path)
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830d",
        observation_cutoff="2026-08-30T10:00:10+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )

    assert replayed == report
    assert probe.calls == 0


def test_exact_judiciary_attempt_e_replays_with_zero_transport_effects(tmp_path: Path) -> None:
    """Attempt E stays bound to form 1.0.3/result 1.0.2 and performs no transport."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_e_fixture(tmp_path)
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830e",
        observation_cutoff="2026-08-30T11:26:32+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )

    assert replayed == report
    assert probe.calls == 0


def test_exact_judiciary_attempt_f_replays_with_zero_transport_effects(tmp_path: Path) -> None:
    """Attempt F stays bound to form 1.0.4/result 1.0.3 and performs no transport."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_f_fixture(tmp_path)
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830f",
        observation_cutoff="2026-08-30T13:08:05+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
    )

    assert replayed == report
    assert probe.calls == 0


def test_exact_judiciary_attempt_g_is_old_104_replay_with_zero_transport_effects(
    tmp_path: Path,
) -> None:
    """Attempt G remains frozen under Cases .6/form 1.0.5/result 1.0.4."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_g_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=matrix,
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-30T14:26:56+08:00",
        attempt_id="judiciary-live-baseline-20260830g",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )
    assert authorization.historical_replay is True
    assert authorization.register_identity == (
        "hcr_000000000000000000000000000000000000000000000001",
        "2026-08-30.6",
        "sha256:6b7c4e73d0549c0ac3d8f1767323f8289f62f01b8bb357a319932b10870e9df4",
    )
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830g",
        observation_cutoff="2026-08-30T14:26:56+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
    )

    assert replayed == report
    assert probe.calls == 0


def test_exact_judiciary_attempt_h_is_old_105_replay_with_zero_transport_effects(
    tmp_path: Path,
) -> None:
    """Attempt H remains frozen under Cases .7/form 1.0.6/result 1.0.5."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_h_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=matrix,
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-30T15:33:12+08:00",
        attempt_id="judiciary-live-baseline-20260830h",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )
    assert authorization.historical_replay is True
    assert authorization.register_identity == (
        "hcr_000000000000000000000000000000000000000000000001",
        "2026-08-30.7",
        "sha256:fc1646375f89cceb8f7476e08b9619787cd4bc1160a12f0e6d829885460b4324",
    )
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830h",
        observation_cutoff="2026-08-30T15:33:12+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
    )

    assert replayed == report
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830g", "2026-08-30T15:33:12+08:00", None),
        ("judiciary-live-baseline-20260830h", "2026-08-30T15:33:13+08:00", None),
        (
            "judiciary-live-baseline-20260830h",
            "2026-08-30T15:33:12+08:00",
            "judiciary-live-baseline-20260830g",
        ),
    ],
)
def test_judiciary_attempt_h_requires_exact_invocation_tuple(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt H cannot be replayed under another attempt, cutoff, or predecessor."""
    authority, output, _report = _install_judiciary_attempt_h_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_h_report_mutation_rejects_before_transport(tmp_path: Path) -> None:
    """Any byte-changing Attempt-H report mutation rejects before transport."""
    authority, output, report = _install_judiciary_attempt_h_fixture(tmp_path)
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-live-baseline-20260830h/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830h",
            observation_cutoff="2026-08-30T15:33:12+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


def test_exact_judiciary_attempt_i_is_old_106_replay_with_zero_transport_effects(
    tmp_path: Path,
) -> None:
    """Attempt I remains frozen under Cases .8/form 1.0.7/result 1.0.6."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_i_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=matrix,
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-30T17:07:10+08:00",
        attempt_id="judiciary-live-baseline-20260830i",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )
    assert authorization.historical_replay is True
    assert authorization.register_identity == (
        "hcr_000000000000000000000000000000000000000000000001",
        "2026-08-30.8",
        "sha256:d99f67eb6e993c1654e6033555d2e145a5eb62525de3576291c9eaabe11e36d9",
    )
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830i",
        observation_cutoff="2026-08-30T17:07:10+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
    )

    assert replayed == report
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830h", "2026-08-30T17:07:10+08:00", None),
        ("judiciary-live-baseline-20260830i", "2026-08-30T17:07:11+08:00", None),
        (
            "judiciary-live-baseline-20260830i",
            "2026-08-30T17:07:10+08:00",
            "judiciary-live-baseline-20260830h",
        ),
    ],
)
def test_judiciary_attempt_i_requires_exact_invocation_tuple(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt I cannot be replayed under another attempt, cutoff, or predecessor."""
    authority, output, _report = _install_judiciary_attempt_i_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize("mutation", ["authority", "register", "allowed_url"])
def test_judiciary_attempt_i_rejects_mutated_authority_binding(
    tmp_path: Path, mutation: str
) -> None:
    """Historical replay binds the exact authority, register, and URL grant."""
    authority, output, _report = _install_judiciary_attempt_i_fixture(tmp_path)
    document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    if mutation == "authority":
        document["authority_id"] = "hka_000000000000000000000000000000000000000000000789"
    elif mutation == "register":
        registers = cast("list[dict[str, object]]", document["registers"])
        next(item for item in registers if item["family"] == "CASES")["register_version"] = (
            "2026-08-30.9"
        )
    else:
        sources = cast("list[dict[str, object]]", document["selected_sources"])
        judiciary = next(
            item for item in sources if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY"
        )
        endpoints = cast("list[dict[str, object]]", judiciary["endpoints"])
        endpoints[0]["path"] = cast("str", endpoints[0]["path"]) + "&changed=1"
    document.pop("fingerprint")
    document["fingerprint"] = "sha256:" + hashlib.sha256(execution._canonical(document)).hexdigest()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    authority.write_bytes(execution._canonical(document))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff="2026-08-30T17:07:10+08:00",
            attempt_id="judiciary-live-baseline-20260830i",
            predecessor_attempt_id=None,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_i_report_mutation_rejects_before_transport(tmp_path: Path) -> None:
    """Any byte-changing Attempt-I report mutation rejects before transport."""
    authority, output, report = _install_judiciary_attempt_i_fixture(tmp_path)
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-live-baseline-20260830i/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830i",
            observation_cutoff="2026-08-30T17:07:10+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


def test_exact_judiciary_attempt_j_is_old_107_replay_with_zero_effects(
    tmp_path: Path,
) -> None:
    """Attempt J remains frozen under Cases .9/form 1.0.8/result 1.0.7."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    def explode(*arguments: object) -> NoReturn:
        raise AssertionError(arguments)

    authority, output, report = _install_judiciary_attempt_j_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=matrix,
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-30T18:23:17+08:00",
        attempt_id="judiciary-live-baseline-20260830j",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )
    assert authorization.historical_replay is True
    assert authorization.register_identity == (
        "hcr_000000000000000000000000000000000000000000000001",
        "2026-08-30.9",
        "sha256:72a07543a191652108d479f73dc4f545a31f453356aafe9767a6ead8c62a0ec1",
    )
    assert authorization.authority_manifest_fingerprint == (
        "sha256:7092606aa9791902568a7fff63d994a85c37bd123d39d4369659eaf26bd90c2d"
    )
    assert authorization.binding_fingerprint == (
        "sha256:237bd2d902ea5ecabfba07fcefc2812637e579afef9e529d93dd78dcff2e854e"
    )
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830j",
        observation_cutoff="2026-08-30T18:23:17+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
        judiciary_clock=explode,
        judiciary_sleeper=explode,
    )

    assert replayed == report
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830i", "2026-08-30T18:23:17+08:00", None),
        ("judiciary-live-baseline-20260830j", "2026-08-30T18:23:18+08:00", None),
        (
            "judiciary-live-baseline-20260830j",
            "2026-08-30T18:23:17+08:00",
            "judiciary-live-baseline-20260830i",
        ),
    ],
)
def test_judiciary_attempt_j_requires_exact_invocation_tuple(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt J cannot be replayed under another attempt, cutoff, or predecessor."""
    authority, output, _report = _install_judiciary_attempt_j_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize("mutation", ["authority", "register", "allowed_url"])
def test_judiciary_attempt_j_rejects_mutated_authority_binding(
    tmp_path: Path, mutation: str
) -> None:
    """Historical replay binds the exact J authority, register, and URL grant."""
    authority, output, _report = _install_judiciary_attempt_j_fixture(tmp_path)
    document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    if mutation == "authority":
        document["authority_id"] = "hka_000000000000000000000000000000000000000000000790"
    elif mutation == "register":
        registers = cast("list[dict[str, object]]", document["registers"])
        next(item for item in registers if item["family"] == "CASES")["register_version"] = (
            "2026-08-30.10"
        )
    else:
        sources = cast("list[dict[str, object]]", document["selected_sources"])
        judiciary = next(
            item for item in sources if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY"
        )
        endpoints = cast("list[dict[str, object]]", judiciary["endpoints"])
        endpoints[0]["path"] = cast("str", endpoints[0]["path"]) + "&changed=1"
    document.pop("fingerprint")
    document["fingerprint"] = "sha256:" + hashlib.sha256(execution._canonical(document)).hexdigest()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    authority.write_bytes(execution._canonical(document))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff="2026-08-30T18:23:17+08:00",
            attempt_id="judiciary-live-baseline-20260830j",
            predecessor_attempt_id=None,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_j_report_mutation_rejects_before_transport(tmp_path: Path) -> None:
    """Any byte-changing Attempt-J report mutation rejects before transport."""
    authority, output, report = _install_judiciary_attempt_j_fixture(tmp_path)
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-live-baseline-20260830j/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830j",
            observation_cutoff="2026-08-30T18:23:17+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


def test_exact_judiciary_attempt_k_is_old_108_replay_with_zero_effects(
    tmp_path: Path,
) -> None:
    """Attempt K remains frozen under Cases .10/form 1.0.9/result 1.0.8."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    def explode(*arguments: object) -> NoReturn:
        raise AssertionError(arguments)

    authority, output, report = _install_judiciary_attempt_k_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=matrix,
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-30T20:22:35+08:00",
        attempt_id="judiciary-live-baseline-20260830k",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )
    assert authorization.historical_replay is True
    assert authorization.register_identity == (
        "hcr_000000000000000000000000000000000000000000000001",
        "2026-08-30.10",
        "sha256:cfb4eb10a12b9358162d5fc01834bce82038838a313ad8dd9f5fa62065400285",
    )
    assert authorization.authority_manifest_fingerprint == (
        "sha256:14eac34bae71ffa8fdf400465387e084c631cd60a2f941797463749303153119"
    )
    assert authorization.binding_fingerprint == (
        "sha256:d15389eee2ecec73fe7d633b7eb230b6dfd4a6aa40e9f0719c8052c64adecd83"
    )
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260830k",
        observation_cutoff="2026-08-30T20:22:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
        judiciary_clock=explode,
        judiciary_sleeper=explode,
    )

    assert replayed == report
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("suffix", "cutoff"),
    [
        ("l", "2026-08-30T21:55:51+08:00"),
        ("m", "2026-08-30T22:12:07+08:00"),
    ],
)
def test_exact_judiciary_attempts_l_and_m_remain_old_schema_replay_only(
    tmp_path: Path, suffix: str, cutoff: str
) -> None:
    """Retry policy binding never retrofits the frozen one-attempt L/M reports."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_fixture(tmp_path, suffix)
    attempt_id = f"judiciary-live-baseline-20260830{suffix}"
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=matrix,
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff=cutoff,
        attempt_id=attempt_id,
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )
    probe = TransportProbe()
    replay = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replay == report
    assert probe.calls == 0


def test_exact_judiciary_attempt_n_is_policy_bound_old_1010_replay_with_zero_effects(
    tmp_path: Path,
) -> None:
    """Attempt N remains exact under Cases .11/form 1.0.10/result 1.0.9."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    def explode(*arguments: object) -> NoReturn:
        raise AssertionError(arguments)

    authority, output, report = _install_judiciary_attempt_fixture(tmp_path, "n")
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=(
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-31T02:58:45+08:00",
        attempt_id="judiciary-live-baseline-20260831n",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )

    assert authorization.historical_replay is True
    assert authorization.register_identity == (
        "hcr_000000000000000000000000000000000000000000000001",
        "2026-08-30.11",
        "sha256:2ff13c0f113ab3790d174897ac14485f758afded2cd9a02932df18ef9cc59f54",
    )
    assert authorization.authority_manifest_fingerprint == (
        "sha256:3b5bce2967f2ec8e1e5ed073e6848000044a98d83616a05ba60a145ccee46f5f"
    )
    assert authorization.binding_fingerprint == (
        "sha256:e2f4449a4ffc39ce6098aee090dfcadf6718914767d88f601eca595df69c0b3f"
    )
    assert report["report_schema_version"] == "1.1.0"
    assert report["execution_policy_fingerprint"] == (
        "sha256:9993c64e7cc62654d773cf1e860699cd9b56737d1cea4c4c17ee016308bf8353"
    )
    probe = TransportProbe()

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831n",
        observation_cutoff="2026-08-31T02:58:45+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
        judiciary_clock=explode,
        judiciary_sleeper=explode,
    )

    assert replayed == report
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830m", "2026-08-31T02:58:45+08:00", None),
        ("judiciary-live-baseline-20260831n", "2026-08-31T02:58:46+08:00", None),
        (
            "judiciary-live-baseline-20260831n",
            "2026-08-31T02:58:45+08:00",
            "judiciary-live-baseline-20260830m",
        ),
    ],
)
def test_judiciary_attempt_n_requires_exact_invocation_tuple(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt N cannot be replayed under another attempt, cutoff, or predecessor."""
    authority, output, _report = _install_judiciary_attempt_fixture(tmp_path, "n")

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize(
    "mutation",
    ["authority", "register", "allowed_url", "schema", "policy", "binding", "report"],
)
def test_judiciary_attempt_n_rejects_every_pinned_identity_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    """N's raw report, authority, register, URL, schema, policy, and binding are exact."""
    authority, output, report = _install_judiciary_attempt_fixture(tmp_path, "n")
    report_path = output / "attempts/judiciary-live-baseline-20260831n/report.json"
    if mutation in {"schema", "policy", "binding", "report"}:
        field, value = {
            "schema": ("report_schema_version", "1.0.0"),
            "policy": ("execution_policy_fingerprint", "sha256:" + "0" * 64),
            "binding": ("execution_authorization_fingerprint", "sha256:" + "0" * 64),
            "report": ("result", "COMPLETE"),
        }[mutation]
        report[field] = value
        report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    else:
        document = cast("dict[str, object]", json.loads(authority.read_bytes()))
        if mutation == "authority":
            document["authority_id"] = "hka_000000000000000000000000000000000000000000000792"
        elif mutation == "register":
            registers = cast("list[dict[str, object]]", document["registers"])
            next(item for item in registers if item["family"] == "CASES")["register_version"] = (
                "2026-08-31.12"
            )
        else:
            sources = cast("list[dict[str, object]]", document["selected_sources"])
            judiciary = next(
                item for item in sources if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY"
            )
            endpoints = cast("list[dict[str, object]]", judiciary["endpoints"])
            endpoints[0]["path"] = cast("str", endpoints[0]["path"]) + "&changed=1"
        document.pop("fingerprint")
        document["fingerprint"] = (
            "sha256:" + hashlib.sha256(execution._canonical(document)).hexdigest()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        )
        authority.write_bytes(execution._canonical(document))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff="2026-08-31T02:58:45+08:00",
            attempt_id="judiciary-live-baseline-20260831n",
            predecessor_attempt_id=None,
            repository_root=REPOSITORY_ROOT,
        )


def test_exact_judiciary_attempt_o_is_policy_bound_old_1011_replay_with_zero_effects(
    tmp_path: Path,
) -> None:
    """Attempt O remains exact under Cases .12/form 1.0.11/result 1.0.10."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    def explode(*arguments: object) -> NoReturn:
        raise AssertionError(arguments)

    authority, output, report = _install_judiciary_attempt_fixture(tmp_path, "o")
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=(
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-31T06:27:06+08:00",
        attempt_id="judiciary-live-baseline-20260831o",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )

    assert authorization.historical_replay is True
    assert authorization.register_identity == (
        "hcr_000000000000000000000000000000000000000000000001",
        "2026-08-31.12",
        "sha256:9ba0809d837459b341dd57fec23d857bc839a6c0ffbbbfc14f839c3176c88245",
    )
    assert authorization.authority_manifest_fingerprint == (
        "sha256:fd04e3943ee3d9a2de0b734adc780c515c841c5a66e309a775f9e9a4269cc2ae"
    )
    assert authorization.binding_fingerprint == (
        "sha256:d2e128c79d7ea671e200c19c29d8d723c047b479634b9c3f04950c76dd1914f2"
    )
    assert report["report_schema_version"] == "1.1.0"
    assert report["execution_policy_fingerprint"] == (
        "sha256:9993c64e7cc62654d773cf1e860699cd9b56737d1cea4c4c17ee016308bf8353"
    )
    probe = TransportProbe()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831o",
        observation_cutoff="2026-08-31T06:27:06+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
        judiciary_clock=explode,
        judiciary_sleeper=explode,
    )
    assert replayed == report
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260831n", "2026-08-31T06:27:06+08:00", None),
        ("judiciary-live-baseline-20260831o", "2026-08-31T06:27:07+08:00", None),
        (
            "judiciary-live-baseline-20260831o",
            "2026-08-31T06:27:06+08:00",
            "judiciary-live-baseline-20260831n",
        ),
    ],
)
def test_judiciary_attempt_o_requires_exact_invocation_tuple(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt O cannot replay under a different attempt, cutoff, or predecessor."""
    authority, output, _report = _install_judiciary_attempt_fixture(tmp_path, "o")
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize(
    "mutation", ["authority", "register", "allowed_url", "schema", "policy", "binding", "report"]
)
def test_judiciary_attempt_o_rejects_every_pinned_identity_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    """O binds its report, authority, register, URLs, schema, policy, and execution."""
    authority, output, report = _install_judiciary_attempt_fixture(tmp_path, "o")
    report_path = output / "attempts/judiciary-live-baseline-20260831o/report.json"
    if mutation in {"schema", "policy", "binding", "report"}:
        field, value = {
            "schema": ("report_schema_version", "1.0.0"),
            "policy": ("execution_policy_fingerprint", "sha256:" + "0" * 64),
            "binding": ("execution_authorization_fingerprint", "sha256:" + "0" * 64),
            "report": ("result", "COMPLETE"),
        }[mutation]
        report[field] = value
        report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    else:
        document = cast("dict[str, object]", json.loads(authority.read_bytes()))
        if mutation == "authority":
            document["authority_id"] = "hka_000000000000000000000000000000000000000000000793"
        elif mutation == "register":
            registers = cast("list[dict[str, object]]", document["registers"])
            next(item for item in registers if item["family"] == "CASES")["register_version"] = (
                "2026-08-31.13"
            )
        else:
            sources = cast("list[dict[str, object]]", document["selected_sources"])
            judiciary = next(
                item for item in sources if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY"
            )
            endpoints = cast("list[dict[str, object]]", judiciary["endpoints"])
            endpoints[0]["path"] = cast("str", endpoints[0]["path"]) + "&changed=1"
        document.pop("fingerprint")
        document["fingerprint"] = (
            "sha256:" + hashlib.sha256(execution._canonical(document)).hexdigest()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        )
        authority.write_bytes(execution._canonical(document))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff="2026-08-31T06:27:06+08:00",
            attempt_id="judiciary-live-baseline-20260831o",
            predecessor_attempt_id=None,
            repository_root=REPOSITORY_ROOT,
        )


def test_exact_judiciary_attempt_p_preserves_old_contract_drift_replay_with_zero_effects(
    tmp_path: Path,
) -> None:
    """P stays an old-policy CAPTURED physical response and logical contract change."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    def explode(*arguments: object) -> NoReturn:
        raise AssertionError(arguments)

    authority, output, report = _install_judiciary_attempt_fixture(tmp_path, "p")
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=(
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        attempt_id="judiciary-live-baseline-20260831p",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )

    assert authorization.register_identity == (
        "hcr_000000000000000000000000000000000000000000000001",
        "2026-08-31.13",
        "sha256:a5e35954d6d030f5b073c33b1b5006c71c8181388289870e05be15aac54c072b",
    )
    assert authorization.authority_manifest_fingerprint == (
        "sha256:66bc570014539cc9ec14ee2b56cb4f64c0b651a27ff8596704810887013ae352"
    )
    assert authorization.binding_fingerprint == (
        "sha256:71cd5fcebc6f283e5bc581eeeea17ece643334ce8cdfdf7845602c5ecd91a1d6"
    )
    assert report["report_schema_version"] == "1.1.0"
    assert report["execution_policy_fingerprint"] == (
        "sha256:9993c64e7cc62654d773cf1e860699cd9b56737d1cea4c4c17ee016308bf8353"
    )
    physical = next(
        item
        for item in _items(report, "transport_attempts")
        if item["endpoint_id"] == "judiciary-year-2006-page-259"
    )
    logical = next(
        item
        for item in _items(report, "endpoints")
        if item["endpoint_id"] == "judiciary-year-2006-page-259"
    )
    assert physical["terminal_code"] == "CAPTURED"
    assert logical["terminal_code"] == "SOURCE_CONTRACT_CHANGED"
    assert report["result"] == "SOURCE_CONTRACT_CHANGED"

    probe = TransportProbe()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831p",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
        judiciary_clock=explode,
        judiciary_sleeper=explode,
    )
    assert replayed == report
    assert probe.calls == 0


def test_exact_judiciary_attempt_q_preserves_old_policy_outage_replay_with_zero_effects(
    tmp_path: Path,
) -> None:
    """Q remains an exact schema-1.2 status-500 outage under policy 1.1."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    def explode(*arguments: object) -> NoReturn:
        raise AssertionError(arguments)

    authority, output, report = _install_judiciary_attempt_fixture(tmp_path, "q")
    report_path = output / "attempts/judiciary-live-baseline-20260831q/report.json"
    raw_report = report_path.read_bytes()
    before = {
        path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=(
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        attempt_id="judiciary-live-baseline-20260831q",
        predecessor_attempt_id="judiciary-live-baseline-20260831p",
        repository_root=REPOSITORY_ROOT,
    )

    assert authorization.historical_replay is True
    assert authorization.register_identity == (
        "hcr_000000000000000000000000000000000000000000000001",
        "2026-08-31.13",
        "sha256:a5e35954d6d030f5b073c33b1b5006c71c8181388289870e05be15aac54c072b",
    )
    assert authorization.authority_manifest_fingerprint == (
        "sha256:08c2fb878c11b00cb8b76107cdcdab33f77720aca9dfadb0342fb65e932d31bf"
    )
    assert authorization.binding_fingerprint == (
        "sha256:03d97139806e7cbcf89baaca0a97fdaad60c8781fc662113aded11d229b1a072"
    )
    assert hashlib.sha256(raw_report).hexdigest() == (
        "7e5f8d86a289f6ca0581e869a51b6e89831bdf42896b50d822c7c87eec2883c9"
    )
    assert report["report_schema_version"] == "1.2.0"
    assert report["predecessor_attempt_id"] == "judiciary-live-baseline-20260831p"
    assert report["execution_policy_fingerprint"] == (
        "sha256:d42d817e27d08896358a0fcf218833b1feaf9b285e5f71fc902731dff136a349"
    )
    physical = _items(report, "transport_attempts")
    assert len(physical) == 1
    assert physical[0]["status"] == 500
    assert physical[0]["byte_length"] == 8_314
    assert physical[0]["body_fingerprint"] == (
        "sha256:1cbb67dbed1fd0ef4aa6a5132c6a4bf578e88577591062d40e2ead87d6b9a81c"
    )
    assert physical[0]["terminal_code"] == "OUTAGE"
    assert report["result"] == "SOURCE_OUTAGE"

    probe = TransportProbe()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831q",
        predecessor_attempt_id="judiciary-live-baseline-20260831p",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
        judiciary_clock=explode,
        judiciary_sleeper=explode,
    )
    after = {
        path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    assert replayed == report
    assert probe.calls == 0
    assert report_path.read_bytes() == raw_report
    assert after == before


def test_exact_judiciary_attempt_r_replays_current_policy_outage_without_effects() -> None:
    """R remains bound to Q and the old Cases/form/result contract after Cases .14."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    def explode(*arguments: object) -> NoReturn:
        raise AssertionError(arguments)

    authority = (
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-31-judiciary-attempt-r.json"
    )
    output = REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-p"
    report_path = output / "attempts/judiciary-live-baseline-20260831r/report.json"
    raw_report = report_path.read_bytes()
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=(
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        attempt_id="judiciary-live-baseline-20260831r",
        predecessor_attempt_id="judiciary-live-baseline-20260831q",
        repository_root=REPOSITORY_ROOT,
    )

    assert authorization.historical_replay is True
    assert authorization.register_identity[1] == "2026-08-31.13"
    assert authorization.authority_manifest_fingerprint == (
        "sha256:85360be62646366d8b56eafe6191e776fa8077a7c6390d78760846b1c498f333"
    )
    assert authorization.binding_fingerprint == (
        "sha256:90b367494ae2a7914f6c589f6b939e89aba6e6f7025400740e8420f7fbb54edc"
    )
    assert hashlib.sha256(raw_report).hexdigest() == (
        "ab67805a5bde97f6f0903e452c38b9e2e95f822516445a36e1ce93d9347016fd"
    )

    probe = TransportProbe()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831r",
        predecessor_attempt_id="judiciary-live-baseline-20260831q",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
        judiciary_clock=explode,
        judiciary_sleeper=explode,
    )

    assert replayed == json.loads(raw_report)
    assert report_path.read_bytes() == raw_report
    assert probe.calls == 0


def test_exact_judiciary_attempt_s_replays_the_frozen_contract_stop_without_effects() -> None:
    """Attempt S remains a zero-effect replay under its old Cases/form/result contracts."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    def explode(*arguments: object) -> NoReturn:
        raise AssertionError(arguments)

    authority = (
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-31-judiciary-attempt-s.json"
    )
    output = REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-p"
    report_path = output / "attempts/judiciary-live-baseline-20260831s/report.json"
    raw_report = report_path.read_bytes()
    authorization = admission.authorize_retained_replay(
        authority_manifest=authority,
        matrix=(
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        attempt_id="judiciary-live-baseline-20260831s",
        predecessor_attempt_id="judiciary-live-baseline-20260831r",
        repository_root=REPOSITORY_ROOT,
    )

    probe = TransportProbe()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831s",
        predecessor_attempt_id="judiciary-live-baseline-20260831r",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        authorization=authorization,
        judiciary_clock=explode,
        judiciary_sleeper=explode,
    )

    assert replayed["result"] == "SOURCE_CONTRACT_CHANGED"
    assert replayed == json.loads(raw_report)
    assert report_path.read_bytes() == raw_report
    assert probe.calls == 0


def test_judiciary_attempt_t_continues_s_contract_stop_at_exact_failed_request(
    tmp_path: Path,
) -> None:
    """A new parser may resume S only by refetching its exact stopped page first."""
    source_output = REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-p"
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-s-contract-stop"
    )

    def exclude_after_s(directory: str, names: list[str]) -> list[str]:
        if Path(directory).name != "attempts":
            return []
        allowed = {
            "judiciary-live-baseline-20260831p",
            "judiciary-live-baseline-20260831q",
            "judiciary-live-baseline-20260831r",
            "judiciary-live-baseline-20260831s",
        }
        return [name for name in names if name not in allowed]

    shutil.copytree(
        source_output,
        output,
        copy_function=os.link,
        ignore=exclude_after_s,
    )
    authority = tmp_path / "judiciary-attempt-t-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-31-judiciary-attempt-t.json",
        authority,
    )
    _replace_authority_identity_with_current_cases_register(authority)
    predecessor_path = output / "attempts/judiciary-live-baseline-20260831s/report.json"
    predecessor_bytes = predecessor_path.read_bytes()
    predecessor = cast("dict[str, object]", json.loads(predecessor_bytes))
    failed = _items(predecessor, "endpoints")[-1]
    expected_request = (
        cast("str", failed["requested_url"]),
        16_777_216,
    )

    @dataclass(slots=True)
    class FirstRequestOnly:
        calls: list[tuple[str, int]] = field(
            default_factory=lambda: cast("list[tuple[str, int]]", [])
        )

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls.append((url, max_bytes))
            assert self.calls == [expected_request]
            return CapturedResponse(418, "text/html", b"synthetic terminal", url)

    transport = FirstRequestOnly()
    clock = _JudiciaryClock()
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831t",
        predecessor_attempt_id="judiciary-live-baseline-20260831s",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert transport.calls == [expected_request]
    assert cast("dict[str, object]", child["continuation_binding"])["next_request"] == {
        "endpoint_id": "judiciary-year-2011-page-84",
        "endpoint_version": "1.0.12",
        "max_bytes": 16_777_216,
        "method": "GET",
        "requested_url": expected_request[0],
    }
    assert _items(child, "endpoints")[-1]["endpoint_id"] == "judiciary-year-2011-page-84"
    assert _items(child, "endpoints")[-1]["endpoint_version"] == "1.0.12"
    assert predecessor_path.read_bytes() == predecessor_bytes

    @dataclass(slots=True)
    class ExplodingReplay:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ExplodingReplay()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831t",
        predecessor_attempt_id="judiciary-live-baseline-20260831s",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replayed == child
    assert replay_transport.calls == 0
    assert predecessor_path.read_bytes() == predecessor_bytes


def test_judiciary_attempt_u_continues_mixed_contract_t_at_exact_failed_request(
    tmp_path: Path,
) -> None:
    """A chained continuation validates T's old prefix and current suffix separately."""
    source_output = REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-p"
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "judiciary-attempt-t-chained-continuation"
    )

    def exclude_after_t(directory: str, names: list[str]) -> list[str]:
        if Path(directory).name != "attempts":
            return []
        allowed = {
            "judiciary-live-baseline-20260831p",
            "judiciary-live-baseline-20260831q",
            "judiciary-live-baseline-20260831r",
            "judiciary-live-baseline-20260831s",
            "judiciary-live-baseline-20260831t",
        }
        return [name for name in names if name not in allowed]

    shutil.copytree(
        source_output,
        output,
        copy_function=os.link,
        ignore=exclude_after_t,
    )
    authority = tmp_path / "judiciary-attempt-u-authority.json"
    shutil.copyfile(
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-31-judiciary-attempt-u.json",
        authority,
    )
    _replace_authority_identity_with_current_cases_register(authority)
    predecessor_path = output / "attempts/judiciary-live-baseline-20260831t/report.json"
    predecessor_bytes = predecessor_path.read_bytes()
    predecessor = cast("dict[str, object]", json.loads(predecessor_bytes))
    failed = _items(predecessor, "endpoints")[-1]
    expected_request = (cast("str", failed["requested_url"]), 16_777_216)

    @dataclass(slots=True)
    class FirstRequestOnly:
        calls: list[tuple[str, int]] = field(
            default_factory=lambda: cast("list[tuple[str, int]]", [])
        )

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls.append((url, max_bytes))
            assert self.calls == [expected_request]
            return CapturedResponse(418, "text/html", b"synthetic terminal", url)

    transport = FirstRequestOnly()
    clock = _JudiciaryClock()
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831u",
        predecessor_attempt_id="judiciary-live-baseline-20260831t",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert transport.calls == [expected_request]
    assert cast("dict[str, object]", child["continuation_binding"])["next_request"] == {
        "endpoint_id": "judiciary-year-2011-page-148",
        "endpoint_version": "1.0.12",
        "max_bytes": 16_777_216,
        "method": "GET",
        "requested_url": expected_request[0],
    }
    assert _items(child, "endpoints")[-1]["endpoint_id"] == "judiciary-year-2011-page-148"
    assert _items(child, "endpoints")[-1]["endpoint_version"] == "1.0.12"
    assert predecessor_path.read_bytes() == predecessor_bytes

    @dataclass(slots=True)
    class ExplodingReplay:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = ExplodingReplay()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831u",
        predecessor_attempt_id="judiciary-live-baseline-20260831t",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replayed == child
    assert replay_transport.calls == 0
    assert predecessor_path.read_bytes() == predecessor_bytes


@pytest.mark.parametrize(
    "mutation",
    ["parser", "identity", "url", "version", "physical-object"],
)
def test_judiciary_semantic_continuation_gate_rejects_changed_s_facts(
    mutation: str,
) -> None:
    """Current-parser eligibility binds the exact body, request identity, and version seam."""
    output = REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-p"
    report = cast(
        "dict[str, object]",
        json.loads(
            (output / "attempts/judiciary-live-baseline-20260831s/report.json").read_bytes()
        ),
    )
    failed = dict(_items(report, "endpoints")[-1])
    physical = dict(_items(report, "transport_attempts")[-1])
    body = (output / cast("str", failed["object_key"])).read_bytes()
    if mutation == "parser":
        body = b"<html>still outside the current result contract</html>"
    elif mutation == "identity":
        failed["endpoint_id"] = "judiciary-year-2011-page-85"
    elif mutation == "url":
        failed["requested_url"] = cast("str", failed["requested_url"]) + "&changed=1"
    elif mutation == "version":
        failed["endpoint_version"] = "1.0.12"
        physical["endpoint_version"] = "1.0.12"
    else:
        physical["object_key"] = "objects/" + "0" * 64 + ".bin"
    records = tuple(dict(item) for item in _items(report, "endpoints"))
    records = (*records[:-1], failed)
    bodies = {
        cast("str", record["endpoint_id"]): (
            body if record is failed else (output / cast("str", record["object_key"])).read_bytes()
        )
        for record in records
    }
    historical_entry_version = execution._judiciary_report_entry_contract_version(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        report
    )

    assert not execution._judiciary_semantic_stop_is_accepted_by_current_contract(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        failed,
        physical,
        body,
        current_registered_endpoints=execution._registered_endpoints("JUDICIARY"),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        historical_registered_endpoints=execution._registered_endpoints(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            "JUDICIARY",
            judiciary_endpoint_204_version=historical_entry_version,
        ),
        records=records,
        bodies=bodies,
        observation_cutoff=cast("str", report["observation_cutoff"]),
    )


@pytest.mark.parametrize(
    "mutation",
    ["invocation", "authority", "predecessor", "register", "url", "policy", "report"],
)
def test_judiciary_attempt_s_replay_mutations_reject_before_effects(
    tmp_path: Path, mutation: str
) -> None:
    """S accepts only its exact frozen invocation, authority, register, policy, and report."""
    source_authority = (
        REPOSITORY_ROOT
        / "var/hk-v1/source-admission"
        / "authority-user-attested-live-2026-08-31-judiciary-attempt-s.json"
    )
    source_output = REPOSITORY_ROOT / "var/hk-v1/source-admission/judiciary-attempt-p"
    authority = source_authority
    output = source_output
    arguments: dict[str, object] = {
        "authority_manifest": authority,
        "matrix": REPOSITORY_ROOT
        / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json",
        "output_root": output,
        "source_family": "JUDICIARY",
        "observation_cutoff": "2026-08-31T11:05:35+08:00",
        "attempt_id": "judiciary-live-baseline-20260831s",
        "predecessor_attempt_id": "judiciary-live-baseline-20260831r",
        "repository_root": REPOSITORY_ROOT,
    }
    if mutation in {"authority", "register", "url"}:
        document = cast("dict[str, object]", json.loads(source_authority.read_bytes()))
        if mutation == "authority":
            document["fingerprint"] = "sha256:" + "0" * 64
        else:
            sources = cast("list[dict[str, object]]", document["selected_sources"])
            if mutation == "register":
                registers = cast("list[dict[str, object]]", document["registers"])
                next(item for item in registers if item["family"] == "CASES")[
                    "register_version"
                ] = "2026-08-31.14"
            else:
                endpoints = cast("list[dict[str, object]]", sources[0]["endpoints"])
                endpoints[0]["path"] = "/lrs/forged"
        authority = tmp_path / "forged-authority.json"
        authority.write_bytes(execution._canonical(document))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        arguments["authority_manifest"] = authority
    elif mutation in {"policy", "report"}:
        report_path = source_output / "attempts/judiciary-live-baseline-20260831s/report.json"
        report = cast("dict[str, object]", json.loads(report_path.read_bytes()))
        if mutation == "policy":
            report["execution_policy_fingerprint"] = "sha256:" + "0" * 64
        else:
            report["result"] = "SOURCE_OUTAGE"
        output = tmp_path / "output"
        target = output / "attempts/judiciary-live-baseline-20260831s/report.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        arguments["output_root"] = output
    elif mutation == "invocation":
        arguments["attempt_id"] = "judiciary-live-baseline-20260831r"
    else:
        arguments["predecessor_attempt_id"] = "judiciary-live-baseline-20260831q"

    with pytest.raises(
        ValueError,
        match=r"EXECUTION_(?:REPLAY_BINDING_INVALID|NOT_AUTHORIZED:AUTHORITY_MANIFEST_MALFORMED)",
    ):
        admission.authorize_retained_replay(**arguments)  # type: ignore[arg-type]


def test_judiciary_attempt_q_rejects_invocation_and_report_pin_mutations(
    tmp_path: Path,
) -> None:
    """Q's predecessor-bound invocation and raw old-policy report are not fungible."""
    authority, output, report = _install_judiciary_attempt_fixture(tmp_path, "q")
    arguments: dict[str, object] = {
        "authority_manifest": authority,
        "matrix": (
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        "output_root": output,
        "source_family": "JUDICIARY",
        "observation_cutoff": "2026-08-31T11:05:35+08:00",
        "attempt_id": "judiciary-live-baseline-20260831q",
        "predecessor_attempt_id": "judiciary-live-baseline-20260831p",
        "repository_root": REPOSITORY_ROOT,
    }
    for argument_name, value in (
        ("observation_cutoff", "2026-08-31T11:05:36+08:00"),
        ("attempt_id", "judiciary-live-baseline-20260831p"),
        ("predecessor_attempt_id", None),
        ("predecessor_attempt_id", "judiciary-live-baseline-20260831o"),
    ):
        hostile = dict(arguments)
        hostile[argument_name] = value
        with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
            admission.authorize_retained_replay(**hostile)  # type: ignore[arg-type]

    report_path = output / "attempts/judiciary-live-baseline-20260831q/report.json"
    forged = cast("dict[str, object]", json.loads(execution._canonical(report)))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    forged["execution_policy_fingerprint"] = "sha256:" + "0" * 64
    report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(**arguments)  # type: ignore[arg-type]


def test_judiciary_continuation_from_p_reuses_prefix_and_starts_at_exact_failed_page(  # noqa: C901, PLR0915
    tmp_path: Path,
) -> None:
    """A continuation rereads P's verified prefix and spends its first start on page 259."""
    authority, output, predecessor = _install_judiciary_attempt_fixture(tmp_path, "p")
    predecessor_authority = tmp_path / "judiciary-attempt-p-original-authority.json"
    shutil.copyfile(authority, predecessor_authority)
    predecessor_path = output / "attempts/judiciary-live-baseline-20260831p/report.json"
    predecessor_bytes = predecessor_path.read_bytes()
    fresh_authority_fingerprint = _replace_authority_identity_with_current_cases_register(authority)
    expected_url = cast("str", _items(predecessor, "endpoints")[-1]["requested_url"])

    @dataclass(slots=True)
    class FirstSuffixRequestOnly:
        calls: list[tuple[str, int]] = field(
            default_factory=lambda: cast("list[tuple[str, int]]", [])
        )

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls.append((url, max_bytes))
            assert len(self.calls) == 1
            assert url == expected_url
            assert "year=2006&page=259" in url
            return CapturedResponse(503, "text/html", b"temporarily unavailable", None)

    transport = FirstSuffixRequestOnly()
    clock = _JudiciaryClock()
    child_attempt_id = "judiciary-synthetic-continuation-from-p"
    report = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=child_attempt_id,
        predecessor_attempt_id="judiciary-live-baseline-20260831p",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )

    assert transport.calls == [(expected_url, 16_777_216)]
    assert report["report_schema_version"] == "1.2.0"
    assert report["predecessor_attempt_id"] == "judiciary-live-baseline-20260831p"
    assert report["authority_manifest_fingerprint"] == fresh_authority_fingerprint
    logical = _items(report, "endpoints")
    assert logical[:3265] == _items(predecessor, "endpoints")[:3265]
    assert logical[3265]["endpoint_id"] == "judiciary-year-2006-page-259"
    assert logical[3265]["endpoint_version"] == "1.0.12"
    assert logical[3265]["terminal_code"] == "OUTAGE"
    transport_attempts = _items(report, "transport_attempts")
    assert len(transport_attempts) == 1
    assert transport_attempts[0]["endpoint_version"] == "1.0.12"
    continuation_binding = cast("dict[str, object]", report["continuation_binding"])
    next_request = cast("dict[str, object]", continuation_binding["next_request"])
    assert next_request["endpoint_version"] == "1.0.12"
    segment = cast("dict[str, object]", report["observation_accounting"])
    cumulative = cast("dict[str, object]", report["cumulative_observation_accounting"])
    assert segment["request_starts"] == 1
    assert cumulative["request_starts"] == 3267
    assert predecessor_path.read_bytes() == predecessor_bytes

    @dataclass(slots=True)
    class ExplodingReplay:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = ExplodingReplay()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=child_attempt_id,
        predecessor_attempt_id="judiciary-live-baseline-20260831p",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=probe,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replayed == report
    assert probe.calls == 0

    for mutation in (
        "cumulative-starts",
        "cumulative-bytes",
        "cumulative-elapsed",
        "segment-starts",
        "prefix-count",
        "prefix-digest",
        "next-request",
        "continuation-authority",
        "continuation-execution",
        "first-transport-request",
    ):
        forged = cast(
            "dict[str, object]",
            json.loads(execution._canonical(report)),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        )
        forged_segment = cast("dict[str, object]", forged["observation_accounting"])
        forged_cumulative = cast("dict[str, object]", forged["cumulative_observation_accounting"])
        forged_binding = cast("dict[str, object]", forged["continuation_binding"])
        if mutation == "cumulative-starts":
            forged_cumulative["request_starts"] = 3266
        elif mutation == "cumulative-bytes":
            forged_cumulative["retained_response_bytes"] = 0
        elif mutation == "cumulative-elapsed":
            forged_cumulative["elapsed_seconds"] = 0.0
        elif mutation == "segment-starts":
            forged_segment["request_starts"] = 2
        elif mutation == "prefix-count":
            forged_binding["prefix_endpoint_count"] = 3264
        elif mutation == "prefix-digest":
            forged_binding["prefix_endpoints_fingerprint"] = "sha256:" + "0" * 64
        elif mutation == "next-request":
            next_request = cast("dict[str, object]", forged_binding["next_request"])
            next_request["endpoint_id"] = "judiciary-year-2006-page-260"
        elif mutation == "continuation-authority":
            forged_binding["continuation_authority_manifest_fingerprint"] = "sha256:" + "0" * 64
        elif mutation == "continuation-execution":
            forged_binding["continuation_execution_authorization_fingerprint"] = (
                "sha256:" + "0" * 64
            )
        else:
            _items(forged, "transport_attempts")[0]["requested_url"] = expected_url + "&x=1"
        with pytest.raises(
            execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"
        ):
            execution._validate_judiciary_continuation_report(forged)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    predecessor_probe = ExplodingReplay()
    predecessor_authorization = admission.authorize_retained_replay(
        authority_manifest=predecessor_authority,
        matrix=(
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        output_root=output,
        source_family="JUDICIARY",
        observation_cutoff="2026-08-31T11:05:35+08:00",
        attempt_id="judiciary-live-baseline-20260831p",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )
    predecessor_replayed = execute_source_family(
        authority_manifest=predecessor_authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-live-baseline-20260831p",
        predecessor_attempt_id=None,
        observation_cutoff="2026-08-31T11:05:35+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=predecessor_probe,
        authorization=predecessor_authorization,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert predecessor_replayed == predecessor
    assert predecessor_probe.calls == 0
    assert predecessor_path.read_bytes() == predecessor_bytes


def test_judiciary_pre_entry_bounded_lineage_does_not_invent_a_form_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stopped lineage before endpoint 204 replays without a guessed parser contract."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 1, raising=False)
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "pre-entry-bounded-lineage"
    )

    parent_id = "judiciary-pre-entry-parent"
    parent_clock = _JudiciaryClock()
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_TimedJudiciaryTransport(parent_clock),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    assert parent["result"] == "OBSERVATION_BUDGET_EXHAUSTED"
    assert all(
        item["endpoint_id"] != "sep_000000000000000000000000000000000000000000000204"
        for item in _items(parent, "endpoints")
    )
    assert execution._judiciary_report_entry_contract_version_if_reached(parent) is None  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    child_id = "judiciary-pre-entry-child"
    child_clock = _JudiciaryClock()
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=child_id,
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_TimedJudiciaryTransport(child_clock),
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )
    assert child["result"] == "OBSERVATION_BUDGET_EXHAUSTED"

    @dataclass(slots=True)
    class NoReplayTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = NoReplayTransport()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=child_id,
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replayed == child
    assert replay_transport.calls == 0


def test_judiciary_continuation_rederives_an_ancestor_bridge_before_replay(
    tmp_path: Path,
) -> None:
    """A descendant replay cannot trust a mutated ancestor continuation binding."""
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "ancestor-bridge"
    )

    class ParentOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == 6:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"parent outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_id = "judiciary-ancestor-parent"
    parent_clock = _JudiciaryClock()
    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ParentOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )

    @dataclass(slots=True)
    class OneOutage:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            assert url.startswith("https://legalref.judiciary.hk/")
            assert max_bytes == 16_777_216
            return CapturedResponse(503, "text/html", b"continued outage", None)

    _replace_authority_identity(authority)
    child_id = "judiciary-ancestor-child"
    child_transport = OneOutage()
    child_clock = _JudiciaryClock()
    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=child_id,
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=child_transport,
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )
    authority_document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    authority_document["authority_id"] = "hka_000000000000000000000000000000000000000000000009"
    authority_document.pop("fingerprint")
    authority_document["fingerprint"] = execution._digest(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        execution._canonical(authority_document)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )
    authority.write_bytes(
        execution._canonical(authority_document)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )
    grandchild_id = "judiciary-ancestor-grandchild"
    grandchild_transport = OneOutage()
    grandchild_clock = _JudiciaryClock()
    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=grandchild_id,
        predecessor_attempt_id=child_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=grandchild_transport,
        judiciary_clock=grandchild_clock.monotonic,
        judiciary_sleeper=grandchild_clock.sleep,
    )

    child_path = output / "attempts" / child_id / "report.json"
    child = cast("dict[str, object]", json.loads(child_path.read_bytes()))
    child_binding = cast("dict[str, object]", child["continuation_binding"])
    child_binding["prefix_endpoints_fingerprint"] = "sha256:" + "0" * 64
    child_bytes = execution._canonical(child)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    child_path.write_bytes(child_bytes)
    grandchild_path = output / "attempts" / grandchild_id / "report.json"
    grandchild = cast("dict[str, object]", json.loads(grandchild_path.read_bytes()))
    grandchild_binding = cast("dict[str, object]", grandchild["continuation_binding"])
    grandchild_binding["predecessor_report_fingerprint"] = (
        "sha256:" + hashlib.sha256(child_bytes).hexdigest()
    )
    grandchild_path.write_bytes(
        execution._canonical(grandchild)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )

    replay_transport = OneOutage()
    with pytest.raises(
        execution.PredecessorValidationError,
        match="PREDECESSOR_REPORT_MALFORMED",
    ):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=grandchild_id,
            predecessor_attempt_id=child_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=replay_transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert replay_transport.calls == 0


@dataclass(frozen=True, slots=True)
class _MixedJudiciaryChain:
    authority: Path
    output: Path
    cutoff: str
    parent_id: str
    child_id: str
    grandchild_id: str
    child: dict[str, object]
    grandchild: dict[str, object]


def _mixed_judiciary_three_generation_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    label: str,
) -> _MixedJudiciaryChain:
    """Create a disposable old-prefix/current-suffix continuation chain."""
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / label
    )
    original_registered = execution._registered_endpoints  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def historical_registered_endpoints(
        source_family: str,
        *,
        judiciary_endpoint_204_version: str | None = None,
        hkex_historical_attempt_id: str | None = None,
    ) -> tuple[OfficialEndpointContract, ...]:
        if source_family == "JUDICIARY" and judiciary_endpoint_204_version is None:
            judiciary_endpoint_204_version = "1.0.12"
        return original_registered(
            source_family,
            judiciary_endpoint_204_version=judiciary_endpoint_204_version,
            hkex_historical_attempt_id=hkex_historical_attempt_id,
        )

    class ParentOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if "year=1997&page=2" in url:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"historical parent outage", None)
            if "year=1997" in url:
                self.urls.append(url)
                body = _current_judiciary_paginated_result_body(
                    year=1997,
                    page=1,
                    reported_results=11,
                    reported_pages=2,
                    rows=tuple((1000 + day, f"{day:02d}/07/1997") for day in range(1, 11)),
                )
                return CapturedResponse(200, "text/html", body[: max_bytes + 1], url)
            return super().get(url=url, max_bytes=max_bytes)

    monkeypatch.setattr(execution, "_registered_endpoints", historical_registered_endpoints)
    parent_id = "judiciary-mixed-chain-parent"
    parent_clock = _JudiciaryClock()
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ParentOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    assert parent["result"] == "SOURCE_OUTAGE"
    assert _items(parent, "endpoints")[-1]["endpoint_version"] == "1.0.11"

    monkeypatch.setattr(execution, "_registered_endpoints", original_registered)

    @dataclass(slots=True)
    class OneOutage:
        calls: list[tuple[str, int]] = field(
            default_factory=lambda: cast("list[tuple[str, int]]", [])
        )

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls.append((url, max_bytes))
            return CapturedResponse(503, "text/html", b"continued outage", None)

    _replace_authority_identity(authority)
    child_id = "judiciary-mixed-chain-child"
    child_transport = OneOutage()
    child_clock = _JudiciaryClock()
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=child_id,
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=child_transport,
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )
    prefix_count = cast("dict[str, object]", child["continuation_binding"])["prefix_endpoint_count"]
    assert type(prefix_count) is int
    assert any(
        item["endpoint_version"] == "1.0.11" for item in _items(child, "endpoints")[:prefix_count]
    )
    assert _items(child, "endpoints")[prefix_count]["endpoint_version"] == "1.0.12"

    authority_document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    authority_document["authority_id"] = "hka_000000000000000000000000000000000000000000000009"
    authority_document.pop("fingerprint")
    authority_document["fingerprint"] = execution._digest(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        execution._canonical(authority_document)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )
    authority.write_bytes(
        execution._canonical(authority_document)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )

    grandchild_id = "judiciary-mixed-chain-grandchild"
    grandchild_transport = OneOutage()
    grandchild_clock = _JudiciaryClock()
    grandchild = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=grandchild_id,
        predecessor_attempt_id=child_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=grandchild_transport,
        judiciary_clock=grandchild_clock.monotonic,
        judiciary_sleeper=grandchild_clock.sleep,
    )
    assert grandchild_transport.calls == child_transport.calls
    assert grandchild["predecessor_attempt_id"] == child_id

    return _MixedJudiciaryChain(
        authority,
        output,
        cutoff,
        parent_id,
        child_id,
        grandchild_id,
        child,
        grandchild,
    )


def test_judiciary_three_generation_chain_replays_each_mixed_contract_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A child with an old prefix and current suffix may itself be continued safely."""
    chain = _mixed_judiciary_three_generation_chain(
        tmp_path,
        monkeypatch,
        label="mixed-contract-three-generation",
    )

    @dataclass(slots=True)
    class NoReplayTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = NoReplayTransport()
    replayed = execute_source_family(
        authority_manifest=chain.authority,
        source_family="JUDICIARY",
        output_root=chain.output,
        attempt_id=chain.grandchild_id,
        predecessor_attempt_id=chain.child_id,
        observation_cutoff=chain.cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replayed == chain.grandchild
    assert replay_transport.calls == 0


def test_judiciary_mixed_contract_semantic_stop_continues_after_parser_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repaired suffix parser replays inherited URLs under their owning contracts."""
    chain = _mixed_judiciary_three_generation_chain(
        tmp_path,
        monkeypatch,
        label="mixed-contract-semantic-stop",
    )
    repaired_body = _current_judiciary_paginated_result_body(
        year=1997,
        page=2,
        reported_results=11,
        reported_pages=2,
        rows=((1011, "11/07/1997"),),
    )
    original_parser = execution.parse_judiciary_year_result_page
    original_registered = execution._registered_endpoints  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    original_result_version = execution._judiciary_result_contract_version  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    original_build_year = execution.build_judiciary_year_result_url
    original_build_next = execution.build_judiciary_next_result_url
    original_require_year = execution.require_judiciary_year_result_url
    original_replay = execution._replay_judiciary_procedures  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    parser_repair_active = False

    def gated_parser(
        body: bytes,
        *,
        year: int,
        page: int,
        contract_version: str,
    ) -> JudiciaryYearResultPage:
        if (
            not parser_repair_active
            and contract_version == "1.0.12"
            and page == 2
            and body == repaired_body
        ):
            error = "synthetic parser contract stop"
            raise ValueError(error)
        return original_parser(
            body,
            year=year,
            page=page,
            contract_version="1.0.12" if contract_version == "1.0.13" else contract_version,
        )

    def future_result_version(entry_contract_version: str) -> str:
        if entry_contract_version == "1.0.14":
            return "1.0.13"
        return original_result_version(entry_contract_version)

    def future_build_year(
        form_body: bytes,
        *,
        entry_url: str,
        year: int,
        page: int,
        contract_version: str = "1.0.2",
    ) -> str:
        return original_build_year(
            form_body,
            entry_url=entry_url,
            year=year,
            page=page,
            contract_version="1.0.13" if contract_version == "1.0.14" else contract_version,
        )

    def future_build_next(
        current_url: str,
        *,
        result_page: JudiciaryYearResultPage,
        form_contract_version: str = "1.0.3",
    ) -> str:
        return original_build_next(
            current_url,
            result_page=result_page,
            form_contract_version=(
                "1.0.13" if form_contract_version == "1.0.14" else form_contract_version
            ),
        )

    def future_require_year(
        url: str,
        *,
        year: int,
        page: int,
        contract_version: str = "1.0.2",
    ) -> str:
        return original_require_year(
            url,
            year=year,
            page=page,
            contract_version="1.0.13" if contract_version == "1.0.14" else contract_version,
        )

    def future_replay(
        **kwargs: object,
    ) -> tuple[
        list[dict[str, object]],
        set[str],
        tuple[str, str, str, str, int] | None,
    ]:
        nonlocal parser_repair_active
        kwargs["result_contract_version_override"] = "1.0.12"
        parser_repair_active = True
        try:
            return original_replay(**kwargs)  # type: ignore[arg-type]
        finally:
            parser_repair_active = False

    monkeypatch.setattr(execution, "parse_judiciary_year_result_page", gated_parser)
    monkeypatch.setattr(execution, "_judiciary_result_contract_version", future_result_version)
    monkeypatch.setattr(execution, "build_judiciary_year_result_url", future_build_year)
    monkeypatch.setattr(execution, "build_judiciary_next_result_url", future_build_next)
    monkeypatch.setattr(execution, "require_judiciary_year_result_url", future_require_year)
    monkeypatch.setattr(execution, "_replay_judiciary_procedures", future_replay)

    records = tuple(
        cast("dict[str, object]", json.loads(execution._canonical(item)))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        for item in _items(chain.child, "endpoints")
    )
    failed = records[-1]
    failed["body_fingerprint"] = execution._digest(repaired_body)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    failed["byte_length"] = len(repaired_body)
    failed["media_type"] = "text/html"
    failed["status"] = 200
    failed["terminal_code"] = "SOURCE_CONTRACT_CHANGED"
    final_attempt = dict(_items(chain.child, "transport_attempts")[-1])
    final_attempt.update(
        {
            "body_fingerprint": failed["body_fingerprint"],
            "byte_length": len(repaired_body),
            "final_url": failed["requested_url"],
            "media_type": "text/html",
            "redirect_rejected": False,
            "status": 200,
            "terminal_code": "CAPTURED",
        }
    )
    _fingerprints, bodies = execution._projection_bodies(chain.output, chain.child)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    bodies[cast("str", failed["endpoint_id"])] = repaired_body
    historical_endpoints = original_registered("JUDICIARY", judiciary_endpoint_204_version="1.0.13")
    current_endpoints = original_registered("JUDICIARY", judiciary_endpoint_204_version="1.0.14")
    assert execution._judiciary_semantic_stop_is_accepted_by_current_contract(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        failed,
        final_attempt,
        repaired_body,
        current_registered_endpoints=current_endpoints,
        historical_registered_endpoints=historical_endpoints,
        records=records,
        bodies=bodies,
        observation_cutoff=chain.cutoff,
        record_urls_are_prevalidated=True,
    )


@pytest.mark.parametrize(
    "mutation",
    ["version", "url", "binding", "object", "prefix", "suffix"],
)
def test_judiciary_mixed_contract_chain_rejects_each_hostile_pre_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """Every mixed-chain contract surface is rederived before descendant transport."""
    chain = _mixed_judiciary_three_generation_chain(
        tmp_path,
        monkeypatch,
        label=f"mixed-contract-hostile-{mutation}",
    )
    child_path = chain.output / "attempts" / chain.child_id / "report.json"
    grandchild_path = chain.output / "attempts" / chain.grandchild_id / "report.json"
    child = cast(
        "dict[str, object]",
        json.loads(execution._canonical(chain.child)),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )
    grandchild = cast(
        "dict[str, object]",
        json.loads(execution._canonical(chain.grandchild)),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )
    binding = cast("dict[str, object]", child["continuation_binding"])
    prefix_count = cast("int", binding["prefix_endpoint_count"])
    suffix = _items(child, "endpoints")[prefix_count]
    final_attempt = _items(child, "transport_attempts")[-1]
    if mutation == "version":
        suffix["endpoint_version"] = "1.0.11"
        final_attempt["endpoint_version"] = "1.0.11"
        cast("dict[str, object]", binding["next_request"])["endpoint_version"] = "1.0.11"
    elif mutation == "url":
        hostile_url = cast("str", suffix["requested_url"]) + "&hostile=1"
        suffix["requested_url"] = hostile_url
        final_attempt["requested_url"] = hostile_url
        cast("dict[str, object]", binding["next_request"])["requested_url"] = hostile_url
    elif mutation == "binding":
        binding["prefix_endpoints_fingerprint"] = "sha256:" + "0" * 64
    elif mutation == "object":
        object_path = chain.output / cast("str", suffix["object_key"])
        object_path.write_bytes(object_path.read_bytes() + b"hostile")
    elif mutation == "prefix":
        _items(child, "endpoints")[prefix_count - 1]["endpoint_version"] = "1.0.12"
        binding["prefix_endpoints_fingerprint"] = execution._digest(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            execution._canonical(_items(child, "endpoints")[:prefix_count])  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        )
    else:
        suffix["terminal_code"] = "SOURCE_CONTRACT_CHANGED"
        suffix["status"] = 200
        final_attempt.update(
            {
                "final_url": suffix["requested_url"],
                "redirect_rejected": False,
                "status": 200,
                "terminal_code": "CAPTURED",
            }
        )
        counts = cast("dict[str, object]", child["endpoint_counts"])
        counts.pop("OUTAGE")
        counts["SOURCE_CONTRACT_CHANGED"] = 1
        child["result"] = "SOURCE_CONTRACT_CHANGED"

    if mutation != "object":
        child_bytes = execution._canonical(child)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        child_path.write_bytes(child_bytes)
        grandchild_binding = cast("dict[str, object]", grandchild["continuation_binding"])
        grandchild_binding["predecessor_report_fingerprint"] = (
            "sha256:" + hashlib.sha256(child_bytes).hexdigest()
        )
        grandchild_path.write_bytes(execution._canonical(grandchild))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class NoTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    transport = NoTransport()
    with pytest.raises(
        execution.PredecessorValidationError,
        match=r"PREDECESSOR_(?:REPORT_MALFORMED|EVIDENCE_READBACK_INVALID)",
    ):
        execute_source_family(
            authority_manifest=chain.authority,
            source_family="JUDICIARY",
            output_root=chain.output,
            attempt_id=chain.grandchild_id,
            predecessor_attempt_id=chain.child_id,
            observation_cutoff=chain.cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert transport.calls == 0


@pytest.mark.parametrize(
    ("phase", "failed_call", "endpoint_fragment"),
    [
        ("pass1", 5, "judiciary-year-1997-page-1"),
        ("pass2", 6, "judiciary-year-1997-verification-page-1"),
        ("detail", 7, "judiciary-dis-2"),
    ],
)
def test_judiciary_continuation_derives_each_writer_phase_without_prefix_transport(
    tmp_path: Path,
    phase: str,
    failed_call: int,
    endpoint_fragment: str,
) -> None:
    """The generic bridge resumes the writer's pass-1, pass-2, and detail order."""
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / phase
    )

    class OutageAtPhase(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == failed_call:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"temporary outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_transport = OutageAtPhase()
    parent_clock = _JudiciaryClock()
    parent_id = f"judiciary-generic-{phase}-parent"
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=parent_transport,
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    assert parent["result"] == "SOURCE_OUTAGE"
    failed = _items(parent, "endpoints")[-1]
    assert failed["endpoint_id"] == endpoint_fragment
    assert failed["endpoint_version"] == "1.0.12"
    expected_url = cast("str", failed["requested_url"])
    _replace_authority_identity(authority)

    @dataclass(slots=True)
    class SuffixOnly:
        urls: list[str] = field(default_factory=lambda: cast("list[str]", []))

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.urls.append(url)
            assert len(self.urls) == 1
            assert url == expected_url
            assert max_bytes == 16_777_216
            return CapturedResponse(503, "text/html", b"still unavailable", None)

    suffix = SuffixOnly()
    child_id = f"judiciary-generic-{phase}-child"
    crash_debris = output / "attempts" / child_id / ".report.json.crash-debris"
    crash_debris.parent.mkdir(parents=True, exist_ok=True)
    crash_debris.write_bytes(b"incomplete-unpublished-report")
    child_clock = _JudiciaryClock()
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=child_id,
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=suffix,
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )
    assert suffix.urls == [expected_url]
    assert child["report_schema_version"] == "1.2.0"
    assert _items(child, "endpoints")[-1]["endpoint_id"] == endpoint_fragment
    assert _items(child, "endpoints")[-1]["endpoint_version"] == "1.0.12"
    continuation_binding = cast("dict[str, object]", child["continuation_binding"])
    next_request = cast("dict[str, object]", continuation_binding["next_request"])
    assert next_request["endpoint_version"] == "1.0.12"
    assert crash_debris.read_bytes() == b"incomplete-unpublished-report"

    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_ATTEMPT_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=f"judiciary-generic-{phase}-competing-child",
            predecessor_attempt_id=parent_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=suffix,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert suffix.urls == [expected_url]


def test_judiciary_continuation_retries_only_the_suffix_and_charges_cumulative_budget(
    tmp_path: Path,
) -> None:
    """A transient suffix retry is physical-only and inherits the parent's accounting."""
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "segment-retry"
    )

    class ParentOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == 5:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"parent-outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_clock = _JudiciaryClock()
    parent_id = "judiciary-segment-retry-parent"
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ParentOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    expected_url = cast("str", _items(parent, "endpoints")[-1]["requested_url"])
    parent_accounting = cast("dict[str, object]", parent["observation_accounting"])
    _replace_authority_identity(authority)

    class RetrySuffix(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.starts.append(self._clock.value)
            self.urls.append(url)
            assert url == expected_url
            assert max_bytes == 16_777_216
            if len(self.urls) == 1:
                raise OSError
            return CapturedResponse(503, "text/html", b"child-outage", None)

    child_clock = _JudiciaryClock()
    suffix = RetrySuffix(child_clock)
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-segment-retry-child",
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=suffix,
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )

    assert suffix.urls == [expected_url, expected_url]
    assert len(_items(child, "transport_attempts")) == 2
    segment = cast("dict[str, object]", child["observation_accounting"])
    cumulative = cast("dict[str, object]", child["cumulative_observation_accounting"])
    assert segment["request_starts"] == 2
    assert cumulative["request_starts"] == cast("int", parent_accounting["request_starts"]) + 2
    assert cumulative["retained_response_bytes"] == (
        cast("int", parent_accounting["retained_response_bytes"])
        + cast("int", segment["retained_response_bytes"])
    )

    first_attempt = _items(child, "transport_attempts")[0]
    first_attempt_object = output / cast("str", first_attempt["object_key"])
    assert first_attempt_object.exists()
    assert first_attempt["object_key"] != _items(child, "endpoints")[-1]["object_key"]
    first_attempt_object.unlink()

    @dataclass(slots=True)
    class NoReplayTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = NoReplayTransport()
    with pytest.raises(
        execution.PredecessorValidationError,
        match="PREDECESSOR_EVIDENCE_READBACK_INVALID",
    ):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-segment-retry-child",
            predecessor_attempt_id=parent_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=replay_transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert replay_transport.calls == 0


def test_judiciary_continuation_runs_pass1_then_fresh_pass2_and_details(
    tmp_path: Path,
) -> None:
    """A pass-1 outage resumes through fresh verification and detail capture."""
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "complete-continuation"
    )

    class ParentOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == 5:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"parent-outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_clock = _JudiciaryClock()
    parent_id = "judiciary-complete-continuation-parent"
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ParentOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    assert parent["result"] == "SOURCE_OUTAGE"
    expected_url = cast("str", _items(parent, "endpoints")[-1]["requested_url"])
    prefix_count = len(_items(parent, "endpoints")) - 1
    _replace_authority_identity(authority)

    suffix = _JudiciaryTransport()
    child_clock = _JudiciaryClock()
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-complete-continuation-child",
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=suffix,
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )

    assert suffix.urls[0] == expected_url
    assert len(_items(child, "endpoints")) > prefix_count
    assert child["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"
    suffix_ids = [item["endpoint_id"] for item in _items(child, "transport_attempts")]
    assert "judiciary-year-1997-verification-page-1" in suffix_ids
    assert "judiciary-dis-2" in suffix_ids

    report_path = output / "attempts/judiciary-complete-continuation-child/report.json"

    @dataclass(slots=True)
    class NoReplayTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = NoReplayTransport()

    def assert_replay_rejected(forged: dict[str, object]) -> None:
        report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        with pytest.raises(
            execution.PredecessorValidationError,
            match="PREDECESSOR_REPORT_MALFORMED",
        ):
            execute_source_family(
                authority_manifest=authority,
                source_family="JUDICIARY",
                output_root=output,
                attempt_id="judiciary-complete-continuation-child",
                predecessor_attempt_id=parent_id,
                observation_cutoff=cutoff,
                repository_root=REPOSITORY_ROOT,
                transport=replay_transport,
                judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
                judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
            )
        assert replay_transport.calls == 0

    forged_max = cast(
        "dict[str, object]",
        json.loads(execution._canonical(child)),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )
    _items(forged_max, "transport_attempts")[1]["max_bytes"] = 1_000_000
    assert_replay_rejected(forged_max)

    forged_binding_type = cast(
        "dict[str, object]",
        json.loads(execution._canonical(child)),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )
    binding = cast("dict[str, object]", forged_binding_type["continuation_binding"])
    predecessor_accounting = cast(
        "dict[str, object]", binding["predecessor_observation_accounting"]
    )
    predecessor_elapsed = predecessor_accounting["elapsed_seconds"]
    assert type(predecessor_elapsed) is float
    predecessor_accounting["elapsed_seconds"] = int(predecessor_elapsed)
    assert_replay_rejected(forged_binding_type)

    forged_sequence_types = cast(
        "dict[str, object]",
        json.loads(execution._canonical(child)),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )
    first_attempt = _items(forged_sequence_types, "transport_attempts")[0]
    first_attempt["sequence"] = 1.0
    first_attempt["attempt_number"] = 1.0
    assert_replay_rejected(forged_sequence_types)


def test_judiciary_continuation_stops_at_inherited_request_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The child gets only the parent's remaining request starts, not a fresh ceiling."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 6)
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "inherited-request-ceiling"
    )

    class ParentOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == 5:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"parent-outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_clock = _JudiciaryClock()
    parent_id = "judiciary-inherited-ceiling-parent"
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ParentOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    expected_url = cast("str", _items(parent, "endpoints")[-1]["requested_url"])
    assert cast("dict[str, object]", parent["observation_accounting"])["request_starts"] == 5
    _replace_authority_identity(authority)

    @dataclass(slots=True)
    class OneFailedStart:
        urls: list[str] = field(default_factory=lambda: cast("list[str]", []))

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.urls.append(url)
            assert url == expected_url
            assert max_bytes == 16_777_216
            raise OSError

    suffix = OneFailedStart()
    child_clock = _JudiciaryClock()
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-inherited-ceiling-child",
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=suffix,
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )

    assert suffix.urls == [expected_url]
    segment = cast("dict[str, object]", child["observation_accounting"])
    cumulative = cast("dict[str, object]", child["cumulative_observation_accounting"])
    assert segment["request_starts"] == 1
    assert segment["stop_code"] == "REQUEST_BUDGET_EXHAUSTED"
    assert cumulative["request_starts"] == 6
    assert cumulative["stop_code"] == "REQUEST_BUDGET_EXHAUSTED"

    @dataclass(slots=True)
    class NoReplayTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = NoReplayTransport()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-inherited-ceiling-child",
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=replay_transport,
        judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
        judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
    )
    assert replayed == child
    assert replay_transport.calls == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "profile-limit-float",
        "cumulative-starts-float",
        "stop-starts-float",
        "binding-elapsed-int",
        "binding-next-max-float",
        "attempt-sequence-float",
        "attempt-number-float",
        "prefix-count-float",
        "cumulative-stop-code-bool",
    ],
)
def test_judiciary_continuation_schema12_nested_fields_are_type_exact(  # noqa: C901
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """Canonical schema-1.2 replay rejects nested numeric and scalar type changes."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 6)
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / mutation
    )

    class ParentOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == 5:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"parent-outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_clock = _JudiciaryClock()
    parent_id = f"judiciary-type-{mutation}-parent"
    execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ParentOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    _replace_authority_identity(authority)

    class OneFailedStart:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            del url, max_bytes
            raise OSError

    child_clock = _JudiciaryClock()
    child_id = f"judiciary-type-{mutation}-child"
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=child_id,
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=OneFailedStart(),
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )
    forged = cast(
        "dict[str, object]",
        json.loads(execution._canonical(child)),  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    )
    binding = cast("dict[str, object]", forged["continuation_binding"])
    cumulative = cast("dict[str, object]", forged["cumulative_observation_accounting"])
    stop = cast("dict[str, object]", forged["observation_stop"])
    attempts = _items(forged, "transport_attempts")
    if mutation == "profile-limit-float":
        for container_name in (
            "observation_accounting",
            "cumulative_observation_accounting",
            "observation_stop",
        ):
            container = cast("dict[str, object]", forged[container_name])
            profile = cast("dict[str, object]", container["profile"])
            profile["request_start_limit"] = 6.0
            container["profile_fingerprint"] = execution._digest(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
                execution._canonical(profile)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            )
    elif mutation == "cumulative-starts-float":
        cumulative["request_starts"] = 6.0
    elif mutation == "stop-starts-float":
        stop["request_starts"] = 1.0
    elif mutation == "binding-elapsed-int":
        predecessor_accounting = cast(
            "dict[str, object]", binding["predecessor_observation_accounting"]
        )
        predecessor_accounting["elapsed_seconds"] = int(
            cast("float", predecessor_accounting["elapsed_seconds"])
        )
    elif mutation == "binding-next-max-float":
        next_request = cast("dict[str, object]", binding["next_request"])
        next_request["max_bytes"] = float(cast("int", next_request["max_bytes"]))
    elif mutation == "attempt-sequence-float":
        attempts[0]["sequence"] = 1.0
    elif mutation == "attempt-number-float":
        attempts[0]["attempt_number"] = 1.0
    elif mutation == "prefix-count-float":
        binding["prefix_endpoint_count"] = float(cast("int", binding["prefix_endpoint_count"]))
    else:
        cumulative["stop_code"] = False
    report_path = output / "attempts" / child_id / "report.json"
    report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class NoReplayTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = NoReplayTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=child_id,
            predecessor_attempt_id=parent_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=replay_transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert replay_transport.calls == 0


def test_judiciary_continuation_binds_later_physical_only_stop_to_exact_next_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later stopped retry group cannot claim a different traversal request."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 7)
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "later-physical-stop"
    )

    class ParentOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == 5:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"parent-outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_clock = _JudiciaryClock()
    parent_id = "judiciary-later-stop-parent"
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ParentOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    assert parent["result"] == "SOURCE_OUTAGE"
    _replace_authority_identity(authority)

    class StopOnVerification(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if self.urls:
                self.starts.append(self._clock.value)
                self.urls.append(url)
                raise OSError
            return super().get(url=url, max_bytes=max_bytes)

    child_clock = _JudiciaryClock()
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-later-stop-child",
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=StopOnVerification(child_clock),
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )
    assert cast("dict[str, object]", child["observation_accounting"])["stop_code"] == (
        "REQUEST_BUDGET_EXHAUSTED"
    )
    assert len(_items(child, "transport_attempts")) == 2
    assert len(_items(child, "endpoints")) == 5

    report_path = output / "attempts/judiciary-later-stop-child/report.json"
    forged = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    stopped = _items(forged, "transport_attempts")[-1]
    stopped["endpoint_id"] = "judiciary-forged-stop"
    stopped["requested_url"] = "https://evil.example/x"
    report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class NoReplayTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    replay_transport = NoReplayTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-later-stop-child",
            predecessor_attempt_id=parent_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=replay_transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert replay_transport.calls == 0


@pytest.mark.parametrize("tamper", ["report", "object", "failed-not-last", "parser"])
def test_judiciary_continuation_rejects_parent_evidence_tamper_before_transport(
    tmp_path: Path,
    tamper: str,
) -> None:
    """The bridge independently closes the parent report, objects, order, and parser contract."""
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / tamper
    )

    class ParentOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == 5:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"parent-outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_id = f"judiciary-{tamper}-parent"
    parent_clock = _JudiciaryClock()
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ParentOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    assert parent["result"] == "SOURCE_OUTAGE"
    report_path = output / "attempts" / parent_id / "report.json"
    forged = cast("dict[str, object]", json.loads(report_path.read_bytes()))
    if tamper == "report":
        forged["result"] = "COMPLETE"
        report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    elif tamper == "object":
        object_key = cast("str", _items(parent, "endpoints")[0]["object_key"])
        (output / object_key).write_bytes(b"tampered-object")
    elif tamper == "failed-not-last":
        endpoints = _items(forged, "endpoints")
        later_capture = dict(_items(forged, "transport_attempts")[0])
        later_capture["endpoint_id"] = "judiciary-forged-later-capture"
        endpoints.append(later_capture)
        counts = cast("dict[str, int]", forged["endpoint_counts"])
        counts["CAPTURED"] = 1
        report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    else:
        _items(forged, "endpoints")[0]["endpoint_version"] = "99.0.0"
        report_path.write_bytes(execution._canonical(forged))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    _replace_authority_identity(authority)

    @dataclass(slots=True)
    class NoTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    transport = NoTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=f"judiciary-{tamper}-child",
            predecessor_attempt_id=parent_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert transport.calls == 0


def test_judiciary_continuation_rejects_cutoff_drift_before_transport(tmp_path: Path) -> None:
    """A new valid authority at a different cutoff cannot continue an older observation."""
    parent_cutoff = "1997-12-31T23:59:59+08:00"
    child_cutoff = "1998-01-01T00:00:00+08:00"
    authority = _authority(tmp_path, cutoff=parent_cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "cutoff-drift"
    )

    class ParentOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == 5:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"parent-outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_clock = _JudiciaryClock()
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-cutoff-drift-parent",
        observation_cutoff=parent_cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ParentOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    assert parent["result"] == "SOURCE_OUTAGE"
    authority = _authority(tmp_path, cutoff=child_cutoff)

    @dataclass(slots=True)
    class NoTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    transport = NoTransport()
    with pytest.raises(
        execution.PredecessorValidationError, match="PREDECESSOR_REPORT_BINDING_INVALID"
    ):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-cutoff-drift-child",
            predecessor_attempt_id="judiciary-cutoff-drift-parent",
            observation_cutoff=child_cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert transport.calls == 0


@pytest.mark.parametrize("budget", ["request", "byte", "elapsed"])
def test_judiciary_continuation_rejects_exhausted_cumulative_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    budget: str,
) -> None:
    """A fresh authorization cannot reset any exhausted observation ceiling."""
    if budget == "request":
        monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 1)
    elif budget == "byte":
        monkeypatch.setattr(execution, "_JUDICIARY_RETAINED_BYTE_LIMIT", 0)
    else:
        monkeypatch.setattr(execution, "_JUDICIARY_ELAPSED_SECONDS_LIMIT", 1.0)

    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / budget
    )
    clock = _JudiciaryClock()

    class ExhaustBudget(_TimedJudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.starts.append(self._clock.value)
            self.urls.append(url)
            assert max_bytes > 0
            if len(self.urls) == 1:
                raise OSError
            if budget == "byte":
                return CapturedResponse(200, "text/html", b"rejected-body", url)
            raise OSError

    parent_id = f"judiciary-{budget}-budget-parent"
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ExhaustBudget(clock),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    assert parent["result"] == "OBSERVATION_BUDGET_EXHAUSTED"
    assert (
        cast("dict[str, object]", parent["observation_accounting"])["stop_code"]
        == {
            "request": "REQUEST_BUDGET_EXHAUSTED",
            "byte": "BYTE_BUDGET_EXHAUSTED",
            "elapsed": "ELAPSED_TIME_BUDGET_EXHAUSTED",
        }[budget]
    )
    _replace_authority_identity(authority)

    @dataclass(slots=True)
    class NoTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    transport = NoTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id=f"judiciary-{budget}-budget-child",
            predecessor_attempt_id=parent_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert transport.calls == 0


def test_judiciary_continuation_rejects_outage_on_final_allowed_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An outage at the exact ceiling is exhausted even without an observation stop."""
    monkeypatch.setattr(execution, "_JUDICIARY_REQUEST_START_LIMIT", 5)
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "final-allowed-request"
    )

    class FinalRequestOutage(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if len(self.urls) + 1 == 5:
                self.urls.append(url)
                return CapturedResponse(503, "text/html", b"final-request-outage", None)
            return super().get(url=url, max_bytes=max_bytes)

    parent_clock = _JudiciaryClock()
    parent_id = "judiciary-final-allowed-request-parent"
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=FinalRequestOutage(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    assert parent["result"] == "SOURCE_OUTAGE"
    assert "observation_stop" not in parent
    assert cast("dict[str, object]", parent["observation_accounting"])["request_starts"] == 5
    _replace_authority_identity(authority)

    @dataclass(slots=True)
    class NoTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    transport = NoTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-final-allowed-request-child",
            predecessor_attempt_id=parent_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert transport.calls == 0


def test_judiciary_continuation_rejects_parser_contract_failure_before_transport(
    tmp_path: Path,
) -> None:
    """A semantic failure the current parser still rejects remains non-resumable."""
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "semantic-parent"
    )
    clock = _JudiciaryClock()
    parent_id = "judiciary-semantic-parent"
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_JudiciaryContractChangedTransport(),
        judiciary_clock=clock.monotonic,
        judiciary_sleeper=clock.sleep,
    )
    assert parent["result"] == "SOURCE_CONTRACT_CHANGED"
    assert _items(parent, "endpoints")[-1]["terminal_code"] == "SOURCE_CONTRACT_CHANGED"
    _replace_authority_identity(authority)

    @dataclass(slots=True)
    class NoTransport:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    transport = NoTransport()
    with pytest.raises(execution.PredecessorValidationError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-semantic-child",
            predecessor_attempt_id=parent_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=transport,
            judiciary_clock=lambda: (_ for _ in ()).throw(AssertionError("clock")),
            judiciary_sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep")),
        )
    assert transport.calls == 0


@pytest.mark.parametrize(
    ("final_dis_id", "expected_outcome"),
    [(1011, "resumable"), (1010, "rejected")],
)
def test_judiciary_semantic_continuation_requires_repaired_full_pass1_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_dis_id: int,
    expected_outcome: str,
) -> None:
    """A parsed final page is resumable only when current full-prefix semantics reconcile."""
    cutoff = "1997-12-31T23:59:59+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "semantic-repair"
    )
    original_registered = execution._registered_endpoints  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def historical_registered_endpoints(
        source_family: str,
        *,
        judiciary_endpoint_204_version: str | None = None,
        hkex_historical_attempt_id: str | None = None,
    ) -> tuple[OfficialEndpointContract, ...]:
        endpoints = original_registered(
            source_family,
            judiciary_endpoint_204_version=judiciary_endpoint_204_version,
            hkex_historical_attempt_id=hkex_historical_attempt_id,
        )
        if source_family != "JUDICIARY" or judiciary_endpoint_204_version is not None:
            return endpoints
        return tuple(
            replace(endpoint, version="1.0.12")
            if endpoint.endpoint_id == "sep_000000000000000000000000000000000000000000000204"
            else endpoint
            for endpoint in endpoints
        )

    class HistoricalPass1ContractStop(_JudiciaryTransport):
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if "year=1997" in url:
                self.urls.append(url)
                page = 2 if "&page=2" in url else 1
                body = _current_judiciary_paginated_result_body(
                    year=1997,
                    page=page,
                    reported_results=11,
                    reported_pages=2,
                    rows=(
                        ((final_dis_id, "11/07/1997"),)
                        if page == 2
                        else tuple((1000 + day, f"{day:02d}/07/1997") for day in range(1, 11))
                    ),
                )
                if page == 2:
                    original = (
                        b"<a href=\"javascript:judpop1('search_result_detail_frame.jsp?'"
                        + f'+temp{final_dis_id});">entry</a>'.encode()
                        + b"<a href=\"javascript:judpop('search_result_detail_frame.jsp?'"
                        + f'+temp{final_dis_id});">entry</a>'.encode()
                    )
                    replacement = (
                        b"<a href=\"javascript:judpop1('/doc/judg/word/vetted/other/en/"
                        b"1997/sanitized.doc');\">entry</a>"
                        b'<a href="https://legalref.judiciary.hk/lrs//common/ju/ju_frame.jsp?'
                        + f'AH=S&DIS={final_dis_id}&QS=%2B&TP=JU" '.encode()
                        + b'target="_top" class=default >frame</a>'
                    )
                    assert body.count(original) == 1
                    body = body.replace(original, replacement, 1)
                return CapturedResponse(200, "text/html", body[: max_bytes + 1], url)
            return super().get(url=url, max_bytes=max_bytes)

    monkeypatch.setattr(execution, "_registered_endpoints", historical_registered_endpoints)
    parent_id = "judiciary-synthetic-semantic-repair-parent"
    parent_clock = _JudiciaryClock()
    parent = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=HistoricalPass1ContractStop(),
        judiciary_clock=parent_clock.monotonic,
        judiciary_sleeper=parent_clock.sleep,
    )
    failed = _items(parent, "endpoints")[-1]
    assert failed["endpoint_id"] == "judiciary-year-1997-page-2"
    assert failed["endpoint_version"] == "1.0.11"
    assert failed["terminal_code"] == "SOURCE_CONTRACT_CHANGED"
    expected_url = cast("str", failed["requested_url"])

    monkeypatch.setattr(execution, "_registered_endpoints", original_registered)
    _replace_authority_identity(authority)

    @dataclass(slots=True)
    class FirstRequestOnly:
        calls: list[tuple[str, int]] = field(
            default_factory=lambda: cast("list[tuple[str, int]]", [])
        )

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls.append((url, max_bytes))
            assert self.calls == [(expected_url, 16_777_216)]
            return CapturedResponse(418, "text/html", b"synthetic terminal", url)

    transport = FirstRequestOnly()
    child_clock = _JudiciaryClock()
    if expected_outcome == "rejected":
        with pytest.raises(
            execution.PredecessorValidationError,
            match="PREDECESSOR_REPORT_MALFORMED",
        ):
            execute_source_family(
                authority_manifest=authority,
                source_family="JUDICIARY",
                output_root=output,
                attempt_id="judiciary-synthetic-semantic-repair-child",
                predecessor_attempt_id=parent_id,
                observation_cutoff=cutoff,
                repository_root=REPOSITORY_ROOT,
                transport=transport,
                judiciary_clock=child_clock.monotonic,
                judiciary_sleeper=child_clock.sleep,
            )
        assert transport.calls == []
        return
    child = execute_source_family(
        authority_manifest=authority,
        source_family="JUDICIARY",
        output_root=output,
        attempt_id="judiciary-synthetic-semantic-repair-child",
        predecessor_attempt_id=parent_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        judiciary_clock=child_clock.monotonic,
        judiciary_sleeper=child_clock.sleep,
    )

    assert transport.calls == [(expected_url, 16_777_216)]
    binding = cast("dict[str, object]", child["continuation_binding"])
    assert binding["next_request"] == {
        "endpoint_id": "judiciary-year-1997-page-2",
        "endpoint_version": "1.0.12",
        "max_bytes": 16_777_216,
        "method": "GET",
        "requested_url": expected_url,
    }


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260831o", "2026-08-31T11:05:35+08:00", None),
        ("judiciary-live-baseline-20260831p", "2026-08-31T11:05:36+08:00", None),
        (
            "judiciary-live-baseline-20260831p",
            "2026-08-31T11:05:35+08:00",
            "judiciary-live-baseline-20260831o",
        ),
    ],
)
def test_judiciary_attempt_p_requires_exact_invocation_tuple(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """P cannot replay under a different attempt, cutoff, or predecessor."""
    authority, output, _report = _install_judiciary_attempt_fixture(tmp_path, "p")
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize(
    "mutation", ["authority", "register", "allowed_url", "schema", "policy", "binding", "report"]
)
def test_judiciary_attempt_p_rejects_every_pinned_identity_mutation(
    tmp_path: Path, mutation: str
) -> None:
    """P binds its report, authority, register, URLs, schema, policy, and execution."""
    authority, output, report = _install_judiciary_attempt_fixture(tmp_path, "p")
    report_path = output / "attempts/judiciary-live-baseline-20260831p/report.json"
    if mutation in {"schema", "policy", "binding", "report"}:
        field, value = {
            "schema": ("report_schema_version", "1.0.0"),
            "policy": ("execution_policy_fingerprint", "sha256:" + "0" * 64),
            "binding": ("execution_authorization_fingerprint", "sha256:" + "0" * 64),
            "report": ("result", "COMPLETE"),
        }[mutation]
        report[field] = value
        report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    else:
        document = cast("dict[str, object]", json.loads(authority.read_bytes()))
        if mutation == "authority":
            document["authority_id"] = "hka_000000000000000000000000000000000000000000000796"
        elif mutation == "register":
            registers = cast("list[dict[str, object]]", document["registers"])
            next(item for item in registers if item["family"] == "CASES")["register_version"] = (
                "2026-08-31.12"
            )
        else:
            sources = cast("list[dict[str, object]]", document["selected_sources"])
            judiciary = next(
                item for item in sources if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY"
            )
            endpoints = cast("list[dict[str, object]]", judiciary["endpoints"])
            endpoints[0]["path"] = cast("str", endpoints[0]["path"]) + "&changed=1"
        document.pop("fingerprint")
        document["fingerprint"] = (
            "sha256:" + hashlib.sha256(execution._canonical(document)).hexdigest()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        )
        authority.write_bytes(execution._canonical(document))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff="2026-08-31T11:05:35+08:00",
            attempt_id="judiciary-live-baseline-20260831p",
            predecessor_attempt_id=None,
            repository_root=REPOSITORY_ROOT,
        )


def test_frozen_judiciary_reports_a_through_p_match_their_raw_sha256_pins() -> None:
    """Contract evolution must not rewrite any historical retained report bytes."""
    expected = {
        "a": "262e7c9447802df3a76ceca29bc6d3986fd14116788ddee48b868eccd5d06296",
        "b": "1617c6f37ea553078587ce7d9bbd404a0d35f0e53ca002b91657eece538a0df6",
        "c": "482cf5c615688e10f39886cdfab7a03eaf1604e5ca29cb27aff907ec6ce06a2d",
        "d": "210e3818e68c4703cc4afa9030f81cdaccdb951def5ce086fe9e6050576ec9e4",
        "e": "16206775ab262bd969f802c15fcfc3af1a47a06c821584ad20a23c1aa46188a1",
        "f": "ea768746b1b9d497cab97a52274df0acd32b03d20d1fdfdcd1cb701c3dbc6456",
        "g": "853e12c69864016f49aa2222763ec2b8291966e691336ec4769dd236d430318c",
        "h": "88672a88dbdd3f76867a5d322e491ffa890ba145eab44ec25588e854e1f4905e",
        "i": "c39c7d1e9323648d22ef46617493e850dfc10922a43d2c76d55466eee6eaea76",
        "j": "a8c0be2da723aa45d89e95b33283e116f12ffc7bfcd37d7e88c2e178a73caca3",
        "k": "363aa365f8fdc4cc2ca08b0fcb623a6ddc0e2f67d7f7b8db3388c1163f558d04",
        "l": "9803075a2bf092743a97080d8adc1dc91eafe3e68ed8172f166cfdf32b3eab31",
        "m": "eb382465f907cfd6bff216e8c7412e21f70d718a7ee4180282e64fb80c2b51c0",
        "n": "1213a1edb85870f053f86f63bb6fc3544a9b6181bea76175e4083da3149d4660",
        "o": "7d61c67d83696af61f78594a69282668c045b744437f31fa40897d3db5fe514d",
        "p": "e8cc1c5e11a4c25f7a23e89b8889761c14aca240f5f717dc6f29966a3a96e918",
    }
    for suffix, fingerprint in expected.items():
        attempt_id = (
            "judiciary-live-baseline-20260828a"
            if suffix == "a"
            else (
                f"judiciary-live-baseline-20260831{suffix}"
                if suffix in {"n", "o", "p"}
                else f"judiciary-live-baseline-20260830{suffix}"
            )
        )
        report_path = (
            REPOSITORY_ROOT
            / "var/hk-v1/source-admission"
            / f"judiciary-attempt-{suffix}"
            / "attempts"
            / attempt_id
            / "report.json"
        )
        assert hashlib.sha256(report_path.read_bytes()).hexdigest() == fingerprint


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830j", "2026-08-30T20:22:35+08:00", None),
        ("judiciary-live-baseline-20260830k", "2026-08-30T20:22:36+08:00", None),
        (
            "judiciary-live-baseline-20260830k",
            "2026-08-30T20:22:35+08:00",
            "judiciary-live-baseline-20260830j",
        ),
    ],
)
def test_judiciary_attempt_k_requires_exact_invocation_tuple(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt K cannot be replayed under another attempt, cutoff, or predecessor."""
    authority, output, _report = _install_judiciary_attempt_k_fixture(tmp_path)

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize("mutation", ["authority", "register", "allowed_url"])
def test_judiciary_attempt_k_rejects_mutated_authority_binding(
    tmp_path: Path, mutation: str
) -> None:
    """Historical replay binds the exact K authority, register, and URL grant."""
    authority, output, _report = _install_judiciary_attempt_k_fixture(tmp_path)
    document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    if mutation == "authority":
        document["authority_id"] = "hka_000000000000000000000000000000000000000000000791"
    elif mutation == "register":
        registers = cast("list[dict[str, object]]", document["registers"])
        next(item for item in registers if item["family"] == "CASES")["register_version"] = (
            "2026-08-30.11"
        )
    else:
        sources = cast("list[dict[str, object]]", document["selected_sources"])
        judiciary = next(
            item for item in sources if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY"
        )
        endpoints = cast("list[dict[str, object]]", judiciary["endpoints"])
        endpoints[0]["path"] = cast("str", endpoints[0]["path"]) + "&changed=1"
    document.pop("fingerprint")
    document["fingerprint"] = "sha256:" + hashlib.sha256(execution._canonical(document)).hexdigest()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    authority.write_bytes(execution._canonical(document))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=(
                REPOSITORY_ROOT
                / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
            ),
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff="2026-08-30T20:22:35+08:00",
            attempt_id="judiciary-live-baseline-20260830k",
            predecessor_attempt_id=None,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_k_report_mutation_rejects_before_transport(tmp_path: Path) -> None:
    """Any byte-changing Attempt-K report mutation rejects before transport."""
    authority, output, report = _install_judiciary_attempt_k_fixture(tmp_path)
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-live-baseline-20260830k/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830k",
            observation_cutoff="2026-08-30T20:22:35+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830f", "2026-08-30T14:26:56+08:00", None),
        ("judiciary-live-baseline-20260830g", "2026-08-30T14:26:57+08:00", None),
        (
            "judiciary-live-baseline-20260830g",
            "2026-08-30T14:26:56+08:00",
            "judiciary-live-baseline-20260830f",
        ),
    ],
)
def test_judiciary_attempt_g_requires_exact_invocation_tuple(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt G cannot be replayed under another attempt, cutoff, or predecessor."""
    authority, output, _report = _install_judiciary_attempt_g_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_g_report_mutation_rejects_before_transport(tmp_path: Path) -> None:
    """Any byte-changing Attempt-G report mutation rejects before transport."""
    authority, output, report = _install_judiciary_attempt_g_fixture(tmp_path)
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-live-baseline-20260830g/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830g",
            observation_cutoff="2026-08-30T14:26:56+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830e", "2026-08-30T13:08:05+08:00", None),
        ("judiciary-live-baseline-20260830f", "2026-08-30T13:08:06+08:00", None),
        (
            "judiciary-live-baseline-20260830f",
            "2026-08-30T13:08:05+08:00",
            "judiciary-live-baseline-20260830e",
        ),
    ],
)
def test_judiciary_attempt_f_requires_exact_invocation_tuple(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt F cannot be replayed under another attempt, cutoff, or predecessor."""
    authority, output, _report = _install_judiciary_attempt_f_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_f_report_mutation_rejects_before_transport(tmp_path: Path) -> None:
    """Any byte-changing Attempt-F report mutation rejects before transport."""
    authority, output, report = _install_judiciary_attempt_f_fixture(tmp_path)
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-live-baseline-20260830f/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830f",
            observation_cutoff="2026-08-30T13:08:05+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830d", "2026-08-30T11:26:32+08:00", None),
        ("judiciary-live-baseline-20260830e", "2026-08-30T11:26:33+08:00", None),
        (
            "judiciary-live-baseline-20260830e",
            "2026-08-30T11:26:32+08:00",
            "judiciary-live-baseline-20260830d",
        ),
    ],
)
def test_judiciary_attempt_e_requires_exact_attempt_cutoff_and_no_predecessor(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt E's replay authority cannot be reused with another invocation tuple."""
    authority, output, _report = _install_judiciary_attempt_e_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_e_report_mutation_rejects_before_transport(tmp_path: Path) -> None:
    """Any byte-changing Attempt-E report mutation rejects before transport."""
    authority, output, report = _install_judiciary_attempt_e_fixture(tmp_path)
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-live-baseline-20260830e/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830e",
            observation_cutoff="2026-08-30T11:26:32+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830c", "2026-08-30T10:00:10+08:00", None),
        ("judiciary-live-baseline-20260830d", "2026-08-30T10:00:11+08:00", None),
        (
            "judiciary-live-baseline-20260830d",
            "2026-08-30T10:00:10+08:00",
            "judiciary-live-baseline-20260830c",
        ),
    ],
)
def test_judiciary_attempt_d_requires_exact_attempt_cutoff_and_no_predecessor(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Attempt D's replay authority is non-fungible across its invocation tuple."""
    authority, output, _report = _install_judiciary_attempt_d_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_d_report_mutation_rejects_before_transport(tmp_path: Path) -> None:
    """Any byte-changing Attempt-D report mutation rejects before transport."""
    authority, output, report = _install_judiciary_attempt_d_fixture(tmp_path)
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-live-baseline-20260830d/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830d",
            observation_cutoff="2026-08-30T10:00:10+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


def test_judiciary_attempt_c_report_mutation_rejects_before_transport(tmp_path: Path) -> None:
    """The new current grammar cannot inherit authority from altered frozen Attempt C bytes."""
    authority, output, report = _install_judiciary_attempt_c_fixture(tmp_path)
    report["result"] = "COMPLETE"
    report_path = output / "attempts/judiciary-live-baseline-20260830c/report.json"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    probe = TransportProbe()
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830c",
            observation_cutoff="2026-08-30T08:46:02+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


def test_cli_reaches_exact_attempt_b_replay_after_current_register_drift(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """The CLI must use the exact replay-only gate when current capture authority drifts."""
    authority, output, report = _install_judiciary_attempt_b_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    exit_code = admission.main(
        [
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "JUDICIARY",
            "--attempt-id",
            "judiciary-live-baseline-20260830b",
            "--observation-cutoff",
            "2026-08-30T07:18:07+08:00",
            "--output-root",
            str(output),
        ]
    )

    captured = capfd.readouterr()
    assert exit_code == 1
    assert captured.err == ""
    assert json.loads(captured.out) == report


def test_judiciary_attempt_a_raw_report_mutation_rejects_before_replay_authorization(
    tmp_path: Path,
) -> None:
    """A one-field report mutation cannot inherit the one exact historical replay grant."""
    authority, output, report = _install_judiciary_attempt_a_fixture(tmp_path)
    report["result"] = "SOURCE_CONTRACT_CHANGED"
    report_path = output / "attempts/judiciary-live-baseline-20260828a/report.json"
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff="2026-08-28T22:20:23+08:00",
            attempt_id="judiciary-live-baseline-20260828a",
            predecessor_attempt_id=None,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_b_raw_report_or_object_mutation_rejects_pre_effect(
    tmp_path: Path,
) -> None:
    """Attempt B's raw report pin and retained object readback both precede transport."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, report = _install_judiciary_attempt_b_fixture(tmp_path)
    report_path = output / "attempts/judiciary-live-baseline-20260830b/report.json"
    report["result"] = "COMPLETE"
    report_path.write_bytes(execution._canonical(report))  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    probe = TransportProbe()

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830b",
            observation_cutoff="2026-08-30T07:18:07+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0

    object_case = tmp_path.parent / f"{tmp_path.name}-object"
    authority, output, _report = _install_judiciary_attempt_b_fixture(object_case)
    object_path = next((output / "objects").glob("*.bin"))
    object_path.write_bytes(object_path.read_bytes() + b"x")
    probe = TransportProbe()
    with pytest.raises(ValueError, match="PREDECESSOR_EVIDENCE_READBACK_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260830b",
            observation_cutoff="2026-08-30T07:18:07+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260830c", "2026-08-30T07:18:07+08:00", None),
        ("judiciary-live-baseline-20260830b", "2026-08-30T07:18:08+08:00", None),
        (
            "judiciary-live-baseline-20260830b",
            "2026-08-30T07:18:07+08:00",
            "judiciary-live-baseline-20260830a",
        ),
    ],
)
def test_judiciary_attempt_b_requires_exact_attempt_cutoff_and_no_predecessor(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """No one field of attempt B's invocation tuple is fungible."""
    authority, output, _report = _install_judiciary_attempt_b_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize("drift", ["register_identity", "allowed_url", "authority"])
def test_judiciary_attempt_b_rejects_each_old_binding_component(tmp_path: Path, drift: str) -> None:
    """The old Cases pair and authority fingerprint are all independently pinned."""
    authority, output, _report = _install_judiciary_attempt_b_fixture(tmp_path)
    document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    if drift == "register_identity":
        cases = next(
            item
            for item in cast("list[dict[str, object]]", document["registers"])
            if item["family"] == "CASES"
        )
        cases["fingerprint"] = "sha256:" + "0" * 64
    elif drift == "allowed_url":
        judiciary = next(
            item
            for item in cast("list[dict[str, object]]", document["selected_sources"])
            if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY"
        )
        cast("list[dict[str, object]]", judiciary["endpoints"])[0]["path"] = (
            "/lrs/common/fabricated.jsp"
        )
    else:
        document["authority_id"] = "hka_000000000000000000000000000000000000000000000999"
    document.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    authority.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")))
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff="2026-08-30T07:18:07+08:00",
            attempt_id="judiciary-live-baseline-20260830b",
            predecessor_attempt_id=None,
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("judiciary-live-baseline-20260828b", "2026-08-28T22:20:23+08:00", None),
        ("judiciary-live-baseline-20260828a", "2026-08-28T22:20:24+08:00", None),
        (
            "judiciary-live-baseline-20260828a",
            "2026-08-28T22:20:23+08:00",
            "judiciary-live-baseline-20260828b",
        ),
    ],
)
def test_judiciary_historical_replay_requires_exact_attempt_cutoff_and_no_predecessor(
    tmp_path: Path,
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """Any invocation-field drift rejects before the old Cases authority is evaluated."""
    authority, output, _report = _install_judiciary_attempt_a_fixture(tmp_path)
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize("drift", ["register_identity", "allowed_url"])
def test_judiciary_attempt_a_rejects_old_cases_identity_or_url_drift(
    tmp_path: Path, drift: str
) -> None:
    """The raw-pinned report does not make either old Cases binding component fungible."""
    authority, output, _report = _install_judiciary_attempt_a_fixture(tmp_path)
    document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    if drift == "register_identity":
        cases = next(
            item
            for item in cast("list[dict[str, object]]", document["registers"])
            if item["family"] == "CASES"
        )
        cases["fingerprint"] = "sha256:" + "0" * 64
    else:
        judiciary = next(
            item
            for item in cast("list[dict[str, object]]", document["selected_sources"])
            if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY"
        )
        endpoint = cast("list[dict[str, object]]", judiciary["endpoints"])[0]
        endpoint["path"] = "/lrs/common/ju/fabricated.jsp"
    document.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    authority.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")))
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=authority,
            matrix=matrix,
            output_root=output,
            source_family="JUDICIARY",
            observation_cutoff="2026-08-28T22:20:23+08:00",
            attempt_id="judiciary-live-baseline-20260828a",
            predecessor_attempt_id=None,
            repository_root=REPOSITORY_ROOT,
        )


def test_judiciary_attempt_a_rejects_a_fabricated_old_cases_binding(tmp_path: Path) -> None:
    """Matching old URLs and register identity cannot replace the exact authority fingerprint."""

    @dataclass(slots=True)
    class TransportProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    authority, output, _report = _install_judiciary_attempt_a_fixture(tmp_path)
    document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    document["authority_id"] = "hka_000000000000000000000000000000000000000000000999"
    document.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    authority.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")))
    probe = TransportProbe()

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="judiciary-live-baseline-20260828a",
            observation_cutoff="2026-08-28T22:20:23+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=probe,
        )

    assert probe.calls == 0


@pytest.mark.parametrize("source_family", ["GLD"])
def test_historical_replay_authorization_rejects_unallocated_families(
    tmp_path: Path, source_family: str
) -> None:
    """No unallocated source family gains either frozen replay exception."""
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=_authority(tmp_path),
            matrix=matrix,
            output_root=REPOSITORY_ROOT / "var/test-hk-v1-source-execution/replay-scope",
            source_family=source_family,
            observation_cutoff="2026-08-27T22:52:09+08:00",
            repository_root=REPOSITORY_ROOT,
        )


@pytest.mark.parametrize(
    ("attempt_id", "observation_cutoff", "predecessor_attempt_id"),
    [
        ("hkex-live-baseline-20260901z", "2026-09-01T15:33:35+08:00", None),
        ("hkex-live-baseline-20260901a", "2026-09-01T15:33:36+08:00", None),
        (
            "hkex-live-baseline-20260901a",
            "2026-09-01T15:33:35+08:00",
            "hkex-live-baseline-20260901b",
        ),
    ],
)
def test_hkex_retained_replay_rejects_unpinned_invocation(
    attempt_id: str,
    observation_cutoff: str,
    predecessor_attempt_id: str | None,
) -> None:
    """HKEX replay allocation is exact, not a family-wide historical bypass."""
    base = REPOSITORY_ROOT / "var/hk-v1/source-admission"
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    with pytest.raises(ValueError, match="EXECUTION_REPLAY_BINDING_INVALID"):
        admission.authorize_retained_replay(
            authority_manifest=(
                base / "authority-user-attested-live-2026-09-01-hkex-baseline.json"
            ),
            matrix=matrix,
            output_root=base / "hkex/authentic-baseline-20260901a",
            source_family="HKEX",
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=REPOSITORY_ROOT,
        )


def test_attempt_c_has_exact_historical_replay_authorization() -> None:
    """Attempt C must survive current-register evolution under its literal pin."""
    base = REPOSITORY_ROOT / "var/hk-v1/source-admission"
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    authorization = admission.authorize_retained_replay(
        authority_manifest=(base / "authority-user-attested-live-2026-09-01-hkex-baseline-c.json"),
        matrix=matrix,
        output_root=base / "hkex/authentic-baseline-20260901c",
        source_family="HKEX",
        observation_cutoff="2026-09-01T15:33:35+08:00",
        attempt_id="hkex-live-baseline-20260901c",
        predecessor_attempt_id=None,
        repository_root=REPOSITORY_ROOT,
    )

    assert authorization.register_identity == (
        "hrr_000000000000000000000000000000000000000000000001",
        "2026-09-01.1",
        "sha256:bd153183d740b809f9ccdd611dfe44abeeb824f42d696e232f4aac819d4b23c3",
    )
    assert authorization.binding_fingerprint == (
        "sha256:d01f762173c1c97726aa5f0b97ca4d256d1c6bee19e48f76df308255efa8a213"
    )
    assert authorization.historical_replay is True


def test_basic_law_reachable_arbitrary_body_is_contract_drift_not_complete(
    tmp_path: Path,
) -> None:
    """A required content URL needs admitted HTML structure and page identity."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "basic-law-arbitrary-body"
    )

    report = execute_source_family(
        authority_manifest=_authority(tmp_path),
        source_family="HKEL",
        output_root=output,
        attempt_id="basic-law-arbitrary-body",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=_BasicLawArbitraryBodyTransport(),
    )

    basic_law = next(
        item
        for item in _items(report, "source_procedures")
        if item["source_id"] == "HK-LEG-BASIC-LAW-PORTAL"
    )
    assert basic_law["terminal_code"] == "SOURCE_CONTRACT_CHANGED"
    assert report["result"] == "SOURCE_CONTRACT_CHANGED"


def test_hkel_direct_capability_stage_gates_session_gets_and_replays_without_transport(
    tmp_path: Path,
) -> None:
    """The registered client check is retained safely before terms and replays semantically."""

    @dataclass(slots=True)
    class ReplayProbe:
        calls: int = 0

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.calls += 1
            raise AssertionError((url, max_bytes))

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "direct-capability"
    )
    authority = _authority(tmp_path)
    transport = _DirectConfiguredHkelTransport()

    report = execute_source_family(
        authority_manifest=authority,
        source_family="HKEL",
        output_root=output,
        attempt_id="hkel-direct-capability",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
    )

    records = {item["endpoint_id"]: item for item in _items(report, "endpoints")}
    capability = records["sep_000000000000000000000000000000000000000000000056"]
    assert capability["method"] == "GET"
    assert capability["requested_url"] == _HKEL_CLIENT_CHECK_COORDINATE
    assert capability["terminal_code"] == "CAPTURED"
    assert "comparison_fingerprint" in capability
    assert not any(str(endpoint_id).startswith("hkel-session-config-") for endpoint_id in records)
    assert transport.urls.index(_HKEL_CLIENT_CHECK_URL) < transport.urls.index(
        "https://www.elegislation.gov.hk/terms"
    )
    serialized = json.dumps(report, sort_keys=True)
    assert "cookie" not in serialized.lower()
    assert "session-secret" not in serialized
    retained_bytes = b"".join(path.read_bytes() for path in sorted((output / "objects").iterdir()))
    report_bytes = serialized.encode()
    for key, value in CAPABILITY_CLAIM.items():
        assert json.dumps(key).encode() not in report_bytes
        assert json.dumps(key).encode() not in retained_bytes
        assert json.dumps(value).encode() not in report_bytes
        assert json.dumps(value).encode() not in retained_bytes

    replay_probe = ReplayProbe()
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="HKEL",
        output_root=output,
        attempt_id="hkel-direct-capability",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=replay_probe,
    )
    assert replayed == report
    assert replay_probe.calls == 0


def test_hkel_failed_direct_capability_stage_prevents_every_session_get(tmp_path: Path) -> None:
    """A non-captured client check cannot unlock terms or other session pages."""

    class FailedCapabilityTransport(_DirectConfiguredHkelTransport):
        def configure_hkel_session(self, *, url: str, max_bytes: int) -> HkelSessionCapture:
            capture = super().configure_hkel_session(url=url, max_bytes=max_bytes)
            assert capture.capability is not None
            return replace(
                capture,
                capability=replace(
                    capture.capability,
                    terminal_code="OUTAGE",
                    status=503,
                ),
            )

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            if url in _HKEL_SESSION_GET_URLS:
                raise AssertionError(url)
            return super().get(url=url, max_bytes=max_bytes)

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "failed-direct-capability"
    )
    report = execute_source_family(
        authority_manifest=_authority(tmp_path),
        source_family="HKEL",
        output_root=output,
        attempt_id="hkel-failed-direct-capability",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=FailedCapabilityTransport(),
    )

    records = {item["endpoint_id"]: item for item in _items(report, "endpoints")}
    assert (
        records["sep_000000000000000000000000000000000000000000000056"]["terminal_code"] == "OUTAGE"
    )
    terms = records["sep_000000000000000000000000000000000000000000000051"]
    assert terms["terminal_code"] == "SESSION_PROCEDURE_NOT_IMPLEMENTED"


@pytest.mark.parametrize(
    "target",
    [
        "https://attacker.example/collect",
        "https://www.elegislation.gov.hk/unregistered",
    ],
)
def test_unadmitted_redirect_is_rejected_before_a_followup_request_exists(target: str) -> None:
    """The urllib handler never constructs a cross-host or same-host unregistered request."""
    handler_type = getattr(execution, "_ConfiningRedirectHandler", None)
    assert handler_type is not None
    handler = handler_type(frozenset({"https://www.elegislation.gov.hk/terms"}))
    original = urllib.request.Request("https://www.elegislation.gov.hk/terms")

    with pytest.raises(urllib.error.HTTPError, match="REDIRECT_NOT_ADMITTED"):
        handler.redirect_request(
            original,
            None,
            302,
            "Found",
            {},
            target,
        )


def test_hkel_direct_capability_check_uses_the_shared_exact_claim_without_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current session starts with the owner-settled query and performs one GET only."""
    opener = _FakeOpener(get_body=b"client capability accepted")
    monkeypatch.setattr(urllib.request, "build_opener", _fake_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset({_HKEL_CLIENT_CHECK_URL})
    )

    capture = transport.configure_hkel_session(
        url=_HKEL_CLIENT_CHECK_URL,
        max_bytes=20_000_000,
    )

    assert capture.capability is not None
    assert capture.capability.stage_id == "CAPABILITY_GET"
    assert capture.capability.terminal_code == "CAPTURED"
    assert capture.capability.final_url == _HKEL_CLIENT_CHECK_URL
    assert opener.requests == [opener.requests[0]]
    request = opener.requests[0]
    assert request.get_method() == "GET"
    assert request.full_url == (
        "https://www.elegislation.gov.hk/client-check?" + urlencode(CAPABILITY_CLAIM)
    )
    assert request.data is None
    assert capture.initial.attempted is False
    assert capture.parser.attempted is False
    assert capture.submission.attempted is False


def test_hkel_mutated_shared_capability_claim_fails_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mutable shared claim is checked against its owned snapshot before any request."""
    opener = _FakeOpener(get_body=b"must not be read")
    monkeypatch.setattr(urllib.request, "build_opener", _fake_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset({_HKEL_CLIENT_CHECK_URL})
    )
    monkeypatch.setitem(CAPABILITY_CLAIM, "BR", "HostileBrowser")

    with pytest.raises(ValueError, match="HKEL_CAPABILITY_CLAIM_INVALID"):
        transport.configure_hkel_session(url=_HKEL_CLIENT_CHECK_URL, max_bytes=20_000_000)

    assert opener.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "http://www.elegislation.gov.hk/client-check?" + urlencode(CAPABILITY_CLAIM),
        "https://attacker.example/client-check?" + urlencode(CAPABILITY_CLAIM),
        "https://user@www.elegislation.gov.hk/client-check?" + urlencode(CAPABILITY_CLAIM),
        "https://www.elegislation.gov.hk:443/client-check?" + urlencode(CAPABILITY_CLAIM),
        "https://www.elegislation.gov.hk/client-check?"
        + urlencode(dict(reversed(CAPABILITY_CLAIM.items()))),
        _HKEL_CLIENT_CHECK_URL + "&extra=true",
        _HKEL_CLIENT_CHECK_URL + "#fragment",
    ],
)
def test_hkel_capability_check_rejects_locator_drift_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    """Scheme, authority, order, query, and fragment drift cannot reach the opener."""
    opener = _FakeOpener(get_body=b"must not be read")
    monkeypatch.setattr(urllib.request, "build_opener", _fake_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset({_HKEL_CLIENT_CHECK_URL})
    )

    with pytest.raises(ValueError, match="HKEL_CAPABILITY_CHECK_URL_INVALID"):
        transport.configure_hkel_session(url=url, max_bytes=20_000_000)

    assert opener.requests == []


def test_hkel_capability_check_redirect_is_rejected_without_followup() -> None:
    """The direct client check has no admitted redirect transition."""
    handler_type = getattr(execution, "_ConfiningRedirectHandler", None)
    assert handler_type is not None
    handler = handler_type(frozenset({_HKEL_CLIENT_CHECK_URL, _HKEL_CONFIGURATION_GET}))
    original = urllib.request.Request(_HKEL_CLIENT_CHECK_URL, method="GET")

    with pytest.raises(urllib.error.HTTPError, match="REDIRECT_NOT_ADMITTED"):
        handler.redirect_request(
            original,
            None,
            302,
            "Found",
            HTTPMessage(),
            _HKEL_CONFIGURATION_GET,
        )


def test_hkel_direct_session_authority_disables_the_legacy_terms_redirect() -> None:
    """Once client-check is registered, terms must remain the exact terminal GET."""
    allowed = frozenset(
        {
            _HKEL_CLIENT_CHECK_URL,
            "https://www.elegislation.gov.hk/terms",
            _HKEL_CONFIGURATION_GET,
            _HKEL_CONFIGURATION_ACTION,
        }
    )
    transport = execution.UrllibReadOnlyTransport(allowed_redirect_urls=allowed)
    assert transport.redirect_capability.allowed_transitions == frozenset()
    handler = _confining_redirect_handler(allowed)

    with pytest.raises(urllib.error.HTTPError, match="REDIRECT_NOT_ADMITTED"):
        handler.redirect_request(
            urllib.request.Request("https://www.elegislation.gov.hk/terms", method="GET"),
            BytesIO(),
            302,
            "Found",
            HTTPMessage(),
            _HKEL_CONFIGURATION_GET,
        )


def test_hkel_real_redirect_chain_reaches_only_exact_config_get_and_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production handler follows the admitted terms/config chain and exact POST only."""
    scripted = _RedirectingHttpsHandler(redirect_target=_HKEL_CONFIGURATION_GET)
    opener = urllib.request.build_opener(
        _confining_redirect_handler(
            frozenset(
                {
                    "https://www.elegislation.gov.hk/terms",
                    _HKEL_CONFIGURATION_GET,
                    _HKEL_CONFIGURATION_ACTION,
                }
            )
        ),
        scripted,
    )
    monkeypatch.setattr(urllib.request, "build_opener", _real_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset(
            {
                "https://www.elegislation.gov.hk/terms",
                _HKEL_CONFIGURATION_GET,
                _HKEL_CONFIGURATION_ACTION,
            }
        )
    )

    capture = transport.configure_hkel_session(
        url="https://www.elegislation.gov.hk/terms", max_bytes=20_000_000
    )

    assert capture.initial.final_url == _HKEL_CONFIGURATION_GET
    assert capture.initial.terminal_code == "CAPTURED"
    assert capture.parser.terminal_code == "CAPTURED"
    assert capture.submission.terminal_code == "CAPTURED"
    assert scripted.requests == [
        ("GET", "https://www.elegislation.gov.hk/terms"),
        ("GET", _HKEL_CONFIGURATION_GET),
        ("POST", _HKEL_CONFIGURATION_ACTION),
    ]


def test_hkel_current_configuration_posts_only_exact_fields_and_truthful_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current form keeps publisher facts and changes only three owned capabilities."""
    opener = _FakeOpener(get_body=_HKEL_CONFIGURATION_FORM, post_body=b"configured")
    monkeypatch.setattr(urllib.request, "build_opener", _fake_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset(
            {
                "https://www.elegislation.gov.hk/terms",
                _HKEL_CONFIGURATION_GET,
                _HKEL_CONFIGURATION_ACTION,
            }
        )
    )

    capture = transport.configure_hkel_session(
        url="https://www.elegislation.gov.hk/terms", max_bytes=20_000_000
    )

    assert capture.parser.configuration_field_count == 12
    assert capture.submission.terminal_code == "CAPTURED"
    request = opener.requests[-1]
    assert request.method == "POST"
    assert request.full_url == _HKEL_CONFIGURATION_ACTION
    assert type(request.data) is bytes
    fields = dict(parse_qsl(request.data.decode("ascii"), strict_parsing=True))
    assert fields == {
        "_CSRF_TOKEN": "short-lived-site-token",
        "applicationId": "RA001",
        "appletLoadFailed": "false",
        "branchCode": "hkel",
        "cookieEnabled": "true",
        "country": "HK",
        "isIpv4Verified": "false",
        "isIpv6Verified": "true",
        "javascriptEnabled": "true",
        "jvmVendor": "publisher-vendor",
        "jvmVersion": "publisher-version",
        "language": "en",
    }
    obsolete = {"OS", "OS_S", "BR", "BR_S", "BRV", "BRV_S", "JS_S", "C_S"}
    assert obsolete.isdisjoint(fields)


def test_hkel_terms_get_cannot_redirect_to_the_post_only_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A family-authorized POST target cannot become the GET stage's next request."""
    terms_url = "https://www.elegislation.gov.hk/terms"
    scripted = _RedirectingHttpsHandler(redirect_target=_HKEL_CONFIGURATION_ACTION)
    opener = urllib.request.build_opener(
        _confining_redirect_handler(
            frozenset({terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION})
        ),
        scripted,
    )
    monkeypatch.setattr(urllib.request, "build_opener", _real_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset(
            {terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION}
        )
    )

    capture = transport.configure_hkel_session(url=terms_url, max_bytes=20_000_000)

    assert capture.initial.terminal_code == "SOURCE_CONTRACT_CHANGED"
    assert capture.initial.redirect_rejected is True
    assert capture.parser.terminal_code == "NOT_ATTEMPTED"
    assert capture.submission.terminal_code == "NOT_ATTEMPTED"
    assert scripted.requests == [("GET", terms_url)]


def test_hkel_legacy_post_redirect_remains_rejected_without_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The obsolete submission cannot widen the current direct-GET session contract."""
    terms_url = "https://www.elegislation.gov.hk/terms"
    scripted = _RedirectingHttpsHandler(
        redirect_target=_HKEL_CONFIGURATION_GET,
        post_redirect_target=_HKEL_CONFIGURATION_GET,
    )
    opener = urllib.request.build_opener(
        _confining_redirect_handler(
            frozenset({terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION})
        ),
        scripted,
    )
    monkeypatch.setattr(urllib.request, "build_opener", _real_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset(
            {terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION}
        )
    )

    capture = transport.configure_hkel_session(url=terms_url, max_bytes=20_000_000)

    assert capture.initial.terminal_code == "CAPTURED"
    assert capture.parser.terminal_code == "CAPTURED"
    assert capture.submission.terminal_code == "SOURCE_CONTRACT_CHANGED"
    assert capture.submission.status == 302
    assert capture.submission.redirect_rejected is True
    assert not hasattr(capture.submission, "body")
    assert scripted.requests == [
        ("GET", terms_url),
        ("GET", _HKEL_CONFIGURATION_GET),
        ("POST", _HKEL_CONFIGURATION_ACTION),
    ]
    assert transport.redirect_capability.allowed_transitions == frozenset(
        {
            ("GET", terms_url, "GET", _HKEL_CONFIGURATION_GET),
        }
    )


@pytest.mark.parametrize(
    "target",
    [
        "http://www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?applicationId=RA001",
        "https://attacker.example/checkconfig/checkClientConfig.jsp?applicationId=RA001",
        "https://user@www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?applicationId=RA001",
        "https://www.elegislation.gov.hk:443/checkconfig/checkClientConfig.jsp?applicationId=RA001",
        "https://www.elegislation.gov.hk:444/checkconfig/checkClientConfig.jsp?applicationId=RA001",
        "https://www.elegislation.gov.hk/checkconfig/changed.jsp?applicationId=RA001",
        "https://www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?application=RA001",
        "https://www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?applicationId=RA002",
        "https://www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?applicationId=RA001&extra=1",
        "https://www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?applicationId=RA001#fragment",
    ],
)
def test_hkel_post_redirect_drift_is_rejected_before_followup(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """Every target drift stops after the POST response and before another request exists."""
    terms_url = "https://www.elegislation.gov.hk/terms"
    scripted = _RedirectingHttpsHandler(
        redirect_target=_HKEL_CONFIGURATION_GET,
        post_redirect_target=target,
    )
    opener = urllib.request.build_opener(
        _confining_redirect_handler(
            frozenset({terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION})
        ),
        scripted,
    )
    monkeypatch.setattr(urllib.request, "build_opener", _real_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset(
            {terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION}
        )
    )

    capture = transport.configure_hkel_session(url=terms_url, max_bytes=20_000_000)

    assert capture.submission.terminal_code == "SOURCE_CONTRACT_CHANGED"
    assert capture.submission.redirect_rejected is True
    assert scripted.requests == [
        ("GET", terms_url),
        ("GET", _HKEL_CONFIGURATION_GET),
        ("POST", _HKEL_CONFIGURATION_ACTION),
    ]


@pytest.mark.parametrize(
    ("status", "terminal"),
    [
        (301, "SOURCE_CONTRACT_CHANGED"),
        (303, "SOURCE_CONTRACT_CHANGED"),
        (307, "OUTAGE"),
        (308, "OUTAGE"),
    ],
)
def test_hkel_post_redirect_rejects_every_nonobserved_status_before_followup(
    monkeypatch: pytest.MonkeyPatch, status: int, terminal: str
) -> None:
    """Only the publisher-observed 302 status can authorize the converted GET."""
    terms_url = "https://www.elegislation.gov.hk/terms"
    scripted = _RedirectingHttpsHandler(
        redirect_target=_HKEL_CONFIGURATION_GET,
        post_redirect_target=_HKEL_CONFIGURATION_GET,
        post_redirect_status=status,
    )
    opener = urllib.request.build_opener(
        _confining_redirect_handler(
            frozenset({terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION})
        ),
        scripted,
    )
    monkeypatch.setattr(urllib.request, "build_opener", _real_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset(
            {terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION}
        )
    )

    capture = transport.configure_hkel_session(url=terms_url, max_bytes=20_000_000)

    assert capture.submission.terminal_code == terminal
    assert scripted.requests == [
        ("GET", terms_url),
        ("GET", _HKEL_CONFIGURATION_GET),
        ("POST", _HKEL_CONFIGURATION_ACTION),
    ]


@pytest.mark.parametrize(
    "followup_target",
    [_HKEL_CONFIGURATION_GET, "https://www.elegislation.gov.hk/terms"],
)
def test_hkel_post_redirect_rejects_any_second_redirect_or_loop_before_extra_followup(
    monkeypatch: pytest.MonkeyPatch, followup_target: str
) -> None:
    """The obsolete POST stops before even a first converted GET or later loop."""
    terms_url = "https://www.elegislation.gov.hk/terms"
    scripted = _RedirectingHttpsHandler(
        redirect_target=_HKEL_CONFIGURATION_GET,
        post_redirect_target=_HKEL_CONFIGURATION_GET,
        post_followup_redirect_target=followup_target,
    )
    opener = urllib.request.build_opener(
        _confining_redirect_handler(
            frozenset({terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION})
        ),
        scripted,
    )
    monkeypatch.setattr(urllib.request, "build_opener", _real_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset(
            {terms_url, _HKEL_CONFIGURATION_GET, _HKEL_CONFIGURATION_ACTION}
        )
    )

    capture = transport.configure_hkel_session(url=terms_url, max_bytes=20_000_000)

    assert capture.submission.terminal_code == "SOURCE_CONTRACT_CHANGED"
    assert capture.submission.redirect_rejected is True
    assert scripted.requests == [
        ("GET", terms_url),
        ("GET", _HKEL_CONFIGURATION_GET),
        ("POST", _HKEL_CONFIGURATION_ACTION),
    ]


@pytest.mark.parametrize("source_method", ["GET", "HEAD"])
def test_hkel_post_redirect_rejects_wrong_source_method_before_followup(
    source_method: str,
) -> None:
    """An admitted URL pair cannot substitute GET or HEAD for the required source POST."""
    handler_type = getattr(execution, "_ConfiningRedirectHandler", None)
    assert handler_type is not None
    handler = handler_type(frozenset({_HKEL_CONFIGURATION_ACTION, _HKEL_CONFIGURATION_GET}))
    original = urllib.request.Request(
        _HKEL_CONFIGURATION_ACTION,
        method=source_method,
    )

    with pytest.raises(urllib.error.HTTPError, match="REDIRECT_NOT_ADMITTED"):
        handler.redirect_request(
            original,
            None,
            302,
            "Found",
            HTTPMessage(),
            _HKEL_CONFIGURATION_GET,
        )


def test_hkel_post_redirect_rejects_wrong_converted_target_method_before_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even an exact 302 source/target pair cannot preserve POST on the follow-up."""

    def preserve_post(
        _handler: urllib.request.HTTPRedirectHandler,
        _request: urllib.request.Request,
        _fp: object,
        _code: int,
        _message: str,
        _headers: HTTPMessage,
        target: str,
    ) -> urllib.request.Request:
        return urllib.request.Request(  # noqa: S310 - fixed test target.
            target,
            data=b"must-not-be-issued",
            method="POST",
        )

    monkeypatch.setattr(urllib.request.HTTPRedirectHandler, "redirect_request", preserve_post)
    handler_type = getattr(execution, "_ConfiningRedirectHandler", None)
    assert handler_type is not None
    handler = handler_type(frozenset({_HKEL_CONFIGURATION_ACTION, _HKEL_CONFIGURATION_GET}))
    original = urllib.request.Request(
        _HKEL_CONFIGURATION_ACTION,
        data=b"safe=true",
        method="POST",
    )

    with pytest.raises(urllib.error.HTTPError, match="REDIRECT_NOT_ADMITTED"):
        handler.redirect_request(
            original,
            None,
            302,
            "Found",
            HTTPMessage(),
            _HKEL_CONFIGURATION_GET,
        )


@pytest.mark.parametrize(
    "target",
    [
        "https://attacker.example/checkconfig/checkClientConfig.jsp?applicationId=RA001",
        "https://www.elegislation.gov.hk/checkconfig/changed.jsp?applicationId=RA001",
        "https://www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?applicationId=RA002",
    ],
)
def test_hkel_real_redirect_chain_stops_before_any_drifted_followup(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """Host, path, or query drift cannot create the config follow-up request."""
    scripted = _RedirectingHttpsHandler(redirect_target=target)
    opener = urllib.request.build_opener(
        _confining_redirect_handler(
            frozenset(
                {
                    "https://www.elegislation.gov.hk/terms",
                    _HKEL_CONFIGURATION_GET,
                    _HKEL_CONFIGURATION_ACTION,
                }
            )
        ),
        scripted,
    )
    monkeypatch.setattr(urllib.request, "build_opener", _real_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset(
            {
                "https://www.elegislation.gov.hk/terms",
                _HKEL_CONFIGURATION_GET,
                _HKEL_CONFIGURATION_ACTION,
            }
        )
    )

    capture = transport.configure_hkel_session(
        url="https://www.elegislation.gov.hk/terms", max_bytes=20_000_000
    )

    assert capture.initial.terminal_code == "SOURCE_CONTRACT_CHANGED"
    assert capture.parser.terminal_code == "NOT_ATTEMPTED"
    assert capture.submission.terminal_code == "NOT_ATTEMPTED"
    assert scripted.requests == [("GET", "https://www.elegislation.gov.hk/terms")]


@pytest.mark.parametrize(
    ("source", "target", "method"),
    [
        (
            "https://data.gov.hk/en-data/dataset/hk-doj-hkel-list",
            "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_en.xml",
            "GET",
        ),
        (
            "https://www.elegislation.gov.hk/checkconfig/submitClientConfig.do",
            "https://data.gov.hk/en-data/dataset/hk-doj-hkel-list",
            "POST",
        ),
    ],
)
def test_redirect_handler_rejects_cross_origin_even_when_both_urls_are_admitted(
    source: str, target: str, method: str
) -> None:
    """Each request stays on its own origin; family-wide admission cannot authorize a hop."""
    handler_type = getattr(execution, "_ConfiningRedirectHandler", None)
    assert handler_type is not None
    handler = handler_type(frozenset({source, target}))
    original = urllib.request.Request(  # noqa: S310 - fixed HTTPS test locators above.
        source,
        data=b"safe=true" if method == "POST" else None,
        method=method,
    )

    with pytest.raises(urllib.error.HTTPError, match="REDIRECT_NOT_ADMITTED"):
        handler.redirect_request(original, None, 302, "Found", HTTPMessage(), target)


def test_real_urllib_transport_exposes_immutable_redirect_capability_and_reaches_opener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production composition uses a declared capability and reaches the opener without probing."""
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    authorization = execution.authorize_execution(
        authority_manifest=authority,
        matrix=(
            REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
        ),
        output_root=output,
        source_family="HKEX",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
    )
    opener = _FakeOpener(get_body=b"<html>publisher bytes</html>")
    monkeypatch.setattr(urllib.request, "build_opener", _fake_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset(authorization.allowed_urls)
    )

    report = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="real-urllib-capability",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        authorization=authorization,
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert opener.requests
    capability = transport.redirect_capability
    assert capability.allowed_urls == frozenset(authorization.allowed_urls)
    assert capability.same_origin_only is True


def test_real_urllib_transport_preserves_rejected_redirect_location_for_bounded_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A confining-handler HTTPError retains its Location for bounded manual admission."""
    source = "https://en-rules.hkex.com.hk/node/3756"
    target = (
        "https://en-rules.hkex.com.hk/rulebook/"
        "listing-application-form-equity-securities-and-debt-securities"
    )
    headers = HTTPMessage()
    headers["Content-Type"] = "text/html"
    headers["Location"] = target

    class RedirectErrorOpener:
        def open(self, request: urllib.request.Request, *, timeout: int) -> NoReturn:
            assert request.full_url == source
            assert timeout == 30
            raise urllib.error.HTTPError(
                source,
                301,
                "REDIRECT_NOT_ADMITTED",
                headers,
                BytesIO(b"bounded redirect body"),
            )

    opener = RedirectErrorOpener()

    def build_opener(*_handlers: object) -> RedirectErrorOpener:
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    transport = execution.UrllibReadOnlyTransport(allowed_redirect_urls=frozenset({source}))

    response = transport.get(url=source, max_bytes=1024)
    probe = execution.probe_hkex_raw_location(response.raw_location_reader)

    assert response.status == 301
    assert response.body == b"bounded redirect body"
    assert response.redirect_rejected is True
    assert probe.location_present is True
    assert probe.representation_complete is True
    assert probe.total_octet_count == len(target.encode("ascii"))
    retained = base64.b64decode(probe.location_octets_base64_prefix or "", validate=True)
    assert retained == target.encode("ascii")


def test_real_urllib_transport_rejects_ambiguous_duplicate_location_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two Location fields must never collapse into one followable target."""
    source = "https://en-rules.hkex.com.hk/node/3756"
    headers = HTTPMessage()
    headers["Content-Type"] = "text/html"
    headers["Location"] = "https://en-rules.hkex.com.hk/rulebook/admitted-target"
    headers["Location"] = "https://attacker.example/hidden-second-target"

    class AmbiguousRedirectErrorOpener:
        def open(self, request: urllib.request.Request, *, timeout: int) -> NoReturn:
            assert request.full_url == source
            assert timeout == 30
            raise urllib.error.HTTPError(
                source,
                301,
                "REDIRECT_NOT_ADMITTED",
                headers,
                BytesIO(b"bounded redirect body"),
            )

    def build_opener(*_handlers: object) -> AmbiguousRedirectErrorOpener:
        return AmbiguousRedirectErrorOpener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    transport = execution.UrllibReadOnlyTransport(allowed_redirect_urls=frozenset({source}))

    response = transport.get(url=source, max_bytes=1024)
    probe = execution.probe_hkex_raw_location(response.raw_location_reader)

    assert headers.get_all("Location") == [
        "https://en-rules.hkex.com.hk/rulebook/admitted-target",
        "https://attacker.example/hidden-second-target",
    ]
    assert response.raw_location_reader is None
    assert probe.location_present is False


def test_mismatched_real_transport_capability_is_rejected_before_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transport admission mismatch fails before its opener receives any request."""
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    opener = _FakeOpener(get_body=b"must-not-be-read")
    monkeypatch.setattr(urllib.request, "build_opener", _fake_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(allowed_redirect_urls=frozenset())

    with pytest.raises(ValueError, match="EXECUTION_AUTHORIZATION_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id="mismatched-urllib-capability",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=transport,
        )
    assert opener.requests == []


def test_hkel_configuration_retains_sanitized_parser_failure_for_every_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed config HTML returns three safe terminal records rather than escaping."""
    terms_url = "https://www.elegislation.gov.hk/terms"
    opener = _FakeOpener(get_body=b"<html>changed form</html>")
    monkeypatch.setattr(urllib.request, "build_opener", _fake_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset({terms_url, _HKEL_CONFIGURATION_ACTION})
    )

    capture = transport.configure_hkel_session(url=terms_url, max_bytes=1024)

    assert capture.initial.terminal_code == "CAPTURED"
    assert capture.initial.byte_length == len(b"<html>changed form</html>")
    assert capture.parser.terminal_code == "SOURCE_CONTRACT_CHANGED"
    assert capture.submission.terminal_code == "NOT_ATTEMPTED"
    assert len(opener.requests) == 1


def test_hkel_configuration_retains_post_truncation_without_secret_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST truncation remains a safe terminal fact and no response body enters the capture."""
    terms_url = "https://www.elegislation.gov.hk/terms"
    opener = _FakeOpener(get_body=_HKEL_CONFIGURATION_FORM, post_body=b"secret" * 1000)
    monkeypatch.setattr(urllib.request, "build_opener", _fake_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset({terms_url, _HKEL_CONFIGURATION_ACTION})
    )

    capture = transport.configure_hkel_session(url=terms_url, max_bytes=1024)

    assert capture.parser.terminal_code == "CAPTURED"
    assert capture.submission.terminal_code == "TRUNCATED"
    assert capture.submission.byte_length == 1025
    assert not hasattr(capture.submission, "body")


@pytest.mark.parametrize(
    ("response", "expected_terminal", "expected_length"),
    [
        (
            CapturedResponse(
                302,
                "text/html",
                b"redirect page",
                "https://data.gov.hk/en-data/dataset/hk-doj-hkel-list",
                redirect_rejected=True,
            ),
            "SOURCE_CONTRACT_CHANGED",
            13,
        ),
        (
            CapturedResponse(200, "text/html", b"x" * 17, None),
            "TRUNCATED",
            17,
        ),
    ],
)
def test_hkel_configuration_preserves_initial_terminal_and_blocks_later_stages(
    monkeypatch: pytest.MonkeyPatch,
    response: CapturedResponse,
    expected_terminal: str,
    expected_length: int,
) -> None:
    """Initial redirect/truncation facts survive sanitization and stop parse/POST."""
    terms_url = "https://www.elegislation.gov.hk/terms"
    opener = _FakeOpener(get_body=b"must-not-be-read")
    monkeypatch.setattr(urllib.request, "build_opener", _fake_opener_factory(opener))
    transport = execution.UrllibReadOnlyTransport(
        allowed_redirect_urls=frozenset({terms_url, _HKEL_CONFIGURATION_ACTION})
    )

    def fixed_get(*, url: str, max_bytes: int) -> CapturedResponse:
        assert url == terms_url
        assert max_bytes == 16
        return response

    monkeypatch.setattr(transport, "get", fixed_get)

    capture = transport.configure_hkel_session(url=terms_url, max_bytes=16)

    assert capture.initial.terminal_code == expected_terminal
    assert capture.initial.byte_length == expected_length
    assert capture.parser.terminal_code == "NOT_ATTEMPTED"
    assert capture.submission.terminal_code == "NOT_ATTEMPTED"
    assert opener.requests == []


@pytest.mark.parametrize(
    "cutoff",
    ["2026-08-27T14:52:09Z", "2026-08-27T22:52:09.1+08:00", "2026-08-27 22:52:09+08:00"],
)
@pytest.mark.parametrize("source_family", ["GLD", "HKEL", "JUDICIARY", "HKEX"])
def test_every_family_rejects_a_noncanonical_hong_kong_cutoff(
    tmp_path: Path, cutoff: str, source_family: str
) -> None:
    """All authentic families share one exact second-resolution +08:00 cutoff grammar."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    with pytest.raises(ValueError, match="OBSERVATION_CUTOFF_MALFORMED"):
        execute_source_family(
            authority_manifest=_authority(tmp_path),
            source_family=source_family,
            output_root=output,
            attempt_id="bad-cutoff",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_HKEXTransport(),
        )


def test_restart_rejects_stale_family_cutoff_and_authority_binding(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """A reused attempt ID cannot adopt a report from another invocation identity."""
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="reused-attempt",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_HKEXTransport(),
    )

    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="JUDICIARY",
            output_root=output,
            attempt_id="reused-attempt",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_JudiciaryTransport(),
        )

    original_report = output / "attempts" / "reused-attempt" / "report.json"
    copied_report = output / "attempts" / "different-attempt" / "report.json"
    copied_report.parent.mkdir(parents=True)
    copied_report.write_bytes(original_report.read_bytes())
    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_MALFORMED"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id="different-attempt",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_HKEXTransport(),
        )
    copied_report.unlink()
    copied_report.parent.rmdir()

    changed_authority = cast("dict[str, object]", json.loads(authority.read_bytes()))
    changed_authority["authority_id"] = "hka_000000000000000000000000000000000000000000000008"
    changed_authority.pop("fingerprint")
    changed_authority["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(changed_authority, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    authority.write_text(json.dumps(changed_authority, sort_keys=True, separators=(",", ":")))
    with pytest.raises(ValueError, match="PREDECESSOR_REPORT_BINDING_INVALID"):
        execute_source_family(
            authority_manifest=authority,
            source_family="HKEX",
            output_root=output,
            attempt_id="reused-attempt",
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_HKEXTransport(),
        )
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    exit_code = admission.main(
        [
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "HKEX",
            "--attempt-id",
            "reused-attempt",
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ]
    )
    captured = capfd.readouterr()
    assert exit_code == 2
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "attempt_id": "reused-attempt",
        "execute_authorized": True,
        "result": "PREDECESSOR_REPORT_BINDING_INVALID",
        "source_attempted": False,
    }


def test_hkex_and_basic_law_parser_drift_stay_distinct(tmp_path: Path) -> None:
    """Reachable contract-invalid family roots must terminate SOURCE_CONTRACT_CHANGED."""
    base = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)

    hkex = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=base / "hkex",
        attempt_id="hkex-drift",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_HKEXContractChangedTransport(),
    )
    basic_law = execute_source_family(
        authority_manifest=authority,
        source_family="HKEL",
        output_root=base / "hkel",
        attempt_id="basic-law-drift",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_BasicLawContractChangedTransport(),
    )

    assert hkex["result"] == "SOURCE_CONTRACT_CHANGED"
    assert basic_law["result"] == "SOURCE_CONTRACT_CHANGED"


def test_basic_law_generated_member_is_bound_before_transport_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a compromised parser cannot cause an off-family generated GET."""
    hostile = "https://attacker.example/en/basiclaw/index.html"

    @dataclass(frozen=True, slots=True)
    class HostileMembership:
        member_urls: tuple[str, ...]

    def hostile_membership(
        _constitution_body: bytes,
        _basic_law_body: bytes,
        *,
        constitution_root_url: str,
        basic_law_root_url: str,
    ) -> HostileMembership:
        assert constitution_root_url == _BASIC_LAW_CONSTITUTION_ROOT
        assert basic_law_root_url == _BASIC_LAW_TEXT_ROOT
        return HostileMembership((hostile,))

    monkeypatch.setattr(
        execution,
        "parse_basic_law_membership",
        hostile_membership,
    )
    transport = _ConfiguredHkelTransport()
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "hostile-basic-member"
    )

    report = execute_source_family(
        authority_manifest=_authority(tmp_path),
        source_family="HKEL",
        output_root=output,
        attempt_id="hostile-basic-member",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
    )

    assert hostile not in transport.urls
    assert report["result"] == "SOURCE_CONTRACT_CHANGED"


@pytest.mark.parametrize(
    ("transport", "attempt_id"),
    [
        (_BasicLawMemberOutageTransport(), "basic-law-member-outage"),
        (_HkelArchiveOutageTransport(), "hkel-archive-outage"),
    ],
)
def test_hkel_outage_is_not_reclassified_as_parser_drift(
    tmp_path: Path,
    transport: _ConfiguredHkelTransport,
    attempt_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A known-contract member outage remains SOURCE_OUTAGE, not contract drift."""
    _install_synthetic_basic_law_contract(monkeypatch)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / attempt_id
    )
    cutoff = "2026-08-27T22:52:09+08:00"

    report = execute_source_family(
        authority_manifest=_authority(tmp_path, cutoff=cutoff),
        source_family="HKEL",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=transport,
    )

    assert report["result"] == "SOURCE_OUTAGE"


@pytest.mark.parametrize("failure", ["TYPE", "EVIDENCE", "WRITE", "READBACK"])
def test_hkel_mandatory_stage_integrity_failure_emits_no_report_or_downstream_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """Type, evidence, write, and read-back defects cross one fail-closed boundary."""

    class HostileTransport(_DirectConfiguredHkelTransport):
        downstream_calls = 0

        def configure_hkel_session(self, *, url: str, max_bytes: int) -> HkelSessionCapture:
            configured = super().configure_hkel_session(url=url, max_bytes=max_bytes)
            if failure == "TYPE":
                return cast("HkelSessionCapture", object())
            if failure == "EVIDENCE":
                return replace(configured, capability=cast("HkelSessionStage", object()))
            return configured

        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            self.downstream_calls += 1
            return super().get(url=url, max_bytes=max_bytes)

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / f"integrity-{failure.lower()}"
    )
    if failure == "WRITE":
        original_write = execution.__dict__["_write_immutable"]

        def reject_capability_write(path: Path, content: bytes) -> None:
            if b'"stage_id":"CAPABILITY_GET"' in content:
                raise OSError
            cast("Callable[[Path, bytes], None]", original_write)(path, content)

        monkeypatch.setattr(execution, "_write_immutable", reject_capability_write)
    elif failure == "READBACK":

        def reject_capability_readback(_body: bytes) -> bytes:
            raise ValueError

        monkeypatch.setattr(execution, "_read_hkel_comparison", reject_capability_readback)

    transport = HostileTransport()
    integrity_error = cast(
        "type[ValueError]", getattr(execution, "SourceEvidenceIntegrityError", ValueError)
    )
    with pytest.raises(integrity_error):
        execute_source_family(
            authority_manifest=_authority(tmp_path),
            source_family="HKEL",
            output_root=output,
            attempt_id=f"integrity-{failure.lower()}",
            observation_cutoff="2026-08-27T22:52:09+08:00",
            repository_root=REPOSITORY_ROOT,
            transport=transport,
        )

    assert transport.downstream_calls == 0
    assert not (output / "attempts" / f"integrity-{failure.lower()}" / "report.json").exists()


def test_hkel_direct_transport_outage_retains_exact_sanitized_mandatory_stage(
    tmp_path: Path,
) -> None:
    """An ordinary capability transport outage is evidence, not an integrity exception."""

    class OutageTransport(_DirectConfiguredHkelTransport):
        def configure_hkel_session(self, *, url: str, max_bytes: int) -> HkelSessionCapture:
            assert url == _HKEL_CLIENT_CHECK_URL
            assert max_bytes > 0
            raise OSError

    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "capability-outage"
    )
    transport = OutageTransport()
    report = execute_source_family(
        authority_manifest=_authority(tmp_path),
        source_family="HKEL",
        output_root=output,
        attempt_id="capability-outage",
        observation_cutoff="2026-08-27T22:52:09+08:00",
        repository_root=REPOSITORY_ROOT,
        transport=transport,
    )

    capability = next(
        endpoint
        for endpoint in _items(report, "endpoints")
        if endpoint["endpoint_id"] == "sep_000000000000000000000000000000000000000000000056"
    )
    assert capability["requested_url"] == _HKEL_CLIENT_CHECK_COORDINATE
    assert capability["terminal_code"] == "OUTAGE"
    assert report["result"] == "SOURCE_OUTAGE"
    assert report["readback_verified"] is True
    assert _HKEL_SESSION_GET_URLS.isdisjoint(transport.urls)


def test_hkel_integrity_failure_has_one_canonical_cli_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The CLI emits no attempt report when mandatory evidence integrity fails."""

    def invalid_configuration(
        _self: execution.UrllibReadOnlyTransport, *, url: str, max_bytes: int
    ) -> HkelSessionCapture:
        assert url == _HKEL_CLIENT_CHECK_URL
        assert max_bytes > 0
        return cast("HkelSessionCapture", object())

    monkeypatch.setattr(
        execution.UrllibReadOnlyTransport,
        "configure_hkel_session",
        invalid_configuration,
    )
    cutoff = "2026-08-27T22:52:09+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "canonical-integrity-boundary"
    )
    matrix = (
        REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    exit_code = admission.main(
        [
            "--authority-manifest",
            str(authority),
            "--matrix",
            str(matrix),
            "--mode",
            "execute",
            "--source-family",
            "HKEL",
            "--attempt-id",
            "canonical-integrity-boundary",
            "--observation-cutoff",
            cutoff,
            "--output-root",
            str(output),
        ]
    )
    captured = capfd.readouterr()
    assert exit_code == 2
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "attempt_id": "canonical-integrity-boundary",
        "execute_authorized": True,
        "result": "SOURCE_EVIDENCE_INTEGRITY_FAILURE",
        "source_attempted": True,
    }
    assert not (output / "attempts" / "canonical-integrity-boundary" / "report.json").exists()


class _FaultingReportWriter:
    """Delegate a final-manifest stream while injecting one exact write fault."""

    def __init__(self, stream: IO[bytes], failure: str) -> None:
        self._stream = stream
        self._failure = failure

    def __enter__(self) -> Self:
        self._stream.__enter__()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return self._stream.__exit__(exception_type, exception, traceback)

    def write(self, content: bytes) -> int:
        if self._failure == "SHORT_WRITE":
            return self._stream.write(content[: max(1, len(content) // 2)])
        return self._stream.write(content)

    def flush(self) -> None:
        if self._failure == "FLUSH":
            self._failure = "FLUSHED_AFTER_FAILURE"
            raise OSError
        self._stream.flush()

    def fileno(self) -> int:
        return self._stream.fileno()


@pytest.mark.parametrize("failure", ["SHORT_WRITE", "FLUSH", "FSYNC", "READBACK", "PUBLISH"])
def test_final_report_publication_failure_leaves_no_manifest_and_retry_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """A failed final write is non-authoritative and cannot poison the retry."""
    cutoff = "2026-08-27T22:52:09+08:00"
    attempt_id = f"report-publication-{failure.lower().replace('_', '-')}"
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / attempt_id
    )
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_root = output / "attempts" / attempt_id
    active = True
    original_open = Path.open
    original_fsync = os.fsync
    original_link = os.link
    original_digest_file = execution.__dict__["_digest_file"]

    def faulting_open(  # noqa: PLR0913, PLR0917 - mirrors Path.open exactly.
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[bytes]:
        stream = cast(
            "IO[bytes]",
            original_open(path, mode, buffering, encoding, errors, newline),
        )
        is_report_write = (
            path.parent == attempt_root
            and mode == "xb"
            and (
                path.name == "report.json"
                or (path.name.startswith(".report.json.") and path.name.endswith(".tmp"))
            )
        )
        if active and failure in {"SHORT_WRITE", "FLUSH"} and is_report_write:
            return cast("IO[bytes]", _FaultingReportWriter(stream, failure))
        return stream

    def faulting_fsync(file_descriptor: int) -> None:
        if active and failure == "FSYNC":
            raise OSError
        original_fsync(file_descriptor)

    def faulting_digest_file(path: Path) -> tuple[str, int]:
        if (
            active
            and failure == "READBACK"
            and path.parent == attempt_root
            and path.name.startswith(".report.json.")
            and path.name.endswith(".tmp")
        ):
            raise OSError
        return cast("Callable[[Path], tuple[str, int]]", original_digest_file)(path)

    def faulting_link(source: Path, destination: Path) -> None:
        if active and failure == "PUBLISH" and destination == attempt_root / "report.json":
            raise OSError
        original_link(source, destination)

    monkeypatch.setattr(Path, "open", faulting_open)
    monkeypatch.setattr(os, "fsync", faulting_fsync)
    monkeypatch.setattr(execution, "_digest_file", faulting_digest_file)
    monkeypatch.setattr(os, "link", faulting_link)
    integrity_error = cast(
        "type[ValueError]", getattr(execution, "SourceEvidenceIntegrityError", ValueError)
    )

    with pytest.raises(integrity_error, match="SOURCE_EVIDENCE_INTEGRITY_FAILURE"):
        execute_source_family(
            authority_manifest=authority,
            source_family="GLD",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_Transport(b"writer-compatible"),
        )

    report_path = attempt_root / "report.json"
    assert not report_path.exists()
    assert list(attempt_root.glob(".report.json.*.tmp")) == []

    active = False
    retried = execute_source_family(
        authority_manifest=authority,
        source_family="GLD",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"writer-compatible"),
    )
    assert json.loads(report_path.read_bytes()) == retried
    assert retried["readback_verified"] is True


def test_final_report_publication_does_not_overwrite_an_existing_exact_manifest(
    tmp_path: Path,
) -> None:
    """Atomic final publication treats an identical existing report as immutable."""
    report_path = tmp_path / "attempt" / "report.json"
    report_path.parent.mkdir(parents=True)
    content = b'{"exact":"report"}'
    report_path.write_bytes(content)
    before = report_path.stat()
    publish = execution._publish_attempt_report  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    publish(report_path, content)

    after = report_path.stat()
    assert report_path.read_bytes() == content
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
    assert list(report_path.parent.glob(".report.json.*.tmp")) == []


def test_final_report_publication_rejects_a_different_existing_manifest(
    tmp_path: Path,
) -> None:
    """A publication collision can never replace different authoritative bytes."""
    report_path = tmp_path / "attempt" / "report.json"
    report_path.parent.mkdir(parents=True)
    existing = b'{"exact":"existing"}'
    report_path.write_bytes(existing)
    before = report_path.stat()

    with pytest.raises(
        execution.SourceEvidenceIntegrityError,
        match="SOURCE_EVIDENCE_INTEGRITY_FAILURE",
    ):
        execution._publish_attempt_report(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            report_path, b'{"exact":"different"}'
        )

    after = report_path.stat()
    assert report_path.read_bytes() == existing
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
    assert list(report_path.parent.glob(".report.json.*.tmp")) == []


def test_non_authoritative_report_temporary_cannot_poison_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even failed temporary cleanup cannot create retained attempt state."""
    cutoff = "2026-08-27T22:52:09+08:00"
    attempt_id = "report-temporary-retry"
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / attempt_id
    )
    authority = _authority(tmp_path, cutoff=cutoff)
    attempt_root = output / "attempts" / attempt_id
    active = True
    original_fsync = os.fsync
    original_unlink = Path.unlink

    def faulting_fsync(file_descriptor: int) -> None:
        if active:
            raise OSError
        original_fsync(file_descriptor)

    def faulting_unlink(
        path: Path,
        missing_ok: bool = False,  # noqa: FBT001, FBT002 - mirrors Path.unlink exactly.
    ) -> None:
        if active and path.parent == attempt_root and path.name.startswith(".report.json."):
            raise OSError
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(os, "fsync", faulting_fsync)
    monkeypatch.setattr(Path, "unlink", faulting_unlink)
    with pytest.raises(
        execution.SourceEvidenceIntegrityError,
        match="SOURCE_EVIDENCE_INTEGRITY_FAILURE",
    ):
        execute_source_family(
            authority_manifest=authority,
            source_family="GLD",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_Transport(b"writer-compatible"),
        )

    assert not (attempt_root / "report.json").exists()
    stale_temporaries = list(attempt_root.glob(".report.json.*.tmp"))
    assert len(stale_temporaries) == 1

    active = False
    retried = execute_source_family(
        authority_manifest=authority,
        source_family="GLD",
        output_root=output,
        attempt_id=attempt_id,
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_Transport(b"writer-compatible"),
    )
    assert json.loads((attempt_root / "report.json").read_bytes()) == retried
    assert stale_temporaries[0].exists()


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_final_report_publication_preserves_base_exception_visibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interruption: type[BaseException],
) -> None:
    """The report durability boundary never converts process-control exceptions."""
    cutoff = "2026-08-27T22:52:09+08:00"
    attempt_id = f"report-{interruption.__name__.lower()}"
    output = (
        REPOSITORY_ROOT
        / "var"
        / "test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / attempt_id
    )
    authority = _authority(tmp_path, cutoff=cutoff)

    def interrupt_fsync(_file_descriptor: int) -> None:
        raise interruption

    monkeypatch.setattr(os, "fsync", interrupt_fsync)
    with pytest.raises(interruption):
        execute_source_family(
            authority_manifest=authority,
            source_family="GLD",
            output_root=output,
            attempt_id=attempt_id,
            observation_cutoff=cutoff,
            repository_root=REPOSITORY_ROOT,
            transport=_Transport(b"writer-compatible"),
        )

    attempt_root = output / "attempts" / attempt_id
    assert not (attempt_root / "report.json").exists()
    assert list(attempt_root.glob(".report.json.*.tmp")) == []


_HKEX_ROLE_FIXTURES = REPOSITORY_ROOT / "packages/source-connectors/tests/fixtures/hkex"


def _hkex_role_aware_candidate_static_bodies() -> dict[str, bytes]:
    bodies = {
        f"sep_000000000000000000000000000000000000000000000{suffix}": (
            _HKEX_ROLE_FIXTURES / "role-roots" / f"endpoint-{suffix}.html"
        ).read_bytes()
        for suffix in range(303, 309)
    }
    section_files = {
        313: "forms-main-6190.html",
        314: "fees-main-3783.html",
        319: "forms-gem-6191.html",
        320: "fees-gem-1836.html",
    }
    bodies.update(
        {
            f"sep_000000000000000000000000000000000000000000000{suffix}": (
                _HKEX_ROLE_FIXTURES / "role-sections" / filename
            ).read_bytes()
            for suffix, filename in section_files.items()
        }
    )
    structure = cast(
        "dict[str, object]",
        json.loads(
            (_HKEX_ROLE_FIXTURES / "role-sections/retained-structure-manifest.json").read_bytes()
        ),
    )
    boards = cast("list[dict[str, object]]", structure["boards"])
    object_root = (
        REPOSITORY_ROOT / "var/hk-v1/source-admission/hkex/authentic-baseline-20260901c/objects"
    )
    for item in boards:
        endpoint_id = cast("str", item["section_endpoint_id"])
        object_sha = cast("str", item["section_object_sha256"])
        object_path = object_root / f"{object_sha}.bin"
        if not object_path.is_file():
            pytest.skip("frozen Attempt-C Updates sections unavailable")
        bodies[endpoint_id] = object_path.read_bytes()
    return bodies


def _hkex_role_aware_candidate_form_facts() -> tuple[dict[str, bytes], dict[str, str]]:
    manifest = cast(
        "dict[str, object]",
        json.loads((_HKEX_ROLE_FIXTURES / "form-members/direct-probe-manifest.json").read_bytes()),
    )
    bodies: dict[str, bytes] = {}
    final_urls: dict[str, str] = {}
    for item in cast("list[dict[str, object]]", manifest["fixtures"]):
        requested_url = cast("str", item["requested_url"])
        bodies[requested_url] = (
            _HKEX_ROLE_FIXTURES / "form-members" / cast("str", item["fixture_filename"])
        ).read_bytes()
        final_urls[requested_url] = cast("str", item["final_url"])
    return bodies, final_urls


def test_hkex_role_aware_candidate_freezes_static_and_forms_tiers_before_pdf_io() -> None:
    """The pure candidate plans every Forms HTML before any PDF request exists."""
    endpoints = candidate_hkex_endpoints()
    plan = execution.build_hkex_traversal_plan(
        _hkex_role_aware_candidate_static_bodies(), endpoints
    )

    assert len(endpoints) == 20
    assert len(plan.root_bindings) == 6
    assert len(plan.form_html_requests) == 17
    assert tuple(request.sequence for request in plan.form_html_requests) == tuple(range(21, 38))
    assert all(
        request.relation is execution.HKEXMembershipRelation.FORM_NODE
        for request in plan.form_html_requests
    )
    assert not any(
        request.relation
        in {
            execution.HKEXMembershipRelation.UPDATE_CONTAINER,
            execution.HKEXMembershipRelation.UPDATE_PAGE,
        }
        for request in (*plan.form_html_requests, *plan.pdf_requests)
    )
    assert plan.accounting.semantic_only_associations == 198
    assert plan.accounting.unfetched_external_associations == 14
    assert len(plan.attachment_occurrences) == 536


def test_hkex_role_aware_candidate_finalizer_matches_authentic_plan_arithmetic() -> None:
    """All Forms bodies must reconcile before the immutable 301-request plan exists."""
    endpoints = candidate_hkex_endpoints()
    initial = execution.build_hkex_traversal_plan(
        _hkex_role_aware_candidate_static_bodies(), endpoints
    )
    bodies, final_urls = _hkex_role_aware_candidate_form_facts()

    plan = execution.finalize_hkex_traversal_plan(
        initial,
        form_bodies=bodies,
        form_final_urls=final_urls,
        endpoints=endpoints,
    )

    assert plan.accounting == execution.HKEXTraversalAccounting(
        static_registered_requests=20,
        unique_dynamic_html_requests=17,
        unique_dynamic_pdf_requests=264,
        logical_request_starts=301,
        semantic_only_associations=198,
        planned_or_reused_associations=298,
        unfetched_external_associations=14,
        declared_associations=510,
    )
    assert len({request.sequence for request in plan.pdf_requests}) == 264
    assert tuple(request.sequence for request in plan.pdf_requests) == tuple(range(38, 302))
    assert len({request.requested_url for request in plan.pdf_requests}) == 264


@pytest.mark.parametrize(
    ("raw", "reader_complete", "expected_prefix", "expected_complete", "expected_total"),
    [
        (b"a" * 8_192, True, 8_192, True, 8_192),
        (b"a" * 8_193, True, 8_193, True, 8_193),
        (b"a" * 8_194, True, 8_193, False, None),
        (b"a" * 20_000, False, 8_193, False, None),
    ],
)
def test_hkex_role_aware_candidate_raw_location_probe_is_strictly_bounded(
    raw: bytes,
    reader_complete: bool,  # noqa: FBT001 - explicit coherence-table parameter
    expected_prefix: int,
    expected_complete: bool,  # noqa: FBT001 - explicit coherence-table parameter
    expected_total: int | None,
) -> None:
    """The boundary retains 8,193 bytes, discards one lookahead, and never asks for 8,195."""
    requested: list[int] = []

    def reader(limit: int) -> tuple[bytes, bool]:
        requested.append(limit)
        return raw[:limit], reader_complete and len(raw) <= limit

    probe = execution.probe_hkex_raw_location(reader)

    assert requested == [8_194]
    assert probe.prefix_octet_count == expected_prefix
    assert probe.representation_complete is expected_complete
    assert probe.total_octet_count == expected_total
    assert probe.over_limit is (len(raw) > 8_192)
    assert len(probe.location_octets_base64_prefix or "") <= 10_924


def test_hkex_role_aware_candidate_raw_location_distinguishes_absent_and_empty() -> None:
    """A present empty value is not collapsed into a missing Location field."""
    absent = execution.probe_hkex_raw_location(None)
    empty = execution.probe_hkex_raw_location(lambda _limit: (b"", True))

    assert absent.location_present is False
    assert absent.location_octets_base64_prefix is None
    assert absent.total_octet_count is None
    assert empty.location_present is True
    assert empty.location_octets_base64_prefix == ""
    assert empty.total_octet_count == 0


def test_hkex_role_aware_candidate_controller_paces_every_physical_start() -> None:
    """Initial and followed starts share one exact permit and pacing boundary."""
    now = 10.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    def sleeper(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    controller = execution.HKEXObservationController(clock=clock, sleeper=sleeper)

    assert controller.before_physical_start() is True
    assert controller.before_physical_start() is True
    assert controller.physical_starts == 2
    assert sleeps == [0.25]
    assert controller.pacing_sleep_count == 1
    assert controller.pacing_sleep_seconds == 0.25
    assert controller.elapsed_seconds == 0.25


def test_hkex_role_aware_candidate_controller_caps_redirect_events_and_followed_starts() -> None:
    """Global redirect-event and followed-hop ceilings reject cap-plus-one pre-effect."""
    events = execution.HKEXObservationController(
        clock=lambda: 0.0,
        sleeper=lambda _seconds: None,
        redirect_events=1_024,
    )
    followed = execution.HKEXObservationController(
        clock=lambda: 0.0,
        sleeper=lambda _seconds: None,
        followed_redirect_starts=512,
    )

    assert events.reserve_redirect_event() is False
    assert events.stop_code == "BUDGET_EXHAUSTED"
    assert followed.before_physical_start(followed_redirect=True) is False
    assert followed.stop_code == "BUDGET_EXHAUSTED"


def test_hkex_role_aware_candidate_controller_stops_before_prohibited_start() -> None:
    """Physical and elapsed ceilings reject the next start without sleeping or transport."""
    sleeps: list[float] = []
    physical = execution.HKEXObservationController(
        clock=lambda: 0.0,
        sleeper=sleeps.append,
        physical_starts=3_680,
    )
    elapsed_values = iter((0.0, 3_600.0))
    elapsed = execution.HKEXObservationController(
        clock=lambda: next(elapsed_values),
        sleeper=sleeps.append,
    )

    assert physical.before_physical_start() is False
    assert physical.stop_code == "BUDGET_EXHAUSTED"
    assert elapsed.before_physical_start() is True
    assert elapsed.before_physical_start() is False
    assert elapsed.stop_code == "OBSERVATION_BUDGET_EXHAUSTED"
    assert sleeps == []


@pytest.mark.parametrize("media_type", ["text/html", "application/pdf"])
def test_hkex_role_aware_candidate_response_reservation_is_exact(media_type: str) -> None:
    """A response at its media bound is retained and bound-plus-one is truncated."""
    bound = {"text/html": 16_777_216, "application/pdf": 67_108_864}[media_type]
    accepted = execution.HKEXObservationController(clock=lambda: 0.0, sleeper=lambda _: None)
    rejected = execution.HKEXObservationController(clock=lambda: 0.0, sleeper=lambda _: None)

    assert accepted.reserve_response(byte_length=bound, media_type=media_type) is True
    assert rejected.reserve_response(byte_length=bound + 1, media_type=media_type) is False
    assert rejected.stop_code == "TRUNCATED"


def test_hkex_role_aware_candidate_plan_projection_is_exact_and_replayable() -> None:
    """The complete plan projection retains every typed member and no semantic-only request."""
    endpoints = candidate_hkex_endpoints()
    initial = execution.build_hkex_traversal_plan(
        _hkex_role_aware_candidate_static_bodies(), endpoints
    )
    bodies, final_urls = _hkex_role_aware_candidate_form_facts()
    plan = execution.finalize_hkex_traversal_plan(
        initial,
        form_bodies=bodies,
        form_final_urls=final_urls,
        endpoints=endpoints,
    )

    projection = execution.hkex_traversal_plan_projection(plan)

    assert set(projection) == {
        "accounting",
        "attachment_occurrences",
        "membership_associations",
        "root_bindings",
        "staged_requests",
    }
    assert execution.require_hkex_traversal_plan_projection(projection, plan) is None
    staged = cast("list[dict[str, object]]", projection["staged_requests"])
    root_bindings = cast("list[dict[str, object]]", projection["root_bindings"])
    assert all(
        set(item)
        == {
            "board",
            "canonical_url",
            "node_id",
            "root_endpoint_id",
            "section_endpoint_id",
            "shortlink_url",
            "source_id",
            "entire_section_url",
        }
        for item in root_bindings
    )
    assert len(staged) == 281
    assert not any(item["relation"] in {"UPDATE_CONTAINER", "UPDATE_PAGE"} for item in staged)


@pytest.mark.parametrize(
    "field",
    [
        "accounting",
        "attachment_occurrences",
        "membership_associations",
        "root_bindings",
        "staged_requests",
    ],
)
def test_hkex_role_aware_candidate_plan_projection_mutations_fail_closed(field: str) -> None:
    """Every schema-2 plan surface is exact-key and canonical-order bound."""
    endpoints = candidate_hkex_endpoints()
    initial = execution.build_hkex_traversal_plan(
        _hkex_role_aware_candidate_static_bodies(), endpoints
    )
    bodies, final_urls = _hkex_role_aware_candidate_form_facts()
    plan = execution.finalize_hkex_traversal_plan(
        initial,
        form_bodies=bodies,
        form_final_urls=final_urls,
        endpoints=endpoints,
    )
    forged = execution.hkex_traversal_plan_projection(plan)
    if field == "accounting":
        cast("dict[str, object]", forged[field])["logical_request_starts"] = 300
    else:
        cast("list[object]", forged[field]).reverse()

    with pytest.raises(ValueError, match="HKEX_ROLE_AWARE_PLAN_INVALID"):
        execution.require_hkex_traversal_plan_projection(forged, plan)


def _hkex_raw_reader(raw: bytes) -> Callable[[int], tuple[bytes, bool]]:
    def read(limit: int) -> tuple[bytes, bool]:
        return raw[:limit], len(raw) <= limit

    return read


def _empty_hkex_urls() -> list[str]:
    return []


def _empty_hkex_calls() -> list[tuple[str, int]]:
    return []


@dataclass
class _HKEXRoleAwareTransport:
    responses: list[CapturedResponse]
    calls: list[str] = field(default_factory=_empty_hkex_urls)

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        self.calls.append(url)
        assert max_bytes == 16_777_216
        return self.responses.pop(0)


@dataclass
class _HKEXRoleAwareCandidateTransport:
    endpoints: tuple[OfficialEndpointContract, ...]
    calls: list[tuple[str, int]] = field(default_factory=_empty_hkex_calls)
    _static_bodies: dict[str, bytes] = field(init=False)
    _form_bodies: dict[str, bytes] = field(init=False)
    _form_final_urls: dict[str, str] = field(init=False)
    _form_body_by_final: dict[str, bytes] = field(init=False)
    _endpoint_by_url: dict[str, OfficialEndpointContract] = field(init=False)

    def __post_init__(self) -> None:
        self._static_bodies = _hkex_role_aware_candidate_static_bodies()
        self._form_bodies, self._form_final_urls = _hkex_role_aware_candidate_form_facts()
        self._form_body_by_final = {
            self._form_final_urls[url]: body for url, body in self._form_bodies.items()
        }
        self._endpoint_by_url = {item.url: item for item in self.endpoints}

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        self.calls.append((url, max_bytes))
        endpoint = self._endpoint_by_url.get(url)
        if endpoint is not None:
            body = self._static_bodies.get(endpoint.endpoint_id)
            if body is None and endpoint.endpoint_id.endswith("309"):
                roots = (
                    "main-board-listing-rules",
                    "gem-listing-rules",
                    "main-board-regulatory-forms",
                    "gem-regulatory-forms",
                    "main-board-fees-rules",
                    "gem-fees-rules",
                    "amendments-main-board-listing-rules",
                    "amendments-gem-listing-rules",
                )
                body = b"".join(
                    f'<a href="https://en-rules.hkex.com.hk/rulebook/{root}">{root}</a>'.encode()
                    for root in roots
                )
            if body is None and "application/pdf" in endpoint.media_types:
                body = b"%PDF-1.7\nstatic candidate"
            if body is None:
                body = b"<html>static candidate</html>"
            return CapturedResponse(200, endpoint.media_types[0], body, url)
        final = self._form_final_urls.get(url)
        if final is not None:
            return CapturedResponse(
                302,
                "text/html",
                b"",
                url,
                raw_location_reader=_hkex_raw_reader(final.encode()),
            )
        body = self._form_body_by_final.get(url)
        if body is not None:
            return CapturedResponse(200, "text/html", body, url)
        if url.endswith(".pdf"):
            return CapturedResponse(200, "application/pdf", b"%PDF-1.7\ndynamic candidate", url)
        raise AssertionError(url)


class _HKEXRoleAwareStaticDriftTransport(_HKEXRoleAwareCandidateTransport):
    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        endpoint = self._endpoint_by_url.get(url)
        if endpoint is not None and endpoint.endpoint_id.endswith("303"):
            self.calls.append((url, max_bytes))
            return CapturedResponse(200, "text/html", b"<html>drift</html>", url)
        return super().get(url=url, max_bytes=max_bytes)


class _HKEXRoleAwareStaticOutageTransport(_HKEXRoleAwareCandidateTransport):
    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        endpoint = self._endpoint_by_url.get(url)
        if endpoint is not None and endpoint.endpoint_id.endswith("303"):
            self.calls.append((url, max_bytes))
            return CapturedResponse(502, "text/html", b"publisher outage", url)
        return super().get(url=url, max_bytes=max_bytes)


class _HKEXRoleAwareFormDriftTransport(_HKEXRoleAwareCandidateTransport):
    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if url in self._form_body_by_final:
            self.calls.append((url, max_bytes))
            return CapturedResponse(200, "text/html", b"<html>drift</html>", url)
        return super().get(url=url, max_bytes=max_bytes)


class _HKEXRoleAwareFormOutageTransport(_HKEXRoleAwareCandidateTransport):
    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if url in self._form_final_urls:
            self.calls.append((url, max_bytes))
            return CapturedResponse(502, "text/html", b"publisher outage", url)
        return super().get(url=url, max_bytes=max_bytes)


class _HKEXRoleAwarePDFOutageTransport(_HKEXRoleAwareCandidateTransport):
    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        if url.endswith(".pdf") and url not in self._endpoint_by_url:
            self.calls.append((url, max_bytes))
            return CapturedResponse(502, "application/pdf", b"publisher outage", url)
        return super().get(url=url, max_bytes=max_bytes)


def test_hkex_role_aware_candidate_captures_all_tiers_in_exact_order(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    """The candidate executor freezes each whole tier and accounts every start exactly once."""
    endpoints = candidate_hkex_endpoints()
    transport = _HKEXRoleAwareCandidateTransport(endpoints)
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    captured = execution.capture_hkex_role_aware(
        endpoints=endpoints,
        transport=transport,
        clock=lambda: now,
        sleeper=sleeper,
    )

    assert captured.plan_state == "COMPLETE_PLAN"
    assert captured.plan is not None
    assert captured.plan.accounting.logical_request_starts == 301
    assert len(captured.captures) == 301
    assert tuple(item.sequence for item in captured.captures) == tuple(range(1, 302))
    assert len(captured.dynamic_html_attempts) == 17
    assert len(captured.page_identities) == 17
    assert len(captured.physical_starts) == 318
    assert tuple(item.sequence for item in captured.physical_starts) == tuple(range(1, 319))
    assert captured.followed_redirect_starts == 17
    assert captured.redirect_event_count == 17
    assert len(transport.calls) == 318
    assert all(not url.endswith(".pdf") for url, _max_bytes in transport.calls[20:54])
    assert transport.calls[54][0].endswith(".pdf")

    fields = execution.hkex_role_aware_report_fields(captured)
    assert set(fields) == {
        "execution_policy",
        "execution_policy_fingerprint",
        "hkex_attachment_occurrences",
        "hkex_dynamic_html_attempts",
        "hkex_membership_associations",
        "hkex_membership_fingerprint",
        "hkex_plan_state",
        "hkex_page_identities",
        "hkex_physical_starts",
        "hkex_request_plan",
        "hkex_root_bindings",
        "hkex_traversal_accounting",
        "report_schema_version",
    }
    assert fields["report_schema_version"] == "2.0.0"
    assert fields["hkex_plan_state"] == "COMPLETE_PLAN"
    accounting = cast("dict[str, object]", fields["hkex_traversal_accounting"])
    assert accounting == {
        "declared_associations": 510,
        "dynamic_html_attempted": 17,
        "dynamic_html_planned": 17,
        "dynamic_pdf_attempted": 264,
        "dynamic_pdf_planned": 264,
        "elapsed_seconds": 79.25,
        "followed_redirect_starts": 17,
        "logical_request_starts": 301,
        "pacing_sleep_count": 317,
        "pacing_sleep_seconds": 79.25,
        "physical_request_starts": 318,
        "planned_or_reused_associations": 298,
        "raw_attachment_occurrences": 536,
        "redirect_event_count": 17,
        "retained_raw_location_octets": sum(
            len(final.encode()) for final in _hkex_role_aware_candidate_form_facts()[1].values()
        ),
        "retained_response_bytes": captured.retained_response_bytes,
        "reused_static_targets": 2,
        "semantic_only_associations": 198,
        "static_attempted": 20,
        "static_planned": 20,
        "stop_code": None,
        "unfetched_external_associations": 14,
        "unique_dynamic_html_urls": 17,
        "unique_dynamic_pdf_urls": 264,
    }
    assert cast("str", fields["hkex_membership_fingerprint"]).startswith("sha256:")
    assert execution.require_hkex_role_aware_report_fields(fields, captured) is None
    procedures = execution.hkex_role_aware_procedures(captured)
    assert procedures == [
        {
            "declared_member_count": 5,
            "source_id": "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
            "terminal_code": "COMPLETE",
        },
        {
            "declared_member_count": 2,
            "source_id": "HK-REG-HKEX-FEES-RULES",
            "terminal_code": "COMPLETE",
        },
        {
            "declared_member_count": 34,
            "source_id": "HK-REG-HKEX-REGULATORY-FORMS",
            "terminal_code": "COMPLETE",
        },
        {
            "declared_member_count": 474,
            "source_id": "HK-REG-HKEX-RULE-UPDATES",
            "terminal_code": "EXTERNAL_REFERENCE_AUTHORITY_REQUIRED",
        },
        {
            "declared_member_count": 8,
            "source_id": "HK-REG-HKEX-RULEBOOK-CATALOGUE",
            "terminal_code": "COMPLETE",
        },
    ]
    assert execution.hkex_role_aware_result(captured, procedures) == (
        "EVIDENCE_CAPTURED_INCOMPLETE"
    )

    forged = copy.deepcopy(fields)
    cast("dict[str, object]", forged["hkex_traversal_accounting"])["physical_request_starts"] = 317
    with pytest.raises(ValueError, match="HKEX_ROLE_AWARE_REPORT_INVALID"):
        execution.require_hkex_role_aware_report_fields(forged, captured)

    output = tmp_path / "candidate-output"
    report = execution.publish_hkex_role_aware_report(
        output_root=output,
        attempt_id="hkex-role-aware-candidate",
        observation_cutoff="2026-09-01T15:33:35+08:00",
        authority_manifest_fingerprint="sha256:" + "a" * 64,
        authority_provenance="USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        execution_authorization_fingerprint="sha256:" + "b" * 64,
        predecessor_attempt_id=None,
        capture=captured,
    )
    report_path = output / "attempts/hkex-role-aware-candidate/report.json"
    assert (
        report_path.read_bytes()
        == json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    )
    assert len(_items(report, "endpoints")) == 301
    assert report["result"] == "EVIDENCE_CAPTURED_INCOMPLETE"
    before = {
        path.relative_to(output).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mode & 0o777,
            path.stat().st_mtime_ns,
        )
        for path in output.rglob("*")
        if path.is_file()
    }

    replayed = execution.replay_hkex_role_aware_report(
        report,
        output_root=output,
        endpoints=endpoints,
    )
    after = {
        path.relative_to(output).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mode & 0o777,
            path.stat().st_mtime_ns,
        )
        for path in output.rglob("*")
        if path.is_file()
    }
    assert replayed == report
    assert after == before

    forged_report = copy.deepcopy(report)
    cast("dict[str, object]", forged_report["hkex_traversal_accounting"])[
        "physical_request_starts"
    ] = 317
    with pytest.raises(ValueError, match="HKEX_ROLE_AWARE_REPORT_INVALID"):
        execution.replay_hkex_role_aware_report(
            forged_report,
            output_root=output,
            endpoints=endpoints,
        )


def test_hkex_role_aware_candidate_static_drift_stops_before_dynamic_io() -> None:
    """A static-root contract drift prevents every dynamic request."""
    endpoints = candidate_hkex_endpoints()
    transport = _HKEXRoleAwareStaticDriftTransport(endpoints)
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    captured = execution.capture_hkex_role_aware(
        endpoints=endpoints,
        transport=transport,
        clock=lambda: now,
        sleeper=sleeper,
    )

    assert captured.plan_state == "ROOT_CONTRACT_CHANGED"
    assert captured.plan is None
    assert len(captured.captures) == 20
    assert len(transport.calls) == 20
    assert captured.dynamic_html_attempts == ()
    assert captured.page_identities == ()


def test_hkex_role_aware_candidate_form_drift_stops_before_pdf_tier() -> None:
    """One Forms identity drift prevents the entire PDF tier."""
    endpoints = candidate_hkex_endpoints()
    transport = _HKEXRoleAwareFormDriftTransport(endpoints)
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    captured = execution.capture_hkex_role_aware(
        endpoints=endpoints,
        transport=transport,
        clock=lambda: now,
        sleeper=sleeper,
    )

    assert captured.plan_state == "FORM_MEMBER_CONTRACT_CHANGED"
    assert captured.plan is not None
    assert len(captured.captures) == 21
    assert len(captured.dynamic_html_attempts) == 1
    assert captured.page_identities == ()
    assert all(item.stage != "PDF_TIER" for item in captured.captures)


@pytest.mark.parametrize(
    ("transport_type", "expected_state", "expected_result"),
    [
        (
            _HKEXRoleAwareStaticDriftTransport,
            "ROOT_CONTRACT_CHANGED",
            "SOURCE_CONTRACT_CHANGED",
        ),
        (
            _HKEXRoleAwareStaticOutageTransport,
            "STATIC_CAPTURE_INCOMPLETE",
            "SOURCE_OUTAGE",
        ),
        (
            _HKEXRoleAwareFormDriftTransport,
            "FORM_MEMBER_CONTRACT_CHANGED",
            "SOURCE_CONTRACT_CHANGED",
        ),
        (
            _HKEXRoleAwareFormOutageTransport,
            "FORM_HTML_TIER_INCOMPLETE",
            "SOURCE_OUTAGE",
        ),
    ],
)
def test_hkex_role_aware_candidate_closed_failure_states_publish_and_replay(
    tmp_path: Path,
    transport_type: type[_HKEXRoleAwareCandidateTransport],
    expected_state: str,
    expected_result: str,
) -> None:
    """A closed pre-PDF stop remains a canonical zero-effect replay boundary."""

    def snapshot(root: Path) -> dict[str, tuple[str, int, int, int]]:
        return {
            path.relative_to(root).as_posix(): (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_size,
                path.stat().st_mode & 0o777,
                path.stat().st_mtime_ns,
            )
            for path in root.rglob("*")
            if path.is_file()
        }

    endpoints = candidate_hkex_endpoints()
    transport = transport_type(endpoints)
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    captured = execution.capture_hkex_role_aware(
        endpoints=endpoints,
        transport=transport,
        clock=lambda: now,
        sleeper=sleeper,
    )
    output = tmp_path / expected_state.lower()
    report = execution.publish_hkex_role_aware_report(
        output_root=output,
        attempt_id=f"hkex-{expected_state.lower().replace('_', '-')}",
        observation_cutoff="2026-09-01T15:33:35+08:00",
        authority_manifest_fingerprint="sha256:" + "a" * 64,
        authority_provenance="USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        execution_authorization_fingerprint="sha256:" + "b" * 64,
        predecessor_attempt_id=None,
        capture=captured,
    )
    before = snapshot(output)
    replayed = execution.replay_hkex_role_aware_report(
        report,
        output_root=output,
        endpoints=endpoints,
    )

    assert report["hkex_plan_state"] == expected_state
    assert report["result"] == expected_result
    assert replayed == report
    assert snapshot(output) == before
    assert all(item["stage"] != "PDF_TIER" for item in _items(report, "hkex_request_plan"))


def test_hkex_role_aware_candidate_root_policy_limit_is_a_closed_replay_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root-derived plan beyond policy stops before dynamic I/O and replays exactly."""
    endpoints = candidate_hkex_endpoints()
    original = execution._hkex_role_plan  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def oversized_role_plan(  # noqa: PLR0913 - mirrors the parser dispatcher.
        *,
        source_id: str,
        board: execution.HKEXPublisherBoard,
        root: OfficialEndpointContract,
        section: OfficialEndpointContract,
        bodies: Mapping[str, bytes],
        capture_id_by_url: Mapping[str, str],
    ) -> execution.HKEXRoleMembershipPlan:
        role_plan = original(
            source_id=source_id,
            board=board,
            root=root,
            section=section,
            bodies=bodies,
            capture_id_by_url=capture_id_by_url,
        )
        if (
            source_id != "HK-REG-HKEX-REGULATORY-FORMS"
            or board is not execution.HKEXPublisherBoard.MAIN
        ):
            return role_plan
        seed = next(
            item
            for item in role_plan.associations
            if item.relation is execution.HKEXMembershipRelation.FORM_NODE
        )
        associations = tuple(
            replace(
                seed,
                association_id=f"sha256:{index:064x}",
                capture_endpoint_id=f"dep_{index:064x}",
                source_order=index,
                target_url=f"https://en-rules.hkex.com.hk/node/{10_000 + index}",
            )
            for index in range(1, 258)
        )
        return replace(role_plan, associations=associations)

    monkeypatch.setattr(execution, "_hkex_role_plan", oversized_role_plan)
    transport = _HKEXRoleAwareCandidateTransport(endpoints)
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    captured = execution.capture_hkex_role_aware(
        endpoints=endpoints,
        transport=transport,
        clock=lambda: now,
        sleeper=sleeper,
    )
    assert captured.plan_state == "ROOT_POLICY_LIMIT_EXCEEDED"
    assert captured.plan is None
    assert len(transport.calls) == 20

    output = tmp_path / "root-policy-limit"
    report = execution.publish_hkex_role_aware_report(
        output_root=output,
        attempt_id="hkex-root-policy-limit",
        observation_cutoff="2026-09-01T15:33:35+08:00",
        authority_manifest_fingerprint="sha256:" + "a" * 64,
        authority_provenance="USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        execution_authorization_fingerprint="sha256:" + "b" * 64,
        predecessor_attempt_id=None,
        capture=captured,
    )
    assert (
        execution.replay_hkex_role_aware_report(
            report,
            output_root=output,
            endpoints=endpoints,
        )
        == report
    )


def test_hkex_role_aware_candidate_pdf_outage_preserves_complete_plan_and_replays(
    tmp_path: Path,
) -> None:
    """A PDF outage retains the already frozen whole plan and wins over parser drift."""
    endpoints = candidate_hkex_endpoints()
    transport = _HKEXRoleAwarePDFOutageTransport(endpoints)
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    captured = execution.capture_hkex_role_aware(
        endpoints=endpoints,
        transport=transport,
        clock=lambda: now,
        sleeper=sleeper,
    )
    output = tmp_path / "pdf-outage"
    report = execution.publish_hkex_role_aware_report(
        output_root=output,
        attempt_id="hkex-pdf-outage",
        observation_cutoff="2026-09-01T15:33:35+08:00",
        authority_manifest_fingerprint="sha256:" + "a" * 64,
        authority_provenance="USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        execution_authorization_fingerprint="sha256:" + "b" * 64,
        predecessor_attempt_id=None,
        capture=captured,
    )

    assert captured.plan_state == "COMPLETE_PLAN"
    assert captured.captures[-1].stage == "PDF_TIER"
    assert captured.captures[-1].terminal_code == "OUTAGE"
    assert report["result"] == "SOURCE_OUTAGE"
    assert (
        execution.replay_hkex_role_aware_report(
            report,
            output_root=output,
            endpoints=endpoints,
        )
        == report
    )


@pytest.mark.parametrize(
    "field",
    [
        "plan_state",
        "policy",
        "root_binding",
        "request_plan",
        "association",
        "occurrence",
        "redirect_event",
        "redirect_location_bytes",
        "physical_start",
        "pacing",
        "page_identity",
        "endpoint_status",
        "result",
    ],
)
def test_hkex_role_aware_candidate_report_mutations_fail_replay_closed(  # noqa: C901, PLR0912
    tmp_path: Path,
    field: str,
) -> None:
    """Every independently bound schema-2 surface is rederived before replay acceptance."""
    endpoints = candidate_hkex_endpoints()
    transport = _HKEXRoleAwareCandidateTransport(endpoints)
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    captured = execution.capture_hkex_role_aware(
        endpoints=endpoints,
        transport=transport,
        clock=lambda: now,
        sleeper=sleeper,
    )
    output = tmp_path / field
    report = execution.publish_hkex_role_aware_report(
        output_root=output,
        attempt_id=f"hkex-mutation-{field.replace('_', '-')}",
        observation_cutoff="2026-09-01T15:33:35+08:00",
        authority_manifest_fingerprint="sha256:" + "a" * 64,
        authority_provenance="USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        execution_authorization_fingerprint="sha256:" + "b" * 64,
        predecessor_attempt_id=None,
        capture=captured,
    )
    forged = copy.deepcopy(report)
    if field == "plan_state":
        forged["hkex_plan_state"] = "FORM_HTML_TIER_INCOMPLETE"
    elif field == "policy":
        forged["execution_policy_fingerprint"] = "sha256:" + "0" * 64
    elif field == "root_binding":
        item = _items(forged, "hkex_root_bindings")[0]
        item["canonical_url"] = cast("str", item["canonical_url"]) + "/drift"
    elif field == "request_plan":
        _items(forged, "hkex_request_plan")[0]["sequence"] = 999
    elif field == "association":
        _items(forged, "hkex_membership_associations")[0]["source_order"] = 999
    elif field == "occurrence":
        item = _items(forged, "hkex_attachment_occurrences")[0]
        item["raw_locator"] = cast("str", item["raw_locator"]) + "#drift"
    elif field == "redirect_event":
        events = cast(
            "list[dict[str, object]]",
            _items(forged, "hkex_dynamic_html_attempts")[0]["redirect_events"],
        )
        events[0]["prefix_octet_count"] = 0
    elif field == "redirect_location_bytes":
        events = cast(
            "list[dict[str, object]]",
            _items(forged, "hkex_dynamic_html_attempts")[0]["redirect_events"],
        )
        encoded = cast("str", events[0]["location_octets_base64_prefix"])
        raw = bytearray(base64.b64decode(encoded))
        raw[-1] = ord("x") if raw[-1] != ord("x") else ord("y")
        events[0]["location_octets_base64_prefix"] = base64.b64encode(raw).decode()
    elif field == "physical_start":
        _items(forged, "hkex_physical_starts")[-1]["start_elapsed_seconds"] = 0.0
    elif field == "pacing":
        accounting = cast("dict[str, object]", forged["hkex_traversal_accounting"])
        accounting["pacing_sleep_count"] = 316
    elif field == "page_identity":
        item = _items(forged, "hkex_page_identities")[0]
        item["final_url"] = cast("str", item["final_url"]) + "/drift"
    elif field == "endpoint_status":
        _items(forged, "endpoints")[0]["status"] = 500
    else:
        forged["result"] = "COMPLETE"

    with pytest.raises(ValueError, match="HKEX_ROLE_AWARE_REPORT_INVALID"):
        execution.replay_hkex_role_aware_report(
            forged,
            output_root=output,
            endpoints=endpoints,
        )


def test_hkex_role_aware_candidate_public_execution_and_replay_are_zero_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The current executor can exercise the immutable candidate before register activation."""

    class ExplodingTransport:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            pytest.fail(f"HKEX replay reached transport: {url=} {max_bytes=}")

    endpoints = candidate_hkex_endpoints()
    cutoff = "2026-09-01T15:33:35+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    authority_document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    authority_fingerprint = cast("str", authority_document["fingerprint"])
    authorization = ExecutionAuthorization(
        authority_manifest_fingerprint=authority_fingerprint,
        source_family="HKEX",
        source_ids=tuple(
            sorted(
                {
                    "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
                    "HK-REG-HKEX-FEES-RULES",
                    "HK-REG-HKEX-REGULATORY-FORMS",
                    "HK-REG-HKEX-RULE-UPDATES",
                    "HK-REG-HKEX-RULEBOOK-CATALOGUE",
                }
            )
        ),
        observation_cutoff=cutoff,
        allowed_urls=tuple(sorted(item.url for item in endpoints)),
        register_identity=("hk-regulatory", "candidate", "sha256:" + "c" * 64),
        binding_fingerprint="sha256:" + "d" * 64,
        historical_replay=False,
    )

    def authorize_candidate(**_kwargs: object) -> ExecutionAuthorization:
        return authorization

    def registered_candidate(
        *_args: object, **_kwargs: object
    ) -> tuple[OfficialEndpointContract, ...]:
        return endpoints

    monkeypatch.setattr(execution, "authorize_execution", authorize_candidate)
    monkeypatch.setattr(execution, "_registered_endpoints", registered_candidate)
    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "candidate-public"
    )
    transport = _HKEXRoleAwareCandidateTransport(endpoints)
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    report = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="hkex-role-aware-public",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=transport,
        authorization=authorization,
        hkex_clock=lambda: now,
        hkex_sleeper=sleeper,
    )
    before = {
        path.relative_to(output).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mode & 0o777,
            path.stat().st_mtime_ns,
        )
        for path in output.rglob("*")
        if path.is_file()
    }
    assert report["report_schema_version"] == "2.0.0"
    assert len(transport.calls) == 318

    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="hkex-role-aware-public",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ExplodingTransport(),
        authorization=authorization,
        hkex_clock=lambda: pytest.fail("HKEX replay reached clock"),
        hkex_sleeper=lambda _seconds: pytest.fail("HKEX replay reached sleeper"),
    )
    after = {
        path.relative_to(output).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mode & 0o777,
            path.stat().st_mtime_ns,
        )
        for path in output.rglob("*")
        if path.is_file()
    }
    assert replayed == report
    assert after == before


def test_hkex_role_aware_candidate_public_contract_stop_replays_without_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public restart path accepts the exact closed schema-2 contract-stop result."""

    class ExplodingTransport:
        def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
            pytest.fail(f"HKEX contract-stop replay reached transport: {url=} {max_bytes=}")

    endpoints = candidate_hkex_endpoints()
    cutoff = "2026-09-01T15:33:35+08:00"
    authority = _authority(tmp_path, cutoff=cutoff)
    authority_document = cast("dict[str, object]", json.loads(authority.read_bytes()))
    authorization = ExecutionAuthorization(
        authority_manifest_fingerprint=cast("str", authority_document["fingerprint"]),
        source_family="HKEX",
        source_ids=tuple(
            sorted(
                {
                    "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
                    "HK-REG-HKEX-FEES-RULES",
                    "HK-REG-HKEX-REGULATORY-FORMS",
                    "HK-REG-HKEX-RULE-UPDATES",
                    "HK-REG-HKEX-RULEBOOK-CATALOGUE",
                }
            )
        ),
        observation_cutoff=cutoff,
        allowed_urls=tuple(sorted(item.url for item in endpoints)),
        register_identity=("hk-regulatory", "candidate", "sha256:" + "c" * 64),
        binding_fingerprint="sha256:" + "d" * 64,
        historical_replay=False,
    )

    def authorize_candidate(**_kwargs: object) -> ExecutionAuthorization:
        return authorization

    def registered_candidate(
        *_args: object, **_kwargs: object
    ) -> tuple[OfficialEndpointContract, ...]:
        return endpoints

    monkeypatch.setattr(execution, "authorize_execution", authorize_candidate)
    monkeypatch.setattr(execution, "_registered_endpoints", registered_candidate)
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    output = (
        REPOSITORY_ROOT
        / "var/test-hk-v1-source-execution"
        / tmp_path.parent.name
        / tmp_path.name
        / "candidate-public-stop"
    )
    report = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="hkex-role-aware-public-stop",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=_HKEXRoleAwareStaticDriftTransport(endpoints),
        authorization=authorization,
        hkex_clock=lambda: now,
        hkex_sleeper=sleeper,
    )
    before = {
        path.relative_to(output).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
        for path in output.rglob("*")
        if path.is_file()
    }
    replayed = execute_source_family(
        authority_manifest=authority,
        source_family="HKEX",
        output_root=output,
        attempt_id="hkex-role-aware-public-stop",
        observation_cutoff=cutoff,
        repository_root=REPOSITORY_ROOT,
        transport=ExplodingTransport(),
        authorization=authorization,
        hkex_clock=lambda: pytest.fail("contract-stop replay reached clock"),
        hkex_sleeper=lambda _seconds: pytest.fail("contract-stop replay reached sleeper"),
    )

    assert report["result"] == "SOURCE_CONTRACT_CHANGED"
    assert replayed == report
    assert {
        path.relative_to(output).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
        for path in output.rglob("*")
        if path.is_file()
    } == before


def test_hkex_role_aware_candidate_form_redirect_retains_both_physical_starts() -> None:
    """One admitted Forms redirect produces one event and two exact physical starts."""
    endpoints = candidate_hkex_endpoints()
    plan = execution.build_hkex_traversal_plan(
        _hkex_role_aware_candidate_static_bodies(), endpoints
    )
    request = plan.form_html_requests[0]
    bodies, final_urls = _hkex_role_aware_candidate_form_facts()
    target = final_urls[request.requested_url]
    transport = _HKEXRoleAwareTransport(
        [
            CapturedResponse(
                302,
                "text/html",
                b"redirect",
                request.requested_url,
                raw_location_reader=_hkex_raw_reader(target.encode()),
            ),
            CapturedResponse(200, "text/html", bodies[request.requested_url], target),
        ]
    )
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    starts: list[execution.HKEXPhysicalStart] = []
    controller = execution.HKEXObservationController(clock=lambda: now, sleeper=sleeper)
    captured = execution.capture_hkex_form_attempt(
        request=request,
        transport=transport,
        controller=controller,
        physical_starts=starts,
        first_event_sequence=1,
    )

    assert captured is not None
    attempt, response = captured
    assert response.body == bodies[request.requested_url]
    assert transport.calls == [request.requested_url, target]
    assert [(item.hop_number, item.requested_url) for item in starts] == [
        (0, request.requested_url),
        (1, target),
    ]
    assert len(attempt.redirect_events) == 1
    assert attempt.redirect_events[0].followed is True
    assert attempt.redirect_events[0].validated_target_url == target
    assert attempt.redirect_rejected is False
    assert attempt.physical_terminal_code == "CAPTURED"
    assert controller.retained_response_bytes == len(b"redirect") + len(response.body)

    identity, associations = execution.derive_hkex_form_member(
        request=request,
        attempt=attempt,
        response=response,
        board=execution.HKEXPublisherBoard.MAIN,
        capture_id_by_url={endpoint.url: endpoint.endpoint_id for endpoint in endpoints},
    )
    assert len(associations) == 1
    assert identity.canonical_url == target
    assert identity.shortlink_url == request.requested_url
    projection = execution.hkex_transport_projection((attempt,), tuple(starts), (identity,))

    assert set(projection) == {
        "dynamic_html_attempts",
        "page_identities",
        "physical_starts",
    }
    attempt_item = cast("list[dict[str, object]]", projection["dynamic_html_attempts"])[0]
    assert set(attempt_item) == {
        "capture_endpoint_id",
        "endpoint_version",
        "final_url",
        "initial_physical_start_sequence",
        "initial_start_elapsed_seconds",
        "media_type",
        "physical_terminal_code",
        "redirect_events",
        "redirect_rejected",
        "relation",
        "requested_url",
        "semantic_terminal_code",
        "sequence",
        "status",
    }
    event = cast("list[dict[str, object]]", attempt_item["redirect_events"])[0]
    assert set(event) == {
        "event_sequence",
        "followed",
        "location_octets_base64_prefix",
        "location_present",
        "over_limit",
        "prefix_octet_count",
        "rejection_code",
        "representation_complete",
        "response_hop_number",
        "response_status",
        "source_url",
        "target_physical_start_sequence",
        "target_start_elapsed_seconds",
        "total_octet_count",
        "validated_target_url",
    }
    assert (
        execution.require_hkex_transport_projection(
            projection, (attempt,), tuple(starts), (identity,)
        )
        is None
    )

    forged = copy.deepcopy(projection)
    cast("list[dict[str, object]]", forged["physical_starts"])[0]["hop_number"] = 1
    with pytest.raises(ValueError, match="HKEX_ROLE_AWARE_TRANSPORT_INVALID"):
        execution.require_hkex_transport_projection(forged, (attempt,), tuple(starts), (identity,))


def test_hkex_role_aware_candidate_second_redirect_is_retained_without_hop_two() -> None:
    """A redirect response on hop one is evidence, but it can never start hop two."""
    endpoints = candidate_hkex_endpoints()
    plan = execution.build_hkex_traversal_plan(
        _hkex_role_aware_candidate_static_bodies(), endpoints
    )
    request = plan.form_html_requests[0]
    _, final_urls = _hkex_role_aware_candidate_form_facts()
    target = final_urls[request.requested_url]
    transport = _HKEXRoleAwareTransport(
        [
            CapturedResponse(
                302,
                "text/html",
                b"",
                request.requested_url,
                raw_location_reader=_hkex_raw_reader(target.encode()),
            ),
            CapturedResponse(
                302,
                "text/html",
                b"",
                target,
                raw_location_reader=_hkex_raw_reader(b"/rulebook/another-page"),
            ),
        ]
    )
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    starts: list[execution.HKEXPhysicalStart] = []
    captured = execution.capture_hkex_form_attempt(
        request=request,
        transport=transport,
        controller=execution.HKEXObservationController(clock=lambda: now, sleeper=sleeper),
        physical_starts=starts,
        first_event_sequence=1,
    )

    assert captured is not None
    attempt, _ = captured
    assert len(transport.calls) == 2
    assert len(starts) == 2
    assert [item.rejection_code for item in attempt.redirect_events] == [
        None,
        "SECOND_REDIRECT_REJECTED",
    ]
    assert attempt.semantic_terminal_code == "SOURCE_CONTRACT_CHANGED"


def test_hkex_role_aware_candidate_overlimit_location_never_starts_target() -> None:
    """Observed byte 8,194 rejects before Location decoding or another physical start."""
    endpoints = candidate_hkex_endpoints()
    plan = execution.build_hkex_traversal_plan(
        _hkex_role_aware_candidate_static_bodies(), endpoints
    )
    request = plan.form_html_requests[0]
    transport = _HKEXRoleAwareTransport(
        [
            CapturedResponse(
                302,
                "text/html",
                b"",
                request.requested_url,
                raw_location_reader=_hkex_raw_reader(b"a" * 20_000),
            )
        ]
    )
    starts: list[execution.HKEXPhysicalStart] = []

    captured = execution.capture_hkex_form_attempt(
        request=request,
        transport=transport,
        controller=execution.HKEXObservationController(clock=lambda: 0.0, sleeper=lambda _: None),
        physical_starts=starts,
        first_event_sequence=1,
    )

    assert captured is not None
    attempt, _ = captured
    assert transport.calls == [request.requested_url]
    assert len(starts) == 1
    assert attempt.redirect_events[0].rejection_code == "LOCATION_OVER_LIMIT"
    assert attempt.redirect_events[0].prefix_octet_count == 8_193
    assert attempt.redirect_events[0].representation_complete is False
    assert attempt.semantic_terminal_code == "SOURCE_CONTRACT_CHANGED"


@pytest.mark.parametrize("raw", [b"a" * 8_193, b"a" * 8_194, b"a" * 20_000])
def test_hkex_role_aware_candidate_overlimit_replay_never_decodes_a_url(
    raw: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replay checks only bounded over-limit coherence and never treats it as a URL."""
    endpoints = candidate_hkex_endpoints()
    plan = execution.build_hkex_traversal_plan(
        _hkex_role_aware_candidate_static_bodies(), endpoints
    )
    request = plan.form_html_requests[0]
    captured = execution.capture_hkex_form_attempt(
        request=request,
        transport=_HKEXRoleAwareTransport(
            [
                CapturedResponse(
                    302,
                    "text/html",
                    b"",
                    request.requested_url,
                    raw_location_reader=_hkex_raw_reader(raw),
                )
            ]
        ),
        controller=execution.HKEXObservationController(
            clock=lambda: 0.0, sleeper=lambda _seconds: None
        ),
        physical_starts=[],
        first_event_sequence=1,
    )
    assert captured is not None
    event = captured[0].redirect_events[0]

    def reject_url_decode(_raw: str, *, kind: execution.HKEXLocatorKind) -> NoReturn:
        pytest.fail(f"over-limit replay decoded a URL: {kind}")

    monkeypatch.setattr(execution, "require_hkex_raw_locator", reject_url_decode)
    assert (
        execution._hkex_parse_redirect_event(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            execution._hkex_redirect_event_projection(event)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        )
        == event
    )


def test_hkex_role_aware_candidate_redirect_event_schema_is_exact() -> None:
    """Invalid Base64, extra event fields, and a hostile third event fail closed."""
    endpoints = candidate_hkex_endpoints()
    plan = execution.build_hkex_traversal_plan(
        _hkex_role_aware_candidate_static_bodies(), endpoints
    )
    request = plan.form_html_requests[0]
    _, final_urls = _hkex_role_aware_candidate_form_facts()
    target = final_urls[request.requested_url]
    now = 0.0

    def sleeper(seconds: float) -> None:
        nonlocal now
        now += seconds

    captured = execution.capture_hkex_form_attempt(
        request=request,
        transport=_HKEXRoleAwareTransport(
            [
                CapturedResponse(
                    302,
                    "text/html",
                    b"",
                    request.requested_url,
                    raw_location_reader=_hkex_raw_reader(target.encode()),
                ),
                CapturedResponse(200, "text/html", b"<html></html>", target),
            ]
        ),
        controller=execution.HKEXObservationController(clock=lambda: now, sleeper=sleeper),
        physical_starts=[],
        first_event_sequence=1,
    )
    assert captured is not None
    attempt = captured[0]
    event = execution._hkex_redirect_event_projection(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        attempt.redirect_events[0]
    )

    invalid_base64 = dict(event)
    invalid_base64["location_octets_base64_prefix"] = "***"
    extra = dict(event)
    extra["discarded_lookahead_octets"] = 1
    for hostile in (invalid_base64, extra):
        with pytest.raises(ValueError, match="HKEX_ROLE_AWARE_REPORT_INVALID"):
            execution._hkex_parse_redirect_event(hostile)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    attempt_projection = execution._hkex_dynamic_attempt_projection(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        attempt
    )
    events = cast("list[dict[str, object]]", attempt_projection["redirect_events"])
    events.extend((dict(event), dict(event)))
    with pytest.raises(ValueError, match="HKEX_ROLE_AWARE_REPORT_INVALID"):
        execution._hkex_parse_dynamic_attempt(attempt_projection)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
