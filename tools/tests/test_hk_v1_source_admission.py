"""Zero-network tests for the Hong Kong V1 source-admission preflight."""

from __future__ import annotations

import ast
import hashlib
import json
import socket
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest

import tools.hk_v1_source_admission as admission
import tools.hk_v1_source_execution as execution

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXTERNAL_CONSTRUCTOR_REACHED = "external constructor reached"
_DISABLED = False
_MATRIX_RAW_SHA256_NAME = "_" + "CHECKED_IN_MATRIX_RAW_SHA256"
MATRIX_PATH = (
    REPOSITORY_ROOT / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
)
_REGISTER_ROOT = REPOSITORY_ROOT / "packages/source-connectors/src/asklegal_source_connectors"
_REGISTER_PATHS = (
    _REGISTER_ROOT / "hk_legislation_source_register.json",
    _REGISTER_ROOT / "hk_cases_source_register.json",
    _REGISTER_ROOT / "hk_regulatory_source_register.json",
)


def test_source_admission_pins_the_current_two_family_matrix_bytes() -> None:
    """Preflight derives authority only from the exact approved two-family snapshot."""
    expected = "2a4a8021b12d1adb52decfd8b007c8610d0eb20c2185b322315b265355de9c29"
    assert hashlib.sha256(MATRIX_PATH.read_bytes()).hexdigest() == expected
    assert getattr(admission, _MATRIX_RAW_SHA256_NAME) == expected


def _object(value: object) -> dict[str, object]:
    assert type(value) is dict
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


def _document(path: Path) -> dict[str, object]:
    return _object(json.loads(path.read_bytes()))


def _register_binding(path: Path, family: str) -> dict[str, object]:
    register = _document(path)
    return {
        "family": family,
        "register_id": register["register_id"],
        "register_version": register["register_version"],
        "fingerprint": register["fingerprint"],
    }


def _manifest() -> dict[str, object]:
    matrix = _document(MATRIX_PATH)
    return {
        "schema_version": "1.0.0",
        "authority_id": "hka_000000000000000000000000000000000000000000000001",
        "scope": "HK_V1_SOURCE_ADMISSION_PREFLIGHT",
        "provenance": "PROJECT_USER_AUTHORITY_REQUEST",
        "effective_date": "2026-08-25",
        "expires_on": "2027-08-26",
        "matrix": {"revision": matrix["revision"], "fingerprint": matrix["fingerprint"]},
        "registers": [
            _register_binding(_REGISTER_PATHS[0], "LEGISLATION"),
            _register_binding(_REGISTER_PATHS[1], "CASES"),
            _register_binding(_REGISTER_PATHS[2], "REGULATORY"),
        ],
        "selected_sources": [],
        "publisher_permissions": [],
        "user_reports": [
            {
                "report_id": "usr_000000000000000000000000000000000000000000000001",
                "reference": _reference("user-report", provenance="USER_REPORTED"),
            }
        ],
        "terms": [],
        "observation_window": {},
        "credentials": [],
        "sessions": [],
    }


