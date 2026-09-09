"""Assemble local Gate A-G evidence only from strict owning artifacts.

The assembler never accepts a generic admission receipt.  Every supported input is
reconstructed by the parser owned by its production boundary.  Evidence kinds whose
owner does not yet emit a parseable terminal artifact remain absent from the manifest,
which makes the existing admission evaluator return ``NOT_ADMITTED``.
"""

# ruff: noqa: SLF001

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from secrets import token_hex
from shutil import rmtree
from typing import Never, cast

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_processing import ProfileError as SemanticProfileError
from asklegal_processing import SemanticProfileSet, load_semantic_profile_set
from asklegal_promotion import (
    ProfileError as ServingProfileError,
)
from asklegal_promotion import (
    PromotionError,
    ServingCapabilityProfile,
    load_serving_capability_profile,
    target_state_fingerprint,
    verify_hk_v1_approved_package,
)
from asklegal_reporting import (
    HongKongV1CoverageError,
    HongKongV1TwoFamilyCoverageReport,
    evaluate_hk_v1_scope_gate,
    is_hk_v1_coverage_matrix_issued,
    is_hk_v1_coverage_matrix_policy_approved,
    load_hk_v1_coverage_matrix,
    parse_hk_v1_two_family_coverage_report,
)

import tools.hk_v1_live_admission as admission
from tools.hk_v1_admission_release_evidence import parse_live_release_accounting
from tools.hk_v1_admission_source_evidence import (
    parse_source_authority_evidence,
    parse_source_exercise_evidence,
)
from tools.hk_v1_live_admission import (
    EXPECTED_FAMILIES,
    EXPECTED_SCOPES,
    GateEvidence,
    GateName,
    HKV1AdmissionEvidence,
    LocalRetainedEvidenceReader,
    RetainedEvidenceRef,
    canonical_report_bytes,
    evaluate_hk_v1_live_admission,
)
from tools.hk_v1_provider_admission import parse_provider_admission_evidence

# This sibling tool deliberately composes the evaluator's closed parser registry.
# It does not widen or bypass those private validation boundaries.
# pyright: reportPrivateUsage=false

_MAX_INPUT_BYTES = 5_000_000
_LEDGER_KEYS = frozenset({"approval_states", "events", "revoked", "schema_id"})
_STATE_KEYS = frozenset({"activation", "active_state_id", "rollback", "schema_id"})
_CANDIDATE_KEYS = frozenset(
    {
        "approval_id",
        "candidate_serving_state_id",
        "candidate_serving_state_fingerprint",
        "coverage_fingerprint",
        "desired_inventory_fingerprint",
        "embedding_profile_fingerprint",
        "embedding_profile_id",
        "execution_lineage_id",
        "predecessor_state_id",
        "target_name",
    }
)


class AdmissionAssemblyError(ValueError):
    """Closed local assembly failure."""


@dataclass(frozen=True, slots=True)
class AdmissionAssemblyInputs:
    """Exact files needed to establish one common live lineage."""

    coverage_matrix: Path
    coverage_report: Path
    semantic_profile: Path
    serving_profile: Path
    approval_ledger: Path
    serving_state: Path
    output_root: Path
    gate_f_operational: Path | None = None
    gate_g_lineage: Path | None = None
    source_authority: Path | None = None
    source_exercises: Path | None = None
    live_release_accounting: Path | None = None
    approval_invalidation_ledger: Path | None = None
    promotion_readback: Path | None = None
    promotion_failure_stop: Path | None = None
    rollback_readback: Path | None = None
    provider_admission: Path | None = None


@dataclass(frozen=True, slots=True)
class _ExactProfileReader:
    reference: ImmutableReference
    content: bytes

    def read_exact(self, reference: ImmutableReference) -> bytes:
        if reference != self.reference:
            message = "HK_V1_ADMISSION_PROFILE_REFERENCE_MISMATCH"
            raise AdmissionAssemblyError(message)
        return self.content


@dataclass(frozen=True, slots=True)
class _ServingFacts:
    state_id: str
    state_fingerprint: str
    predecessor_state_id: str
    approval_id: str
    execution_lineage_id: str
    target_name: str
    embedding_profile_id: str
    embedding_profile_fingerprint: str


