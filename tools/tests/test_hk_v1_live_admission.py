"""Fail-closed tests for the two-family Hong Kong V1 live admission gate."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.hk_v1_live_admission as admission_module
from tools.hk_v1_live_admission import (
    EXPECTED_FAMILIES,
    EXPECTED_SCOPES,
    GateEvidence,
    GateName,
    GateState,
    HKV1AdmissionEvidence,
    LocalRetainedEvidenceReader,
    RetainedEvidenceRef,
    canonical_report_bytes,
    evaluate_hk_v1_live_admission,
    load_hk_v1_live_admission_manifest,
    main,
)

_FINGERPRINT = "sha256:" + "a" * 64
_PROMOTION_ID = "pmn_" + "1" * 48
_REVIEWER_SUBJECT = "act_" + "5" * 48

_REQUIRED_KINDS: dict[GateName, tuple[str, ...]] = {
    "A": ("COVERAGE_MATRIX", "SOURCE_AUTHORITY"),
    "B": (
        "SOURCE_COMPLETENESS",
        "SOURCE_CONTRACT_DRIFT",
        "SOURCE_INCOMPLETE",
        "SOURCE_NO_CHANGE",
        "SOURCE_RESTART",
        "SOURCE_RETRY",
    ),
    "C": ("PACKAGE_READINESS", "RELEASE_ACCOUNTING"),
    "D": (
        "EMBEDDING_PROFILE",
        "MODEL_EVALUATION_RUN_1",
        "MODEL_EVALUATION_RUN_2",
        "MODEL_PROFILE",
        "TOKENIZER_PROFILE",
    ),
    "E": (
        "APPROVAL",
        "APPROVAL_INVALIDATION",
        "BACKUP",
        "PROMOTION",
        "PROMOTION_FAILURE_STOP",
        "READ_BACK",
        "REPLACEMENT_TARGET",
        "REVIEW",
        "ROLLBACK",
    ),
    "F": ("OBSERVABILITY", "RECOVERY", "RESTART", "SCHEDULE", "SUPERVISION"),
    "G": (
        "APPROVAL",
        "BACKUP",
        "BASELINE",
        "CHANGED_CYCLE",
        "NEXT_CYCLE_HEALTH",
        "NO_CHANGE_CYCLE",
        "PROMOTION",
        "READ_BACK",
        "REBOOT",
        "REPLACEMENT_TARGET",
        "RESTORATION",
        "ROLLBACK",
    ),
}

_OWNERS = admission_module._OWNER_BY_GATE_KIND  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_gate_g_aggregate_provenance_names_its_actual_evidence_tool() -> None:
    """Aggregate Gate-G proof bytes name their assembler-independent evidence owner."""
    for kind in admission_module._REQUIRED_EVIDENCE["G"]:  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        expected = "REVIEW_API" if kind == "APPROVAL" else "OPERATIONAL_EVIDENCE_TOOL"
        assert _OWNERS[("G", kind)] == expected


def _canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _proposal_bytes() -> bytes:
    body = {
        "acquisition_manifests": [],
        "completeness_fingerprint": "sha256:" + "4" * 64,
        "coverage_report_fingerprint": "sha256:" + "1" * 64,
        "embedding_capability_evidence_ref": "embedding/evidence.json",
        "embedding_invocation_count": 0,
        "embedding_profile_fingerprint": "sha256:" + "3" * 64,
        "explicit_exclusions": ["HKEX_REGULATORY_POST_V1", "HK-PRINCIPLES"],
        "included_material_families": list(EXPECTED_FAMILIES),
        "model_capability_evidence_ref": "model/evidence.json",
        "model_invocation_count": 0,
        "model_profile_fingerprint": "sha256:" + "2" * 64,
        "observation_cutoff": "2026-09-08T12:00:00+08:00",
        "prepared_batches": [],
        "release_state": "WITHHELD_PENDING_NAMED_HUMAN_REVIEW",
        "schema_id": "asklegal.hk-v1-two-family-proposal-manifest/v1",
        "scope_ids": list(EXPECTED_SCOPES),
        "status": "FROZEN_PROPOSAL_READY_FOR_REVIEW",
    }
    fingerprint = "sha256:" + sha256(_canonical(body)).hexdigest()
    return _canonical({**body, "fingerprint": fingerprint})


_PROPOSAL_BYTES = _proposal_bytes()
_PROPOSAL_FINGERPRINT = str(json.loads(_PROPOSAL_BYTES)["fingerprint"])


def _readiness_bytes() -> bytes:
    members = [
        {
            "material_family": "CASES" if index == 1 else "LEGISLATION",
            "record_id": f"record-{index}",
            "scope_id": scope,
        }
        for index, scope in enumerate(EXPECTED_SCOPES, start=1)
    ]
    body = {
        "backup_profile_fingerprint": "sha256:" + "3" * 64,
        "embedding_profile_fingerprint": "sha256:" + "3" * 64,
        "limitations": ["HKEX remains outside V1."],
        "model_evaluation_ref": "evaluation/model.json",
        "model_profile_fingerprint": "sha256:" + "2" * 64,
        "native_backup_ref": "backup/native.json",
        "proposal_fingerprint": _PROPOSAL_FINGERPRINT,
        "recovery_backup_ref": "backup/recovery.json",
        "retrieval_evaluation_ref": "evaluation/retrieval.json",
        "retryable_count": 0,
        "rollback_state_id": "srv_" + "8" * 48,
        "scope_dispositions": [
            {"result": "COMPLETE", "retryable_count": 0, "scope_id": scope}
            for scope in EXPECTED_SCOPES
        ],
        "serving_profile_fingerprint": "sha256:" + "8" * 64,
        "target_members": members,
        "target_name": "asklegal-v1-hk-local-20260908t120000",
        "target_namespace": "synthetic-v1",
        "zero_record_scope_ids": [],
    }
    fingerprint = "sha256:" + sha256(_canonical(body)).hexdigest()
    return _canonical(
        {**body, "fingerprint": fingerprint, "schema_id": "asklegal.hk-v1-review-readiness/v1"}
    )


_READINESS_BYTES = _readiness_bytes()
_READINESS_FINGERPRINT = str(json.loads(_READINESS_BYTES)["fingerprint"])


def _approval_decision_bytes(*, decision: str = "APPROVED") -> bytes:
    approval_id = (
        "apr_"
        + sha256(f"{_PROMOTION_ID}\x1f{_PROPOSAL_FINGERPRINT}\x1f{decision}".encode()).hexdigest()[
            :48
        ]
    )
    document = {
        "approval_id": approval_id,
        "authority_evidence_ref": {
            "fingerprint": "sha256:" + "2" * 64,
            "ref_id": "evi_" + "2" * 48,
            "ref_type": "EVIDENCE",
        },
        "decision": decision,
        "decision_time": "2026-09-08T12:00:00+08:00",
        "expected_base_serving_state_ref": {
            "fingerprint": "sha256:" + "3" * 64,
            "ref_id": "srv_" + "3" * 48,
            "ref_type": "SERVING_STATE",
        },
        "governance_policy_state": "CONFIGURED",
        "immutable": True,
        "promotion_manifest_ref": {
            "fingerprint": _PROPOSAL_FINGERPRINT,
            "ref_id": _PROMOTION_ID,
            "ref_type": "PROMOTION_MANIFEST",
        },
        "reason": "Named human approved exact local proposal",
        "reviewer_identity_ref": {
            "fingerprint": "sha256:" + "5" * 64,
            "ref_id": "act_" + "5" * 48,
            "ref_type": "ACTOR",
        },
        "schema_id": "asklegal.approval-decision",
        "schema_version": "1.1.0",
        "valid_from": "2026-09-08T11:59:00+08:00",
        "validity_condition_refs": [
            {
                "contract_id": "HK_V1_TWO_FAMILY_PROPOSAL",
                "fingerprint": _PROPOSAL_FINGERPRINT,
                "version": "1.0.0",
            },
            {
                "contract_id": "HK_V1_REVIEW_READINESS",
                "fingerprint": _READINESS_FINGERPRINT,
                "version": "1.0.0",
            },
        ],
    }
    if decision == "APPROVED":
        document["review_readiness_fingerprint"] = _READINESS_FINGERPRINT
    return _canonical(document)


def _approval_fingerprint() -> str:
    return "sha256:" + sha256(_approval_decision_bytes()).hexdigest()


def _ref(gate: GateName, kind: str, subject: str) -> RetainedEvidenceRef:
    return RetainedEvidenceRef(
        evidence_id=f"{gate}-{kind.lower().replace('_', '-')}",
        evidence_kind=kind,
        immutable_ref=f"local-evidence://envelopes/{gate}/{kind.lower()}.json",
        fingerprint="sha256:" + "0" * 64,
        subject_fingerprint=subject,
    )


def _gate(gate: GateName, *, expected: int = 1) -> GateEvidence:
    subject = "sha256:" + sha256(f"subject:{gate}".encode()).hexdigest()
    if gate == "A":
        subject = _FINGERPRINT
    elif gate in {"E", "G"}:
        subject = _PROPOSAL_FINGERPRINT
    if gate in {"A", "C"}:
        expected = 4
    return GateEvidence(
        gate=gate,
        subject_fingerprint=subject,
        families=EXPECTED_FAMILIES,
        scopes=EXPECTED_SCOPES,
        expected=expected,
        discovered=expected,
        verified=expected,
        retryable=0,
        rejected=0,
        terminal=expected,
        evidence_refs=tuple(_ref(gate, kind, subject) for kind in _REQUIRED_KINDS[gate]),
    )


def _complete() -> HKV1AdmissionEvidence:
    return HKV1AdmissionEvidence(
        gates=tuple(_gate(gate) for gate in ("A", "B", "C", "D", "E", "F", "G")),
        common_cutoff="2026-09-08T12:00:00+08:00",
        coverage_matrix_fingerprint=_FINGERPRINT,
        proposal_fingerprint=_PROPOSAL_FINGERPRINT,
        model_profile_fingerprint="sha256:" + "2" * 64,
        embedding_profile_fingerprint="sha256:" + "3" * 64,
        serving_profile_fingerprint="sha256:" + "8" * 64,
        approval_fingerprint=_approval_fingerprint(),
        serving_state_id="srv_" + "3" * 48,
        target_name="asklegal-v1-hk-local-20260908t120000",
        target_fingerprint="sha256:" + "d" * 64,
    )


def _path(root: Path, reference: str) -> Path:
    return root / reference.removeprefix("local-evidence://")


def _task8_approval_ledger(
    *, state: str = "APPROVAL_CONSUMED", decision_value: str = "APPROVED"
) -> bytes:
    decision = _approval_decision_bytes(decision=decision_value)
    approval_id = json.loads(decision)["approval_id"]
    lineage = "lin_" + "7" * 48 if state == "APPROVAL_CONSUMED" else ""
    command = _canonical(
        {
            "action": "RECORD_PROPOSAL_DECISION",
            "approval_id": approval_id,
            "decision_fingerprint": "sha256:" + sha256(decision).hexdigest(),
            "expected_review_version": 0,
            "proposal_package_id": _PROMOTION_ID,
            "reviewer_subject": _REVIEWER_SUBJECT,
        }
    )
    return _canonical(
        {
            "approval_states": (
                {approval_id: {"lineage": lineage, "state": state}}
                if decision_value == "APPROVED"
                else {}
            ),
            "events": [
                {
                    "command_bytes": command.hex(),
                    "command_id": "cmd_" + "8" * 48,
                    "event_bytes": decision.hex(),
                    "proposal_bytes": (
                        _PROPOSAL_BYTES.hex() if decision_value == "APPROVED" else None
                    ),
                    "readiness_bytes": (
                        _READINESS_BYTES.hex() if decision_value == "APPROVED" else None
                    ),
                    "target_id": _PROMOTION_ID,
                    "winner_key": "proposal-decision:" + _PROMOTION_ID,
                }
            ],
            "revoked": (
                [approval_id]
                if decision_value == "APPROVED" and state == "APPROVAL_REVOKED"
                else []
            ),
            "schema_id": "asklegal.local-review-approval-ledger/v1",
        }
    )


def _historical_rejection_event() -> dict[str, object]:
    historical = dict(json.loads(_task8_approval_ledger(decision_value="REJECTED"))["events"][0])
    historical_id = "pmn_" + "9" * 48
    decision = json.loads(bytes.fromhex(str(historical["event_bytes"])))
    decision["promotion_manifest_ref"]["ref_id"] = historical_id
    approval_id = (
        "apr_"
        + sha256(f"{historical_id}\x1f{_PROPOSAL_FINGERPRINT}\x1fREJECTED".encode()).hexdigest()[
            :48
        ]
    )
    decision["approval_id"] = approval_id
    decision_bytes = _canonical(decision)
    command = json.loads(bytes.fromhex(str(historical["command_bytes"])))
    command["approval_id"] = approval_id
    command["decision_fingerprint"] = "sha256:" + sha256(decision_bytes).hexdigest()
    command["proposal_package_id"] = historical_id
    historical.update(
        {
            "command_bytes": _canonical(command).hex(),
            "command_id": "cmd_" + "9" * 48,
            "event_bytes": decision_bytes.hex(),
            "target_id": historical_id,
            "winner_key": "proposal-decision:" + historical_id,
        }
    )
    return historical


def _gate_proof(
    gate: GateEvidence, reference: RetainedEvidenceRef, evidence: HKV1AdmissionEvidence
) -> bytes:
    if reference.evidence_kind == "APPROVAL":
        return _task8_approval_ledger()
    return _canonical(
        {
            "approval_fingerprint": evidence.approval_fingerprint,
            "common_cutoff": evidence.common_cutoff,
            "coverage_matrix_fingerprint": evidence.coverage_matrix_fingerprint,
            "embedding_profile_fingerprint": evidence.embedding_profile_fingerprint,
            "evidence_id": reference.evidence_id,
            "evidence_kind": reference.evidence_kind,
            "gate": gate.gate,
            "model_profile_fingerprint": evidence.model_profile_fingerprint,
            "owner": _OWNERS[(gate.gate, reference.evidence_kind)],
            "proposal_fingerprint": evidence.proposal_fingerprint,
            "result": "VERIFIED",
            "schema_id": (
                f"asklegal.hk-v1-gate-proof/{gate.gate}/{reference.evidence_kind.lower()}/v1"
            ),
            "schema_version": 1,
            "serving_profile_fingerprint": evidence.serving_profile_fingerprint,
            "serving_state_id": evidence.serving_state_id,
            "subject_fingerprint": reference.subject_fingerprint,
            "target_fingerprint": evidence.target_fingerprint,
            "target_name": evidence.target_name,
        }
    )


def _producer_receipt(
    gate: GateEvidence,
    reference: RetainedEvidenceRef,
    evidence: HKV1AdmissionEvidence,
    proof_ref: str,
    proof_bytes: bytes,
) -> bytes:
    return _canonical(
        {
            "approval_fingerprint": evidence.approval_fingerprint,
            "common_cutoff": evidence.common_cutoff,
            "coverage_matrix_fingerprint": evidence.coverage_matrix_fingerprint,
            "embedding_profile_fingerprint": evidence.embedding_profile_fingerprint,
            "evidence_id": reference.evidence_id,
            "evidence_kind": reference.evidence_kind,
            "model_profile_fingerprint": evidence.model_profile_fingerprint,
            "gate": gate.gate,
            "producer": "ADMISSION_ASSEMBLER",
            "proof_fingerprint": "sha256:" + sha256(proof_bytes).hexdigest(),
            "proof_owner": _OWNERS[(gate.gate, reference.evidence_kind)],
            "proof_ref": proof_ref,
            "proposal_fingerprint": evidence.proposal_fingerprint,
            "result": "VERIFIED",
            "schema_id": "asklegal.hk-v1-retained-producer-evidence",
            "schema_version": 1,
            "serving_profile_fingerprint": evidence.serving_profile_fingerprint,
            "serving_state_id": evidence.serving_state_id,
            "subject_fingerprint": reference.subject_fingerprint,
            "target_fingerprint": evidence.target_fingerprint,
            "target_name": evidence.target_name,
        }
    )


def _envelope(
    reference: RetainedEvidenceRef,
    evidence: HKV1AdmissionEvidence,
    producer_ref: str,
    producer_bytes: bytes,
) -> bytes:
    return _canonical(
        {
            "approval_fingerprint": evidence.approval_fingerprint,
            "common_cutoff": evidence.common_cutoff,
            "coverage_matrix_fingerprint": evidence.coverage_matrix_fingerprint,
            "embedding_profile_fingerprint": evidence.embedding_profile_fingerprint,
            "evidence_id": reference.evidence_id,
            "evidence_kind": reference.evidence_kind,
            "immutable_ref": reference.immutable_ref,
            "model_profile_fingerprint": evidence.model_profile_fingerprint,
            "producer_evidence_fingerprint": "sha256:" + sha256(producer_bytes).hexdigest(),
            "producer_evidence_ref": producer_ref,
            "proposal_fingerprint": evidence.proposal_fingerprint,
            "schema_version": 1,
            "serving_profile_fingerprint": evidence.serving_profile_fingerprint,
            "serving_state_id": evidence.serving_state_id,
            "subject_fingerprint": reference.subject_fingerprint,
            "target_fingerprint": evidence.target_fingerprint,
            "target_name": evidence.target_name,
        }
    )


def _materialize(
    evidence: HKV1AdmissionEvidence, root: Path
) -> tuple[HKV1AdmissionEvidence, LocalRetainedEvidenceReader]:
    root.mkdir(parents=True, exist_ok=True)
    gates: list[GateEvidence] = []
    for gate in evidence.gates:
        references: list[RetainedEvidenceRef] = []
        for reference in gate.evidence_refs:
            proof_ref = (
                f"local-evidence://proofs/{gate.gate}/{reference.evidence_kind.lower()}.json"
            )
            proof_bytes = _gate_proof(gate, reference, evidence)
            proof_path = _path(root, proof_ref)
            proof_path.parent.mkdir(parents=True, exist_ok=True)
            proof_path.write_bytes(proof_bytes)
            producer_ref = (
                f"local-evidence://producer/{gate.gate}/{reference.evidence_kind.lower()}.json"
            )
            producer_bytes = _producer_receipt(gate, reference, evidence, proof_ref, proof_bytes)
            producer_path = _path(root, producer_ref)
            producer_path.parent.mkdir(parents=True, exist_ok=True)
            producer_path.write_bytes(producer_bytes)
            envelope = _envelope(reference, evidence, producer_ref, producer_bytes)
            envelope_path = _path(root, reference.immutable_ref)
            envelope_path.parent.mkdir(parents=True, exist_ok=True)
            envelope_path.write_bytes(envelope)
            references.append(
                replace(reference, fingerprint="sha256:" + sha256(envelope).hexdigest())
            )
        gates.append(replace(gate, evidence_refs=tuple(references)))
    return replace(evidence, gates=tuple(gates)), LocalRetainedEvidenceReader(root)


def _replace_gate(
    evidence: HKV1AdmissionEvidence, gate_name: GateName, gate: GateEvidence | None
) -> HKV1AdmissionEvidence:
    gates = tuple(
        replacement
        for item in evidence.gates
        for replacement in (
            ()
            if item.gate == gate_name and gate is None
            else (gate if item.gate == gate_name else item,)
        )
    )
    return replace(evidence, gates=gates)


def _replace_proof(
    evidence: HKV1AdmissionEvidence,
    root: Path,
    *,
    gate_index: int,
    reference_index: int,
    proof_bytes: bytes,
) -> HKV1AdmissionEvidence:
    gate = evidence.gates[gate_index]
    reference = gate.evidence_refs[reference_index]
    producer_path = root / "producer" / gate.gate / f"{reference.evidence_kind.lower()}.json"
    producer = json.loads(producer_path.read_bytes())
    proof_path = root / "proofs" / gate.gate / f"{reference.evidence_kind.lower()}.json"
    proof_path.write_bytes(proof_bytes)
    producer["proof_fingerprint"] = "sha256:" + sha256(proof_bytes).hexdigest()
    producer_bytes = _canonical(producer)
    producer_path.write_bytes(producer_bytes)
    envelope_path = _path(root, reference.immutable_ref)
    envelope = json.loads(envelope_path.read_bytes())
    envelope["producer_evidence_fingerprint"] = "sha256:" + sha256(producer_bytes).hexdigest()
    envelope_bytes = _canonical(envelope)
    envelope_path.write_bytes(envelope_bytes)
    altered_ref = replace(reference, fingerprint="sha256:" + sha256(envelope_bytes).hexdigest())
    altered_gate = replace(
        gate,
        evidence_refs=tuple(
            altered_ref if index == reference_index else item
            for index, item in enumerate(gate.evidence_refs)
        ),
    )
    return _replace_gate(evidence, gate.gate, altered_gate)


def _manifest_bytes(evidence: HKV1AdmissionEvidence) -> bytes:
    return _canonical(
        {
            **evidence.document(),
            "schema_id": "asklegal.hk-v1-live-admission-manifest",
            "schema_version": 1,
        }
    )


def test_complete_generic_envelopes_remain_not_admitted_and_canonical(tmp_path: Path) -> None:
    """Exact envelopes cannot replace Task 10 artifacts that do not exist yet."""
    evidence, reader = _materialize(_complete(), tmp_path)

    first = evaluate_hk_v1_live_admission(evidence, reader)
    second = evaluate_hk_v1_live_admission(evidence, reader)

    assert first.admitted is False
    assert first.result == "NOT_ADMITTED"
    assert "GATE_G_OWNING_PROOF_UNAVAILABLE" in first.blocker_codes
    assert tuple(item.state for item in first.gate_results) == (GateState.INVALID,) * 7
    assert first.evidence_fingerprint.startswith("sha256:")
    assert canonical_report_bytes(first) == canonical_report_bytes(second)


@pytest.mark.parametrize("missing_gate", ["A", "B", "C", "D", "E", "F", "G"])
def test_missing_gate_can_never_report_v1_admitted(missing_gate: GateName, tmp_path: Path) -> None:
    """Every named gate is mandatory."""
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_gate(evidence, missing_gate, None)

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert report.result == "NOT_ADMITTED"
    assert f"GATE_{missing_gate}_MISSING" in report.blocker_codes


@pytest.mark.parametrize("family", ["REGULATORY", "HKEX"])
def test_hkex_or_regulatory_membership_is_rejected(family: str, tmp_path: Path) -> None:
    """The superseded HKEX family cannot re-enter V1 arithmetic."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = evidence.gates[0]
    altered = replace(gate, families=(*gate.families, family))

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, "A", altered), reader)

    assert report.admitted is False
    assert "GATE_A_FAMILY_UNIVERSE_INVALID" in report.blocker_codes


