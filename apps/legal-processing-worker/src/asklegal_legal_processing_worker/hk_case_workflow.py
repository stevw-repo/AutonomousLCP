"""Unwired Task 6A provider-disabled Hong Kong Cases workflow."""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

from asklegal_legal_desks.hk_case_judgment import accept_complete_cases_acquisition_manifest
from asklegal_management_register_ports.hk_case_work import (
    HK_CASE_WORK_REQUIRED_BLOCKERS,
    HKCaseWorkCheckpointFactory,
    HKCaseWorkCheckpointStore,
    HKCaseWorkError,
    HKCaseWorkErrorCode,
    HKCaseWorkRequest,
    build_hk_case_work_identity,
    snapshot_hk_case_work_request,
)


class HKCaseWorkflowStatus(StrEnum):
    """The only Task 6A terminal workflow status."""

    WITHHELD_NOT_PROCESSED = "WITHHELD_NOT_PROCESSED"


SEMANTIC_CAPABILITY_DISABLED = "SEMANTIC_CAPABILITY_DISABLED"
_ORDINARY_FAILURE: type[Exception] = Exception


class HKCaseWorkflowResult(TypedDict):
    """Bounded scheduler-safe negative result primitives."""

    status: str
    reason: str
    work_item_id: str
    checkpoint_fingerprint: str
    blocker_codes: tuple[str, ...]
    semantic_invocation_count: int


def admit_complete_cases_manifest_for_withheld_work(raw: bytes) -> HKCaseWorkflowResult:
    """Admit complete Cases evidence only into the still provider-disabled boundary."""
    accepted = accept_complete_cases_acquisition_manifest(raw)
    return {
        "status": HKCaseWorkflowStatus.WITHHELD_NOT_PROCESSED.value,
        "reason": SEMANTIC_CAPABILITY_DISABLED,
        "work_item_id": accepted.cycle_id,
        "checkpoint_fingerprint": accepted.manifest_fingerprint,
        "blocker_codes": (SEMANTIC_CAPABILITY_DISABLED,),
        "semantic_invocation_count": 0,
    }


def _raise_replay_mismatch() -> None:
    raise HKCaseWorkError(HKCaseWorkErrorCode.REPLAY_MISMATCH)


def _same_request(left: HKCaseWorkRequest, right: HKCaseWorkRequest) -> bool:
    return (
        build_hk_case_work_identity(left).work_item_id
        == build_hk_case_work_identity(right).work_item_id
    )


def _safe_result(
    work_item_id: str, checkpoint_fingerprint: str, blocker_codes: tuple[str, ...]
) -> HKCaseWorkflowResult:
    return {
        "status": HKCaseWorkflowStatus.WITHHELD_NOT_PROCESSED.value,
        "reason": SEMANTIC_CAPABILITY_DISABLED,
        "work_item_id": work_item_id,
        "checkpoint_fingerprint": checkpoint_fingerprint,
        "blocker_codes": blocker_codes,
        "semantic_invocation_count": 0,
    }


def withhold_hk_case_work(
    request: HKCaseWorkRequest, store: HKCaseWorkCheckpointStore
) -> HKCaseWorkflowResult:
    """Record/replay one blocked checkpoint without semantic or external capability."""
    captured = snapshot_hk_case_work_request(request)
    try:
        identity = build_hk_case_work_identity(captured)
        factory = HKCaseWorkCheckpointFactory()
        issued = factory.issue_blocked(identity, HK_CASE_WORK_REQUIRED_BLOCKERS)
        (
            port_value,
            expected_canonical,
            expected_work_item_id,
            expected_checkpoint_fingerprint,
            expected_blockers,
        ) = factory.prepare_port_write(issued)
        checkpoint = store.record_checkpoint(port_value, expected_canonical)
        returned = factory.returned_projection(checkpoint, expected_canonical)
        expected_projection = (
            expected_work_item_id,
            expected_checkpoint_fingerprint,
            expected_blockers,
        )
        if returned != expected_projection:
            _raise_replay_mismatch()
        factory.assert_issued(issued)
        final = snapshot_hk_case_work_request(request)
        if not _same_request(captured, final):
            _raise_replay_mismatch()
        return _safe_result(
            expected_work_item_id,
            expected_checkpoint_fingerprint,
            expected_blockers,
        )
    except HKCaseWorkError:
        raise
    except _ORDINARY_FAILURE:
        raise HKCaseWorkError(HKCaseWorkErrorCode.REPLAY_MISMATCH) from None
