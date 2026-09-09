"""Synthetic conformance proof against the real local SQL Server engine."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_management_register import (
    ApprovedPromotionClaim,
    ApprovedPromotionQueueStore,
    EffectHandoffStore,
    EffectReceiptRecord,
    RegisteredExecutionBeginCommand,
    RegisteredExecutionBeginStore,
    RegisterEventCommand,
    RegisterEventStore,
)
from asklegal_management_register.driver import MssqlConnectionFactory
from asklegal_management_register.migration import apply_packages
from asklegal_management_register.store import (
    CommandFingerprintMismatch,
    ManagementRegisterStore,
    RegisteredApprovalConsumptionCommand,
    RegisteredApprovalLifecycleStore,
    RegisteredApprovalStore,
    RegisteredApprovalTerminalCommand,
    RegisteredExecutionAuthorizationCommand,
    RegisteredExecutionAuthorizationStore,
)

_DATABASE = "AskLegalManagementRegisterSpike"
_MIGRATION = Path(__file__).parents[1] / "migrations" / "000001_management_register_spike"
_M2_MIGRATION = Path(__file__).parents[1] / "migrations" / "000002_complete_m2_register"
_V1_REVIEW_MIGRATION = Path(__file__).parents[1] / "migrations" / "000003_review_ready_proposals"
_V1_DECISION_MIGRATION = Path(__file__).parents[1] / "migrations" / "000004_proposal_decisions"
_V1_CONSUMPTION_MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "000005_registered_approval_consumption"
)
_V1_TERMINAL_MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "000006_registered_approval_terminal_lifecycle"
)
_V1_EXECUTION_AUTHORIZATION_MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "000007_registered_execution_authorization"
)
_V1_EXECUTION_BEGIN_MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "000008_registered_execution_begin"
)
_V1_CLAIMED_EFFECT_READBACK_MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "000009_claimed_effect_readback"
)
_V1_APPROVED_PROMOTION_WAKEUP_MIGRATION = (
    Path(__file__).parents[1] / "migrations" / "000010_approved_promotion_wakeup"
)

_REGISTERED_APPROVAL_ID = "apr_" + "a" * 48
_REGISTERED_PROPOSAL_ID = "ppk_" + "9" * 48
_REGISTERED_MANIFEST_ID = "pmn_" + "b" * 48
_REGISTERED_MANIFEST_FINGERPRINT = "sha256:" + "c" * 64
_REGISTERED_LINEAGE_ID = "exe_" + "d" * 48


def _registered_decision_bytes() -> bytes:
    """Return the exact approved decision used by the registered execution proof."""
    return canonicalize(
        checked_json_value(
            {
                "approval_id": _REGISTERED_APPROVAL_ID,
                "authority_evidence_ref": {
                    "fingerprint": "sha256:" + "e" * 64,
                    "ref_id": "evi_" + "e" * 48,
                    "ref_type": "EVIDENCE",
                },
                "decision": "APPROVED",
                "decision_time": "2026-08-22T00:01:00Z",
                "expected_base_serving_state_ref": {
                    "fingerprint": "sha256:" + "f" * 64,
                    "ref_id": "srv_" + "f" * 48,
                    "ref_type": "SERVING_STATE",
                },
                "governance_policy_state": "CONFIGURED",
                "immutable": True,
                "promotion_manifest_ref": {
                    "fingerprint": _REGISTERED_MANIFEST_FINGERPRINT,
                    "ref_id": _REGISTERED_MANIFEST_ID,
                    "ref_type": "PROMOTION_MANIFEST",
                },
                "reason": "SQL Server registered Approval proof",
                "reviewer_identity_ref": {
                    "fingerprint": "sha256:" + "1" * 64,
                    "ref_id": "act_" + "1" * 48,
                    "ref_type": "ACTOR",
                },
                "schema_id": "asklegal.approval-decision",
                "schema_version": "1.1.0",
                "valid_from": "2026-08-22T00:00:00Z",
                "validity_condition_refs": [
                    {
                        "contract_id": "configuration",
                        "fingerprint": "sha256:" + "2" * 64,
                        "version": "1.0.0",
                    }
                ],
            }
        )
    )


def _execution_authorization_command(
    *,
    command_marker: str,
    event_marker: str,
    approval_id: str = _REGISTERED_APPROVAL_ID,
    lineage_fingerprint: str = "sha256:" + "5" * 64,
) -> RegisteredExecutionAuthorizationCommand:
    """Build one exact consumed-lineage authorization command and event."""
    decision_fingerprint = sha256(_registered_decision_bytes()).digest()
    decision_fingerprint_text = f"sha256:{decision_fingerprint.hex()}"
    worker_id = "act_" + "6" * 48
    worker_fingerprint = "sha256:" + "6" * 64
    evidence_id = "evi_" + "4" * 48
    evidence_fingerprint = "sha256:" + "4" * 64
    authorization_bindings = canonicalize(
        checked_json_value(
            {
                "approval_id": approval_id,
                "decision_fingerprint": decision_fingerprint_text,
                "execution_lineage_fingerprint": lineage_fingerprint,
                "execution_lineage_id": _REGISTERED_LINEAGE_ID,
                "manifest_fingerprint": _REGISTERED_MANIFEST_FINGERPRINT,
                "manifest_id": _REGISTERED_MANIFEST_ID,
                "promotion_worker_identity_fingerprint": worker_fingerprint,
                "promotion_worker_identity_id": worker_id,
                "proposal_package_id": _REGISTERED_PROPOSAL_ID,
                "validation_evidence_fingerprint": evidence_fingerprint,
                "validation_evidence_id": evidence_id,
            }
        )
    )
    authorization_fingerprint = f"sha256:{sha256(authorization_bindings).hexdigest()}"
    command = canonicalize(
        checked_json_value(
            {
                "action": "AUTHORIZE_REGISTERED_PROMOTION_EXECUTION",
                "approval_id": approval_id,
                "authorization_fingerprint": authorization_fingerprint,
                "decision_fingerprint": decision_fingerprint_text,
                "execution_lineage_fingerprint": lineage_fingerprint,
                "execution_lineage_id": _REGISTERED_LINEAGE_ID,
                "manifest_fingerprint": _REGISTERED_MANIFEST_FINGERPRINT,
                "manifest_id": _REGISTERED_MANIFEST_ID,
                "promotion_worker_identity_fingerprint": worker_fingerprint,
                "promotion_worker_identity_id": worker_id,
                "proposal_package_id": _REGISTERED_PROPOSAL_ID,
                "validation_evidence_fingerprint": evidence_fingerprint,
                "validation_evidence_id": evidence_id,
            }
        )
    )
    event_id = "pex_" + event_marker * 48
    event = canonicalize(
        checked_json_value(
            {
                "action_id": "AUTHORIZE",
                "approval_ref": {
                    "fingerprint": decision_fingerprint_text,
                    "ref_id": approval_id,
                    "ref_type": "APPROVAL",
                },
                "attempt_number": 0,
                "event_time": "2026-08-22T00:03:00Z",
                "execution_lineage_id": _REGISTERED_LINEAGE_ID,
                "external_effects": "NONE",
                "failure_codes": [],
                "from_state": "EXECUTION_PLANNED",
                "idempotency": {
                    "idempotency_key": f"authorize:{_REGISTERED_LINEAGE_ID}",
                    "input_fingerprint": authorization_fingerprint,
                },
                "immutable": True,
                "promotion_execution_event_id": event_id,
                "promotion_manifest_ref": {
                    "fingerprint": _REGISTERED_MANIFEST_FINGERPRINT,
                    "ref_id": _REGISTERED_MANIFEST_ID,
                    "ref_type": "PROMOTION_MANIFEST",
                },
                "reason_codes": [
                    "APPROVAL_EXACTLY_BOUND",
                    "TRANSITION_ALLOWED",
                    "VALIDATION_COMPLETE",
                ],
                "receipt_refs": [],
                "result_code": "SUCCEEDED",
                "schema_id": "asklegal.promotion-execution-event",
                "schema_version": "1.0.0",
                "to_state": "EXECUTION_AUTHORIZED",
            }
        )
    )
    return RegisteredExecutionAuthorizationCommand(
        "cmd_" + command_marker * 48,
        command,
        approval_id,
        _REGISTERED_PROPOSAL_ID,
        decision_fingerprint,
        _REGISTERED_MANIFEST_ID,
        _REGISTERED_MANIFEST_FINGERPRINT,
        _REGISTERED_LINEAGE_ID,
        lineage_fingerprint,
        authorization_fingerprint,
        "9999-12-31T23:59:59",
        event_id,
        event,
    )


def _execution_begin_command(
    *,
    command_marker: str,
    event_marker: str,
    intent_marker: str,
    authorization_fingerprint: str | None = None,
) -> RegisteredExecutionBeginCommand:
    """Build one exact first-action BEGIN command, event, and Effect Intent."""
    authorization = _execution_authorization_command(command_marker="1", event_marker="1")
    bound_authorization = authorization_fingerprint or authorization.authorization_fingerprint
    decision_fingerprint = sha256(_registered_decision_bytes()).digest()
    profile_id = "cap_" + "6" * 48
    profile_fingerprint = "sha256:" + "6" * 64
    evidence_id = "evi_" + "7" * 48
    evidence_fingerprint = "sha256:" + "7" * 64
    input_refs = [
        {
            "fingerprint": "sha256:" + "8" * 64,
            "ref_id": "dsi_" + "8" * 48,
            "ref_type": "DESIRED_STATE_INVENTORY",
        },
        {
            "fingerprint": "sha256:" + "9" * 64,
            "ref_id": "emp_" + "9" * 48,
            "ref_type": "EMBEDDING_PROFILE",
        },
    ]
    stop_conditions = [
        "ATTEMPT_CEILING",
        "AUTHORITY_INVALID",
        "CANCELLATION_BEFORE_EFFECT",
        "CAPABILITY_INACTIVE",
        "DEADLINE",
        "POSTCONDITION_MET",
        "PRECONDITION_CHANGED",
    ]
    action = checked_json_value(
        {
            "action_id": "EMBED_RECORDS",
            "attempt_ceiling": 3,
            "capability_profile_ref": {
                "fingerprint": profile_fingerprint,
                "ref_id": profile_id,
                "ref_type": "CAPABILITY_PROFILE",
            },
            "compensation": {"mode": "NO_COMPENSATION"},
            "deadline": "9999-12-31T23:59:59Z",
            "destination_class": "EMBEDDING_PROVIDER",
            "effect_command_fingerprint": "sha256:" + "a" * 64,
            "effect_type": "EMBEDDING_PROVIDER_CALL",
            "expected_remote_precondition_ref": {
                "contract_id": "asklegal.embedding-precondition",
                "fingerprint": "sha256:" + "b" * 64,
                "version": "1.0.0",
            },
            "input_refs": input_refs,
            "owning_application": "PROMOTION_WORKER",
            "permitted_checkpoint": "EMBED_RECORDS",
            "required_capability": "CALL_EMBEDDING_PROVIDER",
            "retry_class": "RECONCILE_BEFORE_RETRY",
            "sequence": 1,
            "stable_idempotency_key": "promotion-embed-records-v1",
            "stop_conditions": stop_conditions,
            "success_postcondition_ref": {
                "contract_id": "asklegal.embedding-postcondition",
                "fingerprint": "sha256:" + "c" * 64,
                "version": "1.0.0",
            },
        }
    )
    action_fingerprint = f"sha256:{sha256(canonicalize(action)).hexdigest()}"
    effect_intent_id = "efi_" + intent_marker * 48
    command_id = "cmd_" + command_marker * 48
    command = canonicalize(
        checked_json_value(
            {
                "action": "BEGIN_REGISTERED_PROMOTION_EXECUTION",
                "action_authority": action,
                "action_contract_version": "1.0.0",
                "action_fingerprint": action_fingerprint,
                "approval_id": _REGISTERED_APPROVAL_ID,
                "authorization_fingerprint": bound_authorization,
                "capability_evidence_ref": {
                    "fingerprint": evidence_fingerprint,
                    "ref_id": evidence_id,
                    "ref_type": "EVIDENCE",
                },
                "effect_intent_id": effect_intent_id,
                "execution_lineage_fingerprint": "sha256:" + "5" * 64,
                "execution_lineage_id": _REGISTERED_LINEAGE_ID,
                "manifest_fingerprint": _REGISTERED_MANIFEST_FINGERPRINT,
                "manifest_id": _REGISTERED_MANIFEST_ID,
                "promotion_worker_identity_fingerprint": "sha256:" + "6" * 64,
                "promotion_worker_identity_id": "act_" + "6" * 48,
                "proposal_package_id": _REGISTERED_PROPOSAL_ID,
            }
        )
    )
    command_fingerprint = f"sha256:{sha256(command).hexdigest()}"
    event_id = "pex_" + event_marker * 48
    event = canonicalize(
        checked_json_value(
            {
                "action_id": "BEGIN",
                "approval_ref": {
                    "fingerprint": f"sha256:{decision_fingerprint.hex()}",
                    "ref_id": _REGISTERED_APPROVAL_ID,
                    "ref_type": "APPROVAL",
                },
                "attempt_number": 0,
                "event_time": "2026-08-22T00:04:00Z",
                "execution_lineage_id": _REGISTERED_LINEAGE_ID,
                "external_effects": "DECLARED_MANIFEST_ACTION",
                "failure_codes": [],
                "from_state": "EXECUTION_AUTHORIZED",
                "idempotency": {
                    "idempotency_key": f"begin:{_REGISTERED_LINEAGE_ID}",
                    "input_fingerprint": command_fingerprint,
                },
                "immutable": True,
                "promotion_execution_event_id": event_id,
                "promotion_manifest_ref": {
                    "fingerprint": _REGISTERED_MANIFEST_FINGERPRINT,
                    "ref_id": _REGISTERED_MANIFEST_ID,
                    "ref_type": "PROMOTION_MANIFEST",
                },
                "reason_codes": [
                    "APPROVAL_EXACTLY_BOUND",
                    "REFERENCE_VERIFIED",
                    "TRANSITION_ALLOWED",
                    "VALIDATION_COMPLETE",
                ],
                "receipt_refs": [],
                "result_code": "SUCCEEDED",
                "schema_id": "asklegal.promotion-execution-event",
                "schema_version": "1.0.0",
                "to_state": "EXECUTION_RUNNING",
            }
        )
    )
    intent = canonicalize(
        checked_json_value(
            {
                "aggregate_ref": {
                    "fingerprint": "sha256:" + "5" * 64,
                    "ref_id": _REGISTERED_LINEAGE_ID,
                    "ref_type": "EXECUTION_LINEAGE",
                },
                "attempt_ceiling": 3,
                "capability_profile_ref": {
                    "fingerprint": profile_fingerprint,
                    "ref_id": profile_id,
                    "ref_type": "CAPABILITY_PROFILE",
                },
                "command_ref": {
                    "fingerprint": command_fingerprint,
                    "ref_id": command_id,
                    "ref_type": "COMMAND",
                },
                "compensation": {"mode": "NO_COMPENSATION"},
                "created_at": "2026-08-22T00:04:00Z",
                "deadline": "9999-12-31T23:59:59Z",
                "destination_class": "EMBEDDING_PROVIDER",
                "effect_command_fingerprint": "sha256:" + "a" * 64,
                "effect_intent_id": effect_intent_id,
                "effect_type": "EMBEDDING_PROVIDER_CALL",
                "execution_lineage_ref": {
                    "fingerprint": "sha256:" + "5" * 64,
                    "ref_id": _REGISTERED_LINEAGE_ID,
                    "ref_type": "EXECUTION_LINEAGE",
                },
                "expected_remote_precondition_ref": {
                    "contract_id": "asklegal.embedding-precondition",
                    "fingerprint": "sha256:" + "b" * 64,
                    "version": "1.0.0",
                },
                "immutable": True,
                "input_refs": input_refs,
                "owning_application": "PROMOTION_WORKER",
                "permitted_checkpoint": "EMBED_RECORDS",
                "required_capability": "CALL_EMBEDDING_PROVIDER",
                "retry_class": "RECONCILE_BEFORE_RETRY",
                "schema_id": "asklegal.effect-intent",
                "schema_version": "1.0.0",
                "stable_idempotency_key": "promotion-embed-records-v1",
                "stop_conditions": stop_conditions,
                "success_postcondition_ref": {
                    "contract_id": "asklegal.embedding-postcondition",
                    "fingerprint": "sha256:" + "c" * 64,
                    "version": "1.0.0",
                },
            }
        )
    )
    return RegisteredExecutionBeginCommand(
        command_id,
        command,
        _REGISTERED_APPROVAL_ID,
        _REGISTERED_PROPOSAL_ID,
        decision_fingerprint,
        _REGISTERED_MANIFEST_ID,
        _REGISTERED_MANIFEST_FINGERPRINT,
        _REGISTERED_LINEAGE_ID,
        "sha256:" + "5" * 64,
        bound_authorization,
        "EMBED_RECORDS",
        action_fingerprint,
        profile_id,
        profile_fingerprint,
        evidence_id,
        evidence_fingerprint,
        "9999-12-31T23:59:59",
        event_id,
        event,
        effect_intent_id,
        "EMBEDDING_PROVIDER_CALL",
        intent,
        "9999-12-31T23:59:59",
        3,
    )


@dataclass(frozen=True, slots=True)
class _TerminalFixture:
    """One registered approved decision used by terminal lifecycle proofs."""

    approval_id: str
    proposal_id: str
    manifest_id: str
    manifest_fingerprint: str
    decision_fingerprint: bytes


@dataclass(frozen=True, slots=True)
class _TerminalFixtureInput:
    """One deliberately malformed or non-approved SQL projection variant."""

    approval_id: str | None = None
    base_state_fingerprint: str | None = None
    base_state_id: str | None = None
    decision_event_type: str = "PROPOSAL_APPROVED"
    decision_value: str = "APPROVED"
    manifest_fingerprint: str | None = None
    manifest_id: str | None = None
    valid_from: str = "2026-08-22T00:00:00Z"


def _register_terminal_fixture(
    database: MssqlConnectionFactory,
    marker: str,
    *,
    fixture_input: _TerminalFixtureInput | None = None,
) -> _TerminalFixture:
    """Register one independent schema-shaped approved proposal."""
    fixture_input = fixture_input or _TerminalFixtureInput()
    identity_suffix = sha256(f"terminal-fixture:{marker}".encode()).hexdigest()[:48]
    fixture_fingerprint = "sha256:" + sha256(f"terminal-fingerprint:{marker}".encode()).hexdigest()
    proposal_id = "ppk_" + identity_suffix
    approval_id = fixture_input.approval_id or "apr_" + identity_suffix
    manifest_id = fixture_input.manifest_id or "pmn_" + identity_suffix
    manifest_fingerprint = fixture_input.manifest_fingerprint or fixture_fingerprint
    receipt = canonicalize(checked_json_value({"package_id": proposal_id, "state": "REVIEW_READY"}))
    registered = RegisterEventStore(database).record_event(
        RegisterEventCommand(
            owning_application="CONTROL_PLANE",
            command_id=f"command-terminal-register-{marker}",
            command_bytes=canonicalize(
                checked_json_value(
                    {
                        "action": "REGISTER_REVIEW_READY_PROPOSAL",
                        "proposal_package_id": proposal_id,
                    }
                )
            ),
            target_id=proposal_id,
            expected_version=None,
            expected_absent=True,
            expires_at="9999-12-31T23:59:59",
            winner_key=f"review-ready:{proposal_id}",
            event_id="evt_" + identity_suffix,
            event_type="PROPOSAL_REVIEW_READY",
            event_bytes=receipt,
        )
    )
    assert registered.result_code == "APPLIED"
    decision = canonicalize(
        checked_json_value(
            {
                "approval_id": approval_id,
                "authority_evidence_ref": {
                    "fingerprint": fixture_fingerprint,
                    "ref_id": "evi_" + identity_suffix,
                    "ref_type": "EVIDENCE",
                },
                "decision": fixture_input.decision_value,
                "decision_time": "2026-08-22T00:01:00Z",
                "expected_base_serving_state_ref": {
                    "fingerprint": fixture_input.base_state_fingerprint or fixture_fingerprint,
                    "ref_id": fixture_input.base_state_id or "srv_" + identity_suffix,
                    "ref_type": "SERVING_STATE",
                },
                "governance_policy_state": "CONFIGURED",
                "immutable": True,
                "promotion_manifest_ref": {
                    "fingerprint": manifest_fingerprint,
                    "ref_id": manifest_id,
                    "ref_type": "PROMOTION_MANIFEST",
                },
                "reason": "Terminal lifecycle SQL proof",
                "reviewer_identity_ref": {
                    "fingerprint": fixture_fingerprint,
                    "ref_id": "act_" + identity_suffix,
                    "ref_type": "ACTOR",
                },
                "schema_id": "asklegal.approval-decision",
                "schema_version": "1.1.0",
                "valid_from": fixture_input.valid_from,
                "validity_condition_refs": [
                    {
                        "contract_id": "configuration",
                        "fingerprint": fixture_fingerprint,
                        "version": "1.0.0",
                    }
                ],
            }
        )
    )
    decided = RegisterEventStore(database).record_event(
        RegisterEventCommand(
            owning_application="REVIEW_APPLICATION",
            command_id=f"command-terminal-decision-{marker}",
            command_bytes=canonicalize(
                checked_json_value(
                    {
                        "action": "RECORD_PROPOSAL_DECISION",
                        "approval_id": approval_id,
                        "proposal_package_id": proposal_id,
                    }
                )
            ),
            target_id=proposal_id,
            expected_version=None,
            expected_absent=True,
            expires_at="9999-12-31T23:59:59",
            winner_key=f"proposal-decision:{manifest_id}",
            event_id="evt_" + sha256(f"decision:{marker}".encode()).hexdigest()[:48],
            event_type=fixture_input.decision_event_type,
            event_bytes=decision,
        )
    )
    assert decided.result_code == "APPLIED"
    return _TerminalFixture(
        approval_id,
        proposal_id,
        manifest_id,
        manifest_fingerprint,
        sha256(decision).digest(),
    )


def _raw_queue_claim(
    database: MssqlConnectionFactory, worker_id: str, claimed_until: str
) -> tuple[object, ...] | None:
    """Call the queue procedure directly to prove SQL-owned grammar enforcement."""
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "EXEC promotion.claim_next_approved_promotion_v1 @worker_id = ?, @claimed_until = ?",
            (worker_id, claimed_until),
        )
        row = cursor.fetchone()
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    else:
        return row
    finally:
        cursor.close()
        connection.close()


def _queue_permission_rows(
    database: MssqlConnectionFactory, principal: str
) -> list[tuple[object, ...]]:
    """Read both procedure and table permissions under one application principal."""
    return _execute(
        database,
        "EXECUTE AS USER='"
        + principal
        + "'; SELECT "
        + "HAS_PERMS_BY_NAME('promotion.claim_next_approved_promotion_v1', 'OBJECT', 'EXECUTE'), "
        + "HAS_PERMS_BY_NAME('promotion.acknowledge_approved_promotion_started_v1', "
        + "'OBJECT', 'EXECUTE'), "
        + "HAS_PERMS_BY_NAME('promotion.approved_promotion_claim_current', 'OBJECT', 'SELECT'), "
        + "HAS_PERMS_BY_NAME('promotion.approved_promotion_acknowledgement_fact', "
        + "'OBJECT', 'SELECT'); REVERT;",
        fetch=True,
    )


def _queue_direct_write_error(
    database: MssqlConnectionFactory, principal: str, table: str, operation: str
) -> str:
    """Attempt one rollback-safe direct queue-table mutation as an application principal."""
    write_statements = {
        ("promotion.approved_promotion_claim_current", "INSERT"): (
            (
                "INSERT promotion.approved_promotion_claim_current (approval_id) "
                "SELECT ? WHERE ? = ?;"
            ),
            ("apr_" + "0" * 48, 1, 0),
        ),
        ("promotion.approved_promotion_claim_current", "UPDATE"): (
            (
                "UPDATE promotion.approved_promotion_claim_current "
                "SET approval_id = approval_id WHERE ? = ?;"
            ),
            (1, 0),
        ),
        ("promotion.approved_promotion_claim_current", "DELETE"): (
            "DELETE FROM promotion.approved_promotion_claim_current WHERE ? = ?;",
            (1, 0),
        ),
        ("promotion.approved_promotion_acknowledgement_fact", "INSERT"): (
            (
                "INSERT promotion.approved_promotion_acknowledgement_fact (approval_id) "
                "SELECT ? WHERE ? = ?;"
            ),
            ("apr_" + "0" * 48, 1, 0),
        ),
        ("promotion.approved_promotion_acknowledgement_fact", "UPDATE"): (
            (
                "UPDATE promotion.approved_promotion_acknowledgement_fact "
                "SET approval_id = approval_id WHERE ? = ?;"
            ),
            (1, 0),
        ),
        ("promotion.approved_promotion_acknowledgement_fact", "DELETE"): (
            "DELETE FROM promotion.approved_promotion_acknowledgement_fact WHERE ? = ?;",
            (1, 0),
        ),
    }
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute(f"EXECUTE AS USER='{principal}';")
        statement, parameters = write_statements[(table, operation)]
        cursor.execute(statement, parameters)
    except Exception as error:
        connection.rollback()
        return str(error)
    else:
        connection.rollback()
    finally:
        cursor.close()
        connection.close()
    pytest.fail(f"{principal} directly performed {operation} on {table}")


def _terminal_command(
    fixture: _TerminalFixture,
    *,
    action: str,
    marker: str,
) -> RegisteredApprovalTerminalCommand:
    """Build one exact schema-valid revoke or invalidate command."""
    revoked = action == "REVOKE"
    event = canonicalize(
        checked_json_value(
            {
                "approval_lifecycle_event_id": "ape_" + marker * 48,
                "approval_ref": {
                    "fingerprint": f"sha256:{fixture.decision_fingerprint.hex()}",
                    "ref_id": fixture.approval_id,
                    "ref_type": "APPROVAL",
                },
                "event_time": "2026-08-22T00:02:00Z",
                "event_type": action,
                "evidence_refs": [
                    {
                        "fingerprint": "sha256:" + marker * 64,
                        "ref_id": "evi_" + marker * 48,
                        "ref_type": "EVIDENCE",
                    }
                ],
                "execution_lineage_refs": [],
                "from_state": "APPROVAL_APPROVED",
                "immutable": True,
                "responsible_identity_ref": {
                    "fingerprint": "sha256:" + marker * 64,
                    "ref_id": "act_" + marker * 48,
                    "ref_type": "ACTOR",
                },
                "schema_id": "asklegal.approval-lifecycle-event",
                "schema_version": "1.1.0",
                "to_state": "APPROVAL_REVOKED" if revoked else "APPROVAL_INVALIDATED",
            }
        )
    )
    document: dict[str, object] = {
        "action": "REVOKE_REGISTERED_APPROVAL" if revoked else "INVALIDATE_REGISTERED_APPROVAL",
        "approval_id": fixture.approval_id,
        "decision_fingerprint": f"sha256:{fixture.decision_fingerprint.hex()}",
        "manifest_fingerprint": fixture.manifest_fingerprint,
        "manifest_id": fixture.manifest_id,
        "proposal_package_id": fixture.proposal_id,
    }
    if revoked:
        document["reason"] = "Withdraw before execution"
        document["revoker_subject"] = "person-sql-proof"
    else:
        document["reason_code"] = "VALIDITY_PREDICATE_DRIFT"
    return RegisteredApprovalTerminalCommand(
        f"command-terminal-{action.lower()}-{marker}",
        canonicalize(checked_json_value(document)),
        fixture.approval_id,
        fixture.proposal_id,
        fixture.decision_fingerprint,
        fixture.manifest_id,
        fixture.manifest_fingerprint,
        "9999-12-31T23:59:59",
        "ape_" + marker * 48,
        event,
    )


def _consumption_for_terminal_fixture(
    fixture: _TerminalFixture,
    marker: str,
) -> RegisteredApprovalConsumptionCommand:
    """Build a valid consumption that must lose after a terminal event."""
    lineage_id = "exe_" + marker * 48
    event_id = "ape_" + marker * 48
    event = canonicalize(
        checked_json_value(
            {
                "approval_lifecycle_event_id": event_id,
                "approval_ref": {
                    "fingerprint": f"sha256:{fixture.decision_fingerprint.hex()}",
                    "ref_id": fixture.approval_id,
                    "ref_type": "APPROVAL",
                },
                "event_time": "2026-08-22T00:03:00Z",
                "event_type": "CONSUME_FOR_ONE_EXECUTION_LINEAGE",
                "evidence_refs": [
                    {
                        "fingerprint": "sha256:" + marker * 64,
                        "ref_id": "evi_" + marker * 48,
                        "ref_type": "EVIDENCE",
                    }
                ],
                "execution_lineage_refs": [
                    {
                        "fingerprint": "sha256:" + marker * 64,
                        "ref_id": lineage_id,
                        "ref_type": "EXECUTION_LINEAGE",
                    }
                ],
                "from_state": "APPROVAL_APPROVED",
                "immutable": True,
                "responsible_identity_ref": {
                    "fingerprint": "sha256:" + marker * 64,
                    "ref_id": "act_" + marker * 48,
                    "ref_type": "ACTOR",
                },
                "schema_id": "asklegal.approval-lifecycle-event",
                "schema_version": "1.1.0",
                "to_state": "APPROVAL_CONSUMED",
            }
        )
    )
    command = canonicalize(
        checked_json_value(
            {
                "action": "CONSUME_REGISTERED_APPROVAL",
                "approval_id": fixture.approval_id,
                "decision_fingerprint": f"sha256:{fixture.decision_fingerprint.hex()}",
                "execution_lineage_id": lineage_id,
                "manifest_fingerprint": fixture.manifest_fingerprint,
                "manifest_id": fixture.manifest_id,
                "proposal_package_id": fixture.proposal_id,
            }
        )
    )
    return RegisteredApprovalConsumptionCommand(
        f"command-terminal-consume-{marker}",
        command,
        fixture.approval_id,
        fixture.proposal_id,
        fixture.decision_fingerprint,
        fixture.manifest_id,
        fixture.manifest_fingerprint,
        lineage_id,
        "9999-12-31T23:59:59",
        event_id,
        event,
    )


def _prove_terminal_lifecycle(database: MssqlConnectionFactory) -> None:
    """Prove revocation/invalidation replay, exclusion, race, and permissions."""
    lifecycle = RegisteredApprovalLifecycleStore(database)
    consumption = RegisteredApprovalStore(database)

    revoked = _register_terminal_fixture(database, "7")
    revoke_command = _terminal_command(revoked, action="REVOKE", marker="a")
    original_revoke = lifecycle.revoke(revoke_command)
    replayed_revoke = lifecycle.revoke(revoke_command)
    assert original_revoke.result_code == "APPLIED"
    assert original_revoke.authoritative_version == 2
    assert replayed_revoke.replayed is True
    with pytest.raises(Exception, match="ASKLEGAL_APPROVAL_NOT_CONSUMABLE"):
        consumption.consume(_consumption_for_terminal_fixture(revoked, "b"))

    invalidated = _register_terminal_fixture(database, "8")
    invalidate_command = _terminal_command(invalidated, action="INVALIDATE", marker="c")
    original_invalidation = lifecycle.invalidate(invalidate_command)
    replayed_invalidation = lifecycle.invalidate(invalidate_command)
    assert original_invalidation.result_code == "APPLIED"
    assert original_invalidation.authoritative_version == 1
    assert replayed_invalidation.replayed is True
    with pytest.raises(Exception, match="ASKLEGAL_APPROVAL_NOT_CONSUMABLE"):
        consumption.consume(_consumption_for_terminal_fixture(invalidated, "d"))


def _prove_queue_exclusions_permissions_and_lock(
    database: MssqlConnectionFactory,
    queue: ApprovedPromotionQueueStore,
    lifecycle: RegisteredApprovalLifecycleStore,
) -> None:
    """Prove every terminal/malformed exclusion and finite-lock recovery path."""
    revoked = _register_terminal_fixture(database, "queue-revoked")
    lifecycle.revoke(_terminal_command(revoked, action="REVOKE", marker="5"))
    assert queue.claim_next("pwr_" + "6" * 48, "9999-12-31T23:59:59Z") is None
    invalidated = _register_terminal_fixture(database, "queue-invalidated")
    lifecycle.invalidate(_terminal_command(invalidated, action="INVALIDATE", marker="6"))
    assert queue.claim_next("pwr_" + "7" * 48, "9999-12-31T23:59:59Z") is None
    rejected = _register_terminal_fixture(
        database,
        "queue-rejected",
        fixture_input=_TerminalFixtureInput(
            decision_event_type="PROPOSAL_REJECTED", decision_value="REJECTED"
        ),
    )
    assert queue.claim_next("pwr_" + "8" * 48, "9999-12-31T23:59:59Z") is None
    assert rejected.approval_id.startswith("apr_")
    not_yet_valid = _register_terminal_fixture(
        database,
        "queue-not-yet-valid",
        fixture_input=_TerminalFixtureInput(valid_from="9999-12-31T23:59:59Z"),
    )
    assert queue.claim_next("pwr_" + "9" * 48, "9999-12-31T23:59:59Z") is None
    assert not_yet_valid.approval_id.startswith("apr_")
    malformed = _register_terminal_fixture(
        database,
        "queue-malformed-fingerprint",
        fixture_input=_TerminalFixtureInput(manifest_fingerprint="sha256:" + "A" * 64),
    )
    assert queue.claim_next("pwr_" + "a" * 48, "9999-12-31T23:59:59Z") is None
    assert malformed.approval_id.startswith("apr_")
    malformed_approval = _register_terminal_fixture(
        database,
        "queue-malformed-approval",
        fixture_input=_TerminalFixtureInput(approval_id="apr_" + "A" * 48),
    )
    assert queue.claim_next("pwr_" + "c" * 48, "9999-12-31T23:59:59Z") is None
    assert malformed_approval.approval_id == "apr_" + "A" * 48
    malformed_manifest = _register_terminal_fixture(
        database,
        "queue-malformed-manifest",
        fixture_input=_TerminalFixtureInput(manifest_id="pmn_" + "b" * 47 + "!"),
    )
    assert queue.claim_next("pwr_" + "d" * 48, "9999-12-31T23:59:59Z") is None
    assert malformed_manifest.manifest_id.endswith("!")
    malformed_base = _register_terminal_fixture(
        database,
        "queue-malformed-base",
        fixture_input=_TerminalFixtureInput(
            base_state_id="srv_" + "c" * 47,
            base_state_fingerprint="sha256:" + "c" * 32 + "A" + "c" * 31,
        ),
    )
    assert queue.claim_next("pwr_" + "e" * 48, "9999-12-31T23:59:59Z") is None
    assert malformed_base.approval_id.startswith("apr_")

    for principal in (
        "asklegal_control_app",
        "asklegal_review_app",
        "asklegal_acquisition_app",
        "asklegal_legal_processing_app",
    ):
        assert _queue_permission_rows(database, principal) == [(0, 0, 0, 0)]
        for table in (
            "promotion.approved_promotion_claim_current",
            "promotion.approved_promotion_acknowledgement_fact",
        ):
            for operation in ("INSERT", "UPDATE", "DELETE"):
                assert (
                    "permission"
                    in _queue_direct_write_error(database, principal, table, operation).lower()
                )
    assert _queue_permission_rows(database, "asklegal_promotion_app") == [(1, 1, 0, 0)]

    timeout = _register_terminal_fixture(database, "queue-claim-lock-timeout")
    holder = database()
    holder_cursor = holder.cursor()
    try:
        holder_cursor.execute("BEGIN TRANSACTION;")
        holder_cursor.execute(
            "SELECT proposal_package_id FROM review.proposal_package_review_v1 WITH "
            "(UPDLOCK, HOLDLOCK) WHERE proposal_package_id = ?;",
            (timeout.proposal_id,),
        )
        with pytest.raises(Exception, match="ASKLEGAL_APPROVED_PROMOTION_QUEUE_LOCK_TIMEOUT"):
            queue.claim_next("pwr_" + "d" * 48, "9999-12-31T23:59:59Z")
    finally:
        holder.rollback()
        holder_cursor.close()
        holder.close()
    retry = queue.claim_next("pwr_" + "d" * 48, "9999-12-31T23:59:59Z")
    assert retry is not None and retry.approval_id == timeout.approval_id

    def terminal_acknowledgement_race(action: str, marker: str, fixture_marker: str) -> None:
        race_fixture = _register_terminal_fixture(database, fixture_marker)
        claim = queue.claim_next("pwr_" + marker * 48, "9999-12-31T23:59:59Z")
        assert claim is not None and claim.approval_id == race_fixture.approval_id
        terminal = _terminal_command(race_fixture, action=action, marker=marker)

        def terminal_or_acknowledge() -> str:
            try:
                if action == "REVOKE":
                    lifecycle.revoke(terminal)
                else:
                    lifecycle.invalidate(terminal)
            except Exception as error:
                return str(error)
            return "terminal"

        def acknowledge_race() -> str:
            try:
                queue.acknowledge_started(claim, "exe_" + marker * 48)
            except Exception as error:
                return str(error)
            return "acknowledged"

        with ThreadPoolExecutor(max_workers=2) as pool:
            terminal_future = pool.submit(terminal_or_acknowledge)
            acknowledgement_future = pool.submit(acknowledge_race)
            terminal_outcome = terminal_future.result()
            acknowledgement_outcome = acknowledgement_future.result()
        assert terminal_outcome == "terminal"
        assert acknowledgement_outcome != "acknowledged"
        assert (
            "ASKLEGAL_APPROVED_PROMOTION_QUEUE_APPROVAL_TERMINAL" in acknowledgement_outcome
            or "ASKLEGAL_APPROVED_PROMOTION_QUEUE_NOT_CONSUMED" in acknowledgement_outcome
        )

    terminal_acknowledgement_race("REVOKE", "0", "queue-revocation-ack-race")
    terminal_acknowledgement_race("INVALIDATE", "8", "queue-invalidation-ack-race")

    acknowledgement_timeout = _register_terminal_fixture(database, "queue-ack-lock-timeout")
    acknowledgement_claim = queue.claim_next("pwr_" + "b" * 48, "9999-12-31T23:59:59Z")
    assert acknowledgement_claim is not None
    acknowledgement_consumption = RegisteredApprovalStore(database).consume(
        _consumption_for_terminal_fixture(acknowledgement_timeout, "7")
    )
    assert acknowledgement_consumption.result_code == "APPLIED"
    acknowledgement_holder = database()
    acknowledgement_cursor = acknowledgement_holder.cursor()
    try:
        acknowledgement_cursor.execute("BEGIN TRANSACTION;")
        acknowledgement_cursor.execute(
            "SELECT approval_id FROM promotion.approved_promotion_claim_current WITH "
            "(UPDLOCK, HOLDLOCK) WHERE approval_id = ?;",
            (acknowledgement_timeout.approval_id,),
        )
        with pytest.raises(
            Exception, match="ASKLEGAL_APPROVED_PROMOTION_ACKNOWLEDGEMENT_LOCK_TIMEOUT"
        ):
            queue.acknowledge_started(acknowledgement_claim, "exe_" + "7" * 48)
    finally:
        acknowledgement_holder.rollback()
        acknowledgement_cursor.close()
        acknowledgement_holder.close()
    assert _execute(database, "SELECT 1;", fetch=True) == [(1,)]
    queue.acknowledge_started(acknowledgement_claim, "exe_" + "7" * 48)
    queue.acknowledge_started(acknowledgement_claim, "exe_" + "7" * 48)


def _prove_approved_promotion_wakeup(database: MssqlConnectionFactory) -> None:
    """Prove queue grammar, fencing, exclusion, finite locking, and no-effect behavior."""
    lifecycle = RegisteredApprovalLifecycleStore(database)
    consumption = RegisteredApprovalStore(database)
    before = _execute(
        database,
        "SELECT (SELECT COUNT(*) FROM register.effect_intent_fact), "
        "(SELECT COUNT(*) FROM register.effect_attempt_fact), "
        "(SELECT COUNT(*) FROM promotion.serving_state_current), "
        "(SELECT COUNT(*) FROM register.event_v1_fact WHERE event_type IN "
        "('PROMOTION_EXECUTION_AUTHORIZED', 'PROMOTION_EXECUTION_BEGUN'));",
        fetch=True,
    )
    fixture = _register_terminal_fixture(database, "queue-first-claim")
    queue = ApprovedPromotionQueueStore(database)
    for invalid_worker in (
        "pwr_" + "E" * 48,
        "pwr_" + "e" * 47 + "!",
        "pwr_" + "e" * 47,
        "pwr_" + "e" * 49,
        "pwr_" + "e" * 24 + "A" + "e" * 23,
    ):
        with pytest.raises(Exception, match="ASKLEGAL_APPROVED_PROMOTION_QUEUE_WORKER_INVALID"):
            _raw_queue_claim(database, invalid_worker, "9999-12-31T23:59:59Z")
    first = queue.claim_next("pwr_" + "e" * 48, "9999-12-31T23:59:59Z")
    assert first is not None
    assert first.approval_id == fixture.approval_id
    assert first.proposal_package_id == fixture.proposal_id
    assert first.decision_fingerprint == "sha256:" + fixture.decision_fingerprint.hex()
    assert first.manifest_id == fixture.manifest_id
    assert first.manifest_fingerprint == fixture.manifest_fingerprint
    assert first.generation == 1
    assert first.fencing_token == 1
    replay = queue.claim_next(first.claimant_worker_id, first.claimed_until)
    assert replay == first
    assert queue.claim_next("pwr_" + "f" * 48, "9999-12-31T23:59:59Z") is None

    concurrent = _register_terminal_fixture(database, "queue-concurrent-claim")

    def concurrent_claim(worker_id: str) -> ApprovedPromotionClaim | None:
        return ApprovedPromotionQueueStore(database).claim_next(worker_id, "9999-12-31T23:59:59Z")

    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent_claims = list(pool.map(concurrent_claim, ("pwr_" + "1" * 48, "pwr_" + "2" * 48)))
    winners = [claim for claim in concurrent_claims if claim is not None]
    assert len(winners) == 1
    assert winners[0].approval_id == concurrent.approval_id

    takeover = _register_terminal_fixture(database, "queue-takeover")
    original = queue.claim_next("pwr_" + "3" * 48, "9999-12-31T23:59:59Z")
    assert original is not None and original.approval_id == takeover.approval_id
    _execute(
        database,
        "UPDATE promotion.approved_promotion_claim_current "
        "SET claimed_until = '2000-01-01T00:00:00' WHERE approval_id = '"
        + takeover.approval_id
        + "';",
    )
    replacement = queue.claim_next("pwr_" + "4" * 48, "9999-12-31T23:59:59Z")
    assert replacement is not None and replacement.approval_id == takeover.approval_id
    assert (replacement.generation, replacement.fencing_token) == (2, 2)

    already_consumed = _register_terminal_fixture(database, "queue-already-consumed")
    consumed_before_acknowledgement = consumption.consume(
        _consumption_for_terminal_fixture(already_consumed, "9")
    )
    assert consumed_before_acknowledgement.result_code == "APPLIED"
    assert queue.claim_next("pwr_" + "9" * 48, "9999-12-31T23:59:59Z") is None

    with pytest.raises(Exception, match="ASKLEGAL_APPROVED_PROMOTION_QUEUE_NOT_CONSUMED"):
        queue.acknowledge_started(first, "exe_" + "f" * 48)

    consumed = RegisteredApprovalStore(database).consume(
        _consumption_for_terminal_fixture(fixture, "f")
    )
    assert consumed.result_code == "APPLIED"
    queue.acknowledge_started(first, "exe_" + "f" * 48)
    queue.acknowledge_started(first, "exe_" + "f" * 48)
    with pytest.raises(
        Exception, match="ASKLEGAL_APPROVED_PROMOTION_ACKNOWLEDGEMENT_REPLAY_MISMATCH"
    ):
        queue.acknowledge_started(first, "exe_" + "a" * 48)
    takeover_consumed = consumption.consume(_consumption_for_terminal_fixture(takeover, "4"))
    assert takeover_consumed.result_code == "APPLIED"
    with pytest.raises(Exception, match="ASKLEGAL_APPROVED_PROMOTION_QUEUE_STALE_CLAIM"):
        queue.acknowledge_started(original, "exe_" + "4" * 48)
    queue.acknowledge_started(replacement, "exe_" + "4" * 48)

    _prove_queue_exclusions_permissions_and_lock(database, queue, lifecycle)

    raced = _register_terminal_fixture(database, "queue-terminal-lifecycle-race")
    race_commands = (
        ("REVOKE", _terminal_command(raced, action="REVOKE", marker="1")),
        ("INVALIDATE", _terminal_command(raced, action="INVALIDATE", marker="2")),
    )

    def race_terminal(item: tuple[str, RegisteredApprovalTerminalCommand]) -> str:
        action, command = item
        try:
            if action == "REVOKE":
                lifecycle.revoke(command)
            else:
                lifecycle.invalidate(command)
        except Exception as error:
            return str(error)
        return "winner"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(race_terminal, race_commands))
    assert outcomes.count("winner") == 1
    assert (
        sum(
            "ASKLEGAL_APPROVAL_NOT_REVOCABLE" in item
            or "ASKLEGAL_APPROVAL_NOT_INVALIDATABLE" in item
            for item in outcomes
        )
        == 1
    )
    with pytest.raises(Exception, match="ASKLEGAL_APPROVAL_NOT_CONSUMABLE"):
        consumption.consume(_consumption_for_terminal_fixture(raced, "e"))

    after = _execute(
        database,
        "SELECT (SELECT COUNT(*) FROM register.effect_intent_fact), "
        "(SELECT COUNT(*) FROM register.effect_attempt_fact), "
        "(SELECT COUNT(*) FROM promotion.serving_state_current), "
        "(SELECT COUNT(*) FROM register.event_v1_fact WHERE event_type IN "
        "('PROMOTION_EXECUTION_AUTHORIZED', 'PROMOTION_EXECUTION_BEGUN'));",
        fetch=True,
    )
    assert after == before

    review_permissions = _execute(
        database,
        "EXECUTE AS USER='asklegal_review_app'; "
        "SELECT HAS_PERMS_BY_NAME('review.revoke_registered_approval_v1', "
        "'OBJECT', 'EXECUTE'), "
        "HAS_PERMS_BY_NAME('promotion.invalidate_registered_approval_v1', "
        "'OBJECT', 'EXECUTE'); REVERT;",
        fetch=True,
    )
    promotion_permissions = _execute(
        database,
        "EXECUTE AS USER='asklegal_promotion_app'; "
        "SELECT HAS_PERMS_BY_NAME('review.revoke_registered_approval_v1', "
        "'OBJECT', 'EXECUTE'), "
        "HAS_PERMS_BY_NAME('promotion.invalidate_registered_approval_v1', "
        "'OBJECT', 'EXECUTE'); REVERT;",
        fetch=True,
    )
    assert review_permissions == [(1, 0)]
    assert promotion_permissions == [(0, 1)]


def _factory(database: str, *, autocommit: bool = False) -> MssqlConnectionFactory:
    base = os.environ.get("ASKLEGAL_SQL_CONNECTION_BASE")
    if base is None:
        pytest.skip("ASKLEGAL_SQL_CONNECTION_BASE is not set")
    return MssqlConnectionFactory(f"{base};Database={database};", autocommit=autocommit)


def _execute(
    factory: MssqlConnectionFactory, sql: str, *, fetch: bool = False
) -> list[tuple[object, ...]]:
    connection = factory()
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchall() if fetch else []
        connection.commit()
        return rows
    finally:
        cursor.close()
        connection.close()


def _prove_review_ready_projection(database: MssqlConnectionFactory) -> None:
    review_receipt = canonicalize(
        checked_json_value({"package_id": _REGISTERED_PROPOSAL_ID, "state": "REVIEW_READY"})
    )
    review_result = RegisterEventStore(database).record_event(
        RegisterEventCommand(
            owning_application="CONTROL_PLANE",
            command_id="command-review-ready",
            command_bytes=b'{"action":"REGISTER_REVIEW_READY_PROPOSAL"}',
            target_id=_REGISTERED_PROPOSAL_ID,
            expected_version=None,
            expected_absent=True,
            expires_at="9999-12-31T23:59:59",
            winner_key=f"review-ready:{_REGISTERED_PROPOSAL_ID}",
            event_id="event-review-ready",
            event_type="PROPOSAL_REVIEW_READY",
            event_bytes=review_receipt,
        )
    )
    assert review_result.result_code == "APPLIED"
    assert review_result.authoritative_version == 1
    review_rows = RegisterEventStore(database).review_ready_proposals()
    assert len(review_rows) == 1
    assert review_rows[0].proposal_package_id == _REGISTERED_PROPOSAL_ID
    assert review_rows[0].receipt_bytes == review_receipt
    assert review_rows[0].receipt_fingerprint == sha256(review_receipt).digest()
    assert review_rows[0].authoritative_version == 1
    assert review_rows[0].decision_bytes is None

    decision = _registered_decision_bytes()
    decision_result = RegisterEventStore(database).record_event(
        RegisterEventCommand(
            owning_application="REVIEW_APPLICATION",
            command_id="command-review-decision",
            command_bytes=b'{"action":"RECORD_PROPOSAL_DECISION"}',
            target_id=_REGISTERED_PROPOSAL_ID,
            expected_version=None,
            expected_absent=True,
            expires_at="9999-12-31T23:59:59",
            winner_key="proposal-decision:pmn-sql-proof",
            event_id="event-review-decision",
            event_type="PROPOSAL_APPROVED",
            event_bytes=decision,
        )
    )
    assert decision_result.result_code == "APPLIED"
    decided_rows = RegisterEventStore(database).review_ready_proposals()
    assert decided_rows[0].decision_bytes == decision
    assert decided_rows[0].decision_fingerprint == sha256(decision).digest()
    assert decided_rows[0].review_version == 1
    assert decided_rows[0].decision_event_type == "PROPOSAL_APPROVED"

    for principal in ("asklegal_review_app", "asklegal_promotion_app"):
        connection = database()
        cursor = connection.cursor()
        try:
            cursor.execute(f"EXECUTE AS USER='{principal}';")
            cursor.execute(
                "SELECT proposal_package_id, receipt_bytes, receipt_fingerprint, "
                "registration_version, decision_bytes, decision_fingerprint, "
                "review_version, decision_event_type "
                "FROM review.proposal_package_review_v1;"
            )
            assert cursor.fetchall() == [
                (
                    _REGISTERED_PROPOSAL_ID,
                    review_receipt,
                    sha256(review_receipt).digest(),
                    1,
                    decision,
                    sha256(decision).digest(),
                    1,
                    "PROPOSAL_APPROVED",
                )
            ]
            cursor.execute("REVERT;")
            connection.commit()
        finally:
            cursor.close()
            connection.close()

    fact_permission_error = ""
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute("EXECUTE AS USER='asklegal_review_app';")
        cursor.execute("SELECT event_id FROM register.event_v1_fact;")
    except Exception as error:
        fact_permission_error = str(error)
        connection.rollback()
    finally:
        cursor.close()
        connection.close()
    assert "permission" in fact_permission_error.lower()

    event_id = "ape_" + "3" * 48
    event = canonicalize(
        checked_json_value(
            {
                "approval_lifecycle_event_id": event_id,
                "approval_ref": {
                    "fingerprint": f"sha256:{sha256(decision).hexdigest()}",
                    "ref_id": _REGISTERED_APPROVAL_ID,
                    "ref_type": "APPROVAL",
                },
                "event_time": "2026-08-22T00:02:00Z",
                "event_type": "CONSUME_FOR_ONE_EXECUTION_LINEAGE",
                "evidence_refs": [
                    {
                        "fingerprint": "sha256:" + "4" * 64,
                        "ref_id": "evi_" + "4" * 48,
                        "ref_type": "EVIDENCE",
                    }
                ],
                "execution_lineage_refs": [
                    {
                        "fingerprint": "sha256:" + "5" * 64,
                        "ref_id": _REGISTERED_LINEAGE_ID,
                        "ref_type": "EXECUTION_LINEAGE",
                    }
                ],
                "from_state": "APPROVAL_APPROVED",
                "immutable": True,
                "responsible_identity_ref": {
                    "fingerprint": "sha256:" + "6" * 64,
                    "ref_id": "act_" + "6" * 48,
                    "ref_type": "ACTOR",
                },
                "schema_id": "asklegal.approval-lifecycle-event",
                "schema_version": "1.1.0",
                "to_state": "APPROVAL_CONSUMED",
            }
        )
    )
    command_bytes = canonicalize(
        checked_json_value(
            {
                "action": "CONSUME_REGISTERED_APPROVAL",
                "approval_id": _REGISTERED_APPROVAL_ID,
                "decision_fingerprint": f"sha256:{sha256(decision).hexdigest()}",
                "execution_lineage_id": _REGISTERED_LINEAGE_ID,
                "manifest_fingerprint": _REGISTERED_MANIFEST_FINGERPRINT,
                "manifest_id": _REGISTERED_MANIFEST_ID,
                "proposal_package_id": _REGISTERED_PROPOSAL_ID,
            }
        )
    )
    consumption = RegisteredApprovalConsumptionCommand(
        "command-registered-consumption",
        command_bytes,
        _REGISTERED_APPROVAL_ID,
        _REGISTERED_PROPOSAL_ID,
        sha256(decision).digest(),
        _REGISTERED_MANIFEST_ID,
        _REGISTERED_MANIFEST_FINGERPRINT,
        _REGISTERED_LINEAGE_ID,
        "9999-12-31T23:59:59",
        event_id,
        event,
    )
    approval_store = RegisteredApprovalStore(database)
    original_consumption = approval_store.consume(consumption)
    replayed_consumption = approval_store.consume(consumption)
    assert original_consumption.result_code == "APPLIED"
    assert original_consumption.authoritative_version == 1
    assert original_consumption.replayed is False
    assert replayed_consumption.replayed is True
    with pytest.raises(Exception, match="ASKLEGAL_APPROVAL_NOT_CONSUMABLE"):
        approval_store.consume(
            RegisteredApprovalConsumptionCommand(
                "command-competing-consumption",
                command_bytes.replace(
                    _REGISTERED_LINEAGE_ID.encode(), ("exe_" + "7" * 48).encode()
                ),
                _REGISTERED_APPROVAL_ID,
                _REGISTERED_PROPOSAL_ID,
                sha256(decision).digest(),
                _REGISTERED_MANIFEST_ID,
                _REGISTERED_MANIFEST_FINGERPRINT,
                "exe_" + "7" * 48,
                "9999-12-31T23:59:59",
                "ape_" + "7" * 48,
                event.replace(
                    _REGISTERED_LINEAGE_ID.encode(), ("exe_" + "7" * 48).encode()
                ).replace(event_id.encode(), ("ape_" + "7" * 48).encode()),
            )
        )
    with pytest.raises(Exception, match="ASKLEGAL_APPROVAL_CONSUMPTION_COMMAND_INVALID"):
        approval_store.consume(
            replace(
                consumption,
                command_id="command-missing-consumption-action",
                command_bytes=command_bytes.replace(
                    b'"action":"CONSUME_REGISTERED_APPROVAL",', b""
                ),
            )
        )

    permission = _execute(
        database,
        "EXECUTE AS USER='asklegal_promotion_app'; "
        "SELECT HAS_PERMS_BY_NAME('register.commit_command_v1', 'OBJECT', 'EXECUTE'); "
        "REVERT;",
        fetch=True,
    )
    assert permission == [(0,)]


def _prove_execution_authorization(database: MssqlConnectionFactory) -> None:
    """Prove exact consumed-lineage authorization, replay, and no-effect behavior."""
    store = RegisteredExecutionAuthorizationStore(database)
    command = _execution_authorization_command(command_marker="1", event_marker="1")
    effect_count_before = _execute(
        database,
        "SELECT COUNT(*) FROM register.effect_intent_fact;",
        fetch=True,
    )

    original = store.authorize(command)
    replay = store.authorize(command)
    lost_ack = store.authorize(command, simulate_lost_ack=True)
    assert original.result_code == "APPLIED"
    assert original.authoritative_version == 1
    assert original.replayed is False
    assert replay.replayed is True
    assert lost_ack.replayed is True

    event_rows = _execute(
        database,
        "SELECT aggregate_id, event_type, prior_version, new_version, "
        "event_bytes, event_fingerprint FROM register.event_v1_fact "
        "WHERE event_id = 'pex_" + "1" * 48 + "';",
        fetch=True,
    )
    assert event_rows == [
        (
            _REGISTERED_LINEAGE_ID,
            "PROMOTION_EXECUTION_AUTHORIZED",
            0,
            1,
            command.event_bytes,
            sha256(command.event_bytes).digest(),
        )
    ]
    assert (
        _execute(
            database,
            "SELECT COUNT(*) FROM register.effect_intent_fact;",
            fetch=True,
        )
        == effect_count_before
    )

    with pytest.raises(CommandFingerprintMismatch):
        store.authorize(
            replace(
                command,
                command_bytes=command.command_bytes.replace(
                    b'"action":"AUTHORIZE_REGISTERED_PROMOTION_EXECUTION"',
                    b'"action":"AUTHORIZE_CHANGED_PROMOTION_EXECUTION"',
                ),
            )
        )
    with pytest.raises(Exception, match="ASKLEGAL_CONSUMED_APPROVAL_NOT_AUTHORIZABLE"):
        store.authorize(
            _execution_authorization_command(
                command_marker="2",
                event_marker="2",
                approval_id="apr_" + "0" * 48,
            )
        )
    with pytest.raises(Exception, match="ASKLEGAL_CONSUMED_APPROVAL_NOT_AUTHORIZABLE"):
        store.authorize(
            _execution_authorization_command(
                command_marker="3",
                event_marker="3",
                lineage_fingerprint="sha256:" + "7" * 64,
            )
        )

    review_permissions = _execute(
        database,
        "EXECUTE AS USER='asklegal_review_app'; "
        "SELECT HAS_PERMS_BY_NAME('promotion.authorize_registered_execution_v1', "
        "'OBJECT', 'EXECUTE'); REVERT;",
        fetch=True,
    )
    promotion_permissions = _execute(
        database,
        "EXECUTE AS USER='asklegal_promotion_app'; "
        "SELECT HAS_PERMS_BY_NAME('promotion.authorize_registered_execution_v1', "
        "'OBJECT', 'EXECUTE'); REVERT;",
        fetch=True,
    )
    assert review_permissions == [(0,)]
    assert promotion_permissions == [(1,)]


def _prove_execution_begin(database: MssqlConnectionFactory) -> None:
    """Prove atomic BEGIN, first intent, replay, competition, and permissions."""
    store = RegisteredExecutionBeginStore(database)
    command = _execution_begin_command(
        command_marker="8",
        event_marker="8",
        intent_marker="8",
    )
    effect_count_before = _execute(
        database,
        "SELECT COUNT(*) FROM register.effect_intent_fact;",
        fetch=True,
    )

    original = store.begin(command)
    replay = store.begin(command)
    lost_ack = store.begin(command, simulate_lost_ack=True)
    assert original.result_code == "APPLIED"
    assert original.authoritative_version == 2
    assert original.replayed is False
    assert replay.replayed is True
    assert lost_ack.replayed is True

    event_rows = _execute(
        database,
        "SELECT aggregate_id, event_type, prior_version, new_version, "
        "event_bytes, event_fingerprint FROM register.event_v1_fact "
        "WHERE event_id = 'pex_" + "8" * 48 + "';",
        fetch=True,
    )
    assert event_rows == [
        (
            _REGISTERED_LINEAGE_ID,
            "PROMOTION_EXECUTION_BEGAN",
            1,
            2,
            command.event_bytes,
            sha256(command.event_bytes).digest(),
        )
    ]
    intent_rows = _execute(
        database,
        "SELECT aggregate_id, command_id, effect_type, intent_bytes, "
        "intent_fingerprint, attempt_ceiling FROM register.effect_intent_fact "
        "WHERE effect_intent_id = 'efi_" + "8" * 48 + "';",
        fetch=True,
    )
    assert intent_rows == [
        (
            _REGISTERED_LINEAGE_ID,
            command.command_id,
            "EMBEDDING_PROVIDER_CALL",
            command.intent_bytes,
            sha256(command.intent_bytes).digest(),
            3,
        )
    ]
    effect_count_value = effect_count_before[0][0]
    assert isinstance(effect_count_value, int)
    assert _execute(
        database,
        "SELECT COUNT(*) FROM register.effect_intent_fact;",
        fetch=True,
    ) == [(effect_count_value + 1,)]
    assert _execute(
        database,
        "SELECT COUNT(*) FROM register.effect_claim_current "
        "WHERE effect_intent_id = 'efi_" + "8" * 48 + "';",
        fetch=True,
    ) == [(0,)]

    with pytest.raises(CommandFingerprintMismatch):
        store.begin(
            replace(
                command,
                command_bytes=command.command_bytes.replace(
                    b'"effect_command_fingerprint":"sha256:' + b"a" * 64 + b'"',
                    b'"effect_command_fingerprint":"sha256:' + b"0" * 64 + b'"',
                ),
            )
        )

    competing = _execution_begin_command(
        command_marker="9",
        event_marker="9",
        intent_marker="9",
    )
    rejected = store.begin(competing)
    assert rejected.result_code == "REJECTED_STALE_VERSION"
    assert rejected.authoritative_version == 2
    assert _execute(
        database,
        "SELECT COUNT(*) FROM register.effect_intent_fact "
        "WHERE effect_intent_id = 'efi_" + "9" * 48 + "';",
        fetch=True,
    ) == [(0,)]

    malformed_profile = _execution_begin_command(
        command_marker="a",
        event_marker="a",
        intent_marker="a",
    )
    with pytest.raises(Exception, match="ASKLEGAL_EXECUTION_BEGIN_ACTION_INVALID"):
        store.begin(
            replace(
                malformed_profile,
                capability_profile_fingerprint="sha256:" + "0" * 64,
            )
        )
    wrong_authorization = _execution_begin_command(
        command_marker="b",
        event_marker="b",
        intent_marker="b",
        authorization_fingerprint="sha256:" + "0" * 64,
    )
    with pytest.raises(Exception, match="ASKLEGAL_AUTHORIZED_EXECUTION_NOT_BEGINNABLE"):
        store.begin(wrong_authorization)

    review_permissions = _execute(
        database,
        "EXECUTE AS USER='asklegal_review_app'; "
        "SELECT HAS_PERMS_BY_NAME('promotion.begin_registered_execution_v1', "
        "'OBJECT', 'EXECUTE'); REVERT;",
        fetch=True,
    )
    promotion_permissions = _execute(
        database,
        "EXECUTE AS USER='asklegal_promotion_app'; "
        "SELECT HAS_PERMS_BY_NAME('promotion.begin_registered_execution_v1', "
        "'OBJECT', 'EXECUTE'); REVERT;",
        fetch=True,
    )
    assert review_permissions == [(0,)]
    assert promotion_permissions == [(1,)]


@pytest.mark.sql_server
def test_management_register_sql_server_proof() -> None:
    """Prove migration, command, concurrency, privilege, atomicity, and ledger behavior."""
    master = _factory("master", autocommit=True)
    _execute(
        master,
        f"""
        IF DB_ID('{_DATABASE}') IS NOT NULL
        BEGIN
            ALTER DATABASE [{_DATABASE}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
            DROP DATABASE [{_DATABASE}];
        END;
        CREATE DATABASE [{_DATABASE}];
        """,
    )
    _execute(
        master,
        f"ALTER DATABASE [{_DATABASE}] SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;",
    )
    _execute(
        master,
        f"ALTER DATABASE [{_DATABASE}] SET ALLOW_SNAPSHOT_ISOLATION ON;",
    )
    database = _factory(_DATABASE)
    migrations = (
        _MIGRATION,
        _M2_MIGRATION,
        _V1_REVIEW_MIGRATION,
        _V1_DECISION_MIGRATION,
        _V1_CONSUMPTION_MIGRATION,
        _V1_TERMINAL_MIGRATION,
        _V1_EXECUTION_AUTHORIZATION_MIGRATION,
        _V1_EXECUTION_BEGIN_MIGRATION,
        _V1_CLAIMED_EFFECT_READBACK_MIGRATION,
        _V1_APPROVED_PROMOTION_WAKEUP_MIGRATION,
    )
    apply_packages(database, migrations, runner_build="management-register-v1-1")
    apply_packages(database, migrations, runner_build="management-register-v1-1")
    _prove_review_ready_projection(database)
    _prove_execution_authorization(database)
    _prove_execution_begin(database)
    _prove_terminal_lifecycle(database)
    _prove_approved_promotion_wakeup(database)

    manifest = sha256(b"synthetic-manifest").digest()
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT review.approval_current
                (approval_id, manifest_fingerprint, state_code, updated_at)
            VALUES
                ('approval-idempotent', ?, 'VALID', SYSUTCDATETIME()),
                ('approval-concurrent', ?, 'VALID', SYSUTCDATETIME()),
                ('approval-ambiguous', ?, 'VALID', SYSUTCDATETIME()),
                ('approval-role', ?, 'VALID', SYSUTCDATETIME());
            """,
            (manifest, manifest, manifest, manifest),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    store = ManagementRegisterStore(database)
    raw = b'{"approval_id":"approval-idempotent"}'
    fingerprint = sha256(raw).digest()
    original = store.consume_approval(
        command_id="command-idempotent",
        command_fingerprint=fingerprint,
        approval_id="approval-idempotent",
        manifest_fingerprint=manifest,
        canonical_command=raw,
    )
    replay = store.consume_approval(
        command_id="command-idempotent",
        command_fingerprint=fingerprint,
        approval_id="approval-idempotent",
        manifest_fingerprint=manifest,
        canonical_command=raw,
    )
    assert original.replayed is False
    assert replay.replayed is True
    assert original.result_bytes == replay.result_bytes == b'{"status":"consumed"}'

    with pytest.raises(CommandFingerprintMismatch):
        store.resolve_command("command-idempotent", sha256(b"different").digest())

    def race(command_id: str) -> str:
        race_raw = f'{{"command_id":"{command_id}"}}'.encode()
        try:
            store.consume_approval(
                command_id=command_id,
                command_fingerprint=sha256(race_raw).digest(),
                approval_id="approval-concurrent",
                manifest_fingerprint=manifest,
                canonical_command=race_raw,
            )
        except Exception as error:
            return str(error)
        return "winner"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(race, ("command-race-a", "command-race-b")))
    assert outcomes.count("winner") == 1
    assert sum("ASKLEGAL_APPROVAL_NOT_VALID" in outcome for outcome in outcomes) == 1

    ambiguous_raw = b'{"approval_id":"approval-ambiguous"}'
    ambiguous = store.consume_approval(
        command_id="command-ambiguous",
        command_fingerprint=sha256(ambiguous_raw).digest(),
        approval_id="approval-ambiguous",
        manifest_fingerprint=manifest,
        canonical_command=ambiguous_raw,
        simulate_lost_ack=True,
    )
    assert ambiguous.replayed is True

    connection = database()
    cursor = connection.cursor()
    role_raw = b'{"approval_id":"approval-role"}'
    try:
        cursor.execute("EXECUTE AS USER='asklegal_review_app';")
        cursor.execute(
            "EXEC review.consume_approval ?, ?, ?, ?, ?",
            (
                "command-role-review",
                sha256(role_raw).digest(),
                "approval-role",
                manifest,
                role_raw,
            ),
        )
        assert cursor.fetchone() is not None
        cursor.execute("REVERT;")
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    connection = database()
    cursor = connection.cursor()
    activation_raw = b'{"manifest":"synthetic-manifest"}'
    try:
        cursor.execute("EXECUTE AS USER='asklegal_promotion_app';")
        cursor.execute(
            "EXEC promotion.activate_serving_state ?, ?, ?, ?, ?",
            (
                "command-activate",
                sha256(activation_raw).digest(),
                "approval-idempotent",
                manifest,
                activation_raw,
            ),
        )
        assert cursor.fetchone() is not None
        cursor.execute("REVERT;")
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    atomic_counts = _execute(
        database,
        """
        SELECT
          (SELECT COUNT(*) FROM register.command_fact WHERE command_id='command-ambiguous'),
          (SELECT COUNT(*) FROM register.inbox_fact WHERE command_id='command-ambiguous'),
          (SELECT COUNT(*) FROM register.lifecycle_fact WHERE command_id='command-ambiguous'),
          (SELECT COUNT(*) FROM register.outbox_fact WHERE command_id='command-ambiguous');
        """,
        fetch=True,
    )
    assert atomic_counts == [(1, 1, 1, 1)]

    command_raw = b'{"command":"m2-applied"}'
    event_raw = b'{"event":"m2-applied"}'
    intent_raw = b'{"intent":"m2-effect"}'
    connection = database()
    cursor = connection.cursor()
    try:
        command_params = (
            "ACQUISITION_WORKER",
            "cmd-m2-applied",
            sha256(command_raw).digest(),
            command_raw,
            "aggregate-m2",
            None,
            True,
            "9999-12-31T23:59:59",
            "APPLIED",
            "winner:m2",
            "event-m2-applied",
            "M2_APPLIED",
            event_raw,
            sha256(event_raw).digest(),
            "intent-m2",
            "EVIDENCE_WRITE",
            intent_raw,
            sha256(intent_raw).digest(),
            "9999-12-31T23:59:59",
            2,
        )
        cursor.execute(
            "EXEC register.commit_command_v1 ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
            command_params,
        )
        applied = cursor.fetchone()
        assert applied is not None and applied[1] == "APPLIED" and applied[2] == 1
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "EXEC register.commit_command_v1 ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
            command_params,
        )
        replayed = cursor.fetchone()
        assert replayed is not None and bool(replayed[4]) is True
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    stale_raw = b'{"command":"m2-stale"}'
    stale_event = b'{"event":"m2-stale"}'
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "EXEC register.commit_command_v1 ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
            (
                "ACQUISITION_WORKER",
                "cmd-m2-stale",
                sha256(stale_raw).digest(),
                stale_raw,
                "aggregate-m2",
                None,
                True,
                "9999-12-31T23:59:59",
                "APPLIED",
                None,
                "event-m2-stale",
                "M2_STALE",
                stale_event,
                sha256(stale_event).digest(),
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        )
        stale = cursor.fetchone()
        assert stale is not None and stale[1] == "REJECTED_STALE_VERSION"
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    attempt_raw = b'{"attempt":"started"}'
    receipt_raw = b'{"receipt":"succeeded"}'
    handoff = EffectHandoffStore(database)
    claim = handoff.claim_next(
        owning_application="ACQUISITION_WORKER",
        effect_type="EVIDENCE_WRITE",
        claimant_id="worker-m2",
        lease_seconds=120,
    )
    assert claim is not None
    assert claim.effect_intent_id == "intent-m2"
    assert claim.intent_bytes == intent_raw
    assert claim.intent_fingerprint == sha256(intent_raw).digest()
    assert claim.prior_attempt_count == 0
    owner_error = ""
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute("EXECUTE AS USER='asklegal_promotion_app';")
        cursor.execute(
            "EXEC register.read_claimed_effect_v1 ?, ?, ?",
            (claim.effect_intent_id, claim.claimant_id, claim.fencing_token),
        )
    except Exception as error:
        owner_error = str(error)
        connection.rollback()
    finally:
        cursor.close()
        connection.close()
    assert "ASKLEGAL_EFFECT_OWNER_MISMATCH" in owner_error
    handoff.renew_claim(claim, lease_seconds=120)
    with pytest.raises(Exception, match="ASKLEGAL_STALE_FENCING_TOKEN"):
        handoff.append_attempt(
            replace(claim, fencing_token=claim.fencing_token + 1),
            attempt_number=1,
            event_code="STARTED",
            event_bytes=attempt_raw,
        )
    handoff.append_attempt(
        claim,
        attempt_number=1,
        event_code="STARTED",
        event_bytes=attempt_raw,
    )
    receipt_record = EffectReceiptRecord(
        "receipt-m2",
        claim.effect_intent_id,
        "SUCCEEDED",
        1,
        receipt_raw,
        sha256(receipt_raw).digest(),
        claim.fencing_token,
        claim.claimant_id,
    )
    receipt = handoff.record_receipt(receipt_record)
    replayed_receipt = handoff.record_receipt(receipt_record)
    assert receipt.terminal_status == "SUCCEEDED"
    assert receipt.replayed is False
    assert replayed_receipt.replayed is True

    _execute(database, "EXEC register.rebuild_projection_v1;")
    m2_counts = _execute(
        database,
        """
        SELECT
          (SELECT COUNT(*) FROM register.command_v1_fact),
          (SELECT COUNT(*) FROM register.event_v1_fact),
          (SELECT COUNT(*) FROM register.effect_intent_fact),
          (SELECT COUNT(*) FROM register.effect_attempt_fact),
          (SELECT COUNT(*) FROM register.effect_receipt_fact),
          (SELECT COUNT(*) FROM register.recovery_export_rows_v1),
          (SELECT checkpoint_sequence FROM register.projection_checkpoint_current
           WHERE projection_name='aggregate_status_v1');
        """,
        fetch=True,
    )
    # Four registered proposals retain Control/Review facts; their Approval
    # terminal winners, execution authorization, atomic BEGIN/intent, and the
    # rejected competing BEGIN remain alongside the M2 applied/stale commands.
    assert m2_counts == [(17, 15, 2, 1, 1, 36, 15)]

    permission_error = ""
    connection = database()
    cursor = connection.cursor()
    try:
        cursor.execute("EXECUTE AS USER='asklegal_review_app';")
        cursor.execute(
            "INSERT review.approval_current VALUES "
            "('forbidden', 0x00, 'VALID', NULL, SYSUTCDATETIME());"
        )
    except Exception as error:
        permission_error = str(error)
        connection.rollback()
    finally:
        cursor.close()
        connection.close()
    assert "permission" in permission_error.lower()

    connection = _factory(_DATABASE, autocommit=True)()
    cursor = connection.cursor()
    try:
        cursor.execute("EXEC sys.sp_generate_database_ledger_digest;")
        digest_row = cursor.fetchone()
        assert digest_row is not None and isinstance(digest_row[0], str)
        cursor.execute(
            "DECLARE @digests nvarchar(max) = CONVERT(nvarchar(max), ?); "
            "EXEC sys.sp_verify_database_ledger @digests;",
            (f"[{digest_row[0]}]",),
        )
        verification = cursor.fetchone()
        assert verification is not None
    finally:
        cursor.close()
        connection.close()

    migration_count = _execute(
        database,
        "SELECT COUNT(*) FROM migration.applied_fact "
        "WHERE migration_id IN "
        "('000001','000002','000003','000004','000005','000006','000007','000008',"
        "'000009','000010');",
        fetch=True,
    )
    assert migration_count == [(10,)]