def test_all_four_scopes_are_required_without_hkex_scopes(tmp_path: Path) -> None:
    """The only accepted scope universe is one Cases plus three Legislation scopes."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = evidence.gates[2]
    altered = replace(
        gate, scopes=gate.scopes[:-1], expected=3, discovered=3, verified=3, terminal=3
    )

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, "C", altered), reader)

    assert report.admitted is False
    assert "GATE_C_SCOPE_UNIVERSE_INVALID" in report.blocker_codes
    assert "GATE_C_EXPECTED_COUNT_INVALID" in report.blocker_codes


@pytest.mark.parametrize(
    ("changes", "state", "blocker"),
    [
        (
            {"verified": 0, "retryable": 1, "terminal": 0},
            GateState.INVALID,
            "GATE_G_RETRYABLE_WORK",
        ),
        ({"verified": 0, "rejected": 1}, GateState.INVALID, "GATE_G_REJECTED_WORK"),
        ({"discovered": 0, "verified": 0, "terminal": 0}, GateState.INVALID, "GATE_G_WORK_MISSING"),
    ],
)
def test_retryable_rejected_or_missing_gate_g_work_never_passes(
    changes: dict[str, int], state: GateState, blocker: str, tmp_path: Path
) -> None:
    """Gate G exposes unfinished work without converting it to completion."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = replace(evidence.gates[-1], **changes)

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, "G", gate), reader)

    assert report.admitted is False
    assert report.gate_results[-1].state is state
    assert blocker in report.blocker_codes