@dataclass(frozen=True, slots=True)
class _ApprovalFacts:
    fingerprint: str
    proposal: bytes
    readiness: bytes
    proposal_fingerprint: str


@dataclass(frozen=True, slots=True)
class _Lineage:
    cutoff: str
    matrix_fingerprint: str
    proposal_fingerprint: str
    model_profile_fingerprint: str
    embedding_profile_fingerprint: str
    serving_profile_fingerprint: str
    approval_fingerprint: str
    serving_state_id: str
    target_name: str
    target_fingerprint: str


def _fail() -> Never:
    message = "HK_V1_ADMISSION_ASSEMBLY_INVALID"
    raise AdmissionAssemblyError(message)


def _read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        _fail()
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_INPUT_BYTES:
        _fail()
    return raw


def _profile_reader(raw: bytes, reference_type: ReferenceType) -> _ExactProfileReader:
    digest = sha256(raw).hexdigest()
    prefix = "wap" if reference_type is ReferenceType.WORKFLOW_PROFILE else "cap"
    return _ExactProfileReader(
        ImmutableReference(reference_type, f"{prefix}_{digest[:48]}", f"sha256:{digest}"),
        raw,
    )


def _load_profiles(
    semantic_raw: bytes, serving_raw: bytes
) -> tuple[SemanticProfileSet, ServingCapabilityProfile]:
    try:
        semantic = load_semantic_profile_set(
            _profile_reader(semantic_raw, ReferenceType.WORKFLOW_PROFILE)
        )
        serving = load_serving_capability_profile(
            _profile_reader(serving_raw, ReferenceType.CAPABILITY_PROFILE)
        )
    except SemanticProfileError, ServingProfileError, TypeError, ValueError:
        _fail()
    return semantic, serving


def _load_coverage(matrix_raw: bytes, report_raw: bytes) -> HongKongV1TwoFamilyCoverageReport:
    try:
        matrix = load_hk_v1_coverage_matrix()
        packaged = files("asklegal_reporting").joinpath("hk_v1_coverage_matrix.json").read_bytes()
        report = parse_hk_v1_two_family_coverage_report(report_raw)
    except OSError, HongKongV1CoverageError, TypeError, ValueError:
        _fail()
    if (
        matrix_raw != packaged
        or not is_hk_v1_coverage_matrix_issued(matrix)
        or not is_hk_v1_coverage_matrix_policy_approved(matrix)
        or evaluate_hk_v1_scope_gate(matrix).result != "ADMITTED"
        or report.included_material_families != EXPECTED_FAMILIES
        or report.scope_ids != EXPECTED_SCOPES
    ):
        _fail()
    return report


def _text(value: object) -> str:
    if type(value) is not str or not value:
        _fail()
    return value


def _load_serving_state(raw: bytes) -> _ServingFacts:
    try:
        value = parse_json_bytes(raw, max_bytes=_MAX_INPUT_BYTES)
    except ValueError:
        _fail()
    if (
        type(value) is not dict
        or frozenset(value) != _STATE_KEYS
        or canonicalize(value) != raw
        or value.get("schema_id") != "asklegal.local-serving-state/v1"
        or value.get("rollback") is not None
    ):
        _fail()
    activation = value.get("activation")
    if type(activation) is not dict or set(activation) != {"candidate", "receipt_id"}:
        _fail()
    candidate = activation.get("candidate")
    if type(candidate) is not dict or frozenset(candidate) != _CANDIDATE_KEYS:
        _fail()
    state_id = _text(candidate.get("candidate_serving_state_id"))
    predecessor = _text(candidate.get("predecessor_state_id"))
    state_fingerprint = _text(candidate.get("candidate_serving_state_fingerprint"))
    receipt_material = canonicalize(
        checked_json_value(
            {
                "candidate_fingerprint": state_fingerprint,
                "operation": "ACTIVATED",
                "predecessor_state_id": predecessor,
                "state_id": state_id,
            }
        )
    )
    if (
        value.get("active_state_id") != state_id
        or activation.get("receipt_id") != "ssr_" + sha256(receipt_material).hexdigest()[:48]
    ):
        _fail()
    return _ServingFacts(
        state_id,
        state_fingerprint,
        predecessor,
        _text(candidate.get("approval_id")),
        _text(candidate.get("execution_lineage_id")),
        _text(candidate.get("target_name")),
        _text(candidate.get("embedding_profile_id")),
        _text(candidate.get("embedding_profile_fingerprint")),
    )


