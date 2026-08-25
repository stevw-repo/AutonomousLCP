"""Effect-free ADR 0005 consequence for an unsafe new-version partition."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Never

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .hk_legislation_partition import (
    BilingualPartitionResult,
    BilingualServingPart,
    PartitionDisposition,
    PartitionReason,
)
from .model import RulebookError, RulebookErrorCode

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue


class PartitionReleaseChoice(StrEnum):
    """Closed ADR 0005 choices after unsafe new-version partitioning."""

    CARRY_FORWARD_LAST_APPROVED_RELEASE = "CARRY_FORWARD_LAST_APPROVED_RELEASE"
    CREATE_WITHHOLDING_RELEASE = "CREATE_WITHHOLDING_RELEASE"
    NO_JURISDICTION_REBUILD = "NO_JURISDICTION_REBUILD"


class PartitionReleaseReason(StrEnum):
    """Stable result code for the explicit consequence boundary."""

    EXPLICIT_UNSAFE_NEW_VERSION_CONSEQUENCE = "EXPLICIT_UNSAFE_NEW_VERSION_CONSEQUENCE"


@dataclass(frozen=True, slots=True)
class PartitionReleaseConsequenceRequest:
    """One recorded Legal Desk choice bound to an unsafe partition result."""

    partition_result: BilingualPartitionResult
    partition_result_fingerprint: str
    new_official_version_ref: dict[str, JsonValue]
    previous_official_version_ref: dict[str, JsonValue]
    previous_release_ref: dict[str, JsonValue]
    previous_target_ref: dict[str, JsonValue]
    decision: PartitionReleaseChoice
    decision_ref: dict[str, JsonValue]
    decision_evidence_ref: dict[str, JsonValue]
    audit_history_ref: dict[str, JsonValue]
    coverage_gap_ref: dict[str, JsonValue]
    decision_reason: str
    legal_desk_author: str
    last_verified_at: str
    decided_at: str
    review_deadline: str
    continued_serving_supported: bool
    affirmative_record_change_proved: bool
    existing_records_materially_misleading: bool
    withholding_supported: bool
    selected_release_ref: dict[str, JsonValue] | None
    withholding_release_ref: dict[str, JsonValue] | None
    warning: str | None


@dataclass(frozen=True, slots=True)
class PartitionReleaseConsequenceResult:
    """Validated explicit release/routing consequence with no effect."""

    disposition: PartitionDisposition
    reason: PartitionReleaseReason
    decision: PartitionReleaseChoice
    partition_result_fingerprint: str
    new_official_version_ref: dict[str, JsonValue]
    previous_official_version_ref: dict[str, JsonValue]
    previous_release_ref: dict[str, JsonValue]
    previous_target_ref: dict[str, JsonValue]
    decision_ref: dict[str, JsonValue]
    decision_evidence_ref: dict[str, JsonValue]
    audit_history_ref: dict[str, JsonValue]
    coverage_gap_ref: dict[str, JsonValue]
    decision_reason: str
    legal_desk_author: str
    last_verified_at: str
    decided_at: str
    review_deadline: str
    selected_release_ref: dict[str, JsonValue] | None
    withholding_release_ref: dict[str, JsonValue] | None
    warning: str | None
    continued_serving_supported: bool
    affirmative_record_change_proved: bool
    existing_records_materially_misleading: bool
    withholding_supported: bool
    release_action: str
    routing_action: str
    approval_required: bool
    coverage_gap_required: bool
    parts: tuple[BilingualServingPart, ...]
    canonical_bytes: bytes
    fingerprint: str

    def document(self) -> dict[str, JsonValue]:
        """Return the exact effect-free consequence proof."""
        return _object(
            {
                "approval_required": self.approval_required,
                "affirmative_record_change_proved": self.affirmative_record_change_proved,
                "audit_history_ref": self.audit_history_ref,
                "coverage_gap_ref": self.coverage_gap_ref,
                "coverage_gap_required": self.coverage_gap_required,
                "continued_serving_supported": self.continued_serving_supported,
                "decided_at": self.decided_at,
                "decision": self.decision.value,
                "decision_evidence_ref": self.decision_evidence_ref,
                "decision_reason": self.decision_reason,
                "decision_ref": self.decision_ref,
                "disposition": self.disposition.value,
                "existing_records_materially_misleading": (
                    self.existing_records_materially_misleading
                ),
                "external_effects": "NONE",
                "last_verified_at": self.last_verified_at,
                "legal_desk_author": self.legal_desk_author,
                "new_official_version_ref": self.new_official_version_ref,
                "partition_result_fingerprint": self.partition_result_fingerprint,
                "parts": [],
                "predecessor_retirement": "FORBIDDEN",
                "previous_official_version_ref": self.previous_official_version_ref,
                "previous_release_ref": self.previous_release_ref,
                "previous_target_ref": self.previous_target_ref,
                "reason": self.reason.value,
                "release_action": self.release_action,
                "review_deadline": self.review_deadline,
                "routing_action": self.routing_action,
                "search_record_output": "NONE",
                "selected_release_ref": self.selected_release_ref,
                "warning": self.warning,
                "withholding_release_ref": self.withholding_release_ref,
                "withholding_supported": self.withholding_supported,
            }
        )


def _fail(detail: str) -> Never:
    raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail)


def _object(value: object) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    if not isinstance(parsed, dict):
        message = "expected JSON object"
        raise TypeError(message)
    return parsed


def _ref_signature(reference: dict[str, JsonValue]) -> tuple[str, str, str]:
    if frozenset(reference) != frozenset({"ref_type", "ref_id", "fingerprint"}):
        _fail("partition release reference fields")
    ref_type = reference.get("ref_type")
    ref_id = reference.get("ref_id")
    fingerprint = reference.get("fingerprint")
    if not all(isinstance(value, str) and value for value in (ref_type, ref_id, fingerprint)):
        _fail("partition release reference")
    return str(ref_type), str(ref_id), str(fingerprint)


def _instant(value: str, detail: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RulebookError(RulebookErrorCode.CONTRACT_MISMATCH, detail) from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        _fail(detail)
    return parsed


def _same_ref(
    left: dict[str, JsonValue] | None,
    right: dict[str, JsonValue],
) -> bool:
    return left is not None and _ref_signature(left) == _ref_signature(right)


def _document_ref(
    document: dict[str, JsonValue],
    key: str,
    *,
    optional: bool = False,
) -> dict[str, JsonValue] | None:
    value = document.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, dict):
        _fail(f"partition release {key}")
    reference = _object(value)
    _ref_signature(reference)
    return reference


def _document_text(
    document: dict[str, JsonValue],
    key: str,
    *,
    optional: bool = False,
) -> str | None:
    value = document.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        _fail(f"partition release {key}")
    return value


def _required_document_ref(
    document: dict[str, JsonValue],
    key: str,
) -> dict[str, JsonValue]:
    reference = _document_ref(document, key)
    if reference is None:
        _fail(f"partition release {key}")
    return reference


def _document_bool(document: dict[str, JsonValue], key: str) -> bool:
    value = document.get(key)
    if type(value) is not bool:
        _fail(f"partition release {key}")
    return value


def partition_release_request_from_document(
    document: dict[str, JsonValue],
    partition_result: BilingualPartitionResult,
) -> PartitionReleaseConsequenceRequest:
    """Parse one strict release-consequence claim without repairing it."""
    expected = frozenset(
        {
            "partition_result_fingerprint",
            "new_official_version_ref",
            "previous_official_version_ref",
            "previous_release_ref",
            "previous_target_ref",
            "decision",
            "decision_ref",
            "decision_evidence_ref",
            "audit_history_ref",
            "coverage_gap_ref",
            "decision_reason",
            "legal_desk_author",
            "last_verified_at",
            "decided_at",
            "review_deadline",
            "continued_serving_supported",
            "affirmative_record_change_proved",
            "existing_records_materially_misleading",
            "withholding_supported",
            "selected_release_ref",
            "withholding_release_ref",
            "warning",
        }
    )
    if frozenset(document) != expected:
        _fail("partition release request fields")
    decision_value = _document_text(document, "decision")
    try:
        decision = PartitionReleaseChoice(str(decision_value))
    except ValueError as error:
        raise RulebookError(
            RulebookErrorCode.CONTRACT_MISMATCH,
            "partition release decision",
        ) from error
    required_refs = tuple(
        _required_document_ref(document, key)
        for key in (
            "new_official_version_ref",
            "previous_official_version_ref",
            "previous_release_ref",
            "previous_target_ref",
            "decision_ref",
            "decision_evidence_ref",
            "audit_history_ref",
            "coverage_gap_ref",
        )
    )
    return PartitionReleaseConsequenceRequest(
        partition_result,
        str(_document_text(document, "partition_result_fingerprint")),
        required_refs[0],
        required_refs[1],
        required_refs[2],
        required_refs[3],
        decision,
        required_refs[4],
        required_refs[5],
        required_refs[6],
        required_refs[7],
        str(_document_text(document, "decision_reason")),
        str(_document_text(document, "legal_desk_author")),
        str(_document_text(document, "last_verified_at")),
        str(_document_text(document, "decided_at")),
        str(_document_text(document, "review_deadline")),
        _document_bool(document, "continued_serving_supported"),
        _document_bool(document, "affirmative_record_change_proved"),
        _document_bool(document, "existing_records_materially_misleading"),
        _document_bool(document, "withholding_supported"),
        _document_ref(document, "selected_release_ref", optional=True),
        _document_ref(document, "withholding_release_ref", optional=True),
        _document_text(document, "warning", optional=True),
    )


def _choice_actions(request: PartitionReleaseConsequenceRequest) -> tuple[str, str, bool]:
    if request.decision is PartitionReleaseChoice.CARRY_FORWARD_LAST_APPROVED_RELEASE:
        if (
            not request.continued_serving_supported
            or request.affirmative_record_change_proved
            or request.existing_records_materially_misleading
            or request.withholding_supported
            or not _same_ref(request.selected_release_ref, request.previous_release_ref)
            or request.withholding_release_ref is not None
            or request.warning is None
        ):
            _fail("partition release carry-forward decision")
        return (
            "SELECT_LAST_APPROVED_WITH_WARNING",
            "BUILD_EXPLICIT_CARRY_FORWARD_TARGET_AFTER_APPROVAL",
            True,
        )
    if request.decision is PartitionReleaseChoice.CREATE_WITHHOLDING_RELEASE:
        if (
            request.continued_serving_supported
            or not request.existing_records_materially_misleading
            or not request.withholding_supported
            or request.withholding_release_ref is None
            or not _same_ref(request.selected_release_ref, request.withholding_release_ref)
            or _same_ref(request.withholding_release_ref, request.previous_release_ref)
        ):
            _fail("partition release withholding decision")
        return "CREATE_COMPLETE_WITHHOLDING_RELEASE", "BUILD_AFTER_EXACT_APPROVAL", True
    if (
        request.continued_serving_supported
        or request.withholding_supported
        or request.selected_release_ref is not None
        or request.withholding_release_ref is not None
        or request.warning is None
    ):
        _fail("partition release no-rebuild decision")
    return "NO_NEW_DESIRED_STATE", "RETAIN_PREVIOUS_VERIFIED_TARGET", False


def decide_partition_failure_release(
    request: PartitionReleaseConsequenceRequest,
) -> PartitionReleaseConsequenceResult:
    """Validate one explicit ADR 0005 choice without creating a release or effect."""
    result = request.partition_result
    if (
        type(request) is not PartitionReleaseConsequenceRequest
        or result.disposition is not PartitionDisposition.QUARANTINE
        or result.reason is not PartitionReason.SMALLEST_DEPENDENT_BRANCH_OVER_LIMIT
        or result.parts
        or not result.coverage_gap_required
        or request.partition_result_fingerprint != result.fingerprint
    ):
        _fail("partition release unsafe result binding")
    references = (
        request.new_official_version_ref,
        request.previous_official_version_ref,
        request.previous_release_ref,
        request.previous_target_ref,
        request.decision_ref,
        request.decision_evidence_ref,
        request.audit_history_ref,
        request.coverage_gap_ref,
    )
    for reference in references:
        _ref_signature(reference)
    if _same_ref(request.new_official_version_ref, request.previous_official_version_ref):
        _fail("partition release version lineage")
    last_verified = _instant(request.last_verified_at, "partition release last verified")
    decided = _instant(request.decided_at, "partition release decided")
    deadline = _instant(request.review_deadline, "partition release review deadline")
    if not last_verified <= decided < deadline:
        _fail("partition release chronology")
    if (
        not request.decision_reason
        or request.decision_reason.strip() != request.decision_reason
        or not request.legal_desk_author
        or request.legal_desk_author.strip() != request.legal_desk_author
        or (request.warning is not None and not request.warning)
    ):
        _fail("partition release decision fields")
    release_action, routing_action, approval_required = _choice_actions(request)
    provisional = PartitionReleaseConsequenceResult(
        disposition=PartitionDisposition.PASS,
        reason=PartitionReleaseReason.EXPLICIT_UNSAFE_NEW_VERSION_CONSEQUENCE,
        decision=request.decision,
        partition_result_fingerprint=result.fingerprint,
        new_official_version_ref=request.new_official_version_ref,
        previous_official_version_ref=request.previous_official_version_ref,
        previous_release_ref=request.previous_release_ref,
        previous_target_ref=request.previous_target_ref,
        decision_ref=request.decision_ref,
        decision_evidence_ref=request.decision_evidence_ref,
        audit_history_ref=request.audit_history_ref,
        coverage_gap_ref=request.coverage_gap_ref,
        decision_reason=request.decision_reason,
        legal_desk_author=request.legal_desk_author,
        last_verified_at=request.last_verified_at,
        decided_at=request.decided_at,
        review_deadline=request.review_deadline,
        selected_release_ref=request.selected_release_ref,
        withholding_release_ref=request.withholding_release_ref,
        warning=request.warning,
        continued_serving_supported=request.continued_serving_supported,
        affirmative_record_change_proved=request.affirmative_record_change_proved,
        existing_records_materially_misleading=(request.existing_records_materially_misleading),
        withholding_supported=request.withholding_supported,
        release_action=release_action,
        routing_action=routing_action,
        approval_required=approval_required,
        coverage_gap_required=True,
        parts=(),
        canonical_bytes=b"",
        fingerprint="",
    )
    canonical_bytes = canonicalize(provisional.document())
    return replace(
        provisional,
        canonical_bytes=canonical_bytes,
        fingerprint=f"sha256:{sha256(canonical_bytes).hexdigest()}",
    )