def test_inconsistent_work_arithmetic_is_invalid_not_retryable(tmp_path: Path) -> None:
    """Contradictory accounting is invalid evidence, not a benign retry."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = replace(evidence.gates[1], verified=0, retryable=1, terminal=1)

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, "B", gate), reader)

    assert report.admitted is False
    assert report.gate_results[1].state is GateState.INVALID
    assert "GATE_B_WORK_ARITHMETIC_INVALID" in report.blocker_codes


@pytest.mark.parametrize("gate_index", range(7))
def test_every_gate_requires_its_exact_retained_evidence_kinds(
    gate_index: int, tmp_path: Path
) -> None:
    """A success flag cannot replace any required retained proof kind."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = evidence.gates[gate_index]
    altered = replace(gate, evidence_refs=gate.evidence_refs[:-1])

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, gate.gate, altered), reader)

    assert report.admitted is False
    assert f"GATE_{gate.gate}_EVIDENCE_INCOMPLETE" in report.blocker_codes


def test_evidence_ref_must_be_immutable_unique_and_subject_bound(tmp_path: Path) -> None:
    """Retained proof references must be unique and bound to their gate subject."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = evidence.gates[4]
    wrong = replace(gate.evidence_refs[0], subject_fingerprint="sha256:" + "e" * 64)
    duplicate = replace(gate.evidence_refs[1], immutable_ref=wrong.immutable_ref)
    altered = replace(gate, evidence_refs=(wrong, duplicate, *gate.evidence_refs[2:]))

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, "E", altered), reader)

    assert report.admitted is False
    assert "GATE_E_EVIDENCE_BINDING_INVALID" in report.blocker_codes
    assert "GATE_E_EVIDENCE_REF_DUPLICATE" in report.blocker_codes


def test_cross_gate_coverage_binding_and_current_serving_identity_are_required(
    tmp_path: Path,
) -> None:
    """The admission verdict retains exact coverage and current-serving identity."""
    evidence, reader = _materialize(_complete(), tmp_path)

    report = evaluate_hk_v1_live_admission(
        replace(evidence, coverage_matrix_fingerprint="", serving_state_id="", target_name=""),
        reader,
    )

    assert report.admitted is False
    assert "COVERAGE_MATRIX_FINGERPRINT_INVALID" in report.blocker_codes
    assert "CURRENT_SERVING_STATE_INVALID" in report.blocker_codes
    assert "CURRENT_TARGET_INVALID" in report.blocker_codes


@pytest.mark.parametrize(
    ("gate_index", "blocker"),
    [
        (0, "GATE_A_COVERAGE_BINDING_MISMATCH"),
        (4, "GATE_E_PROPOSAL_BINDING_MISMATCH"),
        (6, "GATE_G_PROPOSAL_BINDING_MISMATCH"),
    ],
)
def test_gate_subjects_are_cross_bound_to_coverage_and_proposal(
    gate_index: int, blocker: str, tmp_path: Path
) -> None:
    """Coverage, Review, Approval, and live proof cannot cross manifest lineages."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = evidence.gates[gate_index]
    new_subject = "sha256:" + "9" * 64
    altered = replace(
        gate,
        subject_fingerprint=new_subject,
        evidence_refs=tuple(
            replace(item, subject_fingerprint=new_subject) for item in gate.evidence_refs
        ),
    )

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, gate.gate, altered), reader)

    assert report.admitted is False
    assert blocker in report.blocker_codes