def _load_approval(raw: bytes, serving: _ServingFacts) -> _ApprovalFacts:
    ledger = admission._strict_document(raw, _LEDGER_KEYS)
    if ledger is None or ledger.get("schema_id") != "asklegal.local-review-approval-ledger/v1":
        _fail()
    events = ledger.get("events")
    states = ledger.get("approval_states")
    revoked = ledger.get("revoked")
    if (
        not isinstance(events, list)
        or not isinstance(states, dict)
        or not isinstance(revoked, list)
    ):
        _fail()
    selected: admission._Task8LedgerEvent | None = None
    for item in cast("list[object]", events):
        event = admission._approval_event_decision(item)
        if event is None:
            _fail()
        if event.decision.get("approval_id") == serving.approval_id:
            if selected is not None:
                _fail()
            selected = event
    state = cast("dict[object, object]", states).get(serving.approval_id)
    if type(state) is not dict:
        _fail()
    state_document = cast("dict[str, object]", state)
    if (
        selected is None
        or selected.proposal_raw is None
        or selected.readiness_raw is None
        or state_document.get("state") != "APPROVAL_CONSUMED"
        or state_document.get("lineage") != serving.execution_lineage_id
        or serving.approval_id in cast("list[object]", revoked)
    ):
        _fail()
    valid, _, proposal_fingerprint = admission._approved_package_valid(
        selected.proposal_raw,
        selected.readiness_raw,
        selected.decision,
    )
    intrinsic, approval_id = admission._approval_decision_intrinsic_valid(
        selected.decision,
        proposal_fingerprint=proposal_fingerprint,
    )
    base = admission._reference_tuple(selected.decision.get("expected_base_serving_state_ref"))
    if (
        not valid
        or not intrinsic
        or approval_id != serving.approval_id
        or base is None
        or base[1] != serving.predecessor_state_id
    ):
        _fail()
    return _ApprovalFacts(
        selected.event_fingerprint,
        selected.proposal_raw,
        selected.readiness_raw,
        proposal_fingerprint,
    )


def _lineage(  # noqa: PLR0913, PLR0917 - exact cross-bound lineage inputs.
    matrix_fingerprint: str,
    coverage: HongKongV1TwoFamilyCoverageReport,
    semantic: SemanticProfileSet,
    serving_profile: ServingCapabilityProfile,
    serving: _ServingFacts,
    approved: _ApprovalFacts,
) -> _Lineage:
    try:
        proposal = parse_json_bytes(approved.proposal, max_bytes=2_000_000)
        readiness = parse_json_bytes(approved.readiness, max_bytes=2_000_000)
        if type(readiness) is not dict or type(proposal) is not dict:
            _fail()
        members = readiness.get("target_members")
        if not isinstance(members, list):
            _fail()
        record_ids = tuple(
            _text(cast("dict[str, JsonValue]", item).get("record_id"))
            for item in members
            if type(item) is dict
        )
        package = verify_hk_v1_approved_package(approved.proposal, approved.readiness, record_ids)
    except PromotionError, TypeError, ValueError:
        _fail()
    cutoff = _text(proposal.get("observation_cutoff"))
    if (
        len(record_ids) != len(members)
        or coverage.observation_cutoff != cutoff
        or proposal.get("coverage_report_fingerprint") != coverage.fingerprint
        or package.proposal_fingerprint != approved.proposal_fingerprint
        or package.model_profile_fingerprint != semantic.fingerprint
        or package.embedding_profile_fingerprint != serving_profile.embedding.profile_fingerprint
        or package.serving_profile_fingerprint != serving_profile.fingerprint
        or package.target_name != serving.target_name
        or serving.embedding_profile_id != serving_profile.embedding.profile_id
        or serving.embedding_profile_fingerprint != serving_profile.embedding.profile_fingerprint
    ):
        _fail()
    target_fingerprint = target_state_fingerprint(
        serving.target_name,
        serving_profile.dimensions,
        serving_profile.metric,
        serving_profile.namespace,
    )
    return _Lineage(
        cutoff,
        matrix_fingerprint,
        approved.proposal_fingerprint,
        semantic.fingerprint,
        serving_profile.embedding.profile_fingerprint,
        serving_profile.fingerprint,
        approved.fingerprint,
        serving.state_id,
        serving.target_name,
        target_fingerprint,
    )


