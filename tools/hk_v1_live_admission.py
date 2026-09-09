"""Pure fail-closed Gate A-G admission for the two-family Hong Kong V1."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol, cast

from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_processing import ProfileError as SemanticProfileError
from asklegal_processing import load_semantic_profile_set
from asklegal_promotion import ProfileError as ServingProfileError
from asklegal_promotion import (
    PromotionError,
    load_serving_capability_profile,
    verify_hk_v1_approved_package,
)
from asklegal_promotion_worker.promotion_evidence import (
    PromotionEvidenceError,
    parse_promotion_failure_stop,
    parse_promotion_readback,
)
from asklegal_reporting import (
    HongKongV1CoverageError,
    evaluate_hk_v1_scope_gate,
    is_hk_v1_coverage_matrix_issued,
    is_hk_v1_coverage_matrix_policy_approved,
    load_hk_v1_coverage_matrix,
    parse_hk_v1_two_family_coverage_report,
)

from tools.hk_v1_admission_operational_evidence import (
    OperationalEvidenceError,
    parse_gate_f_operational_evidence,
    parse_gate_g_live_lineage,
)
from tools.hk_v1_admission_release_evidence import (
    LiveReleaseAccountingError,
    parse_live_release_accounting,
)
from tools.hk_v1_admission_source_evidence import (
    SourceAdmissionEvidenceError,
    parse_source_authority_evidence,
    parse_source_exercise_evidence,
)
from tools.hk_v1_provider_admission import (
    ProviderAdmissionError,
    parse_provider_admission_evidence,
)

type GateName = Literal["A", "B", "C", "D", "E", "F", "G"]

EXPECTED_FAMILIES = ("CASES", "LEGISLATION")
EXPECTED_PROVIDER_SEMANTIC_CASES = 3
EXPECTED_PROVIDER_RETRIEVAL_CASES = 4
EXPECTED_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)

_GATE_ORDER: tuple[GateName, ...] = ("A", "B", "C", "D", "E", "F", "G")
_REQUIRED_EVIDENCE: dict[GateName, frozenset[str]] = {
    "A": frozenset({"COVERAGE_MATRIX", "SOURCE_AUTHORITY"}),
    "B": frozenset(
        {
            "SOURCE_COMPLETENESS",
            "SOURCE_CONTRACT_DRIFT",
            "SOURCE_INCOMPLETE",
            "SOURCE_NO_CHANGE",
            "SOURCE_RESTART",
            "SOURCE_RETRY",
        }
    ),
    "C": frozenset({"PACKAGE_READINESS", "RELEASE_ACCOUNTING"}),
    "D": frozenset(
        {
            "EMBEDDING_PROFILE",
            "MODEL_EVALUATION_RUN_1",
            "MODEL_EVALUATION_RUN_2",
            "MODEL_PROFILE",
            "TOKENIZER_PROFILE",
        }
    ),
    "E": frozenset(
        {
            "APPROVAL",
            "APPROVAL_INVALIDATION",
            "BACKUP",
            "PROMOTION",
            "PROMOTION_FAILURE_STOP",
            "READ_BACK",
            "REPLACEMENT_TARGET",
            "REVIEW",
            "ROLLBACK",
        }
    ),
    "F": frozenset({"OBSERVABILITY", "RECOVERY", "RESTART", "SCHEDULE", "SUPERVISION"}),
    "G": frozenset(
        {
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
        }
    ),
}
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00\Z")
_SAFE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{2,255}\Z")
_IMMUTABLE_REF = re.compile(r"local-evidence://[a-zA-Z0-9][a-zA-Z0-9._/-]{2,1023}\Z")
_MAX_ADMISSION_BYTES = 1_000_000
_MAX_OWNING_PROOF_BYTES = 5_000_000
_ENVELOPE_KEYS = frozenset(
    {
        "approval_fingerprint",
        "common_cutoff",
        "coverage_matrix_fingerprint",
        "evidence_id",
        "evidence_kind",
        "immutable_ref",
        "embedding_profile_fingerprint",
        "model_profile_fingerprint",
        "producer_evidence_fingerprint",
        "producer_evidence_ref",
        "proposal_fingerprint",
        "schema_version",
        "serving_profile_fingerprint",
        "serving_state_id",
        "subject_fingerprint",
        "target_fingerprint",
        "target_name",
    }
)
_PRODUCER_RECEIPT_KEYS = frozenset(
    {
        "approval_fingerprint",
        "common_cutoff",
        "coverage_matrix_fingerprint",
        "evidence_id",
        "evidence_kind",
        "gate",
        "embedding_profile_fingerprint",
        "model_profile_fingerprint",
        "producer",
        "proof_fingerprint",
        "proof_owner",
        "proof_ref",
        "proposal_fingerprint",
        "result",
        "schema_id",
        "schema_version",
        "serving_profile_fingerprint",
        "serving_state_id",
        "subject_fingerprint",
        "target_fingerprint",
        "target_name",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "approval_fingerprint",
        "common_cutoff",
        "coverage_matrix_fingerprint",
        "gates",
        "embedding_profile_fingerprint",
        "model_profile_fingerprint",
        "proposal_fingerprint",
        "schema_id",
        "schema_version",
        "serving_profile_fingerprint",
        "serving_state_id",
        "target_fingerprint",
        "target_name",
    }
)
_GATE_KEYS = frozenset(
    {
        "discovered",
        "evidence_refs",
        "expected",
        "families",
        "gate",
        "rejected",
        "retryable",
        "scopes",
        "subject_fingerprint",
        "terminal",
        "verified",
    }
)
_REFERENCE_KEYS = frozenset(
    {"evidence_id", "evidence_kind", "fingerprint", "immutable_ref", "subject_fingerprint"}
)
_OWNER_BY_GATE_KIND: dict[tuple[GateName, str], str] = {
    **{("A", kind): "REPORTING_BOUNDARY" for kind in _REQUIRED_EVIDENCE["A"]},
    **{("B", kind): "ACQUISITION_WORKER" for kind in _REQUIRED_EVIDENCE["B"]},
    **{("C", kind): "LEGAL_PROCESSING_WORKER" for kind in _REQUIRED_EVIDENCE["C"]},
    **{("D", kind): "LEGAL_PROCESSING_WORKER" for kind in _REQUIRED_EVIDENCE["D"]},
    **{("E", kind): "PROMOTION_WORKER" for kind in _REQUIRED_EVIDENCE["E"]},
    **{("F", kind): "CONTROL_PLANE" for kind in _REQUIRED_EVIDENCE["F"]},
    **{("G", kind): "CONTROL_PLANE" for kind in _REQUIRED_EVIDENCE["G"]},
}
_OWNER_BY_GATE_KIND[("A", "SOURCE_AUTHORITY")] = "SOURCE_ADMISSION_EVIDENCE_TOOL"
for _source_kind in _REQUIRED_EVIDENCE["B"]:
    _OWNER_BY_GATE_KIND[("B", _source_kind)] = "SOURCE_ADMISSION_EVIDENCE_TOOL"
_OWNER_BY_GATE_KIND[("C", "RELEASE_ACCOUNTING")] = "RELEASE_ACCOUNTING_EVIDENCE_TOOL"
_OWNER_BY_GATE_KIND[("D", "MODEL_EVALUATION_RUN_1")] = "PROVIDER_ADMISSION_TOOL"
_OWNER_BY_GATE_KIND[("D", "MODEL_EVALUATION_RUN_2")] = "PROVIDER_ADMISSION_TOOL"
_OWNER_BY_GATE_KIND[("D", "EMBEDDING_PROFILE")] = "PROMOTION_WORKER"
_OWNER_BY_GATE_KIND[("E", "REVIEW")] = "REVIEW_API"
_OWNER_BY_GATE_KIND[("E", "APPROVAL")] = "REVIEW_API"
_OWNER_BY_GATE_KIND[("E", "APPROVAL_INVALIDATION")] = "REVIEW_API"
_OWNER_BY_GATE_KIND[("G", "APPROVAL")] = "REVIEW_API"
for _operational_kind in _REQUIRED_EVIDENCE["F"]:
    _OWNER_BY_GATE_KIND[("F", _operational_kind)] = "OPERATIONAL_EVIDENCE_TOOL"
for _lineage_kind in _REQUIRED_EVIDENCE["G"]:
    _OWNER_BY_GATE_KIND[("G", _lineage_kind)] = "OPERATIONAL_EVIDENCE_TOOL"
_OWNER_BY_GATE_KIND[("G", "APPROVAL")] = "REVIEW_API"
_APPROVAL_COMMAND_KEYS = frozenset(
    {
        "action",
        "approval_id",
        "decision_fingerprint",
        "expected_review_version",
        "proposal_package_id",
        "reviewer_subject",
    }
)
_APPROVAL_DECISION_KEYS = frozenset(
    {
        "approval_id",
        "authority_evidence_ref",
        "decision",
        "decision_time",
        "expected_base_serving_state_ref",
        "governance_policy_state",
        "immutable",
        "promotion_manifest_ref",
        "reason",
        "reviewer_identity_ref",
        "schema_id",
        "schema_version",
        "valid_from",
        "validity_condition_refs",
    }
)
_READINESS_KEYS = frozenset(
    {
        "backup_profile_fingerprint",
        "embedding_profile_fingerprint",
        "fingerprint",
        "limitations",
        "model_evaluation_ref",
        "model_profile_fingerprint",
        "native_backup_ref",
        "proposal_fingerprint",
        "recovery_backup_ref",
        "retrieval_evaluation_ref",
        "retryable_count",
        "rollback_state_id",
        "schema_id",
        "scope_dispositions",
        "serving_profile_fingerprint",
        "target_members",
        "target_name",
        "target_namespace",
        "zero_record_scope_ids",
    }
)
_PROPOSAL_KEYS = frozenset(
    {
        "acquisition_manifests",
        "completeness_fingerprint",
        "coverage_report_fingerprint",
        "embedding_capability_evidence_ref",
        "embedding_invocation_count",
        "embedding_profile_fingerprint",
        "explicit_exclusions",
        "fingerprint",
        "included_material_families",
        "model_capability_evidence_ref",
        "model_invocation_count",
        "model_profile_fingerprint",
        "observation_cutoff",
        "prepared_batches",
        "release_state",
        "schema_id",
        "scope_ids",
        "status",
    }
)
_SERVING_STATE_KEYS = frozenset({"activation", "active_state_id", "rollback", "schema_id"})
_SERVING_CANDIDATE_KEYS = frozenset(
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


class RetainedEvidenceReader(Protocol):
    """Read-only boundary for exact immutable local evidence bytes."""

    def read_bytes(self, immutable_ref: str) -> bytes:
        """Read the exact bytes at one admitted local immutable reference."""
        ...


@dataclass(frozen=True, slots=True)
class _ExactBytesProfileReader:
    """Expose one retained proof through the repositories' exact profile-reader port."""

    reference: ImmutableReference
    content: bytes

    def read_exact(self, reference: ImmutableReference) -> bytes:
        if reference != self.reference:
            message = "PROFILE_REFERENCE_MISMATCH"
            raise ValueError(message)
        return self.content