def test_gate_order_duplicates_and_unknown_names_fail_closed(tmp_path: Path) -> None:
    """Only the exact ordered A-G inventory is accepted."""
    evidence, reader = _materialize(_complete(), tmp_path)
    duplicate = replace(evidence, gates=(*evidence.gates[:-1], evidence.gates[0]))

    report = evaluate_hk_v1_live_admission(duplicate, reader)

    assert report.admitted is False
    assert "GATE_INVENTORY_INVALID" in report.blocker_codes


def test_changed_claimed_fingerprint_blocks_verified_readback(tmp_path: Path) -> None:
    """A changed claimed fingerprint cannot remain admitted without matching bytes."""
    evidence, reader = _materialize(_complete(), tmp_path)
    original = evaluate_hk_v1_live_admission(evidence, reader)
    gate = evidence.gates[3]
    changed_ref = replace(gate.evidence_refs[0], fingerprint="sha256:" + "f" * 64)
    altered_gate = replace(gate, evidence_refs=(changed_ref, *gate.evidence_refs[1:]))

    changed = evaluate_hk_v1_live_admission(_replace_gate(evidence, "D", altered_gate), reader)

    assert changed.admitted is False
    assert "GATE_D_EVIDENCE_BYTES_MISMATCH" in changed.blocker_codes
    assert changed.evidence_fingerprint != original.evidence_fingerprint