def _subject(gate: GateName, lineage: _Lineage, coverage_fingerprint: str) -> str:
    if gate == "A":
        return lineage.matrix_fingerprint
    if gate in {"E", "G"}:
        return lineage.proposal_fingerprint
    if gate == "C":
        return lineage.proposal_fingerprint
    if gate == "B":
        return coverage_fingerprint
    return "sha256:" + sha256(f"{gate}\x1f{lineage.proposal_fingerprint}".encode()).hexdigest()


def _producer_document(  # noqa: PLR0913, PLR0917 - closed envelope fields.
    gate: GateName,
    kind: str,
    evidence_id: str,
    subject: str,
    lineage: _Lineage,
    proof_ref: str,
    proof: bytes,
) -> dict[str, object]:
    return {
        "approval_fingerprint": lineage.approval_fingerprint,
        "common_cutoff": lineage.cutoff,
        "coverage_matrix_fingerprint": lineage.matrix_fingerprint,
        "embedding_profile_fingerprint": lineage.embedding_profile_fingerprint,
        "evidence_id": evidence_id,
        "evidence_kind": kind,
        "gate": gate,
        "model_profile_fingerprint": lineage.model_profile_fingerprint,
        "producer": "ADMISSION_ASSEMBLER",
        "proof_fingerprint": "sha256:" + sha256(proof).hexdigest(),
        "proof_owner": admission._OWNER_BY_GATE_KIND[(gate, kind)],
        "proof_ref": proof_ref,
        "proposal_fingerprint": lineage.proposal_fingerprint,
        "result": "VERIFIED",
        "schema_id": "asklegal.hk-v1-retained-producer-evidence",
        "schema_version": 1,
        "serving_profile_fingerprint": lineage.serving_profile_fingerprint,
        "serving_state_id": lineage.serving_state_id,
        "subject_fingerprint": subject,
        "target_fingerprint": lineage.target_fingerprint,
        "target_name": lineage.target_name,
    }


def _envelope_document(  # noqa: PLR0913, PLR0917 - closed envelope fields.
    gate: GateName,
    kind: str,
    evidence_id: str,
    subject: str,
    lineage: _Lineage,
    immutable_ref: str,
    producer_ref: str,
    producer: bytes,
) -> dict[str, object]:
    del gate
    return {
        "approval_fingerprint": lineage.approval_fingerprint,
        "common_cutoff": lineage.cutoff,
        "coverage_matrix_fingerprint": lineage.matrix_fingerprint,
        "embedding_profile_fingerprint": lineage.embedding_profile_fingerprint,
        "evidence_id": evidence_id,
        "evidence_kind": kind,
        "immutable_ref": immutable_ref,
        "model_profile_fingerprint": lineage.model_profile_fingerprint,
        "producer_evidence_fingerprint": "sha256:" + sha256(producer).hexdigest(),
        "producer_evidence_ref": producer_ref,
        "proposal_fingerprint": lineage.proposal_fingerprint,
        "schema_version": 1,
        "serving_profile_fingerprint": lineage.serving_profile_fingerprint,
        "serving_state_id": lineage.serving_state_id,
        "subject_fingerprint": subject,
        "target_fingerprint": lineage.target_fingerprint,
        "target_name": lineage.target_name,
    }


