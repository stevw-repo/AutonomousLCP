"""Fail-closed tests for the complete V1 POC admission verdict."""

import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

import tools.v1_poc_admission as admission
from tools.v1_poc_admission import (
    ADMISSION_POLICY_PATH,
    V1AdmissionCode,
    V1AdmissionReport,
    check_v1_admission,
    validate_v1_admission_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_STATIC_GATE_FAILED = "STATIC_GATE_FAILED"
_HOST_PYTHON = Path("/usr/bin/python3")
_WORKSPACE_REEXEC_MARKER = "ASKLEGAL_V1_ADMISSION_WORKSPACE_REEXEC"
_REEXEC_PROBE = (
    "import sys; from pathlib import Path; "
    "from tools.v1_poc_admission import _workspace_reexec; "
    "raise SystemExit(_workspace_reexec(Path(sys.argv[1])))"
)
_EXPECTED_CLI_OUTPUT = (
    b'{"admitted":false,"blockers":14,"components":14,"result":"NOT_ADMITTED",'
    b'"scope_authority":{"blocker_codes":["SOURCE_TECHNICAL_ADMISSION_MISSING",'
    b'"SOURCE_RIGHTS_ADMISSION_MISSING"],"matrix_fingerprint":'
    b'"sha256:f8ae5db8472d24969fd6bc7d7ac6329157258e45dd32452a1d283cb8820fd61e",'
    b'"matrix_revision":"HK-V1-003","result":"NOT_ADMITTED"},'
    b'"static_contracts_validated":8}\n'
)


def _policy() -> dict[str, object]:
    value: object = json.loads((REPOSITORY_ROOT / ADMISSION_POLICY_PATH).read_bytes())
    return _object_map(value)


def _object_map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _component(policy: dict[str, object], component_id: str) -> dict[str, object]:
    for raw_item in _object_list(policy["components"]):
        item = _object_map(raw_item)
        if item.get("component_id") == component_id:
            return item
    raise AssertionError(component_id)


def _codes(policy: dict[str, object]) -> set[V1AdmissionCode]:
    return {finding.code for finding in validate_v1_admission_policy(policy, REPOSITORY_ROOT)}


def test_composite_gate_reports_static_validation_without_v1_admission() -> None:
    """Expose one exact verdict that cannot confuse static proof with readiness."""
    assert check_v1_admission(REPOSITORY_ROOT) == V1AdmissionReport(
        components=14,
        static_contracts_validated=8,
        blockers=14,
        admitted=False,
    )


def test_v1_report_exposes_scope_authority_blockers() -> None:
    """Expose exact Gate A blockers without implying real V1 admission."""
    report = admission.build_v1_admission_report()
    gate = _object_map(report["scope_authority"])

    assert report["result"] == "NOT_ADMITTED"
    assert gate["result"] == "NOT_ADMITTED"
    assert gate["matrix_revision"] == "HK-V1-003"
    assert gate["matrix_fingerprint"] == (
        "sha256:f8ae5db8472d24969fd6bc7d7ac6329157258e45dd32452a1d283cb8820fd61e"
    )
    assert gate["blocker_codes"] == [
        "SOURCE_TECHNICAL_ADMISSION_MISSING",
        "SOURCE_RIGHTS_ADMISSION_MISSING",
    ]


def test_documented_host_python_cli_emits_the_exact_gate_a_report() -> None:
    """The repository-root system-Python command must preserve the exact CLI bytes."""
    result = subprocess.run(  # noqa: S603
        [str(_HOST_PYTHON), "-m", "tools.v1_poc_admission"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == _EXPECTED_CLI_OUTPUT
    assert result.stderr == b""


def test_documented_host_python_cli_ignores_a_shadow_reporting_package(tmp_path: Path) -> None:
    """Ambient PYTHONPATH must not choose Gate A code for the workspace child."""
    shadow_root = tmp_path / "shadow"
    shadow_package = shadow_root / "asklegal_reporting"
    shadow_package.mkdir(parents=True)
    (shadow_package / "__init__.py").write_text(
        "raise RuntimeError('SHADOW_REPORTING_PACKAGE_IMPORTED')\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(shadow_root)

    result = subprocess.run(  # noqa: S603
        [str(_HOST_PYTHON), "-m", "tools.v1_poc_admission"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == _EXPECTED_CLI_OUTPUT
    assert result.stderr == b""


def test_documented_host_python_cli_does_not_pass_pythonhome_to_workspace_child() -> None:
    """The pinned workspace interpreter must not inherit the host Python home."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONHOME"] = "/usr"

    result = subprocess.run(  # noqa: S603
        [str(_HOST_PYTHON), "-m", "tools.v1_poc_admission"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == _EXPECTED_CLI_OUTPUT
    assert result.stderr == b""


def test_host_python_can_import_dev_test_before_workspace_bootstrap() -> None:
    """The shipping entrypoint must stay importable before it prepares the workspace."""
    result = subprocess.run(  # noqa: S603
        [str(_HOST_PYTHON), "-c", "import tools.dev_test"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b""
    assert result.stderr == b""


def test_host_python_cli_reexec_marker_fails_instead_of_recursing() -> None:
    """A failed workspace handoff must stop visibly instead of spawning again."""
    environment = os.environ.copy()
    environment[_WORKSPACE_REEXEC_MARKER] = "1"

    result = subprocess.run(  # noqa: S603
        [str(_HOST_PYTHON), "-m", "tools.v1_poc_admission"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"FAIL WORKSPACE_PYTHON_REEXEC_FAILED\n"


def test_workspace_reexec_sanitizes_python_import_environment(
    tmp_path: Path,
) -> None:
    """The child must receive no ambient path/home and must disable user-site imports."""
    workspace_python = tmp_path / ".venv/bin/python"
    workspace_python.parent.mkdir(parents=True)
    workspace_python.write_text(
        "#!/bin/sh\n"
        "{\n"
        "  printf 'PYTHONPATH=%s\\n' \"${PYTHONPATH-unset}\"\n"
        "  printf 'PYTHONHOME=%s\\n' \"${PYTHONHOME-unset}\"\n"
        "  printf 'PYTHONUSERBASE=%s\\n' \"${PYTHONUSERBASE-unset}\"\n"
        "  printf 'PYTHONNOUSERSITE=%s\\n' \"${PYTHONNOUSERSITE-unset}\"\n"
        '} > "$ASKLEGAL_TEST_ENV_CAPTURE"\n',
        encoding="utf-8",
    )
    workspace_python.chmod(0o700)
    capture_path = tmp_path / "child-environment.txt"
    environment = os.environ.copy()
    environment["ASKLEGAL_TEST_ENV_CAPTURE"] = str(capture_path)
    environment["PYTHONPATH"] = str(tmp_path / "shadow")
    environment["PYTHONHOME"] = "/usr"
    environment["PYTHONUSERBASE"] = str(tmp_path / "user-base")
    environment.pop("PYTHONNOUSERSITE", None)

    result = subprocess.run(  # noqa: S603
        [str(_HOST_PYTHON), "-c", _REEXEC_PROBE, str(tmp_path)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert capture_path.read_text(encoding="utf-8") == (
        "PYTHONPATH=unset\nPYTHONHOME=unset\nPYTHONUSERBASE=unset\nPYTHONNOUSERSITE=1\n"
    )


def test_workspace_reexec_missing_interpreter_fails_closed(tmp_path: Path) -> None:
    """An absent pinned child must emit only the closed handoff failure."""
    result = subprocess.run(  # noqa: S603
        [str(_HOST_PYTHON), "-c", _REEXEC_PROBE, str(tmp_path)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"FAIL WORKSPACE_PYTHON_REEXEC_FAILED\n"


def test_workspace_reexec_spawn_failure_fails_closed(tmp_path: Path) -> None:
    """An OS-level spawn failure must not escape as a traceback."""
    workspace_python = tmp_path / ".venv/bin/python"
    workspace_python.parent.mkdir(parents=True)
    workspace_python.write_text("not an executable image\n", encoding="utf-8")
    workspace_python.chmod(0o700)

    result = subprocess.run(  # noqa: S603
        [str(_HOST_PYTHON), "-c", _REEXEC_PROBE, str(tmp_path)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"FAIL WORKSPACE_PYTHON_REEXEC_FAILED\n"


def test_workspace_reexec_propagates_started_child_failure(tmp_path: Path) -> None:
    """Once spawned, the child's exact non-zero status and diagnostic remain authoritative."""
    workspace_python = tmp_path / ".venv/bin/python"
    workspace_python.parent.mkdir(parents=True)
    workspace_python.write_text(
        "#!/bin/sh\nprintf 'child failure\\n' >&2\nexit 23\n",
        encoding="utf-8",
    )
    workspace_python.chmod(0o700)

    result = subprocess.run(  # noqa: S603
        [str(_HOST_PYTHON), "-c", _REEXEC_PROBE, str(tmp_path)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )

    assert result.returncode == 23
    assert result.stdout == b""
    assert result.stderr == b"child failure\n"


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("ready", True, V1AdmissionCode.ADMISSION),
        ("admission_statement", "V1_POC_ADMITTED", V1AdmissionCode.ADMISSION),
        ("status", "READY", V1AdmissionCode.INVENTORY),
    ],
)
def test_document_admission_or_status_drift_fails_closed(
    field: str, value: object, expected: V1AdmissionCode
) -> None:
    """Reject an invented admission statement or a changed document state."""
    policy = deepcopy(_policy())
    policy[field] = value
    assert expected in _codes(policy)


def test_authority_expansion_fails_closed() -> None:
    """Keep host, image, credential, service, and external authority false."""
    policy = deepcopy(_policy())
    authority = _object_map(policy["authority"])
    authority["image_pull_authorized"] = True
    assert V1AdmissionCode.AUTHORITY in _codes(policy)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("state", "ADMITTED"),
        ("admission_blocker", "NONE"),
        ("evidence", "NOT_CREATED"),
    ],
)
def test_component_state_blocker_or_evidence_drift_fails_closed(field: str, value: object) -> None:
    """Require the exact ordered component inventory and evidence binding."""
    policy = deepcopy(_policy())
    _component(policy, "STATIC_TOPOLOGY")[field] = value
    assert V1AdmissionCode.COMPONENT in _codes(policy)


def test_missing_evidence_file_fails_closed() -> None:
    """Do not count a static contract whose declared evidence is absent."""
    policy = deepcopy(_policy())
    component = _component(policy, "STATIC_TOPOLOGY")
    component["evidence"] = "tools/does_not_exist.py"
    codes = _codes(policy)
    assert V1AdmissionCode.COMPONENT in codes
    assert V1AdmissionCode.EVIDENCE in codes


def test_missing_or_reordered_component_fails_closed() -> None:
    """Require all fourteen admission components in their frozen order."""
    policy = deepcopy(_policy())
    components = _object_list(policy["components"])
    components[0], components[1] = components[1], components[0]
    assert V1AdmissionCode.COMPONENT in _codes(policy)


def test_secret_bearing_addition_fails_closed() -> None:
    """Keep the aggregate admission contract free of secret material."""
    policy = deepcopy(_policy())
    policy["api_key"] = "sk-forbidden"
    assert V1AdmissionCode.SECRET in _codes(policy)


def test_composite_check_propagates_a_static_gate_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Propagate a static-gate failure instead of reporting aggregate success."""

    def _fail(_root: Path) -> None:
        raise ValueError(_STATIC_GATE_FAILED)

    monkeypatch.setattr(admission, "check_topology", _fail)
    with pytest.raises(ValueError, match="STATIC_GATE_FAILED"):
        check_v1_admission(REPOSITORY_ROOT)