def test_model_and_tokenizer_require_one_exact_semantic_profile_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Model and tokenizer claims cannot mix profile-set artifacts."""
    evidence, reader = _materialize(_complete(), tmp_path)
    shared = b'{"real-semantic-profile-set":"same-bytes"}'
    evidence = _replace_proof(
        evidence, tmp_path, gate_index=3, reference_index=3, proof_bytes=shared
    )
    evidence = _replace_proof(
        evidence, tmp_path, gate_index=3, reference_index=4, proof_bytes=shared
    )

    def load_semantic_profile(_reader: object) -> SimpleNamespace:
        return SimpleNamespace(
            fingerprint=evidence.model_profile_fingerprint,
            profiles=(object(),),
            tokenizer_specifications=(object(),),
        )

    monkeypatch.setattr(
        admission_module,
        "load_semantic_profile_set",
        load_semantic_profile,
    )

    same = evaluate_hk_v1_live_admission(evidence, reader)
    drifted = _replace_proof(
        evidence,
        tmp_path,
        gate_index=3,
        reference_index=4,
        proof_bytes=b'{"real-semantic-profile-set":"different-bytes"}',
    )
    changed = evaluate_hk_v1_live_admission(drifted, reader)

    assert "GATE_D_SEMANTIC_PROFILE_PROOF_MISMATCH" not in same.blocker_codes
    assert "GATE_D_OWNING_PROOF_SEMANTICS_INVALID" not in same.blocker_codes
    assert "GATE_D_SEMANTIC_PROFILE_PROOF_MISMATCH" in changed.blocker_codes


@pytest.mark.parametrize(
    ("serving_fingerprint", "embedding_fingerprint"),
    [
        ("sha256:" + "f" * 64, "sha256:" + "3" * 64),
        ("sha256:" + "8" * 64, "sha256:" + "f" * 64),
    ],
)
def test_serving_profile_proof_binds_both_profile_fingerprints(
    serving_fingerprint: str,
    embedding_fingerprint: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A serving profile sharing only its embedding model cannot cross lineages."""
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=3,
        reference_index=0,
        proof_bytes=b'{"real-serving-profile":"retained-bytes"}',
    )

    def load_serving_profile(_reader: object) -> SimpleNamespace:
        return SimpleNamespace(
            fingerprint=serving_fingerprint,
            embedding=SimpleNamespace(profile_fingerprint=embedding_fingerprint),
        )

    monkeypatch.setattr(
        admission_module,
        "load_serving_capability_profile",
        load_serving_profile,
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert "GATE_D_OWNING_PROOF_SEMANTICS_INVALID" in report.blocker_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"common_cutoff": "2026-09-08T12:00:01+08:00"},
        {"model_profile_fingerprint": "sha256:" + "f" * 64},
        {"embedding_profile_fingerprint": "sha256:" + "f" * 64},
        {"serving_profile_fingerprint": "sha256:" + "f" * 64},
    ],
)
def test_task8_package_is_bound_to_cutoff_and_all_profile_lineages(
    changes: dict[str, str], tmp_path: Path
) -> None:
    """The selected Approval cannot authorize another cutoff or capability profile."""
    evidence, reader = _materialize(_complete(), tmp_path)

    report = evaluate_hk_v1_live_admission(replace(evidence, **changes), reader)

    assert "GATE_E_TASK8_APPROVED_PACKAGE_INVALID" in report.blocker_codes