def _supported_proofs(  # noqa: C901, PLR0913, PLR0917 - exact owning artifacts.
    matrix: bytes,
    coverage: bytes,
    semantic: bytes,
    serving_profile: bytes,
    approved: _ApprovalFacts,
    ledger: bytes,
    serving_state: bytes,
    gate_f: bytes | None,
    gate_g: bytes | None,
    source_authority: bytes | None,
    source_exercises: bytes | None,
    live_release_accounting: bytes | None,
    approval_invalidation: bytes | None,
    promotion_readback: bytes | None,
    promotion_failure_stop: bytes | None,
    rollback_readback: bytes | None,
    provider_admission: bytes | None,
) -> dict[tuple[GateName, str], bytes]:
    proofs: dict[tuple[GateName, str], bytes] = {
        ("A", "COVERAGE_MATRIX"): matrix,
        ("C", "PACKAGE_READINESS"): approved.proposal,
        ("C", "RELEASE_ACCOUNTING"): coverage,
        ("D", "EMBEDDING_PROFILE"): serving_profile,
        ("D", "MODEL_PROFILE"): semantic,
        ("D", "TOKENIZER_PROFILE"): semantic,
        ("E", "APPROVAL"): ledger,
        ("E", "PROMOTION"): serving_state,
        ("E", "REPLACEMENT_TARGET"): serving_state,
        ("E", "REVIEW"): approved.readiness,
        ("G", "APPROVAL"): ledger,
    }
    if source_authority is not None:
        proofs[("A", "SOURCE_AUTHORITY")] = source_authority
    if source_exercises is not None:
        proofs.update({("B", kind): source_exercises for kind in admission._REQUIRED_EVIDENCE["B"]})
    if live_release_accounting is not None:
        proofs[("C", "RELEASE_ACCOUNTING")] = live_release_accounting
    if approval_invalidation is not None:
        proofs[("E", "APPROVAL_INVALIDATION")] = approval_invalidation
    if promotion_readback is not None:
        proofs[("E", "BACKUP")] = promotion_readback
        proofs[("E", "READ_BACK")] = promotion_readback
    if promotion_failure_stop is not None:
        proofs[("E", "PROMOTION_FAILURE_STOP")] = promotion_failure_stop
    if rollback_readback is not None:
        proofs[("E", "ROLLBACK")] = rollback_readback
    if provider_admission is not None:
        proofs[("D", "MODEL_EVALUATION_RUN_1")] = provider_admission
        proofs[("D", "MODEL_EVALUATION_RUN_2")] = provider_admission
    if gate_f is not None:
        proofs.update({("F", kind): gate_f for kind in admission._REQUIRED_EVIDENCE["F"]})
    if gate_g is not None:
        proofs.update({("G", kind): gate_g for kind in admission._REQUIRED_EVIDENCE["G"]})
        proofs[("G", "APPROVAL")] = ledger
    return proofs


def _write_bundle(  # noqa: C901 - one staged filesystem transaction.
    root: Path,
    lineage: _Lineage,
    coverage_fingerprint: str,
    proofs: dict[tuple[GateName, str], bytes],
) -> HKV1AdmissionEvidence:
    if root.is_symlink():
        _fail()
    parent = root.parent.resolve(strict=True)
    temporary = parent / f".{root.name}.{token_hex(16)}.tmp"
    try:
        temporary.mkdir(mode=0o700)
        by_gate: dict[GateName, list[RetainedEvidenceRef]] = {
            gate: [] for gate in admission._GATE_ORDER
        }
        for (gate, kind), proof in sorted(proofs.items()):
            subject = _subject(gate, lineage, coverage_fingerprint)
            evidence_id = f"{gate}-{kind.lower().replace('_', '-')}"
            relative = f"{gate}/{kind.lower()}.json"
            proof_ref = f"local-evidence://proofs/{relative}"
            producer_ref = f"local-evidence://producer/{relative}"
            immutable_ref = f"local-evidence://envelopes/{relative}"
            producer = canonicalize(
                checked_json_value(
                    _producer_document(gate, kind, evidence_id, subject, lineage, proof_ref, proof)
                )
            )
            envelope = canonicalize(
                checked_json_value(
                    _envelope_document(
                        gate,
                        kind,
                        evidence_id,
                        subject,
                        lineage,
                        immutable_ref,
                        producer_ref,
                        producer,
                    )
                )
            )
            for directory, content in (
                ("proofs", proof),
                ("producer", producer),
                ("envelopes", envelope),
            ):
                path = temporary / directory / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                if path.read_bytes() != content:
                    _fail()
            by_gate[gate].append(
                RetainedEvidenceRef(
                    evidence_id,
                    kind,
                    immutable_ref,
                    "sha256:" + sha256(envelope).hexdigest(),
                    subject,
                )
            )
        gates: list[GateEvidence] = []
        for gate in admission._GATE_ORDER:
            refs = tuple(sorted(by_gate[gate], key=lambda item: item.evidence_kind))
            expected = 4 if gate in {"A", "C"} else len(admission._REQUIRED_EVIDENCE[gate])
            supplied_kinds = frozenset(item.evidence_kind for item in refs)
            required_kinds = admission._REQUIRED_EVIDENCE[gate]
            verified = (
                expected if required_kinds.issubset(supplied_kinds) else min(len(refs), expected)
            )
            gates.append(
                GateEvidence(
                    gate,
                    _subject(gate, lineage, coverage_fingerprint),
                    EXPECTED_FAMILIES,
                    EXPECTED_SCOPES,
                    expected,
                    verified,
                    verified,
                    0,
                    0,
                    verified,
                    refs,
                )
            )
        evidence = HKV1AdmissionEvidence(
            tuple(gates),
            lineage.cutoff,
            lineage.matrix_fingerprint,
            lineage.proposal_fingerprint,
            lineage.model_profile_fingerprint,
            lineage.embedding_profile_fingerprint,
            lineage.serving_profile_fingerprint,
            lineage.approval_fingerprint,
            lineage.serving_state_id,
            lineage.target_name,
            lineage.target_fingerprint,
        )
        manifest = canonicalize(
            checked_json_value(
                {
                    **evidence.document(),
                    "schema_id": "asklegal.hk-v1-live-admission-manifest",
                    "schema_version": 1,
                }
            )
        )
        path = temporary / "manifest.json"
        path.write_bytes(manifest)
        if path.read_bytes() != manifest:
            _fail()
        if root.exists():
            if not _same_bundle(temporary, root):
                _fail()
            rmtree(temporary)
        else:
            temporary.replace(root)
        return evidence  # noqa: TRY300 - cleanup belongs to the complete staged transaction.
    except Exception:
        if temporary.exists():
            rmtree(temporary)
        raise