def _write_manifest(tmp_path: Path, manifest: dict[str, object]) -> Path:
    path = tmp_path / "authority-manifest.json"
    unsigned = dict(manifest)
    unsigned.pop("fingerprint", None)
    manifest["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    path.write_bytes(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    return path


def _reference(
    label: str,
    *,
    provenance: str = "PUBLISHER_ISSUED",
    scope: str = "READ_ONLY_SOURCE_ADMISSION",
) -> dict[str, object]:
    return {
        "vault": "PRIMARY",
        "logical_key": f"hk-v1/{label}",
        "version_id": "v" + "a" * 64,
        "fingerprint": "sha256:" + "a" * 64,
        "byte_length": 1,
        "publisher": "publisher",
        "scope": scope,
        "effective_date": "2026-08-25",
        "expires_on": "2027-08-26",
        "provenance": provenance,
    }


def _registered_gld_endpoints() -> list[dict[str, object]]:
    register = _document(_REGISTER_PATHS[0])
    endpoints = cast("list[object]", register["endpoints"])
    result: list[dict[str, object]] = []
    for candidate in endpoints:
        endpoint = _object(candidate)
        if endpoint["source_id"] != "HK-LEG-GLD-EGAZETTE":
            continue
        parsed = urlsplit(cast("str", endpoint["url"]))
        result.append(
            {
                "endpoint_id": endpoint["endpoint_id"],
                "host": parsed.netloc,
                "method": cast("list[str]", endpoint["methods"])[0],
                "path": parsed.path + (f"?{parsed.query}" if parsed.query else ""),
                "procedure_id": endpoint["endpoint_id"],
                "redirect_policy": "NO_REDIRECT",
            }
        )
    return result


def _complete_shaped_gld_manifest() -> dict[str, object]:
    manifest = _manifest()
    manifest["effective_date"] = "2026-08-25"
    endpoints = _registered_gld_endpoints()
    endpoint = endpoints[0]
    manifest["publisher_permissions"] = [
        {
            "permission_id": "pp_000000000000000000000000000000000000000000000001",
            "source_ids": ["HK-LEG-GLD-EGAZETTE"],
            "hosts": sorted({cast("str", item["host"]) for item in endpoints}),
            "procedure_ids": sorted({cast("str", item["procedure_id"]) for item in endpoints}),
            "reference": _reference("permission"),
        }
    ]
    manifest["terms"] = [
        {
            "host": endpoint["host"],
            "state": "ALREADY_ACCEPTED_WITH_EVIDENCE",
            "terms_reference": _reference("terms", scope="PUBLISHER_TERMS_EVIDENCE"),
            "acceptance_evidence": _reference("terms-acceptance", scope="PUBLISHER_TERMS_EVIDENCE"),
        }
    ]
    manifest["observation_window"] = {
        "start": "2026-08-25T00:00:00+08:00",
        "end": "2026-08-26T00:00:00+08:00",
        "cutoff": "2026-08-26T00:00:00+08:00",
        "timezone": "Asia/Hong_Kong",
    }
    manifest["selected_sources"] = [
        {
            "family": "LEGISLATION",
            "source_id": "HK-LEG-GLD-EGAZETTE",
            "endpoints": endpoints,
            "publisher_permission_id": "pp_000000000000000000000000000000000000000000000001",
        }
    ]
    return manifest


def _report(tmp_path: Path, manifest: dict[str, object]) -> admission.AdmissionReport:
    return admission.preflight(
        authority_manifest=_write_manifest(tmp_path, manifest),
        matrix=MATRIX_PATH,
        output_root=Path("var/hk-v1/source-admission"),
        repository_root=REPOSITORY_ROOT,
    )


def test_preflight_reports_current_missing_admission_facts_without_execution(
    tmp_path: Path,
) -> None:
    """User-reported authority cannot stand in for publisher evidence or endpoints."""
    report = _report(tmp_path, _manifest())

    assert report["result"] == "NOT_ADMITTED"
    assert report["execute_authorized"] is False
    assert report["missing_codes"] == sorted(report["missing_codes"])
    assert "PUBLISHER_PERMISSION_EVIDENCE_MISSING" in report["missing_codes"]
    assert "OBSERVATION_WINDOW_MISSING" in report["missing_codes"]
    assert "TERMS_STATE_MISSING" in report["missing_codes"]
    assert "CASES_ENDPOINT_CONTRACT_MISSING" not in report["missing_codes"]
    assert "REGULATORY_ENDPOINT_CONTRACT_MISSING" not in report["missing_codes"]


def test_user_attested_document_pending_authority_is_valid_but_remains_visible(
    tmp_path: Path,
) -> None:
    """The controller's operational authority must not be forged as publisher evidence."""
    manifest = _manifest()
    manifest["provenance"] = "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING"

    report = _report(tmp_path, manifest)

    assert "AUTHORITY_MANIFEST_MALFORMED" not in report["missing_codes"]
    assert "PERMISSION_DOCUMENT_PENDING" not in report["missing_codes"]
    assert report["limitation_codes"] == ["PERMISSION_DOCUMENT_PENDING"]
    assert report["result"] == "NOT_ADMITTED"
    assert report["execute_authorized"] is False


def test_preflight_is_byte_identical_and_never_creates_its_output_root(tmp_path: Path) -> None:
    """A pure preflight has deterministic stdout data and no implicit artifact write."""
    manifest = _write_manifest(tmp_path, _manifest())
    output_root = tmp_path / "repository" / "var" / "admission"
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    (repository_root / "var").mkdir()

    first = admission.preflight(
        authority_manifest=manifest,
        matrix=MATRIX_PATH,
        output_root=output_root,
        repository_root=repository_root,
    )
    second = admission.preflight(
        authority_manifest=manifest,
        matrix=MATRIX_PATH,
        output_root=output_root,
        repository_root=repository_root,
    )

    assert admission.canonical_report_bytes(first) == admission.canonical_report_bytes(second)
    assert not output_root.exists()


@pytest.mark.parametrize("field", ["password", "api_key", "token", "credential_value"])
def test_preflight_rejects_secret_like_manifest_fields(tmp_path: Path, field: str) -> None:
    """The authority file is references-only and never accepts a secret value."""
    manifest = _manifest()
    manifest[field] = "not-permitted"

    assert "SECRET_OR_SESSION_VALUE_FORBIDDEN" in _report(tmp_path, manifest)["missing_codes"]


def test_preflight_binds_rehashed_matrix_and_register_bytes(tmp_path: Path) -> None:
    """A declared identity cannot replace a fresh content digest check."""
    manifest = _manifest()
    matrix = _document(MATRIX_PATH)
    matrix["revision"] = "HK-V1-DRIFT"
    drifted_matrix = tmp_path / "matrix.json"
    drifted_matrix.write_bytes(json.dumps(matrix, sort_keys=True, separators=(",", ":")).encode())

    report = admission.preflight(
        authority_manifest=_write_manifest(tmp_path, manifest),
        matrix=drifted_matrix,
        output_root=Path("var/hk-v1/source-admission"),
        repository_root=REPOSITORY_ROOT,
    )

    assert "MATRIX_NOT_CHECKED_IN_SNAPSHOT" in report["missing_codes"]
    assert "MATRIX_IDENTITY_MISMATCH" in report["missing_codes"]


def test_preflight_rejects_unsafe_output_roots(tmp_path: Path) -> None:
    """Preflight accepts only an explicit ignored repository-local var root."""
    report = admission.preflight(
        authority_manifest=_write_manifest(tmp_path, _manifest()),
        matrix=MATRIX_PATH,
        output_root=tmp_path / "outside",
        repository_root=REPOSITORY_ROOT,
    )

    assert "OUTPUT_ROOT_UNSAFE" in report["missing_codes"]


def test_preflight_rejects_repository_var_symlink_escape(tmp_path: Path) -> None:
    """A repository-local output path cannot resolve through a symlink outside it."""
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (repository_root / "var").symlink_to(outside, target_is_directory=True)

    report = admission.preflight(
        authority_manifest=_write_manifest(tmp_path, _manifest()),
        matrix=MATRIX_PATH,
        output_root=repository_root / "var" / "admission",
        repository_root=repository_root,
    )

    assert "OUTPUT_ROOT_UNSAFE" in report["missing_codes"]
    assert not (outside / "admission").exists()


def test_execute_mode_requires_exact_family_attempt_and_cutoff(tmp_path: Path) -> None:
    """Execute cannot acquire anything from an underspecified command."""
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.hk_v1_source_admission",
            "--authority-manifest",
            str(_write_manifest(tmp_path, _manifest())),
            "--matrix",
            str(MATRIX_PATH),
            "--mode",
            "execute",
            "--output-root",
            "var/hk-v1/source-admission",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 2
    assert result.stderr == b""
    assert json.loads(result.stdout) == {
        "execute_authorized": False,
        "result": "EXECUTION_INPUT_REQUIRED",
    }


def test_execute_rejects_detailed_preflight_failure_before_transport_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invalid authority/Matrix bytes cannot reach even the urllib transport constructor."""
    drifted_matrix = tmp_path / "matrix.json"
    matrix = _document(MATRIX_PATH)
    matrix["revision"] = "HK-V1-DRIFT"
    drifted_matrix.write_text(json.dumps(matrix, sort_keys=True, separators=(",", ":")))

    construction_error = "transport constructed before execution preflight"

    def explode() -> object:
        raise AssertionError(construction_error)

    monkeypatch.setattr(execution, "UrllibReadOnlyTransport", explode)

    exit_code = admission.main(
        [
            "--authority-manifest",
            str(_write_manifest(tmp_path, _manifest())),
            "--matrix",
            str(drifted_matrix),
            "--mode",
            "execute",
            "--source-family",
            "HKEX",
            "--attempt-id",
            "blocked-before-transport",
            "--observation-cutoff",
            "2026-08-27T22:52:09+08:00",
            "--output-root",
            "var/hk-v1/source-admission/test",
        ]
    )

    assert exit_code == 2
    result = json.loads(capsys.readouterr().out)
    assert result["execute_authorized"] is False
    assert result["result"] == "EXECUTION_NOT_AUTHORIZED"
    assert "MATRIX_NOT_CHECKED_IN_SNAPSHOT" in result["missing_codes"]


@pytest.mark.parametrize(
    ("terminal", "expected_exit"),
    [("COMPLETE", 0), ("EVIDENCE_CAPTURED_INCOMPLETE", 1)],
)
def test_execute_cli_exit_is_success_only_for_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    terminal: str,
    expected_exit: int,
) -> None:
    """The prescribed execute command must not signal shell success for incomplete proof."""

    def fake_authorize(**_kwargs: object) -> object:
        return object()

    def fake_transport(**_kwargs: object) -> object:
        return object()

    def fake_execute(**_kwargs: object) -> dict[str, object]:
        return {"result": terminal}

    monkeypatch.setattr(admission, "authorize_execution", fake_authorize)
    monkeypatch.setattr(execution, "UrllibReadOnlyTransport", fake_transport)
    monkeypatch.setattr(execution, "execute_source_family", fake_execute)

    exit_code = admission.main(
        [
            "--authority-manifest",
            str(_write_manifest(tmp_path, _manifest())),
            "--matrix",
            str(MATRIX_PATH),
            "--mode",
            "execute",
            "--source-family",
            "HKEX",
            "--attempt-id",
            "cli-terminal",
            "--observation-cutoff",
            "2026-08-27T22:52:09+08:00",
            "--output-root",
            "var/hk-v1/source-admission/test",
        ]
    )

    assert exit_code == expected_exit
    assert json.loads(capsys.readouterr().out)["result"] == terminal


def test_preflight_does_not_modify_matrix_or_register_bytes(tmp_path: Path) -> None:
    """All supplied authority checks are read-only."""
    originals = {
        path: hashlib.sha256(path.read_bytes()).digest() for path in (MATRIX_PATH, *_REGISTER_PATHS)
    }

    _report(tmp_path, _manifest())

    assert {path: hashlib.sha256(path.read_bytes()).digest() for path in originals} == originals


def test_complete_shaped_gld_authority_still_stops_on_partial_cases_and_hkex_roles(
    tmp_path: Path,
) -> None:
    """One-family authority cannot hide the other families' visible blockers."""
    report = _report(tmp_path, _complete_shaped_gld_manifest())

    assert "CASES_ENDPOINT_CONTRACT_MISSING" not in report["missing_codes"]
    assert "REGULATORY_ENDPOINT_CONTRACT_MISSING" not in report["missing_codes"]
    assert "SOURCE_BLOCKERS_PRESENT" in report["missing_codes"]
    assert "ENDPOINT_CONTRACT_UNREGISTERED" not in report["missing_codes"]
    assert "SELECTED_SOURCE_ENDPOINT_MEMBERSHIP_INCOMPLETE" not in report["missing_codes"]


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("host", "ENDPOINT_HOST_UNREGISTERED"),
        ("method", "ENDPOINT_METHOD_UNREGISTERED"),
        ("path", "ENDPOINT_PATH_UNREGISTERED"),
        ("procedure_id", "ENDPOINT_PROCEDURE_UNREGISTERED"),
        ("redirect_policy", "ENDPOINT_REDIRECT_UNREGISTERED"),
    ],
)
def test_registered_endpoint_claims_bind_every_transport_leaf(
    tmp_path: Path, field: str, code: str
) -> None:
    """A manifest cannot widen one admitted endpoint by changing one leaf."""
    manifest = _complete_shaped_gld_manifest()
    source = _object(cast("list[object]", manifest["selected_sources"])[0])
    endpoint = _object(cast("list[object]", source["endpoints"])[0])
    endpoint[field] = "POST" if field == "method" else "unregistered"

    assert code in _report(tmp_path, manifest)["missing_codes"]


