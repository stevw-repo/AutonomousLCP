"""Focused exact-input and atomic-write tests for the local admission assembler."""

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

import tools.hk_v1_assemble_admission as assembler
import tools.tests.test_hk_v1_admission_operational_evidence as operational_fixture
import tools.tests.test_hk_v1_live_admission as admission_fixture
from tools.hk_v1_assemble_admission import (
    AdmissionAssemblyError,
    AdmissionAssemblyInputs,
    assemble_hk_v1_admission,
)
from tools.hk_v1_live_admission import (
    EXPECTED_FAMILIES,
    EXPECTED_SCOPES,
    LocalRetainedEvidenceReader,
    evaluate_hk_v1_live_admission,
    load_hk_v1_live_admission_manifest,
)


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _serving_state() -> bytes:
    ledger = json.loads(admission_fixture._task8_approval_ledger())
    approval_id = next(iter(cast("dict[str, object]", ledger["approval_states"])))
    predecessor = "srv_" + "3" * 48
    state_id = "srv_" + "4" * 48
    fingerprint = "sha256:" + "9" * 64
    candidate = {
        "approval_id": approval_id,
        "candidate_serving_state_id": state_id,
        "candidate_serving_state_fingerprint": fingerprint,
        "coverage_fingerprint": "sha256:" + "1" * 64,
        "desired_inventory_fingerprint": "sha256:" + "2" * 64,
        "embedding_profile_fingerprint": "sha256:" + "3" * 64,
        "embedding_profile_id": "emp_" + "5" * 48,
        "execution_lineage_id": "lin_" + "7" * 48,
        "predecessor_state_id": predecessor,
        "target_name": "asklegal-v1-hk-local-20260908t120000",
    }
    receipt_material = canonicalize(
        checked_json_value(
            {
                "candidate_fingerprint": fingerprint,
                "operation": "ACTIVATED",
                "predecessor_state_id": predecessor,
                "state_id": state_id,
            }
        )
    )
    return canonicalize(
        checked_json_value(
            {
                "activation": {
                    "candidate": candidate,
                    "receipt_id": "ssr_" + sha256(receipt_material).hexdigest()[:48],
                },
                "active_state_id": state_id,
                "rollback": None,
                "schema_id": "asklegal.local-serving-state/v1",
            }
        )
    )


def _inputs(root: Path) -> AdmissionAssemblyInputs:
    matrix = files("asklegal_reporting").joinpath("hk_v1_coverage_matrix.json").read_bytes()
    return AdmissionAssemblyInputs(
        _write(root / "matrix.json", matrix),
        _write(root / "coverage.json", b'{"owner":"reporting"}'),
        _write(root / "semantic.json", b'{"owner":"processing"}'),
        _write(root / "serving.json", b'{"owner":"promotion"}'),
        _write(root / "approval.json", admission_fixture._task8_approval_ledger()),
        _write(root / "state.json", _serving_state()),
        root / "assembled",
    )


def _install_exact_parser_results(monkeypatch: pytest.MonkeyPatch) -> None:
    coverage = SimpleNamespace(
        observation_cutoff="2026-09-08T12:00:00+08:00",
        included_material_families=EXPECTED_FAMILIES,
        scope_ids=EXPECTED_SCOPES,
        fingerprint="sha256:" + "1" * 64,
    )
    semantic = SimpleNamespace(fingerprint="sha256:" + "2" * 64)
    embedding = SimpleNamespace(
        profile_fingerprint="sha256:" + "3" * 64,
        profile_id="emp_" + "5" * 48,
    )
    serving = SimpleNamespace(
        fingerprint="sha256:" + "8" * 64,
        embedding=embedding,
        dimensions=4,
        metric="cosine",
        namespace="synthetic-v1",
    )

    def load_coverage(_matrix: bytes, _report: bytes) -> object:
        return coverage

    def load_profiles(_semantic: bytes, _serving: bytes) -> tuple[object, object]:
        return semantic, serving

    monkeypatch.setattr(assembler, "_load_coverage", load_coverage)
    monkeypatch.setattr(assembler, "_load_profiles", load_profiles)