def test_gate_g_no_change_restart_rollback_and_recovery_proofs_are_mandatory(
    tmp_path: Path,
) -> None:
    """Live admission preserves the accepted recovery and no-change proofs."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = evidence.gates[-1]
    omitted = {"NO_CHANGE_CYCLE", "REBOOT", "ROLLBACK", "RESTORATION", "BACKUP", "READ_BACK"}
    altered = replace(
        gate,
        evidence_refs=tuple(ref for ref in gate.evidence_refs if ref.evidence_kind not in omitted),
    )

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, "G", altered), reader)

    assert report.admitted is False
    assert "GATE_G_EVIDENCE_INCOMPLETE" in report.blocker_codes


def test_nonexistent_retained_envelope_blocks_admission(tmp_path: Path) -> None:
    """A reference is not evidence when its local retained bytes do not exist."""
    evidence, reader = _materialize(_complete(), tmp_path)
    reference = evidence.gates[1].evidence_refs[0]
    _path(tmp_path, reference.immutable_ref).unlink()

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_B_EVIDENCE_READBACK_FAILED" in report.blocker_codes


def test_tampered_retained_envelope_blocks_admission(tmp_path: Path) -> None:
    """Read-back hashes exact envelope bytes rather than trusting its locator."""
    evidence, reader = _materialize(_complete(), tmp_path)
    reference = evidence.gates[4].evidence_refs[0]
    _path(tmp_path, reference.immutable_ref).write_bytes(b'{"tampered":true}')

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_E_EVIDENCE_BYTES_MISMATCH" in report.blocker_codes
    assert "GATE_E_EVIDENCE_ENVELOPE_INVALID" in report.blocker_codes


def test_tampered_owning_boundary_receipt_blocks_admission(tmp_path: Path) -> None:
    """The closed envelope cannot conceal altered producer evidence."""
    evidence, reader = _materialize(_complete(), tmp_path)
    producer_path = tmp_path / "producer/G/baseline.json"
    producer_path.write_bytes(b'{"changed":true}')

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_G_PRODUCER_EVIDENCE_BYTES_MISMATCH" in report.blocker_codes


def test_missing_underlying_proof_blocks_self_consistent_receipt(tmp_path: Path) -> None:
    """A canonical receipt cannot substitute for the owning boundary's exact proof bytes."""
    evidence, reader = _materialize(_complete(), tmp_path)
    (tmp_path / "proofs/E/approval.json").unlink()

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_E_PRODUCER_PROOF_READBACK_FAILED" in report.blocker_codes


def test_producer_receipt_cannot_relabel_a_different_evidence_kind(tmp_path: Path) -> None:
    """Exact bytes for one kind cannot be presented as a different Gate E proof."""
    evidence, reader = _materialize(_complete(), tmp_path)
    approval = tmp_path / "producer/E/approval.json"
    replacement = tmp_path / "producer/E/backup.json"
    approval.write_bytes(replacement.read_bytes())
    gate = evidence.gates[4]
    reference = gate.evidence_refs[0]
    envelope_path = _path(tmp_path, reference.immutable_ref)
    envelope = json.loads(envelope_path.read_bytes())
    producer_bytes = approval.read_bytes()
    envelope["producer_evidence_fingerprint"] = "sha256:" + sha256(producer_bytes).hexdigest()
    changed = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
    envelope_path.write_bytes(changed)
    altered_ref = replace(reference, fingerprint="sha256:" + sha256(changed).hexdigest())
    altered_gate = replace(gate, evidence_refs=(altered_ref, *gate.evidence_refs[1:]))

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, "E", altered_gate), reader)

    assert report.admitted is False
    assert "GATE_E_PRODUCER_EVIDENCE_LINEAGE_MISMATCH" in report.blocker_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"common_cutoff": "2026-09-08T12:00:01+08:00"},
        {"approval_fingerprint": "sha256:" + "e" * 64},
        {"serving_state_id": "ssv_000000000000000000000000000000000000000000000002"},
        {"target_name": "asklegal-v1-hk-local-drifted"},
        {"target_fingerprint": "sha256:" + "e" * 64},
    ],
)
def test_global_lineage_drift_is_detected_inside_every_envelope(
    changes: dict[str, str], tmp_path: Path
) -> None:
    """Cutoff, Approval, Serving State, and target drift invalidate retained proof."""
    evidence, reader = _materialize(_complete(), tmp_path)
    altered = replace(evidence, **changes)

    report = evaluate_hk_v1_live_admission(altered, reader)

    assert report.admitted is False
    assert "GATE_A_EVIDENCE_LINEAGE_MISMATCH" in report.blocker_codes
    assert "GATE_G_EVIDENCE_LINEAGE_MISMATCH" in report.blocker_codes


