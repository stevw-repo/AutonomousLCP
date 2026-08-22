"""Synthetic conformance proof against the real local SQL Server engine."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_management_register import RegisterEventCommand, RegisterEventStore
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


@dataclass(frozen=True, slots=True)
class _TerminalFixture:
    """One registered approved decision used by terminal lifecycle proofs."""

    approval_id: str
    proposal_id: str
    manifest_id: str
    manifest_fingerprint: str
    decision_fingerprint: bytes


def _register_terminal_fixture(
    database: MssqlConnectionFactory,
    marker: str,
) -> _TerminalFixture:
    """Register one independent schema-shaped approved proposal."""
    proposal_id = "ppk_" + marker * 48
    approval_id = "apr_" + marker * 48
    manifest_id = "pmn_" + marker * 48
    manifest_fingerprint = "sha256:" + marker * 64
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
            event_id="evt_" + marker * 48,
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
                    "fingerprint": "sha256:" + marker * 64,
                    "ref_id": "evi_" + marker * 48,
                    "ref_type": "EVIDENCE",
                },
                "decision": "APPROVED",
                "decision_time": "2026-08-22T00:01:00Z",
                "expected_base_serving_state_ref": {
                    "fingerprint": "sha256:" + marker * 64,
                    "ref_id": "srv_" + marker * 48,
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
                    "fingerprint": "sha256:" + marker * 64,
                    "ref_id": "act_" + marker * 48,
                    "ref_type": "ACTOR",
                },
                "schema_id": "asklegal.approval-decision",
                "schema_version": "1.1.0",
                "valid_from": "2026-08-22T00:00:00Z",
                "validity_condition_refs": [
                    {
                        "contract_id": "configuration",
                        "fingerprint": "sha256:" + marker * 64,
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
            event_type="PROPOSAL_APPROVED",
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

    raced = _register_terminal_fixture(database, "6")
    race_commands = (
        ("REVOKE", _terminal_command(raced, action="REVOKE", marker="e")),
        ("INVALIDATE", _terminal_command(raced, action="INVALIDATE", marker="f")),
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
        consumption.consume(_consumption_for_terminal_fixture(raced, "5"))

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
    )
    apply_packages(database, migrations, runner_build="management-register-v1-1")
    apply_packages(database, migrations, runner_build="management-register-v1-1")
    _prove_review_ready_projection(database)
    _prove_execution_authorization(database)
    _prove_terminal_lifecycle(database)

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

    connection = database()
    cursor = connection.cursor()
    attempt_raw = b'{"attempt":"started"}'
    receipt_raw = b'{"receipt":"succeeded"}'
    try:
        cursor.execute("EXEC register.claim_effect_v1 ?, ?, ?", ("intent-m2", "worker-m2", 120))
        claim = cursor.fetchone()
        assert claim is not None and claim[2] == 1 and claim[3] == 1
        fence = claim[3]
        assert isinstance(fence, int)
        cursor.execute(
            "EXEC register.append_effect_attempt_v1 ?, ?, ?, ?, ?, ?, ?",
            (
                "intent-m2",
                "worker-m2",
                fence,
                1,
                "STARTED",
                attempt_raw,
                sha256(attempt_raw).digest(),
            ),
        )
        cursor.execute(
            "EXEC register.record_effect_receipt_v1 ?, ?, ?, ?, ?, ?, ?, ?",
            (
                "receipt-m2",
                "intent-m2",
                "SUCCEEDED",
                1,
                receipt_raw,
                sha256(receipt_raw).digest(),
                "worker-m2",
                fence,
            ),
        )
        receipt = cursor.fetchone()
        assert receipt is not None and receipt[2] == "SUCCEEDED" and bool(receipt[6]) is False
        connection.commit()
    finally:
        cursor.close()
        connection.close()

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
    # terminal winners and the no-effect execution authorization remain present
    # alongside the M2 applied/stale commands.
    assert m2_counts == [(15, 14, 1, 1, 1, 32, 14)]

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
        "('000001','000002','000003','000004','000005','000006','000007');",
        fetch=True,
    )
    assert migration_count == [(7,)]