def test_assembler_atomically_writes_and_exactly_replays_supported_owner_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real Approval package/state lineage yields a canonical but incomplete A-G bundle."""
    _install_exact_parser_results(monkeypatch)
    inputs = _inputs(tmp_path)

    first = assemble_hk_v1_admission(inputs)
    second = assemble_hk_v1_admission(inputs)
    loaded = load_hk_v1_live_admission_manifest(inputs.output_root / "manifest.json")
    report = evaluate_hk_v1_live_admission(loaded, LocalRetainedEvidenceReader(inputs.output_root))

    assert first == second == loaded
    gate_c = next(gate for gate in first.gates if gate.gate == "C")
    assert gate_c.expected == gate_c.discovered == gate_c.verified == gate_c.terminal == 4
    assert report.result == "NOT_ADMITTED"
    assert report.admitted is False
    assert "GATE_B_EVIDENCE_INCOMPLETE" in report.blocker_codes
    assert "GATE_C_OWNING_PROOF_UNAVAILABLE" not in report.blocker_codes
    assert "GATE_E_OWNING_PROOF_UNAVAILABLE" not in report.blocker_codes
    assert not tuple(inputs.output_root.parent.glob(f".{inputs.output_root.name}.*.tmp"))


def test_retained_bundle_drift_is_rejected_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Restart replay never repairs or overwrites an altered retained envelope."""
    _install_exact_parser_results(monkeypatch)
    inputs = _inputs(tmp_path)
    assemble_hk_v1_admission(inputs)
    manifest = inputs.output_root / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    retained = manifest.read_bytes()

    with pytest.raises(AdmissionAssemblyError, match="HK_V1_ADMISSION_ASSEMBLY_INVALID"):
        assemble_hk_v1_admission(inputs)

    assert manifest.read_bytes() == retained


def test_approval_or_serving_state_drift_fails_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The assembler cannot select a different Approval than current Serving State names."""
    _install_exact_parser_results(monkeypatch)
    inputs = _inputs(tmp_path)
    state = json.loads(inputs.serving_state.read_bytes())
    state["activation"]["candidate"]["approval_id"] = "apr_" + "f" * 48
    inputs.serving_state.write_bytes(canonicalize(checked_json_value(state)))

    with pytest.raises(AdmissionAssemblyError, match="HK_V1_ADMISSION_ASSEMBLY_INVALID"):
        assemble_hk_v1_admission(inputs)

    assert not inputs.output_root.exists()


def test_closed_supported_registry_has_no_generic_verified_input() -> None:
    """Every currently emitted proof is exact owner bytes, never caller-provided verdict bytes."""
    assert set(assembler._supported_proofs.__annotations__) == {
        "matrix",
        "coverage",
        "semantic",
        "serving_profile",
        "approved",
        "ledger",
        "serving_state",
        "gate_f",
        "gate_g",
        "source_authority",
        "source_exercises",
        "live_release_accounting",
        "approval_invalidation",
        "promotion_readback",
        "promotion_failure_stop",
        "rollback_readback",
        "provider_admission",
        "return",
    }


def test_gate_d_uses_one_two_execution_provider_report_for_both_repeat_refs() -> None:
    """Gate D cannot substitute one semantic receipt and one retrieval receipt."""
    approved = assembler._ApprovalFacts(
        "sha256:" + "a" * 64,
        b"proposal",
        b"readiness",
        "sha256:" + "b" * 64,
    )
    proofs = assembler._supported_proofs(
        b"matrix",
        b"coverage",
        b"semantic-profile",
        b"serving-profile",
        approved,
        b"approval-ledger",
        b"serving-state",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        b"two-complete-provider-executions",
    )

    assert (
        proofs[("D", "MODEL_EVALUATION_RUN_1")]
        == proofs[("D", "MODEL_EVALUATION_RUN_2")]
        == b"two-complete-provider-executions"
    )


def test_exact_gate_f_composite_is_registered_for_every_f_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One closed F aggregate is reparsed for each required operational evidence kind."""
    _install_exact_parser_results(monkeypatch)
    inputs = _inputs(tmp_path)
    gate_f = _write(
        tmp_path / "gate-f.json",
        operational_fixture._gate_f("srv_" + "4" * 48),
    )
    inputs = replace(inputs, gate_f_operational=gate_f)

    evidence = assemble_hk_v1_admission(inputs)
    report = evaluate_hk_v1_live_admission(
        evidence, LocalRetainedEvidenceReader(inputs.output_root)
    )

    assert "GATE_F_EVIDENCE_INCOMPLETE" not in report.blocker_codes
    assert "GATE_F_OWNING_PROOF_UNAVAILABLE" not in report.blocker_codes