def test_duplicate_json_key_and_unknown_manifest_field_fail_closed(tmp_path: Path) -> None:
    """Ambiguous JSON and unmodelled authority claims have no interpretation."""
    path = tmp_path / "duplicate.json"
    path.write_text('{"authority_id":"first","authority_id":"second"}', encoding="utf-8")
    duplicate = admission.preflight(
        authority_manifest=path,
        matrix=MATRIX_PATH,
        output_root=Path("var/hk-v1/source-admission"),
        repository_root=REPOSITORY_ROOT,
    )
    manifest = _manifest()
    manifest["unmodelled"] = "claim"

    assert "AUTHORITY_MANIFEST_MALFORMED" in duplicate["missing_codes"]
    assert "AUTHORITY_MANIFEST_MALFORMED" in _report(tmp_path, manifest)["missing_codes"]


def test_preflight_never_reaches_socket_http_or_browser_import_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transport and browser boundaries exploding cannot affect pure local validation."""

    def explode(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(_EXTERNAL_CONSTRUCTOR_REACHED)

    monkeypatch.setattr(socket, "create_connection", explode)
    monkeypatch.setattr(socket, "getaddrinfo", explode)
    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(HTTPConnection, "request", explode)
    monkeypatch.setattr(HTTPSConnection, "connect", explode)
    monkeypatch.setattr(urllib.request, "urlopen", explode)
    monkeypatch.setitem(sys.modules, "patchright", None)
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "asklegal_evidence_vault", None)
    monkeypatch.setitem(sys.modules, "asklegal_credential_provider", None)

    report = _report(tmp_path, _complete_shaped_gld_manifest())

    assert report["execute_authorized"] is False


def test_preflight_imports_only_local_parsers_and_standard_library_utilities() -> None:
    """The disabled admission tool owns no transport or credential client import route."""
    module = ast.parse((REPOSITORY_ROOT / "tools/hk_v1_source_admission.py").read_text())
    imports = {
        alias.name
        for statement in module.body
        if isinstance(statement, ast.Import)
        for alias in statement.names
    }
    from_imports = {
        statement.module
        for statement in module.body
        if isinstance(statement, ast.ImportFrom) and statement.module is not None
    }

    assert imports == {"argparse", "hashlib", "json", "re", "sys"}
    assert from_imports == {
        "__future__",
        "dataclasses",
        "datetime",
        "pathlib",
        "typing",
        "urllib.parse",
        "asklegal_contracts",
        "asklegal_contracts.json_types",
        "asklegal_reporting",
        "tools.hk_v1_hkex_history",
        "tools.hk_v1_hkex_policy",
        "tools.hk_v1_judiciary_policy",
    }


def test_manifest_byte_bound_fails_closed(tmp_path: Path) -> None:
    """Oversized authority bytes cannot become an accepted fact."""
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b"x" * 1_000_001 + b"}")
    oversized_report = admission.preflight(
        authority_manifest=oversized,
        matrix=MATRIX_PATH,
        output_root=Path("var/hk-v1/source-admission"),
        repository_root=REPOSITORY_ROOT,
    )

    assert "AUTHORITY_MANIFEST_MALFORMED" in oversized_report["missing_codes"]


def test_manifest_requires_canonical_frozen_json_bytes(tmp_path: Path) -> None:
    """A correctly hashed but whitespace-formatted authority file is not frozen input."""
    manifest = _manifest()
    _write_manifest(tmp_path, manifest)
    path = tmp_path / "authority-manifest.json"
    path.write_bytes(json.dumps(manifest, indent=2, sort_keys=True).encode())

    report = admission.preflight(
        authority_manifest=path,
        matrix=MATRIX_PATH,
        output_root=Path("var/hk-v1/source-admission"),
        repository_root=REPOSITORY_ROOT,
    )

    assert "AUTHORITY_MANIFEST_MALFORMED" in report["missing_codes"]


def test_fixed_matrix_byte_pin_rejects_resealed_checked_in_state_drift(tmp_path: Path) -> None:
    """A rehashed Matrix projection cannot replace the code-owned whole-file pin."""
    root = tmp_path / "repository"
    matrix_path = root / MATRIX_PATH.relative_to(REPOSITORY_ROOT)
    matrix_path.parent.mkdir(parents=True)
    matrix = _document(MATRIX_PATH)
    rows = cast("list[object]", matrix["rows"])
    _object(rows[0])["technical_state"] = "ADMITTED"
    unsigned = dict(matrix)
    unsigned.pop("fingerprint")
    matrix["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    matrix_path.write_bytes(
        json.dumps(matrix, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )
    for register_path in _REGISTER_PATHS:
        target = root / register_path.relative_to(REPOSITORY_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(register_path.read_bytes())
    (root / "var").mkdir()

    report = admission.preflight(
        authority_manifest=_write_manifest(tmp_path, _manifest()),
        matrix=matrix_path,
        output_root=root / "var" / "admission",
        repository_root=root,
    )

    assert "MATRIX_CHECKED_IN_BYTES_DRIFT" in report["missing_codes"]


@pytest.mark.parametrize("dates", [("2026-08-27", "2027-08-26"), ("2026-08-20", "2026-08-24")])
def test_root_authority_must_cover_its_observation_window(
    tmp_path: Path, dates: tuple[str, str]
) -> None:
    """A frozen request cannot predate or outlive the authority it cites."""
    manifest = _complete_shaped_gld_manifest()
    manifest["effective_date"], manifest["expires_on"] = dates

    assert "AUTHORITY_TIME_WINDOW_INVALID" in _report(tmp_path, manifest)["missing_codes"]


def test_publisher_and_terms_evidence_must_cover_observation_window(tmp_path: Path) -> None:
    """Source rights and terms proof must be live at the requested cutoff."""
    manifest = _complete_shaped_gld_manifest()
    permission = _object(cast("list[object]", manifest["publisher_permissions"])[0])
    _object(permission["reference"])["expires_on"] = "2026-08-24"
    terms = _object(cast("list[object]", manifest["terms"])[0])
    _object(terms["acceptance_evidence"])["effective_date"] = "2026-08-27"

    codes = _report(tmp_path, manifest)["missing_codes"]

    assert "PUBLISHER_PERMISSION_EVIDENCE_MALFORMED" in codes
    assert "TERMS_STATE_MALFORMED" in codes


def test_user_report_provenance_cannot_stand_in_for_publisher_terms_evidence(
    tmp_path: Path,
) -> None:
    """A user assertion cannot be reclassified as publisher terms acceptance."""
    baseline = _report(tmp_path, _complete_shaped_gld_manifest())
    assert "TERMS_STATE_MALFORMED" not in baseline["missing_codes"]
    manifest = _complete_shaped_gld_manifest()
    terms = _object(cast("list[object]", manifest["terms"])[0])
    _object(terms["acceptance_evidence"])["provenance"] = "USER_REPORTED"

    assert "TERMS_STATE_MALFORMED" in _report(tmp_path, manifest)["missing_codes"]


def test_calendar_dates_and_register_binding_families_are_closed(tmp_path: Path) -> None:
    """Syntactic dates and surplus register bindings cannot become authority."""
    manifest = _complete_shaped_gld_manifest()
    manifest["effective_date"] = "2026-02-31"
    assert "AUTHORITY_MANIFEST_MALFORMED" in _report(tmp_path, manifest)["missing_codes"]
    manifest = _complete_shaped_gld_manifest()
    permission = _object(cast("list[object]", manifest["publisher_permissions"])[0])
    _object(permission["reference"])["expires_on"] = "9999-99-99"
    assert "PUBLISHER_PERMISSION_EVIDENCE_MALFORMED" in _report(tmp_path, manifest)["missing_codes"]
    manifest = _complete_shaped_gld_manifest()
    bindings = cast("list[object]", manifest["registers"])
    extra = dict(_object(bindings[0]))
    extra["family"] = "UNKNOWN"
    bindings.append(extra)
    assert "REGISTER_IDENTITIES_MALFORMED" in _report(tmp_path, manifest)["missing_codes"]


def test_immutable_references_reject_equality_liars_and_unsafe_locator_fields() -> None:
    """Exact scalar checks prevent clever objects or unsafe vault locators from passing."""

    class EqualityLiar(str):
        __slots__ = ()
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            return True

    reference = _reference("permission")
    reference["vault"] = "https://not-a-vault"
    assert admission.is_immutable_reference(reference) is False
    reference = _reference("permission")
    reference["logical_key"] = "../../outside"
    assert admission.is_immutable_reference(reference) is False
    reference = _reference("permission")
    reference["vault"] = EqualityLiar("PRIMARY")
    assert admission.is_immutable_reference(reference) is False


def _mutate_legislation_endpoint(document: dict[str, object]) -> None:
    _object(cast("list[object]", document["endpoints"])[0])["enabled"] = _DISABLED


def _mutate_cases_access_boundary(document: dict[str, object]) -> None:
    _object(document["access_boundary"])["state"] = "CONFIGURED"


def _mutate_regulatory_rights(document: dict[str, object]) -> None:
    _object(cast("list[object]", document["sources"])[0])["rights_state"] = "ADMITTED"


_REGISTER_MUTATIONS: tuple[tuple[str, Callable[[dict[str, object]], None]], ...] = (
    ("LEGISLATION", _mutate_legislation_endpoint),
    ("CASES", _mutate_cases_access_boundary),
    ("REGULATORY", _mutate_regulatory_rights),
)


@pytest.mark.parametrize(("family", "mutate"), _REGISTER_MUTATIONS)
def test_fixed_full_register_byte_pins_reject_resealed_endpoint_access_and_rights_drift(
    tmp_path: Path, family: str, mutate: Callable[[dict[str, object]], None]
) -> None:
    """No self-rehashed inner document can replace a fixed checked-in family authority."""
    root = tmp_path / "repository"
    matrix_path = root / MATRIX_PATH.relative_to(REPOSITORY_ROOT)
    matrix_path.parent.mkdir(parents=True)
    matrix_path.write_bytes(MATRIX_PATH.read_bytes())
    for register_path in _REGISTER_PATHS:
        target = root / register_path.relative_to(REPOSITORY_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(register_path.read_bytes())
    (root / "var").mkdir()
    target = root / (
        _REGISTER_PATHS[{"LEGISLATION": 0, "CASES": 1, "REGULATORY": 2}[family]].relative_to(
            REPOSITORY_ROOT
        )
    )
    document = _document(target)
    mutate(document)
    unsigned = dict(document)
    unsigned.pop("fingerprint")
    document["fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    target.write_bytes(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )

    report = admission.preflight(
        authority_manifest=_write_manifest(tmp_path, _manifest()),
        matrix=matrix_path,
        output_root=root / "var" / "admission",
        repository_root=root,
    )

    assert f"{family}_REGISTER_CHECKED_IN_BYTES_DRIFT" in report["missing_codes"]


@pytest.mark.parametrize(
    "window",
    [
        {"start": "x", "end": "x", "cutoff": "x", "timezone": "x"},
        {
            "start": "2026-08-27T00:00:00+08:00",
            "end": "2026-08-26T00:00:00+08:00",
            "cutoff": "2026-08-26T00:00:00+08:00",
            "timezone": "Asia/Hong_Kong",
        },
    ],
)
def test_observation_window_requires_exact_hong_kong_ordered_timestamps(
    tmp_path: Path, window: dict[str, str]
) -> None:
    """A loose timestamp or reversed observation range cannot be admitted."""
    manifest = _complete_shaped_gld_manifest()
    manifest["observation_window"] = window

    assert "OBSERVATION_WINDOW_MISSING" in _report(tmp_path, manifest)["missing_codes"]


def test_observation_window_rejects_non_hong_kong_offset_boundary_bypass(tmp_path: Path) -> None:
    """The declared Hong Kong timezone requires its exact UTC offset."""
    manifest = _complete_shaped_gld_manifest()
    manifest["observation_window"] = {
        "start": "2026-08-25T12:00:00-12:00",
        "end": "2026-08-26T11:00:00-12:00",
        "cutoff": "2026-08-26T12:00:00-12:00",
        "timezone": "Asia/Hong_Kong",
    }
    assert "OBSERVATION_WINDOW_MISSING" in _report(tmp_path, manifest)["missing_codes"]


def test_cookie_like_session_name_or_value_is_not_a_capability_reference(tmp_path: Path) -> None:
    """Session material is neither a name nor a type in the authority manifest."""
    manifest = _complete_shaped_gld_manifest()
    manifest["sessions"] = [{"name": "sessionid=SECRETCOOKIE", "type": "cookie=value"}]

    codes = _report(tmp_path, manifest)["missing_codes"]

    assert "CAPABILITY_REFERENCES_MALFORMED" in codes
    assert "SECRET_OR_SESSION_VALUE_FORBIDDEN" in codes


@pytest.mark.parametrize(
    ("field", "entry"),
    [
        ("credentials", {"name": "session_reference", "type": "SESSION_REFERENCE"}),
        ("sessions", {"name": "credential_reference", "type": "CREDENTIAL_REFERENCE"}),
    ],
)
def test_capability_references_cannot_cross_credential_session_kinds(
    tmp_path: Path, field: str, entry: dict[str, str]
) -> None:
    """Credential and session names are references, with separate closed type grammars."""
    baseline = _report(tmp_path, _complete_shaped_gld_manifest())
    assert "CAPABILITY_REFERENCES_MALFORMED" not in baseline["missing_codes"]
    manifest = _complete_shaped_gld_manifest()
    manifest[field] = [entry]

    assert "CAPABILITY_REFERENCES_MALFORMED" in _report(tmp_path, manifest)["missing_codes"]


def test_user_report_reference_cannot_be_reused_as_publisher_permission(tmp_path: Path) -> None:
    """A distinct user-report provenance never establishes publisher permission."""
    manifest = _complete_shaped_gld_manifest()
    permission = _object(cast("list[object]", manifest["publisher_permissions"])[0])
    permission["reference"] = _reference("user-report", provenance="USER_REPORTED")

    codes = _report(tmp_path, manifest)["missing_codes"]

    assert "PUBLISHER_PERMISSION_EVIDENCE_MALFORMED" in codes
    assert "PUBLISHER_PERMISSION_EVIDENCE_MISSING" in codes


def test_complete_shaped_cases_authority_cannot_invent_an_unregistered_endpoint(
    tmp_path: Path,
) -> None:
    """A detailed Cases manifest remains bound to its strict registered endpoints."""
    manifest = _complete_shaped_gld_manifest()
    permission_id = "pp_000000000000000000000000000000000000000000000002"
    endpoint = {
        "endpoint_id": "sep_000000000000000000000000000000000000000000000999",
        "host": "judiciary.example.invalid",
        "method": "GET",
        "path": "/judgments",
        "procedure_id": "sep_000000000000000000000000000000000000000000000999",
        "redirect_policy": "NO_REDIRECT",
    }
    permissions = cast("list[object]", manifest["publisher_permissions"])
    permissions.append(
        {
            "permission_id": permission_id,
            "source_ids": ["HK-CASE-JUDICIARY-LRS-INVENTORY"],
            "hosts": [endpoint["host"]],
            "procedure_ids": [endpoint["procedure_id"]],
            "reference": _reference("cases-permission"),
        }
    )
    selected = cast("list[object]", manifest["selected_sources"])
    selected.append(
        {
            "family": "CASES",
            "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
            "endpoints": [endpoint],
            "publisher_permission_id": permission_id,
        }
    )

    codes = _report(tmp_path, manifest)["missing_codes"]

    assert "CASES_ENDPOINT_CONTRACT_MISSING" not in codes
    assert "ENDPOINT_CONTRACT_UNREGISTERED" in codes


_FULL_PERIODIC_DUE_ROLES = (
    ("LEGISLATION", "HK-LEG-GLD-EGAZETTE"),
    ("LEGISLATION", "HK-LEG-HKEL-CURRENT-INVENTORY"),
    ("LEGISLATION", "HK-LEG-HKEL-EDITORIAL-RECORDS"),
    ("LEGISLATION", "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS"),
    ("LEGISLATION", "HK-LEG-BASIC-LAW-PORTAL"),
    ("CASES", "HK-CASE-HKLII-DISCOVERY"),
    ("CASES", "HK-CASE-JUDICIARY-LRS-INVENTORY"),
)


def test_due_membership_accepts_all_seven_roles_and_rejects_one_missing(tmp_path: Path) -> None:
    """Full-periodic source identity comparison is by role ID, not tuple shape."""
    manifest = _manifest()
    manifest["selected_sources"] = [
        {
            "family": family,
            "source_id": source_id,
            "endpoints": [],
            "publisher_permission_id": "pp_missing",
        }
        for family, source_id in _FULL_PERIODIC_DUE_ROLES
    ]
    full_codes = _report(tmp_path, manifest)["missing_codes"]
    assert "DUE_SOURCE_MEMBERSHIP_MISSING" not in full_codes
    manifest["selected_sources"] = cast("list[object]", manifest["selected_sources"])[:-1]
    missing_codes = _report(tmp_path, manifest)["missing_codes"]
    assert "DUE_SOURCE_MEMBERSHIP_MISSING" in missing_codes


@pytest.mark.parametrize(
    "source_id",
    ["HK-LEG-NPC-NATIONAL-LAWS-DATABASE", "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS"],
)
def test_preflight_rejects_dormant_npc_role_as_a_selected_v1_source(
    tmp_path: Path, source_id: str
) -> None:
    """Task 7 cannot accept an excluded NPC role or ask authority evidence for it."""
    manifest = _manifest()
    manifest["selected_sources"] = [
        {
            "family": "LEGISLATION",
            "source_id": source_id,
            "endpoints": [],
            "publisher_permission_id": "pp_missing",
        }
    ]
    manifest["publisher_permissions"] = [
        {
            "permission_id": "pp_000000000000000000000000000000000000000000000099",
            "source_ids": ["HK-LEG-GLD-EGAZETTE"],
            "hosts": [],
            "procedure_ids": [],
            "reference": _reference("unrelated-permission"),
        }
    ]

    codes = _report(tmp_path, manifest)["missing_codes"]

    assert "SELECTED_SOURCE_NOT_DUE" in codes
    assert "PUBLISHER_PERMISSION_EVIDENCE_MISSING" not in codes


def _manifest_list_entry(manifest: dict[str, object], key: str) -> dict[str, object]:
    return _object(cast("list[object]", manifest[key])[0])


def _unknown_matrix(manifest: dict[str, object]) -> None:
    _object(manifest["matrix"])["unknown"] = "x"


def _unknown_register(manifest: dict[str, object]) -> None:
    _manifest_list_entry(manifest, "registers")["unknown"] = "x"


def _unknown_permission(manifest: dict[str, object]) -> None:
    _manifest_list_entry(manifest, "publisher_permissions")["unknown"] = "x"


def _unknown_permission_reference(manifest: dict[str, object]) -> None:
    _object(_manifest_list_entry(manifest, "publisher_permissions")["reference"])["unknown"] = "x"


def _unknown_user_report(manifest: dict[str, object]) -> None:
    _manifest_list_entry(manifest, "user_reports")["unknown"] = "x"


def _unknown_terms(manifest: dict[str, object]) -> None:
    _manifest_list_entry(manifest, "terms")["unknown"] = "x"


def _unknown_window(manifest: dict[str, object]) -> None:
    _object(manifest["observation_window"])["unknown"] = "x"


def _unknown_capability(manifest: dict[str, object]) -> None:
    manifest["credentials"] = [
        {"name": "reference", "type": "CREDENTIAL_REFERENCE", "unknown": "x"}
    ]


def _unknown_selected_source(manifest: dict[str, object]) -> None:
    _manifest_list_entry(manifest, "selected_sources")["unknown"] = "x"


def _unknown_endpoint(manifest: dict[str, object]) -> None:
    source = _manifest_list_entry(manifest, "selected_sources")
    _object(cast("list[object]", source["endpoints"])[0])["unknown"] = "x"


_NESTED_UNKNOWN_MUTATIONS: tuple[tuple[Callable[[dict[str, object]], None], str], ...] = (
    (_unknown_matrix, "MATRIX_IDENTITY_MISMATCH"),
    (_unknown_register, "REGISTER_IDENTITIES_MALFORMED"),
    (_unknown_permission, "PUBLISHER_PERMISSION_EVIDENCE_MALFORMED"),
    (_unknown_permission_reference, "PUBLISHER_PERMISSION_EVIDENCE_MALFORMED"),
    (_unknown_user_report, "USER_REPORT_REFERENCES_MALFORMED"),
    (_unknown_terms, "TERMS_STATE_MALFORMED"),
    (_unknown_window, "OBSERVATION_WINDOW_MISSING"),
    (_unknown_capability, "CAPABILITY_REFERENCES_MALFORMED"),
    (_unknown_selected_source, "SELECTED_SOURCES_MALFORMED"),
    (_unknown_endpoint, "ENDPOINT_CONTRACT_MALFORMED"),
)


@pytest.mark.parametrize(("mutate", "expected"), _NESTED_UNKNOWN_MUTATIONS)
def test_nested_unknown_authority_fields_fail_closed(
    tmp_path: Path, mutate: Callable[[dict[str, object]], None], expected: str
) -> None:
    """Every nested authority object has a closed schema, not only the root manifest."""
    manifest = _complete_shaped_gld_manifest()
    mutate(manifest)

    codes = _report(tmp_path, manifest)["missing_codes"]

    assert expected in codes