@dataclass(frozen=True, slots=True)
class LocalRetainedEvidenceReader:
    """Confined file-backed evidence reader for Task 10 local admission."""

    root: Path

    def read_bytes(self, immutable_ref: str) -> bytes:
        """Read one no-symlink file below the configured evidence root."""
        relative = _local_evidence_path(immutable_ref)
        if self.root.is_symlink():
            message = "EVIDENCE_ROOT_SYMLINK"
            raise ValueError(message)
        resolved_root = self.root.resolve(strict=True)
        path = resolved_root.joinpath(*relative.parts)
        cursor = resolved_root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                message = "EVIDENCE_PATH_SYMLINK"
                raise ValueError(message)
        resolved_path = path.resolve(strict=True)
        if not resolved_path.is_relative_to(resolved_root) or not resolved_path.is_file():
            message = "EVIDENCE_PATH_INVALID"
            raise ValueError(message)
        raw = resolved_path.read_bytes()
        if not raw or len(raw) > _MAX_OWNING_PROOF_BYTES:
            message = "EVIDENCE_BYTES_INVALID"
            raise ValueError(message)
        return raw


@dataclass(frozen=True, slots=True)
class _ReadbackContext:
    prefix: str
    gate: GateName
    reference: RetainedEvidenceRef
    admission: HKV1AdmissionEvidence
    reader: RetainedEvidenceReader


@dataclass(frozen=True, slots=True)
class _Task8LedgerEvent:
    record: dict[str, object]
    decision: dict[str, object]
    command: dict[str, object]
    proposal_raw: bytes | None
    readiness_raw: bytes | None
    event_fingerprint: str