@pytest.mark.parametrize("mutation", ["UNKNOWN_KEY", "DUPLICATE_KEY"])
def test_retained_envelope_has_a_closed_duplicate_free_schema(
    mutation: str, tmp_path: Path
) -> None:
    """Canonical hashes cannot make an extended or duplicate-key envelope valid."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = evidence.gates[3]
    reference = gate.evidence_refs[0]
    path = _path(tmp_path, reference.immutable_ref)
    raw = path.read_bytes()
    if mutation == "UNKNOWN_KEY":
        document = json.loads(raw)
        assert isinstance(document, dict)
        document["unexpected"] = True
        changed = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    else:
        value = json.loads(raw)["approval_fingerprint"]
        changed = b'{"approval_fingerprint":' + json.dumps(value).encode() + b"," + raw[1:]
    path.write_bytes(changed)
    changed_ref = replace(reference, fingerprint="sha256:" + sha256(changed).hexdigest())
    altered_gate = replace(gate, evidence_refs=(changed_ref, *gate.evidence_refs[1:]))

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, "D", altered_gate), reader)

    assert report.admitted is False
    assert "GATE_D_EVIDENCE_ENVELOPE_INVALID" in report.blocker_codes


def test_invalid_calendar_cutoff_is_rejected_semantically(tmp_path: Path) -> None:
    """A timestamp-shaped impossible date cannot pass the common-cutoff gate."""
    evidence, reader = _materialize(_complete(), tmp_path)

    report = evaluate_hk_v1_live_admission(
        replace(evidence, common_cutoff="2026-02-31T12:00:00+08:00"), reader
    )

    assert report.admitted is False
    assert "COMMON_CUTOFF_INVALID" in report.blocker_codes


def test_arbitrary_vault_uri_is_not_an_accepted_local_proof(tmp_path: Path) -> None:
    """Only references confined by the local file-backed reader can prove admission."""
    evidence, reader = _materialize(_complete(), tmp_path)
    gate = evidence.gates[0]
    altered_ref = replace(gate.evidence_refs[0], immutable_ref="vault://claimed/proof.json")
    altered_gate = replace(gate, evidence_refs=(altered_ref, *gate.evidence_refs[1:]))

    report = evaluate_hk_v1_live_admission(_replace_gate(evidence, "A", altered_gate), reader)

    assert report.admitted is False
    assert "GATE_A_EVIDENCE_BINDING_INVALID" in report.blocker_codes
    assert "GATE_A_EVIDENCE_READBACK_FAILED" in report.blocker_codes


def test_arbitrary_literal_proof_bytes_cannot_be_wrapped_into_admission(tmp_path: Path) -> None:
    """A self-consistent hash chain cannot turn an untyped literal into owning proof."""
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=3,
        reference_index=0,
        proof_bytes=b'{"observed_result":"VERIFIED"}',
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_D_OWNING_PROOF_SCHEMA_INVALID" in report.blocker_codes


def test_exact_generic_self_asserted_proof_never_satisfies_a_real_gate(tmp_path: Path) -> None:
    """The old exact-looking VERIFIED receipt is not a producer artifact contract."""
    evidence, reader = _materialize(_complete(), tmp_path)

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_G_OWNING_PROOF_UNAVAILABLE" in report.blocker_codes


def test_owning_proof_kind_cannot_be_relabelled_to_another_owner(tmp_path: Path) -> None:
    """A canonical proof with the wrong owning application is not equivalent evidence."""
    evidence, reader = _materialize(_complete(), tmp_path)
    proof_path = tmp_path / "proofs/D/embedding_profile.json"
    proof = json.loads(proof_path.read_bytes())
    proof["owner"] = "REVIEW_API"
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=3,
        reference_index=0,
        proof_bytes=_canonical(proof),
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_D_OWNING_PROOF_SCHEMA_INVALID" in report.blocker_codes


@pytest.mark.parametrize("state", ["APPROVAL_APPROVED", "APPROVAL_REVOKED"])
def test_unconsumed_or_revoked_task8_approval_cannot_admit(state: str, tmp_path: Path) -> None:
    """Gate E requires the real retained Task 8 Approval to remain current and consumed."""
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=4,
        reference_index=0,
        proof_bytes=_task8_approval_ledger(state=state),
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_E_TASK8_APPROVAL_NOT_CURRENT" in report.blocker_codes


def test_actual_task8_approval_package_and_command_are_accepted_as_gate_e_input(
    tmp_path: Path,
) -> None:
    """The actual package verifier accepts the exact current consumed Approval fixture."""
    evidence, reader = _materialize(_complete(), tmp_path)

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert not any("TASK8_APPROVAL" in code for code in report.blocker_codes)
    assert "GATE_E_OWNING_PROOF_UNAVAILABLE" in report.blocker_codes


def test_selected_consumed_approval_allows_valid_revoked_historical_approval(
    tmp_path: Path,
) -> None:
    """Selection uses the exact event fingerprint without rejecting valid ledger history."""
    ledger = json.loads(_task8_approval_ledger())
    historical = dict(ledger["events"][0])
    historical_id = "pmn_" + "9" * 48
    decision = json.loads(bytes.fromhex(historical["event_bytes"]))
    decision["promotion_manifest_ref"]["ref_id"] = historical_id
    approval_id = (
        "apr_"
        + sha256(f"{historical_id}\x1f{_PROPOSAL_FINGERPRINT}\x1fAPPROVED".encode()).hexdigest()[
            :48
        ]
    )
    decision["approval_id"] = approval_id
    decision_bytes = _canonical(decision)
    command = json.loads(bytes.fromhex(historical["command_bytes"]))
    command["approval_id"] = approval_id
    command["decision_fingerprint"] = "sha256:" + sha256(decision_bytes).hexdigest()
    command["proposal_package_id"] = historical_id
    historical.update(
        {
            "command_bytes": _canonical(command).hex(),
            "command_id": "cmd_" + "9" * 48,
            "event_bytes": decision_bytes.hex(),
            "target_id": historical_id,
            "winner_key": "proposal-decision:" + historical_id,
        }
    )
    ledger["events"].append(historical)
    ledger["approval_states"][approval_id] = {"lineage": "", "state": "APPROVAL_REVOKED"}
    ledger["revoked"] = [approval_id]
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=4,
        reference_index=0,
        proof_bytes=_canonical(ledger),
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert not any("TASK8_APPROVAL" in code for code in report.blocker_codes)


def test_selected_approval_allows_valid_real_shaped_historical_rejection(
    tmp_path: Path,
) -> None:
    """A prior rejection has null package fields and no approval-state projection."""
    ledger = json.loads(_task8_approval_ledger())
    ledger["events"].insert(0, _historical_rejection_event())
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=4,
        reference_index=0,
        proof_bytes=_canonical(ledger),
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert not any("TASK8_APPROVAL" in code for code in report.blocker_codes)


def test_invalid_historical_rejection_command_invalidates_whole_ledger(tmp_path: Path) -> None:
    """Every historical event command remains intrinsically validated."""
    ledger = json.loads(_task8_approval_ledger())
    historical = _historical_rejection_event()
    command = json.loads(bytes.fromhex(str(historical["command_bytes"])))
    command["decision_fingerprint"] = "sha256:" + "f" * 64
    historical["command_bytes"] = _canonical(command).hex()
    ledger["events"].insert(0, historical)
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=4,
        reference_index=0,
        proof_bytes=_canonical(ledger),
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert "GATE_E_TASK8_APPROVAL_COMMAND_INVALID" in report.blocker_codes


def test_rejected_task8_decision_cannot_be_presented_as_approval(tmp_path: Path) -> None:
    """A retained named-human rejection is never normalized into an Approval."""
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=4,
        reference_index=0,
        proof_bytes=_task8_approval_ledger(state="APPROVAL_REJECTED", decision_value="REJECTED"),
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_E_TASK8_APPROVAL_DECISION_INVALID" in report.blocker_codes


def test_malformed_task8_approval_schema_cannot_admit(tmp_path: Path) -> None:
    """Approval-like JSON cannot replace the exact retained Task 8 ledger schema."""
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=4,
        reference_index=0,
        proof_bytes=_canonical({"decision": "APPROVED", "state": "APPROVAL_CONSUMED"}),
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_E_TASK8_APPROVAL_LEDGER_INVALID" in report.blocker_codes


@pytest.mark.parametrize("field", ["proposal_bytes", "readiness_bytes"])
def test_task8_approval_rejects_one_byte_embedded_package_fields(
    field: str, tmp_path: Path
) -> None:
    """Nonempty arbitrary package bytes cannot satisfy the actual Task 8 verifier."""
    ledger = json.loads(_task8_approval_ledger())
    ledger["events"][0][field] = "00"
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=4,
        reference_index=0,
        proof_bytes=_canonical(ledger),
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_E_TASK8_APPROVED_PACKAGE_INVALID" in report.blocker_codes


def test_task8_approval_requires_the_exact_recorded_command(tmp_path: Path) -> None:
    """The retained command must bind the Approval event, package, and reviewer."""
    ledger = json.loads(_task8_approval_ledger())
    command = json.loads(bytes.fromhex(ledger["events"][0]["command_bytes"]))
    command["decision_fingerprint"] = "sha256:" + "f" * 64
    ledger["events"][0]["command_bytes"] = _canonical(command).hex()
    evidence, reader = _materialize(_complete(), tmp_path)
    evidence = _replace_proof(
        evidence,
        tmp_path,
        gate_index=4,
        reference_index=0,
        proof_bytes=_canonical(ledger),
    )

    report = evaluate_hk_v1_live_admission(evidence, reader)

    assert report.admitted is False
    assert "GATE_E_TASK8_APPROVAL_COMMAND_INVALID" in report.blocker_codes


def test_nonexistent_evidence_root_cannot_admit(tmp_path: Path) -> None:
    """The public local path fails visibly when no retained evidence root exists."""
    evidence, _ = _materialize(_complete(), tmp_path / "real")

    report = evaluate_hk_v1_live_admission(
        evidence, LocalRetainedEvidenceReader(tmp_path / "missing")
    )

    assert report.admitted is False
    assert "GATE_A_EVIDENCE_READBACK_FAILED" in report.blocker_codes


def test_local_reader_accepts_task8_sized_owning_proof_bytes(tmp_path: Path) -> None:
    """Owning proofs may use Task 8's five-megabyte retained-ledger contract."""
    proof = b"x" * 1_000_001
    path = tmp_path / "proofs/E/approval.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(proof)

    observed = LocalRetainedEvidenceReader(tmp_path).read_bytes(
        "local-evidence://proofs/E/approval.json"
    )

    assert observed == proof