def _same_bundle(expected: Path, retained: Path) -> bool:
    """Compare one retained bundle without following a symlink or accepting extras."""
    if retained.is_symlink() or not retained.is_dir():
        return False
    expected_paths = tuple(sorted(path.relative_to(expected) for path in expected.rglob("*")))
    retained_paths = tuple(sorted(path.relative_to(retained) for path in retained.rglob("*")))
    if expected_paths != retained_paths:
        return False
    for relative in expected_paths:
        expected_path = expected / relative
        retained_path = retained / relative
        if retained_path.is_symlink() or expected_path.is_dir() != retained_path.is_dir():
            return False
        if expected_path.is_file() and expected_path.read_bytes() != retained_path.read_bytes():
            return False
    return True


def assemble_hk_v1_admission(inputs: AdmissionAssemblyInputs) -> HKV1AdmissionEvidence:
    """Parse, cross-bind, and atomically retain the supported admission evidence."""
    matrix_raw = _read(inputs.coverage_matrix)
    coverage_raw = _read(inputs.coverage_report)
    semantic_raw = _read(inputs.semantic_profile)
    serving_profile_raw = _read(inputs.serving_profile)
    ledger_raw = _read(inputs.approval_ledger)
    serving_state_raw = _read(inputs.serving_state)
    gate_f_raw = None if inputs.gate_f_operational is None else _read(inputs.gate_f_operational)
    gate_g_raw = None if inputs.gate_g_lineage is None else _read(inputs.gate_g_lineage)
    source_authority_raw = (
        None if inputs.source_authority is None else _read(inputs.source_authority)
    )
    source_exercises_raw = (
        None if inputs.source_exercises is None else _read(inputs.source_exercises)
    )
    live_release_raw = (
        None if inputs.live_release_accounting is None else _read(inputs.live_release_accounting)
    )
    approval_invalidation_raw = (
        None
        if inputs.approval_invalidation_ledger is None
        else _read(inputs.approval_invalidation_ledger)
    )
    promotion_readback_raw = (
        None if inputs.promotion_readback is None else _read(inputs.promotion_readback)
    )
    promotion_failure_raw = (
        None if inputs.promotion_failure_stop is None else _read(inputs.promotion_failure_stop)
    )
    rollback_readback_raw = (
        None if inputs.rollback_readback is None else _read(inputs.rollback_readback)
    )
    provider_admission_raw = (
        None if inputs.provider_admission is None else _read(inputs.provider_admission)
    )
    if source_authority_raw is not None:
        parse_source_authority_evidence(source_authority_raw)
    if source_exercises_raw is not None:
        parse_source_exercise_evidence(source_exercises_raw)
    if live_release_raw is not None:
        parse_live_release_accounting(live_release_raw)
    if provider_admission_raw is not None:
        parse_provider_admission_evidence(provider_admission_raw)
    coverage = _load_coverage(matrix_raw, coverage_raw)
    semantic, serving_profile = _load_profiles(semantic_raw, serving_profile_raw)
    serving = _load_serving_state(serving_state_raw)
    approved = _load_approval(ledger_raw, serving)
    matrix = load_hk_v1_coverage_matrix()
    lineage = _lineage(matrix.fingerprint, coverage, semantic, serving_profile, serving, approved)
    proofs = _supported_proofs(
        matrix_raw,
        coverage_raw,
        semantic_raw,
        serving_profile_raw,
        approved,
        ledger_raw,
        serving_state_raw,
        gate_f_raw,
        gate_g_raw,
        source_authority_raw,
        source_exercises_raw,
        live_release_raw,
        approval_invalidation_raw,
        promotion_readback_raw,
        promotion_failure_raw,
        rollback_readback_raw,
        provider_admission_raw,
    )
    evidence = _write_bundle(inputs.output_root, lineage, coverage.fingerprint, proofs)
    report = evaluate_hk_v1_live_admission(
        evidence, LocalRetainedEvidenceReader(inputs.output_root)
    )
    if report.result not in {"V1_ADMITTED", "NOT_ADMITTED"}:
        _fail()
    return evidence


