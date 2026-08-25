"""Consumed-Approval promotion execution authorization proofs."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import SchemaRegistry, parse_json_bytes
from asklegal_management_register import (
    RegisteredExecutionAuthorizationCommand,
    V1CommandResult,
)
from asklegal_promotion import PromotionApprovalSnapshot
from asklegal_promotion_worker.registered_approval import RegisteredApprovalCandidate
from asklegal_promotion_worker.registered_execution import (
    RegisteredExecutionAuthorizationContext,
    RegisteredExecutionAuthorizationError,
    RegisteredExecutionAuthorizationErrorCode,
    RegisteredExecutionAuthorizationService,
)

_PROPOSAL = "ppk_" + "1" * 48
_APPROVAL = "apr_" + "2" * 48
_DECISION_FP = "sha256:" + "2" * 64
_MANIFEST = "pmn_" + "3" * 48
_MANIFEST_FP = "sha256:" + "3" * 64
_LINEAGE = "exe_" + "4" * 48
_LINEAGE_FP = "sha256:" + "4" * 64


class Candidates:
    """Complete-reread candidate fake."""

    def __init__(self, candidate: RegisteredApprovalCandidate | None) -> None:
        """Set the exact candidate returned on every read."""
        self.candidate = candidate

    def approved(self, proposal_package_id: str) -> RegisteredApprovalCandidate | None:
        """Return only the configured proposal candidate."""
        if self.candidate is None or self.candidate.proposal_package_id != proposal_package_id:
            return None
        return self.candidate


class Writer:
    """Durable command replay fake for the specialized authorization boundary."""

    def __init__(self, *, reject: bool = False) -> None:
        """Create an empty writer with an optional database rejection."""
        self.reject = reject
        self.commands: dict[str, tuple[str, V1CommandResult]] = {}
        self.received: list[RegisteredExecutionAuthorizationCommand] = []

    def authorize(
        self,
        command: RegisteredExecutionAuthorizationCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Apply or exactly replay one authorization command."""
        del simulate_lost_ack
        command_fingerprint = f"sha256:{sha256(command.command_bytes).hexdigest()}"
        prior = self.commands.get(command.command_id)
        if prior is not None:
            if prior[0] != command_fingerprint:
                message = "command fingerprint mismatch"
                raise RuntimeError(message)
            return replace(prior[1], replayed=True)
        result = V1CommandResult(
            command_id=command.command_id,
            result_code="REJECTED_INVALID_STATE" if self.reject else "APPLIED",
            authoritative_version=None if self.reject else 1,
            result_bytes=b'{"result_code":"REJECTED_INVALID_STATE"}'
            if self.reject
            else b'{"authoritative_version":1,"result_code":"APPLIED"}',
            replayed=False,
        )
        self.commands[command.command_id] = (command_fingerprint, result)
        self.received.append(command)
        return result


def _candidate() -> RegisteredApprovalCandidate:
    return RegisteredApprovalCandidate(
        _PROPOSAL,
        _APPROVAL,
        _DECISION_FP,
        PromotionApprovalSnapshot(
            _MANIFEST,
            _MANIFEST_FP,
            "srv_" + "a" * 48,
            "srv_" + "b" * 48,
            "2026-08-22T00:00:00Z",
            "2026-08-23T00:00:00Z",
            (("configuration", "1.0.0", "sha256:" + "a" * 64),),
            "1.0.0",
            (),
        ),
        "act_" + "5" * 48,
        "sha256:" + "5" * 64,
        "evi_" + "6" * 48,
        "sha256:" + "6" * 64,
    )


def _context() -> RegisteredExecutionAuthorizationContext:
    return RegisteredExecutionAuthorizationContext(
        "2026-08-22T12:00:00Z",
        "2026-08-22T12:05:00Z",
        _LINEAGE,
        _LINEAGE_FP,
        "evi_" + "7" * 48,
        "sha256:" + "7" * 64,
        "act_" + "8" * 48,
        "sha256:" + "8" * 64,
    )


def _service(candidates: Candidates, writer: Writer) -> RegisteredExecutionAuthorizationService:
    return RegisteredExecutionAuthorizationService(
        candidates,
        writer,
        SchemaRegistry.from_contracts_root(Path(__file__).parents[3] / "contracts"),
    )


def test_consumed_lineage_authorization_is_schema_valid_and_has_no_effect() -> None:
    """Authorization records only the exact PLANNED-to-AUTHORIZED fact."""
    writer = Writer()
    result = _service(Candidates(_candidate()), writer).authorize(
        _PROPOSAL,
        "cmd_" + "9" * 48,
        _context(),
    )

    assert result.result_code == "APPLIED"
    assert len(writer.received) == 1
    command = writer.received[0]
    command_document = parse_json_bytes(command.command_bytes, max_bytes=10_000)
    event = parse_json_bytes(command.event_bytes, max_bytes=10_000)
    assert isinstance(command_document, dict)
    assert command_document["action"] == "AUTHORIZE_REGISTERED_PROMOTION_EXECUTION"
    assert "effect_intent" not in command_document
    assert isinstance(event, dict)
    assert event["from_state"] == "EXECUTION_PLANNED"
    assert event["to_state"] == "EXECUTION_AUTHORIZED"
    assert event["external_effects"] == "NONE"
    assert event["execution_lineage_id"] == _LINEAGE
    assert event["receipt_refs"] == []


def test_execution_authorization_replays_exactly_after_restart() -> None:
    """One command identity returns the original durable authorization result."""
    writer = Writer()
    command_id = "cmd_" + "a" * 48
    first = _service(Candidates(_candidate()), writer).authorize(
        _PROPOSAL,
        command_id,
        _context(),
    )
    replay = _service(Candidates(_candidate()), writer).authorize(
        _PROPOSAL,
        command_id,
        _context(),
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert len(writer.received) == 1


def test_execution_authorization_rejects_missing_approval_or_invalid_lineage() -> None:
    """No approved candidate or a non-contract lineage reaches the register."""
    writer = Writer()
    with pytest.raises(RegisteredExecutionAuthorizationError) as missing:
        _service(Candidates(None), writer).authorize(
            _PROPOSAL,
            "cmd_" + "b" * 48,
            _context(),
        )
    assert missing.value.code is RegisteredExecutionAuthorizationErrorCode.NOT_APPROVED
    invalid = replace(_context(), execution_lineage_id="lin_" + "4" * 48)
    with pytest.raises(RegisteredExecutionAuthorizationError) as malformed:
        _service(Candidates(_candidate()), writer).authorize(
            _PROPOSAL,
            "cmd_" + "c" * 48,
            invalid,
        )
    assert malformed.value.code is RegisteredExecutionAuthorizationErrorCode.INVALID
    assert not writer.received


def test_database_guard_rejection_never_becomes_authorized() -> None:
    """A failed consumed-Approval guard remains a closed application failure."""
    with pytest.raises(RegisteredExecutionAuthorizationError) as raised:
        _service(Candidates(_candidate()), Writer(reject=True)).authorize(
            _PROPOSAL,
            "cmd_" + "d" * 48,
            _context(),
        )
    assert raised.value.code is RegisteredExecutionAuthorizationErrorCode.REJECTED