def test_exact_manifest_loader_round_trips_only_canonical_closed_input(tmp_path: Path) -> None:
    """The executable path reconstructs the exact typed admission manifest."""
    evidence, _ = _materialize(_complete(), tmp_path / "evidence")
    manifest = tmp_path / "admission.json"
    manifest.write_bytes(_manifest_bytes(evidence))

    assert load_hk_v1_live_admission_manifest(manifest) == evidence

    document = json.loads(manifest.read_bytes())
    document["unknown"] = True
    manifest.write_bytes(_canonical(document))
    with pytest.raises(ValueError, match="HK_V1_ADMISSION_MANIFEST_INVALID"):
        load_hk_v1_live_admission_manifest(manifest)


def test_cli_is_the_complete_local_manifest_and_readback_entrypoint(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """CLI reads every proof and exits one while Task 10 artifacts remain unavailable."""
    evidence_root = tmp_path / "evidence"
    evidence, _ = _materialize(_complete(), evidence_root)
    manifest = tmp_path / "admission.json"
    manifest.write_bytes(_manifest_bytes(evidence))

    assert main(["--manifest", str(manifest), "--evidence-root", str(evidence_root)]) == 1
    captured = capfd.readouterr()
    assert json.loads(captured.out)["result"] == "NOT_ADMITTED"
    assert captured.err == ""


def test_module_cli_executes_the_complete_local_path(tmp_path: Path) -> None:
    """The documented module command executes loading and retained read-back."""
    evidence_root = tmp_path / "evidence"
    evidence, _ = _materialize(_complete(), evidence_root)
    manifest = tmp_path / "admission.json"
    manifest.write_bytes(_manifest_bytes(evidence))

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.hk_v1_live_admission",
            "--manifest",
            str(manifest),
            "--evidence-root",
            str(evidence_root),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
    )

    assert result.returncode == 1, result.stderr.decode()
    assert json.loads(result.stdout)["result"] == "NOT_ADMITTED"


def test_cli_rejects_nonexistent_manifest_or_evidence_root(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """CLI cannot silently substitute a missing manifest or retained evidence tree."""
    missing_manifest = tmp_path / "missing.json"
    assert main(["--manifest", str(missing_manifest), "--evidence-root", str(tmp_path)]) == 2
    assert capfd.readouterr().err == "FAIL HK_V1_ADMISSION_MANIFEST_INVALID\n"

    evidence_root = tmp_path / "evidence"
    evidence, _ = _materialize(_complete(), evidence_root)
    manifest = tmp_path / "admission.json"
    manifest.write_bytes(_manifest_bytes(evidence))
    missing_root = tmp_path / "absent"
    assert main(["--manifest", str(manifest), "--evidence-root", str(missing_root)]) == 1
    captured = capfd.readouterr()
    assert json.loads(captured.out)["result"] == "NOT_ADMITTED"