def main(argv: list[str] | None = None) -> int:
    """Assemble without effects; exit two for invalid input and zero for a valid bundle."""
    parser = argparse.ArgumentParser(description="Assemble exact local HK V1 admission evidence")
    parser.add_argument("--coverage-matrix", required=True, type=Path)
    parser.add_argument("--coverage-report", required=True, type=Path)
    parser.add_argument("--semantic-profile", required=True, type=Path)
    parser.add_argument("--serving-profile", required=True, type=Path)
    parser.add_argument("--approval-ledger", required=True, type=Path)
    parser.add_argument("--serving-state", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--gate-f-operational", type=Path)
    parser.add_argument("--gate-g-lineage", type=Path)
    parser.add_argument("--source-authority", type=Path)
    parser.add_argument("--source-exercises", type=Path)
    parser.add_argument("--live-release-accounting", type=Path)
    parser.add_argument("--approval-invalidation-ledger", type=Path)
    parser.add_argument("--promotion-readback", type=Path)
    parser.add_argument("--promotion-failure-stop", type=Path)
    parser.add_argument("--rollback-readback", type=Path)
    parser.add_argument("--provider-admission", type=Path)
    args = parser.parse_args(argv)
    try:
        evidence = assemble_hk_v1_admission(
            AdmissionAssemblyInputs(
                coverage_matrix=args.coverage_matrix,
                coverage_report=args.coverage_report,
                semantic_profile=args.semantic_profile,
                serving_profile=args.serving_profile,
                approval_ledger=args.approval_ledger,
                serving_state=args.serving_state,
                output_root=args.output_root,
                gate_f_operational=args.gate_f_operational,
                gate_g_lineage=args.gate_g_lineage,
                source_authority=args.source_authority,
                source_exercises=args.source_exercises,
                live_release_accounting=args.live_release_accounting,
                approval_invalidation_ledger=args.approval_invalidation_ledger,
                promotion_readback=args.promotion_readback,
                promotion_failure_stop=args.promotion_failure_stop,
                rollback_readback=args.rollback_readback,
                provider_admission=args.provider_admission,
            )
        )
        report = evaluate_hk_v1_live_admission(
            evidence, LocalRetainedEvidenceReader(args.output_root)
        )
    except AdmissionAssemblyError, OSError, ValueError:
        sys.stderr.write("FAIL HK_V1_ADMISSION_ASSEMBLY_INVALID\n")
        return 2
    sys.stdout.buffer.write(canonical_report_bytes(report) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