class GateState(StrEnum):
    """Derived gate state; input evidence cannot assert it."""

    PASSED = "PASSED"
    INCOMPLETE_RETRYABLE = "INCOMPLETE_RETRYABLE"
    REJECTED = "REJECTED"
    MISSING = "MISSING"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class RetainedEvidenceRef:
    """One immutable, fingerprinted proof produced by an owning boundary."""

    evidence_id: str
    evidence_kind: str
    immutable_ref: str
    fingerprint: str
    subject_fingerprint: str

    def document(self) -> dict[str, object]:
        """Return the canonical retained-reference projection."""
        return {
            "evidence_id": self.evidence_id,
            "evidence_kind": self.evidence_kind,
            "fingerprint": self.fingerprint,
            "immutable_ref": self.immutable_ref,
            "subject_fingerprint": self.subject_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class GateEvidence:
    """Accounting and independently retained proofs offered for one gate."""

    gate: GateName
    subject_fingerprint: str
    families: tuple[str, ...]
    scopes: tuple[str, ...]
    expected: int
    discovered: int
    verified: int
    retryable: int
    rejected: int
    terminal: int
    evidence_refs: tuple[RetainedEvidenceRef, ...]

    def document(self) -> dict[str, object]:
        """Return the canonical evidence projection used for fingerprinting."""
        return {
            "discovered": self.discovered,
            "evidence_refs": [item.document() for item in self.evidence_refs],
            "expected": self.expected,
            "families": list(self.families),
            "gate": self.gate,
            "rejected": self.rejected,
            "retryable": self.retryable,
            "scopes": list(self.scopes),
            "subject_fingerprint": self.subject_fingerprint,
            "terminal": self.terminal,
            "verified": self.verified,
        }


@dataclass(frozen=True, slots=True)
class HKV1AdmissionEvidence:
    """Complete identity and Gate A-G inputs for one two-family admission."""

    gates: tuple[GateEvidence, ...]
    common_cutoff: str
    coverage_matrix_fingerprint: str
    proposal_fingerprint: str
    model_profile_fingerprint: str
    embedding_profile_fingerprint: str
    serving_profile_fingerprint: str
    approval_fingerprint: str
    serving_state_id: str
    target_name: str
    target_fingerprint: str

    def document(self) -> dict[str, object]:
        """Return the canonical complete evidence projection."""
        return {
            "approval_fingerprint": self.approval_fingerprint,
            "common_cutoff": self.common_cutoff,
            "coverage_matrix_fingerprint": self.coverage_matrix_fingerprint,
            "embedding_profile_fingerprint": self.embedding_profile_fingerprint,
            "gates": [item.document() for item in self.gates],
            "proposal_fingerprint": self.proposal_fingerprint,
            "model_profile_fingerprint": self.model_profile_fingerprint,
            "serving_profile_fingerprint": self.serving_profile_fingerprint,
            "serving_state_id": self.serving_state_id,
            "target_fingerprint": self.target_fingerprint,
            "target_name": self.target_name,
        }


@dataclass(frozen=True, slots=True)
class HKV1GateResult:
    """One derived gate verdict with its exact retained evidence inventory."""

    gate: GateName
    state: GateState
    expected: int
    discovered: int
    verified: int
    retryable: int
    rejected: int
    terminal: int
    evidence_refs: tuple[RetainedEvidenceRef, ...]
    blocker_codes: tuple[str, ...]

    def document(self) -> dict[str, object]:
        """Return one canonical gate-result projection."""
        return {
            "blocker_codes": list(self.blocker_codes),
            "discovered": self.discovered,
            "evidence_refs": [item.document() for item in self.evidence_refs],
            "expected": self.expected,
            "gate": self.gate,
            "rejected": self.rejected,
            "retryable": self.retryable,
            "state": self.state.value,
            "terminal": self.terminal,
            "verified": self.verified,
        }


@dataclass(frozen=True, slots=True)
class HKV1LiveAdmissionReport:
    """Canonical consolidated evidence and the only V1 admission verdict."""

    result: Literal["V1_ADMITTED", "NOT_ADMITTED"]
    admitted: bool
    gate_results: tuple[HKV1GateResult, ...]
    blocker_codes: tuple[str, ...]
    common_cutoff: str
    coverage_matrix_fingerprint: str
    proposal_fingerprint: str
    model_profile_fingerprint: str
    embedding_profile_fingerprint: str
    serving_profile_fingerprint: str
    approval_fingerprint: str
    serving_state_id: str
    target_name: str
    target_fingerprint: str
    evidence_fingerprint: str

    def document(self) -> dict[str, object]:
        """Return the complete deterministic report document."""
        return {
            "admitted": self.admitted,
            "approval_fingerprint": self.approval_fingerprint,
            "blocker_codes": list(self.blocker_codes),
            "common_cutoff": self.common_cutoff,
            "coverage_matrix_fingerprint": self.coverage_matrix_fingerprint,
            "embedding_profile_fingerprint": self.embedding_profile_fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
            "gate_results": [item.document() for item in self.gate_results],
            "proposal_fingerprint": self.proposal_fingerprint,
            "model_profile_fingerprint": self.model_profile_fingerprint,
            "result": self.result,
            "serving_profile_fingerprint": self.serving_profile_fingerprint,
            "serving_state_id": self.serving_state_id,
            "target_fingerprint": self.target_fingerprint,
            "target_name": self.target_name,
        }


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _local_evidence_path(immutable_ref: str) -> PurePosixPath:
    if _IMMUTABLE_REF.fullmatch(immutable_ref) is None:
        message = "EVIDENCE_REF_INVALID"
        raise ValueError(message)
    value = immutable_ref.removeprefix("local-evidence://")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        message = "EVIDENCE_REF_INVALID"
        raise ValueError(message)
    return relative


def _valid_timestamp(value: str) -> bool:
    if _TIMESTAMP.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.utcoffset() == timedelta(hours=8) and parsed.microsecond == 0


def _instant(value: object) -> datetime | None:
    if type(value) is not str:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.utcoffset() is None or parsed.microsecond != 0:
        return None
    return parsed


def _strict_document(raw: bytes, keys: frozenset[str]) -> dict[str, object] | None:
    duplicate = False

    def object_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        nonlocal duplicate
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                duplicate = True
            result[key] = value
        return result

    try:
        value: object = json.loads(raw, object_pairs_hook=object_hook)
    except UnicodeDecodeError, json.JSONDecodeError:
        return None
    if duplicate or not isinstance(value, dict):
        return None
    candidate = cast("dict[object, object]", value)
    if not all(type(key) is str for key in candidate):
        return None
    document = cast("dict[str, object]", candidate)
    if frozenset(document) != keys or raw != _canonical_bytes(document):
        return None
    return document


def _valid_fingerprint(value: str) -> bool:
    return _FINGERPRINT.fullmatch(value) is not None


def _missing_result(gate: GateName) -> HKV1GateResult:
    blocker = f"GATE_{gate}_MISSING"
    return HKV1GateResult(gate, GateState.MISSING, 0, 0, 0, 0, 0, 0, (), (blocker,))


def _gate_identity_findings(evidence: GateEvidence) -> set[str]:
    prefix = f"GATE_{evidence.gate}_"
    findings: set[str] = set()
    if evidence.families != EXPECTED_FAMILIES:
        findings.add(prefix + "FAMILY_UNIVERSE_INVALID")
    if evidence.scopes != EXPECTED_SCOPES:
        findings.add(prefix + "SCOPE_UNIVERSE_INVALID")
    if not _valid_fingerprint(evidence.subject_fingerprint):
        findings.add(prefix + "SUBJECT_FINGERPRINT_INVALID")
    if evidence.expected <= 0 or (
        evidence.gate in {"A", "C"} and evidence.expected != len(EXPECTED_SCOPES)
    ):
        findings.add(prefix + "EXPECTED_COUNT_INVALID")
    return findings


def _gate_arithmetic_invalid(evidence: GateEvidence) -> bool:
    counts = (
        evidence.discovered,
        evidence.verified,
        evidence.retryable,
        evidence.rejected,
        evidence.terminal,
    )
    return any(type(item) is not int or item < 0 for item in counts) or (
        evidence.discovered != evidence.verified + evidence.retryable + evidence.rejected
        or evidence.terminal != evidence.verified + evidence.rejected
        or (evidence.expected > 0 and evidence.discovered > evidence.expected)
    )


def _verify_reference(
    prefix: str,
    gate: GateName,
    reference: RetainedEvidenceRef,
    admission: HKV1AdmissionEvidence,
    reader: RetainedEvidenceReader,
) -> tuple[set[str], str | None, tuple[str, str] | None]:
    findings: set[str] = set()
    try:
        raw = reader.read_bytes(reference.immutable_ref)
    except OSError, ValueError:
        return {prefix + "EVIDENCE_READBACK_FAILED"}, None, None
    if type(raw) is not bytes or not raw or len(raw) > _MAX_ADMISSION_BYTES:
        return {prefix + "EVIDENCE_READBACK_FAILED"}, None, None
    if "sha256:" + sha256(raw).hexdigest() != reference.fingerprint:
        findings.add(prefix + "EVIDENCE_BYTES_MISMATCH")
    envelope = _strict_document(raw, _ENVELOPE_KEYS)
    if envelope is None:
        return findings | {prefix + "EVIDENCE_ENVELOPE_INVALID"}, None, None
    expected: dict[str, object] = {
        "approval_fingerprint": admission.approval_fingerprint,
        "common_cutoff": admission.common_cutoff,
        "coverage_matrix_fingerprint": admission.coverage_matrix_fingerprint,
        "embedding_profile_fingerprint": admission.embedding_profile_fingerprint,
        "evidence_id": reference.evidence_id,
        "evidence_kind": reference.evidence_kind,
        "immutable_ref": reference.immutable_ref,
        "model_profile_fingerprint": admission.model_profile_fingerprint,
        "proposal_fingerprint": admission.proposal_fingerprint,
        "schema_version": 1,
        "serving_profile_fingerprint": admission.serving_profile_fingerprint,
        "serving_state_id": admission.serving_state_id,
        "subject_fingerprint": reference.subject_fingerprint,
        "target_fingerprint": admission.target_fingerprint,
        "target_name": admission.target_name,
    }
    if any(envelope.get(key) != value for key, value in expected.items()):
        findings.add(prefix + "EVIDENCE_LINEAGE_MISMATCH")
    producer_ref = envelope.get("producer_evidence_ref")
    producer_fingerprint = envelope.get("producer_evidence_fingerprint")
    if (
        not isinstance(producer_ref, str)
        or not isinstance(producer_fingerprint, str)
        or not _valid_fingerprint(producer_fingerprint)
        or producer_ref == reference.immutable_ref
    ):
        return findings | {prefix + "PRODUCER_EVIDENCE_BINDING_INVALID"}, None, None
    try:
        _local_evidence_path(producer_ref)
        producer_raw = reader.read_bytes(producer_ref)
    except OSError, ValueError:
        return findings | {prefix + "PRODUCER_EVIDENCE_READBACK_FAILED"}, producer_ref, None
    proof_binding: tuple[str, str] | None = None
    if (
        type(producer_raw) is not bytes
        or not producer_raw
        or len(producer_raw) > _MAX_ADMISSION_BYTES
        or "sha256:" + sha256(producer_raw).hexdigest() != producer_fingerprint
    ):
        findings.add(prefix + "PRODUCER_EVIDENCE_BYTES_MISMATCH")
    else:
        receipt_findings, proof_binding = _verify_producer_receipt(
            _ReadbackContext(prefix, gate, reference, admission, reader),
            producer_ref,
            producer_raw,
        )
        findings.update(receipt_findings)
    return findings, producer_ref, proof_binding


def _verify_producer_receipt(
    context: _ReadbackContext,
    producer_ref: str,
    producer_raw: bytes,
) -> tuple[set[str], tuple[str, str] | None]:
    findings: set[str] = set()
    producer = _strict_document(producer_raw, _PRODUCER_RECEIPT_KEYS)
    if producer is None:
        return {context.prefix + "PRODUCER_EVIDENCE_RECEIPT_INVALID"}, None
    expected_producer: dict[str, object] = {
        "approval_fingerprint": context.admission.approval_fingerprint,
        "common_cutoff": context.admission.common_cutoff,
        "coverage_matrix_fingerprint": context.admission.coverage_matrix_fingerprint,
        "embedding_profile_fingerprint": context.admission.embedding_profile_fingerprint,
        "evidence_id": context.reference.evidence_id,
        "evidence_kind": context.reference.evidence_kind,
        "gate": context.gate,
        "model_profile_fingerprint": context.admission.model_profile_fingerprint,
        "producer": "ADMISSION_ASSEMBLER",
        "proof_owner": _OWNER_BY_GATE_KIND.get((context.gate, context.reference.evidence_kind)),
        "proposal_fingerprint": context.admission.proposal_fingerprint,
        "result": "VERIFIED",
        "schema_id": "asklegal.hk-v1-retained-producer-evidence",
        "schema_version": 1,
        "serving_profile_fingerprint": context.admission.serving_profile_fingerprint,
        "serving_state_id": context.admission.serving_state_id,
        "subject_fingerprint": context.reference.subject_fingerprint,
        "target_fingerprint": context.admission.target_fingerprint,
        "target_name": context.admission.target_name,
    }
    if any(producer.get(key) != value for key, value in expected_producer.items()):
        findings.add(context.prefix + "PRODUCER_EVIDENCE_LINEAGE_MISMATCH")
    proof_ref = producer.get("proof_ref")
    proof_fingerprint = producer.get("proof_fingerprint")
    if (
        type(proof_ref) is not str
        or type(proof_fingerprint) is not str
        or not _valid_fingerprint(proof_fingerprint)
        or proof_ref in {context.reference.immutable_ref, producer_ref}
    ):
        return findings | {context.prefix + "PRODUCER_PROOF_BINDING_INVALID"}, None
    try:
        _local_evidence_path(proof_ref)
        proof_raw = context.reader.read_bytes(proof_ref)
    except OSError, ValueError:
        return findings | {context.prefix + "PRODUCER_PROOF_READBACK_FAILED"}, None
    if (
        type(proof_raw) is not bytes
        or not proof_raw
        or len(proof_raw) > _MAX_OWNING_PROOF_BYTES
        or "sha256:" + sha256(proof_raw).hexdigest() != proof_fingerprint
    ):
        findings.add(context.prefix + "PRODUCER_PROOF_BYTES_MISMATCH")
    elif context.reference.evidence_kind == "APPROVAL":
        findings.update(_verify_task8_approval_ledger(context, proof_raw))
    else:
        findings.update(_verify_gate_proof(context, proof_raw))
    return findings, (proof_ref, proof_fingerprint)


def _exact_profile_reader(raw: bytes) -> _ExactBytesProfileReader:
    digest = sha256(raw).hexdigest()
    return _ExactBytesProfileReader(
        ImmutableReference(
            ReferenceType.CAPABILITY_PROFILE,
            "cap_" + digest[:48],
            "sha256:" + digest,
        ),
        raw,
    )


def _verify_coverage_matrix(context: _ReadbackContext, raw: bytes) -> set[str]:
    try:
        repository_bytes = (
            files("asklegal_reporting").joinpath("hk_v1_coverage_matrix.json").read_bytes()
        )
        matrix = load_hk_v1_coverage_matrix()
    except OSError, TypeError, ValueError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if raw != repository_bytes:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if (
        not is_hk_v1_coverage_matrix_issued(matrix)
        or not is_hk_v1_coverage_matrix_policy_approved(matrix)
        or evaluate_hk_v1_scope_gate(matrix).result != "ADMITTED"
        or matrix.fingerprint != context.admission.coverage_matrix_fingerprint
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_release_accounting(context: _ReadbackContext, raw: bytes) -> set[str]:
    try:
        live = parse_live_release_accounting(raw)
    except LiveReleaseAccountingError:
        live = None
    if live is not None:
        if (
            live.observation_cutoff != context.admission.common_cutoff
            or live.proposal_fingerprint != context.admission.proposal_fingerprint
        ):
            return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
        return set()
    try:
        report = parse_hk_v1_two_family_coverage_report(raw)
    except HongKongV1CoverageError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if (
        report.observation_cutoff != context.admission.common_cutoff
        or report.included_material_families != EXPECTED_FAMILIES
        or report.scope_ids != EXPECTED_SCOPES
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return {context.prefix + "OWNING_PROOF_NOT_LIVE"}


def _verify_source_authority(context: _ReadbackContext, raw: bytes) -> set[str]:
    """Require exact, re-read source reports for all V1 authority families."""
    try:
        evidence = parse_source_authority_evidence(raw)
    except SourceAdmissionEvidenceError, TypeError, ValueError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if evidence.observation_cutoff != context.admission.common_cutoff:
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_source_exercises(context: _ReadbackContext, raw: bytes) -> set[str]:
    """Require the closed six-scenario aggregate built from source-owner reports."""
    try:
        evidence = parse_source_exercise_evidence(raw)
    except SourceAdmissionEvidenceError, TypeError, ValueError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if (
        evidence.observation_cutoff != context.admission.common_cutoff
        or context.reference.evidence_kind not in evidence.scenario_names
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_package_readiness(context: _ReadbackContext, raw: bytes) -> set[str]:
    """Verify the exact frozen Task 7 proposal without inferring Review or Approval."""
    proposal = _strict_document(raw, _PROPOSAL_KEYS)
    if proposal is None:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    unsigned = {key: value for key, value in proposal.items() if key != "fingerprint"}
    if (
        proposal.get("schema_id") != "asklegal.hk-v1-two-family-proposal-manifest/v1"
        or proposal.get("status") != "FROZEN_PROPOSAL_READY_FOR_REVIEW"
        or proposal.get("release_state") != "WITHHELD_PENDING_NAMED_HUMAN_REVIEW"
        or proposal.get("fingerprint") != "sha256:" + sha256(_canonical_bytes(unsigned)).hexdigest()
        or proposal.get("fingerprint") != context.admission.proposal_fingerprint
        or proposal.get("observation_cutoff") != context.admission.common_cutoff
        or proposal.get("included_material_families") != list(EXPECTED_FAMILIES)
        or proposal.get("scope_ids") != list(EXPECTED_SCOPES)
        or proposal.get("model_profile_fingerprint") != context.admission.model_profile_fingerprint
        or proposal.get("embedding_profile_fingerprint")
        != context.admission.embedding_profile_fingerprint
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_review_readiness(context: _ReadbackContext, raw: bytes) -> set[str]:
    """Verify Review's frozen readiness projection against the consolidated lineage."""
    readiness = _strict_document(raw, _READINESS_KEYS)
    if readiness is None:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    unsigned = dict(readiness)
    observed = unsigned.pop("fingerprint", None)
    unsigned.pop("schema_id", None)
    if (
        readiness.get("schema_id") != "asklegal.hk-v1-review-readiness/v1"
        or observed != "sha256:" + sha256(_canonical_bytes(unsigned)).hexdigest()
        or readiness.get("proposal_fingerprint") != context.admission.proposal_fingerprint
        or readiness.get("model_profile_fingerprint") != context.admission.model_profile_fingerprint
        or readiness.get("embedding_profile_fingerprint")
        != context.admission.embedding_profile_fingerprint
        or readiness.get("serving_profile_fingerprint")
        != context.admission.serving_profile_fingerprint
        or readiness.get("target_name") != context.admission.target_name
        or readiness.get("retryable_count") != 0
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_semantic_profile(context: _ReadbackContext, raw: bytes) -> set[str]:
    try:
        profile = load_semantic_profile_set(_exact_profile_reader(raw))
    except SemanticProfileError, TypeError, ValueError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if profile.fingerprint != context.admission.model_profile_fingerprint:
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    if context.reference.evidence_kind == "MODEL_PROFILE" and not profile.profiles:
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    if (
        context.reference.evidence_kind == "TOKENIZER_PROFILE"
        and not profile.tokenizer_specifications
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_embedding_profile(context: _ReadbackContext, raw: bytes) -> set[str]:
    try:
        profile = load_serving_capability_profile(_exact_profile_reader(raw))
    except ServingProfileError, TypeError, ValueError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if (
        profile.fingerprint != context.admission.serving_profile_fingerprint
        or profile.embedding.profile_fingerprint != context.admission.embedding_profile_fingerprint
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_provider_admission(context: _ReadbackContext, raw: bytes) -> set[str]:
    """Bind two complete repeat executions to the consolidated lineage."""
    try:
        receipt = parse_provider_admission_evidence(raw)
    except ProviderAdmissionError, TypeError, ValueError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if (
        receipt.observation_cutoff != context.admission.common_cutoff
        or receipt.proposal_fingerprint != context.admission.proposal_fingerprint
        or receipt.semantic_profile_fingerprint != context.admission.model_profile_fingerprint
        or receipt.embedding_profile_fingerprint != context.admission.embedding_profile_fingerprint
        or receipt.serving_profile_fingerprint != context.admission.serving_profile_fingerprint
        or receipt.target_name != context.admission.target_name
        or receipt.target_fingerprint != context.admission.target_fingerprint
        or receipt.semantic_case_count != EXPECTED_PROVIDER_SEMANTIC_CASES
        or receipt.retrieval_case_count != EXPECTED_PROVIDER_RETRIEVAL_CASES
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_task8_invalidation_ledger(context: _ReadbackContext, raw: bytes) -> set[str]:
    """Require an exact historical invalidation alongside the selected current Approval."""
    findings = _verify_task8_approval_ledger(context, raw)
    if findings:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    ledger = _strict_document(raw, frozenset({"approval_states", "events", "revoked", "schema_id"}))
    if ledger is None or not isinstance(ledger.get("approval_states"), dict):
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    states = cast("dict[object, object]", ledger["approval_states"])
    if not any(
        type(value) is dict
        and cast("dict[object, object]", value).get("state") == "APPROVAL_INVALIDATED"
        for value in states.values()
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_active_serving_state(  # noqa: PLR0911 - closed state parser exits fail early.
    context: _ReadbackContext, raw: bytes
) -> set[str]:
    """Verify Promotion's canonical activated Serving State and its CAS receipt."""
    state = _strict_document(raw, _SERVING_STATE_KEYS)
    if state is None or state.get("schema_id") != "asklegal.local-serving-state/v1":
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    activation_value = state.get("activation")
    if type(activation_value) is not dict:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    activation = cast("dict[object, object]", activation_value)
    if set(activation) != {"candidate", "receipt_id"}:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    candidate_value = activation.get("candidate")
    if type(candidate_value) is not dict:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    candidate = cast("dict[object, object]", candidate_value)
    if frozenset(candidate) != _SERVING_CANDIDATE_KEYS:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    candidate_document = cast("dict[str, object]", candidate)
    state_id = candidate_document.get("candidate_serving_state_id")
    predecessor = candidate_document.get("predecessor_state_id")
    state_fingerprint = candidate_document.get("candidate_serving_state_fingerprint")
    if not all(
        type(value) is str and bool(value) for value in (state_id, predecessor, state_fingerprint)
    ):
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    receipt_material = _canonical_bytes(
        {
            "candidate_fingerprint": state_fingerprint,
            "operation": "ACTIVATED",
            "predecessor_state_id": predecessor,
            "state_id": state_id,
        }
    )
    expected_receipt = "ssr_" + sha256(receipt_material).hexdigest()[:48]
    if (
        state.get("rollback") is not None
        or state.get("active_state_id") != context.admission.serving_state_id
        or state_id != context.admission.serving_state_id
        or candidate_document.get("target_name") != context.admission.target_name
        or candidate_document.get("embedding_profile_fingerprint")
        != context.admission.embedding_profile_fingerprint
        or activation.get("receipt_id") != expected_receipt
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_operational_composite(context: _ReadbackContext, raw: bytes) -> set[str]:
    """Reparse every F/G owner artifact carried by its exact closed aggregate."""
    try:
        untrusted: object = json.loads(raw)
    except UnicodeDecodeError, json.JSONDecodeError:
        untrusted = None
    if isinstance(untrusted, dict):
        generic = cast("dict[object, object]", untrusted).get("schema_id")
        if type(generic) is str and generic.startswith("asklegal.hk-v1-gate-proof/"):
            return {context.prefix + "OWNING_PROOF_UNAVAILABLE"}
    try:
        if context.gate == "F":
            evidence = parse_gate_f_operational_evidence(raw)
            if evidence.serving_state_id != context.admission.serving_state_id:
                return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
            return set()
        evidence = parse_gate_g_live_lineage(raw)
    except OperationalEvidenceError, TypeError, ValueError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if (
        evidence.current_serving_state_id != context.admission.serving_state_id
        or evidence.proposal_fingerprint != context.admission.proposal_fingerprint
        or evidence.approval_fingerprint != context.admission.approval_fingerprint
        or evidence.target_name != context.admission.target_name
        or evidence.target_fingerprint != context.admission.target_fingerprint
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_promotion_readback(context: _ReadbackContext, raw: bytes) -> set[str]:
    """Bind Promotion's terminal owner artifact to the admitted package and target."""
    try:
        evidence = parse_promotion_readback(raw)
    except PromotionEvidenceError, TypeError, ValueError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    expected_operation = (
        "ROLLBACK" if context.reference.evidence_kind == "ROLLBACK" else "PROMOTION"
    )
    if (
        evidence.operation != expected_operation
        or evidence.proposal_fingerprint != context.admission.proposal_fingerprint
        or evidence.approval_fingerprint != context.admission.approval_fingerprint
        or (
            expected_operation == "PROMOTION"
            and (
                evidence.serving_state_id != context.admission.serving_state_id
                or evidence.target_name != context.admission.target_name
                or evidence.target_fingerprint != context.admission.target_fingerprint
            )
        )
        or (
            expected_operation == "ROLLBACK"
            and (
                evidence.predecessor_serving_state_id != context.admission.serving_state_id
                or evidence.predecessor_target_name != context.admission.target_name
                or evidence.predecessor_target_fingerprint != context.admission.target_fingerprint
                or evidence.serving_state_id == context.admission.serving_state_id
                or evidence.target_name == context.admission.target_name
                or evidence.target_fingerprint == context.admission.target_fingerprint
            )
        )
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_promotion_failure_stop(context: _ReadbackContext, raw: bytes) -> set[str]:
    """Bind an exact no-state-change Promotion failure to the selected package."""
    try:
        evidence = parse_promotion_failure_stop(raw)
    except PromotionEvidenceError, TypeError, ValueError:
        return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
    if (
        evidence.proposal_fingerprint != context.admission.proposal_fingerprint
        or evidence.approval_fingerprint != context.admission.approval_fingerprint
    ):
        return {context.prefix + "OWNING_PROOF_SEMANTICS_INVALID"}
    return set()


def _verify_gate_proof(  # noqa: C901, PLR0911, PLR0912 - closed owning-proof parser dispatch.
    context: _ReadbackContext, raw: bytes
) -> set[str]:
    try:
        untrusted: object = json.loads(raw)
    except UnicodeDecodeError, json.JSONDecodeError:
        untrusted = None
    if isinstance(untrusted, dict):
        generic = cast("dict[object, object]", untrusted)
        schema = generic.get("schema_id")
        if type(schema) is str and schema.startswith("asklegal.hk-v1-gate-proof/"):
            if generic.get("owner") != _OWNER_BY_GATE_KIND.get(
                (context.gate, context.reference.evidence_kind)
            ):
                return {context.prefix + "OWNING_PROOF_SCHEMA_INVALID"}
            return {context.prefix + "OWNING_PROOF_UNAVAILABLE"}
    key = (context.gate, context.reference.evidence_kind)
    if key == ("A", "COVERAGE_MATRIX"):
        return _verify_coverage_matrix(context, raw)
    if key == ("A", "SOURCE_AUTHORITY"):
        return _verify_source_authority(context, raw)
    if context.gate == "B":
        return _verify_source_exercises(context, raw)
    if key == ("C", "RELEASE_ACCOUNTING"):
        return _verify_release_accounting(context, raw)
    if key == ("C", "PACKAGE_READINESS"):
        return _verify_package_readiness(context, raw)
    if key in {("D", "MODEL_PROFILE"), ("D", "TOKENIZER_PROFILE")}:
        return _verify_semantic_profile(context, raw)
    if key == ("D", "EMBEDDING_PROFILE"):
        return _verify_embedding_profile(context, raw)
    if key in {("D", "MODEL_EVALUATION_RUN_1"), ("D", "MODEL_EVALUATION_RUN_2")}:
        return _verify_provider_admission(context, raw)
    if key == ("E", "REVIEW"):
        return _verify_review_readiness(context, raw)
    if key == ("E", "APPROVAL_INVALIDATION"):
        return _verify_task8_invalidation_ledger(context, raw)
    if key in {("E", "PROMOTION"), ("E", "REPLACEMENT_TARGET")}:
        return _verify_active_serving_state(context, raw)
    if key in {("E", "BACKUP"), ("E", "READ_BACK"), ("E", "ROLLBACK")}:
        return _verify_promotion_readback(context, raw)
    if key == ("E", "PROMOTION_FAILURE_STOP"):
        return _verify_promotion_failure_stop(context, raw)
    if context.gate in {"F", "G"}:
        return _verify_operational_composite(context, raw)
    return {context.prefix + "OWNING_PROOF_UNAVAILABLE"}


def _reference_tuple(value: object) -> tuple[str, str, str] | None:
    if not isinstance(value, dict):
        return None
    candidate = cast("dict[object, object]", value)
    if set(candidate) != {"fingerprint", "ref_id", "ref_type"}:
        return None
    document = cast("dict[str, object]", candidate)
    ref_type = document.get("ref_type")
    ref_id = document.get("ref_id")
    fingerprint = document.get("fingerprint")
    if (
        type(ref_type) is not str
        or type(ref_id) is not str
        or type(fingerprint) is not str
        or not _valid_fingerprint(fingerprint)
    ):
        return None
    return ref_type, ref_id, fingerprint


def _valid_approval_predicates(
    value: object, proposal_fingerprint: str, readiness_fingerprint: str
) -> bool:
    if not isinstance(value, list):
        return False
    items = cast("list[object]", value)
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            return False
        candidate = cast("dict[object, object]", item)
        if set(candidate) != {"contract_id", "fingerprint", "version"}:
            return False
        document = cast("dict[str, object]", candidate)
        contract_id = document.get("contract_id")
        version = document.get("version")
        fingerprint = document.get("fingerprint")
        if (
            type(contract_id) is not str
            or not contract_id
            or type(version) is not str
            or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
            or type(fingerprint) is not str
            or not _valid_fingerprint(fingerprint)
        ):
            return False
        key = (contract_id, version, fingerprint)
        if key in seen:
            return False
        seen.add(key)
    return seen == {
        ("HK_V1_TWO_FAMILY_PROPOSAL", "1.0.0", proposal_fingerprint),
        ("HK_V1_REVIEW_READINESS", "1.0.0", readiness_fingerprint),
    }


def _approval_event_document(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    candidate = cast("dict[object, object]", value)
    if set(candidate) != {
        "command_bytes",
        "command_id",
        "event_bytes",
        "proposal_bytes",
        "readiness_bytes",
        "target_id",
        "winner_key",
    }:
        return None
    return cast("dict[str, object]", candidate)


def _approval_event_decision(  # noqa: C901, PLR0911, PLR0912 - closed event/command parser.
    value: object,
) -> _Task8LedgerEvent | None:
    document = _approval_event_document(value)
    if document is None:
        return None
    event_hex = document.get("event_bytes")
    command_hex = document.get("command_bytes")
    if type(event_hex) is not str or type(command_hex) is not str:
        return None
    try:
        event_raw = bytes.fromhex(event_hex)
        command_raw = bytes.fromhex(command_hex)
    except ValueError:
        return None
    if not event_raw or not command_raw:
        return None
    decision = _strict_document(event_raw, _APPROVAL_DECISION_KEYS)
    if decision is None:
        decision = _strict_document(
            event_raw,
            _APPROVAL_DECISION_KEYS | {"review_readiness_fingerprint"},
        )
    command = _strict_document(command_raw, _APPROVAL_COMMAND_KEYS)
    if decision is None or command is None:
        return None
    decision_value = decision.get("decision")
    proposal_hex = document.get("proposal_bytes")
    readiness_hex = document.get("readiness_bytes")
    if decision_value == "APPROVED":
        if type(proposal_hex) is not str or type(readiness_hex) is not str:
            return None
        try:
            proposal_raw = bytes.fromhex(proposal_hex)
            readiness_raw = bytes.fromhex(readiness_hex)
        except ValueError:
            return None
        if not proposal_raw or not readiness_raw:
            return None
    elif decision_value == "REJECTED":
        if proposal_hex is not None or readiness_hex is not None:
            return None
        proposal_raw = None
        readiness_raw = None
    else:
        return None
    promotion = _reference_tuple(decision.get("promotion_manifest_ref"))
    reviewer = _reference_tuple(decision.get("reviewer_identity_ref"))
    approval_id = decision.get("approval_id")
    reviewer_subject = command.get("reviewer_subject")
    event_fingerprint = "sha256:" + sha256(event_raw).hexdigest()
    if (
        promotion is None
        or reviewer is None
        or type(approval_id) is not str
        or command.get("action") != "RECORD_PROPOSAL_DECISION"
        or command.get("approval_id") != approval_id
        or command.get("decision_fingerprint") != event_fingerprint
        or command.get("expected_review_version") != 0
        or command.get("proposal_package_id") != promotion[1]
        or type(reviewer_subject) is not str
        or reviewer_subject != reviewer[1]
        or document.get("target_id") != promotion[1]
        or document.get("winner_key") != "proposal-decision:" + promotion[1]
        or type(document.get("command_id")) is not str
        or _SAFE_ID.fullmatch(cast("str", document.get("command_id"))) is None
    ):
        return None
    return _Task8LedgerEvent(
        document,
        decision,
        command,
        proposal_raw,
        readiness_raw,
        event_fingerprint,
    )


def _approved_package_valid(  # noqa: PLR0911 - closed actual package validation stages.
    proposal_raw: bytes,
    readiness_raw: bytes,
    decision: dict[str, object],
    context: _ReadbackContext | None = None,
) -> tuple[bool, str, str]:
    proposal = _strict_document(proposal_raw, _PROPOSAL_KEYS)
    readiness = _strict_document(readiness_raw, _READINESS_KEYS)
    if proposal is None or readiness is None:
        return False, "", ""
    raw_members = readiness.get("target_members")
    if not isinstance(raw_members, list):
        return False, "", ""
    member_items = cast("list[object]", raw_members)
    record_ids: list[str] = []
    for item in member_items:
        if not isinstance(item, dict):
            return False, "", ""
        candidate = cast("dict[object, object]", item)
        if set(candidate) != {"material_family", "record_id", "scope_id"}:
            return False, "", ""
        record_id = candidate.get("record_id")
        if type(record_id) is not str or not record_id:
            return False, "", ""
        record_ids.append(record_id)
    if not record_ids or len(set(record_ids)) != len(record_ids):
        return False, "", ""
    try:
        package = verify_hk_v1_approved_package(
            proposal_raw,
            readiness_raw,
            tuple(record_ids),
        )
    except PromotionError, TypeError, ValueError:
        return False, "", ""
    readiness_fingerprint = readiness.get("fingerprint")
    if (
        type(readiness_fingerprint) is not str
        or package.review_readiness_fingerprint != readiness_fingerprint
        or (
            decision.get("decision") == "APPROVED"
            and decision.get("review_readiness_fingerprint") != readiness_fingerprint
        )
        or (
            decision.get("decision") == "REJECTED"
            and decision.get("review_readiness_fingerprint") is not None
        )
        or (
            context is not None
            and (
                package.proposal_fingerprint != context.admission.proposal_fingerprint
                or package.model_profile_fingerprint != context.admission.model_profile_fingerprint
                or package.embedding_profile_fingerprint
                != context.admission.embedding_profile_fingerprint
                or package.serving_profile_fingerprint
                != context.admission.serving_profile_fingerprint
                or package.target_name != context.admission.target_name
                or proposal.get("observation_cutoff") != context.admission.common_cutoff
            )
        )
    ):
        return False, "", ""
    return True, readiness_fingerprint, package.proposal_fingerprint


def _approval_readiness_predicate_fingerprint(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    fingerprints: set[str] = set()
    for item in cast("list[object]", value):
        if not isinstance(item, dict):
            continue
        candidate = cast("dict[object, object]", item)
        fingerprint = candidate.get("fingerprint")
        if candidate.get("contract_id") == "HK_V1_REVIEW_READINESS" and type(fingerprint) is str:
            fingerprints.add(fingerprint)
    if len(fingerprints) != 1:
        return None
    return fingerprints.pop()


def _approval_decision_intrinsic_valid(
    decision: dict[str, object],
    readiness_fingerprint: str | None = None,
    proposal_fingerprint: str | None = None,
) -> tuple[bool, str]:
    promotion = _reference_tuple(decision.get("promotion_manifest_ref"))
    reviewer = _reference_tuple(decision.get("reviewer_identity_ref"))
    authority = _reference_tuple(decision.get("authority_evidence_ref"))
    base = _reference_tuple(decision.get("expected_base_serving_state_ref"))
    approval_id = decision.get("approval_id")
    reason = decision.get("reason")
    readiness = decision.get("review_readiness_fingerprint")
    predicates = decision.get("validity_condition_refs")
    decision_value = decision.get("decision")
    decision_time = _instant(decision.get("decision_time"))
    valid_from = _instant(decision.get("valid_from"))
    if proposal_fingerprint is None and promotion is not None:
        proposal_fingerprint = promotion[2]
    if readiness_fingerprint is None:
        readiness_fingerprint = _approval_readiness_predicate_fingerprint(predicates)
    valid = (
        decision.get("schema_id") == "asklegal.approval-decision"
        and decision.get("schema_version") == "1.1.0"
        and decision_value in {"APPROVED", "REJECTED"}
        and decision.get("governance_policy_state") == "CONFIGURED"
        and decision.get("immutable") is True
        and isinstance(reason, str)
        and bool(reason.strip())
        and decision_time is not None
        and valid_from is not None
        and valid_from <= decision_time
        and promotion is not None
        and promotion[0] == "PROMOTION_MANIFEST"
        and re.fullmatch(r"pmn_[0-9a-f]{48}", promotion[1]) is not None
        and proposal_fingerprint is not None
        and promotion[2] == proposal_fingerprint
        and reviewer is not None
        and reviewer[0] == "ACTOR"
        and re.fullmatch(r"act_[0-9a-f]{48}", reviewer[1]) is not None
        and authority is not None
        and authority[0] == "EVIDENCE"
        and re.fullmatch(r"evi_[0-9a-f]{48}", authority[1]) is not None
        and base is not None
        and base[0] == "SERVING_STATE"
        and re.fullmatch(r"srv_[0-9a-f]{48}", base[1]) is not None
        and readiness_fingerprint is not None
        and (
            (decision_value == "APPROVED" and readiness == readiness_fingerprint)
            or (decision_value == "REJECTED" and readiness is None)
        )
        and _valid_approval_predicates(
            predicates,
            proposal_fingerprint,
            readiness_fingerprint,
        )
        and type(approval_id) is str
    )
    if not valid or promotion is None or type(approval_id) is not str:
        return False, ""
    expected_id = (
        "apr_"
        + sha256(
            "\x1f".join((promotion[1], promotion[2], cast("str", decision_value))).encode()
        ).hexdigest()[:48]
    )
    return approval_id == expected_id, approval_id


def _approval_decision_valid(
    decision: dict[str, object],
    context: _ReadbackContext,
    readiness_fingerprint: str,
    proposal_fingerprint: str,
) -> tuple[bool, str]:
    intrinsic, approval_id = _approval_decision_intrinsic_valid(
        decision,
        readiness_fingerprint,
        proposal_fingerprint,
    )
    promotion = _reference_tuple(decision.get("promotion_manifest_ref"))
    base = _reference_tuple(decision.get("expected_base_serving_state_ref"))
    valid = (
        intrinsic
        and decision.get("decision") == "APPROVED"
        and promotion is not None
        and promotion[2] == context.admission.proposal_fingerprint
        and base is not None
    )
    return valid, approval_id if valid else ""


def _verify_task8_approval_ledger(  # noqa: C901, PLR0911, PLR0912 - exact ledger gates.
    context: _ReadbackContext, raw: bytes
) -> set[str]:
    ledger = _strict_document(raw, frozenset({"approval_states", "events", "revoked", "schema_id"}))
    if ledger is None or ledger.get("schema_id") != "asklegal.local-review-approval-ledger/v1":
        return {context.prefix + "TASK8_APPROVAL_LEDGER_INVALID"}
    events = ledger.get("events")
    if not isinstance(events, list):
        return {context.prefix + "TASK8_APPROVAL_LEDGER_INVALID"}
    event_items = cast("list[object]", events)
    parsed_events = tuple(_approval_event_decision(item) for item in event_items)
    if not parsed_events or any(item is None for item in parsed_events):
        return {context.prefix + "TASK8_APPROVAL_COMMAND_INVALID"}
    valid_events = tuple(item for item in parsed_events if item is not None)
    approvals: dict[str, tuple[_Task8LedgerEvent, str, str]] = {}
    for item in valid_events:
        if item.decision.get("decision") == "APPROVED":
            if item.proposal_raw is None or item.readiness_raw is None:
                return {context.prefix + "TASK8_APPROVED_PACKAGE_INVALID"}
            package_valid, readiness_fingerprint, proposal_fingerprint = _approved_package_valid(
                item.proposal_raw,
                item.readiness_raw,
                item.decision,
            )
            intrinsic, approval_id = _approval_decision_intrinsic_valid(
                item.decision,
                readiness_fingerprint,
                proposal_fingerprint,
            )
        else:
            package_valid = True
            intrinsic, approval_id = _approval_decision_intrinsic_valid(item.decision)
            readiness_fingerprint = ""
            proposal_fingerprint = ""
        if not package_valid or not intrinsic:
            return {context.prefix + "TASK8_APPROVED_PACKAGE_INVALID"}
        if item.decision.get("decision") == "APPROVED":
            if approval_id in approvals:
                return {context.prefix + "TASK8_APPROVAL_LEDGER_INVALID"}
            approvals[approval_id] = (item, readiness_fingerprint, proposal_fingerprint)
    selected = tuple(
        values
        for values in approvals.values()
        if values[0].event_fingerprint == context.admission.approval_fingerprint
    )
    if len(selected) != 1:
        return {context.prefix + "TASK8_APPROVAL_DECISION_INVALID"}
    selected_event, readiness_fingerprint, proposal_fingerprint = selected[0]
    if selected_event.proposal_raw is None or selected_event.readiness_raw is None:
        return {context.prefix + "TASK8_APPROVED_PACKAGE_INVALID"}
    selected_package_valid, _, _ = _approved_package_valid(
        selected_event.proposal_raw,
        selected_event.readiness_raw,
        selected_event.decision,
        context,
    )
    if not selected_package_valid:
        return {context.prefix + "TASK8_APPROVED_PACKAGE_INVALID"}
    valid, approval_id = _approval_decision_valid(
        selected_event.decision,
        context,
        readiness_fingerprint,
        proposal_fingerprint,
    )
    states = ledger.get("approval_states")
    revoked = ledger.get("revoked")
    if not valid or not isinstance(states, dict) or not isinstance(revoked, list):
        return {context.prefix + "TASK8_APPROVAL_DECISION_INVALID"}
    state_candidates = cast("dict[object, object]", states)
    revoked_ids = cast("list[object]", revoked)
    if any(type(key) is not str for key in state_candidates) or any(
        type(item) is not str for item in revoked_ids
    ):
        return {context.prefix + "TASK8_APPROVAL_DECISION_INVALID"}
    state_documents = cast("dict[str, object]", state_candidates)
    revoked_texts = cast("list[str]", revoked_ids)
    if set(state_documents) != set(approvals):
        return {context.prefix + "TASK8_APPROVAL_LEDGER_INVALID"}
    if len(set(revoked_texts)) != len(revoked_texts) or any(
        item not in approvals for item in revoked_texts
    ):
        return {context.prefix + "TASK8_APPROVAL_LEDGER_INVALID"}
    valid_states = {
        "APPROVAL_APPROVED",
        "APPROVAL_CONSUMED",
        "APPROVAL_INVALIDATED",
        "APPROVAL_REVOKED",
    }
    for state_id, state_value in state_documents.items():
        if not isinstance(state_value, dict):
            return {context.prefix + "TASK8_APPROVAL_LEDGER_INVALID"}
        state_document = cast("dict[object, object]", state_value)
        state = state_document.get("state")
        lineage = state_document.get("lineage")
        if (
            set(state_document) != {"lineage", "state"}
            or type(state) is not str
            or state not in valid_states
            or type(lineage) is not str
            or (state == "APPROVAL_CONSUMED") != bool(lineage)
            or (bool(lineage) and _SAFE_ID.fullmatch(lineage) is None)
            or ((state == "APPROVAL_REVOKED") != (state_id in revoked_texts))
        ):
            return {context.prefix + "TASK8_APPROVAL_LEDGER_INVALID"}
    selected_state = cast("dict[str, object]", state_documents[approval_id])
    if selected_state.get("state") != "APPROVAL_CONSUMED" or approval_id in revoked_texts:
        return {context.prefix + "TASK8_APPROVAL_NOT_CURRENT"}
    return set()


def _gate_d_binding_findings(proof_bindings: dict[str, tuple[str, str]], prefix: str) -> set[str]:
    findings: set[str] = set()
    model_binding = proof_bindings.get("MODEL_PROFILE")
    tokenizer_binding = proof_bindings.get("TOKENIZER_PROFILE")
    first_run = proof_bindings.get("MODEL_EVALUATION_RUN_1")
    second_run = proof_bindings.get("MODEL_EVALUATION_RUN_2")
    if (
        model_binding is None
        or tokenizer_binding is None
        or model_binding[1] != tokenizer_binding[1]
    ):
        findings.add(prefix + "SEMANTIC_PROFILE_PROOF_MISMATCH")
    if first_run is None or second_run is None or first_run[1] != second_run[1]:
        findings.add(prefix + "PROVIDER_REPEAT_PROOF_MISMATCH")
    return findings


def _gate_reference_findings(
    evidence: GateEvidence,
    admission: HKV1AdmissionEvidence,
    reader: RetainedEvidenceReader,
) -> tuple[set[str], set[str], tuple[str, ...]]:
    prefix = f"GATE_{evidence.gate}_"
    invalid: set[str] = set()
    missing: set[str] = set()
    refs = evidence.evidence_refs
    kinds = tuple(item.evidence_kind for item in refs)
    if frozenset(kinds) != _REQUIRED_EVIDENCE[evidence.gate] or len(kinds) != len(
        _REQUIRED_EVIDENCE[evidence.gate]
    ):
        missing.add(prefix + "EVIDENCE_INCOMPLETE")
    immutable_refs = tuple(item.immutable_ref for item in refs)
    evidence_ids = tuple(item.evidence_id for item in refs)
    if len(set(immutable_refs)) != len(immutable_refs) or len(set(evidence_ids)) != len(
        evidence_ids
    ):
        invalid.add(prefix + "EVIDENCE_REF_DUPLICATE")
    if any(
        not _SAFE_ID.fullmatch(item.evidence_id)
        or not _IMMUTABLE_REF.fullmatch(item.immutable_ref)
        or not _valid_fingerprint(item.fingerprint)
        or item.subject_fingerprint != evidence.subject_fingerprint
        for item in refs
    ):
        invalid.add(prefix + "EVIDENCE_BINDING_INVALID")
    producer_refs: list[str] = []
    proof_bindings: dict[str, tuple[str, str]] = {}
    for item in refs:
        readback_findings, producer_ref, proof_binding = _verify_reference(
            prefix, evidence.gate, item, admission, reader
        )
        invalid.update(readback_findings)
        if producer_ref is not None:
            producer_refs.append(producer_ref)
        if proof_binding is not None:
            proof_bindings[item.evidence_kind] = proof_binding
    if len(set(producer_refs)) != len(producer_refs):
        invalid.add(prefix + "PRODUCER_EVIDENCE_REF_DUPLICATE")
    if evidence.gate == "D":
        invalid.update(_gate_d_binding_findings(proof_bindings, prefix))
    return invalid, missing, tuple(producer_refs)


def _evaluate_gate(
    evidence: GateEvidence,
    admission: HKV1AdmissionEvidence,
    reader: RetainedEvidenceReader,
) -> tuple[HKV1GateResult, tuple[str, ...]]:
    prefix = f"GATE_{evidence.gate}_"
    invalid = _gate_identity_findings(evidence)
    if _gate_arithmetic_invalid(evidence):
        invalid.add(prefix + "WORK_ARITHMETIC_INVALID")
    reference_invalid, missing, producer_refs = _gate_reference_findings(
        evidence, admission, reader
    )
    invalid.update(reference_invalid)

    retryable: set[str] = set()
    rejected: set[str] = set()
    if evidence.retryable > 0:
        retryable.add(prefix + "RETRYABLE_WORK")
    if evidence.rejected > 0:
        rejected.add(prefix + "REJECTED_WORK")
    if evidence.discovered < evidence.expected:
        missing.add(prefix + "WORK_MISSING")

    if invalid:
        state = GateState.INVALID
    elif retryable:
        state = GateState.INCOMPLETE_RETRYABLE
    elif rejected:
        state = GateState.REJECTED
    elif missing:
        state = GateState.MISSING
    else:
        state = GateState.PASSED
    blockers = tuple(sorted(invalid | retryable | rejected | missing))
    return (
        HKV1GateResult(
            gate=evidence.gate,
            state=state,
            expected=evidence.expected,
            discovered=evidence.discovered,
            verified=evidence.verified,
            retryable=evidence.retryable,
            rejected=evidence.rejected,
            terminal=evidence.terminal,
            evidence_refs=tuple(
                sorted(evidence.evidence_refs, key=lambda item: item.evidence_kind)
            ),
            blocker_codes=blockers,
        ),
        producer_refs,
    )


def _global_findings(evidence: HKV1AdmissionEvidence) -> set[str]:
    findings: set[str] = set()
    checks = (
        (_valid_timestamp(evidence.common_cutoff), "COMMON_CUTOFF_INVALID"),
        (
            _valid_fingerprint(evidence.coverage_matrix_fingerprint),
            "COVERAGE_MATRIX_FINGERPRINT_INVALID",
        ),
        (_valid_fingerprint(evidence.proposal_fingerprint), "PROPOSAL_FINGERPRINT_INVALID"),
        (
            _valid_fingerprint(evidence.model_profile_fingerprint),
            "MODEL_PROFILE_FINGERPRINT_INVALID",
        ),
        (
            _valid_fingerprint(evidence.embedding_profile_fingerprint),
            "EMBEDDING_PROFILE_FINGERPRINT_INVALID",
        ),
        (
            _valid_fingerprint(evidence.serving_profile_fingerprint),
            "SERVING_PROFILE_FINGERPRINT_INVALID",
        ),
        (_valid_fingerprint(evidence.approval_fingerprint), "APPROVAL_FINGERPRINT_INVALID"),
        (
            _SAFE_ID.fullmatch(evidence.serving_state_id) is not None,
            "CURRENT_SERVING_STATE_INVALID",
        ),
        (_SAFE_ID.fullmatch(evidence.target_name) is not None, "CURRENT_TARGET_INVALID"),
        (_valid_fingerprint(evidence.target_fingerprint), "CURRENT_TARGET_FINGERPRINT_INVALID"),
    )
    findings.update(code for valid, code in checks if not valid)
    return findings


def _cross_gate_findings(
    evidence: HKV1AdmissionEvidence, by_gate: dict[GateName, GateEvidence]
) -> set[str]:
    findings: set[str] = set()
    gate_a = by_gate.get("A")
    if gate_a is not None and gate_a.subject_fingerprint != evidence.coverage_matrix_fingerprint:
        findings.add("GATE_A_COVERAGE_BINDING_MISMATCH")
    for gate_name in ("E", "G"):
        gate = by_gate.get(gate_name)
        if gate is not None and gate.subject_fingerprint != evidence.proposal_fingerprint:
            findings.add(f"GATE_{gate_name}_PROPOSAL_BINDING_MISMATCH")
    return findings


def evaluate_hk_v1_live_admission(
    evidence: HKV1AdmissionEvidence, reader: RetainedEvidenceReader
) -> HKV1LiveAdmissionReport:
    """Re-read retained proofs and derive Gate A-G without trusting a success flag."""
    blockers: set[str] = set()
    by_gate: dict[GateName, GateEvidence] = {}
    supplied_names: list[object] = []
    for item in evidence.gates:
        supplied_names.append(item.gate)
        if item.gate in _GATE_ORDER and item.gate not in by_gate:
            by_gate[item.gate] = item
    if tuple(supplied_names) != _GATE_ORDER:
        blockers.add("GATE_INVENTORY_INVALID")

    results: list[HKV1GateResult] = []
    for gate in _GATE_ORDER:
        gate_evidence = by_gate.get(gate)
        if gate_evidence is None:
            result = _missing_result(gate)
        else:
            result, _ = _evaluate_gate(gate_evidence, evidence, reader)
        results.append(result)
        blockers.update(result.blocker_codes)

    blockers.update(_global_findings(evidence))
    blockers.update(_cross_gate_findings(evidence, by_gate))

    evidence_fingerprint = "sha256:" + sha256(_canonical_bytes(evidence.document())).hexdigest()
    blocker_codes = tuple(sorted(blockers))
    admitted = not blocker_codes and all(item.state is GateState.PASSED for item in results)
    return HKV1LiveAdmissionReport(
        result="V1_ADMITTED" if admitted else "NOT_ADMITTED",
        admitted=admitted,
        gate_results=tuple(results),
        blocker_codes=blocker_codes,
        common_cutoff=evidence.common_cutoff,
        coverage_matrix_fingerprint=evidence.coverage_matrix_fingerprint,
        proposal_fingerprint=evidence.proposal_fingerprint,
        model_profile_fingerprint=evidence.model_profile_fingerprint,
        embedding_profile_fingerprint=evidence.embedding_profile_fingerprint,
        serving_profile_fingerprint=evidence.serving_profile_fingerprint,
        approval_fingerprint=evidence.approval_fingerprint,
        serving_state_id=evidence.serving_state_id,
        target_name=evidence.target_name,
        target_fingerprint=evidence.target_fingerprint,
        evidence_fingerprint=evidence_fingerprint,
    )


def canonical_report_bytes(report: HKV1LiveAdmissionReport) -> bytes:
    """Serialize the consolidated report for immutable retention."""
    return _canonical_bytes(report.document())


def _manifest_error() -> ValueError:
    return ValueError("HK_V1_ADMISSION_MANIFEST_INVALID")


def _required_text(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if type(value) is not str:
        raise _manifest_error()
    return value


def _required_int(document: dict[str, object], key: str) -> int:
    value = document.get(key)
    if type(value) is not int:
        raise _manifest_error()
    return value


def _required_text_tuple(document: dict[str, object], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list):
        raise _manifest_error()
    items = cast("list[object]", value)
    if any(type(item) is not str for item in items):
        raise _manifest_error()
    return tuple(item for item in items if type(item) is str)


def _parse_reference(value: object) -> RetainedEvidenceRef:
    if not isinstance(value, dict):
        raise _manifest_error()
    candidate = cast("dict[object, object]", value)
    if frozenset(candidate) != _REFERENCE_KEYS:
        raise _manifest_error()
    document = cast("dict[str, object]", candidate)
    return RetainedEvidenceRef(
        evidence_id=_required_text(document, "evidence_id"),
        evidence_kind=_required_text(document, "evidence_kind"),
        immutable_ref=_required_text(document, "immutable_ref"),
        fingerprint=_required_text(document, "fingerprint"),
        subject_fingerprint=_required_text(document, "subject_fingerprint"),
    )


def _parse_gate(value: object) -> GateEvidence:
    if not isinstance(value, dict):
        raise _manifest_error()
    candidate = cast("dict[object, object]", value)
    if frozenset(candidate) != _GATE_KEYS:
        raise _manifest_error()
    document = cast("dict[str, object]", candidate)
    gate_value = _required_text(document, "gate")
    refs = document.get("evidence_refs")
    if gate_value not in _GATE_ORDER or not isinstance(refs, list):
        raise _manifest_error()
    reference_items = cast("list[object]", refs)
    return GateEvidence(
        gate=gate_value,
        subject_fingerprint=_required_text(document, "subject_fingerprint"),
        families=_required_text_tuple(document, "families"),
        scopes=_required_text_tuple(document, "scopes"),
        expected=_required_int(document, "expected"),
        discovered=_required_int(document, "discovered"),
        verified=_required_int(document, "verified"),
        retryable=_required_int(document, "retryable"),
        rejected=_required_int(document, "rejected"),
        terminal=_required_int(document, "terminal"),
        evidence_refs=tuple(_parse_reference(item) for item in reference_items),
    )


def load_hk_v1_live_admission_manifest(path: Path) -> HKV1AdmissionEvidence:
    """Load one canonical, closed local admission manifest without repairing it."""
    if path.is_symlink() or not path.is_file():
        raise _manifest_error()
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_ADMISSION_BYTES:
        raise _manifest_error()
    document = _strict_document(raw, _MANIFEST_KEYS)
    if (
        document is None
        or document.get("schema_id") != "asklegal.hk-v1-live-admission-manifest"
        or document.get("schema_version") != 1
    ):
        raise _manifest_error()
    gates = document.get("gates")
    if not isinstance(gates, list):
        raise _manifest_error()
    gate_items = cast("list[object]", gates)
    return HKV1AdmissionEvidence(
        gates=tuple(_parse_gate(item) for item in gate_items),
        common_cutoff=_required_text(document, "common_cutoff"),
        coverage_matrix_fingerprint=_required_text(document, "coverage_matrix_fingerprint"),
        proposal_fingerprint=_required_text(document, "proposal_fingerprint"),
        model_profile_fingerprint=_required_text(document, "model_profile_fingerprint"),
        embedding_profile_fingerprint=_required_text(document, "embedding_profile_fingerprint"),
        serving_profile_fingerprint=_required_text(document, "serving_profile_fingerprint"),
        approval_fingerprint=_required_text(document, "approval_fingerprint"),
        serving_state_id=_required_text(document, "serving_state_id"),
        target_name=_required_text(document, "target_name"),
        target_fingerprint=_required_text(document, "target_fingerprint"),
    )


def main(argv: list[str] | None = None) -> int:
    """Evaluate one retained local manifest; exit zero only for V1_ADMITTED."""
    parser = argparse.ArgumentParser(description="Evaluate retained Hong Kong V1 admission")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        evidence = load_hk_v1_live_admission_manifest(arguments.manifest)
        report = evaluate_hk_v1_live_admission(
            evidence, LocalRetainedEvidenceReader(arguments.evidence_root)
        )
    except OSError, ValueError:
        sys.stderr.write("FAIL HK_V1_ADMISSION_MANIFEST_INVALID\n")
        return 2
    sys.stdout.buffer.write(canonical_report_bytes(report) + b"\n")
    return 0 if report.admitted else 1


if __name__ == "__main__":
    raise SystemExit(main())
