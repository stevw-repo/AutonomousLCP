"""First-action authority and atomic promotion execution BEGIN proofs."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import SchemaRegistry, parse_json_bytes
from asklegal_domain import (
    ApplicationCode,
    ContractReference,
    DestinationClass,
    EffectCapability,
    EffectType,
    ImmutableReference,
    NoCompensation,
    ReferenceType,
    RetryClass,
    StopCondition,
)
from asklegal_management_register import RegisteredExecutionBeginCommand, V1CommandResult
from asklegal_promotion import PromotionActionAuthority, PromotionApprovalSnapshot
from asklegal_promotion_worker import (
    CurrentCapabilityEvidence,
    RegisteredExecutionBeginContext,
    RegisteredExecutionBeginError,
    RegisteredExecutionBeginErrorCode,
    RegisteredExecutionBeginService,
)
from asklegal_promotion_worker.registered_approval import RegisteredApprovalCandidate

_PROPOSAL = "ppk_" + "1" * 48
_APPROVAL = "apr_" + "2" * 48
_DECISION_FP = "sha256:" + "2" * 64
_MANIFEST = "pmn_" + "3" * 48
_MANIFEST_FP = "sha256:" + "3" * 64
_LINEAGE = "exe_" + "4" * 48
_LINEAGE_FP = "sha256:" + "4" * 64
_AUTHORIZATION_FP = "sha256:" + "5" * 64
_PROFILE = ImmutableReference(
    ReferenceType.CAPABILITY_PROFILE,
    "cap_" + "6" * 48,
    "sha256:" + "6" * 64,
)
_CAPABILITY_EVIDENCE = ImmutableReference(
    ReferenceType.EVIDENCE,
    "evi_" + "7" * 48,
    "sha256:" + "7" * 64,
)


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


class Capabilities:
    """Current capability evidence fake with exact request accounting."""

    def __init__(self, evidence: CurrentCapabilityEvidence | None) -> None:
        """Set the current evidence returned by the fake."""
        self.evidence = evidence
        self.requests: list[tuple[str, str]] = []

    def current(self, profile_id: str, at: str) -> CurrentCapabilityEvidence | None:
        """Return the configured current evidence and record the exact lookup."""
        self.requests.append((profile_id, at))
        return self.evidence


class Writer:
    """Atomic BEGIN and exact-command replay fake."""

    def __init__(self) -> None:
        """Create an empty command and lineage register."""
        self.commands: dict[str, tuple[str, V1CommandResult]] = {}
        self.begun_lineages: set[str] = set()
        self.received: list[RegisteredExecutionBeginCommand] = []

    def begin(
        self,
        command: RegisteredExecutionBeginCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Commit one event and intent together, reject competition, or replay."""
        command_fingerprint = f"sha256:{sha256(command.command_bytes).hexdigest()}"
        prior = self.commands.get(command.command_id)
        if prior is not None:
            if prior[0] != command_fingerprint:
                message = "command fingerprint mismatch"
                raise RuntimeError(message)
            return replace(prior[1], replayed=True)
        if command.execution_lineage_id in self.begun_lineages:
            return V1CommandResult(
                command_id=command.command_id,
                result_code="REJECTED_STALE_VERSION",
                authoritative_version=2,
                result_bytes=(
                    b'{"authoritative_version":2,"result_code":"REJECTED_STALE_VERSION"}'
                ),
                replayed=False,
            )
        result = V1CommandResult(
            command_id=command.command_id,
            result_code="APPLIED",
            authoritative_version=2,
            result_bytes=b'{"authoritative_version":2,"result_code":"APPLIED"}',
            replayed=False,
        )
        self.commands[command.command_id] = (command_fingerprint, result)
        self.begun_lineages.add(command.execution_lineage_id)
        self.received.append(command)
        return replace(result, replayed=True) if simulate_lost_ack else result


def _contract(name: str, digit: str) -> ContractReference:
    return ContractReference(name, "1.0.0", "sha256:" + digit * 64)


def _action() -> PromotionActionAuthority:
    return PromotionActionAuthority(
        1,
        "EMBED_RECORDS",
        EffectType.EMBEDDING_PROVIDER_CALL,
        ApplicationCode.PROMOTION_WORKER,
        "EMBED_RECORDS",
        (
            ImmutableReference(
                ReferenceType.DESIRED_STATE_INVENTORY,
                "dsi_" + "8" * 48,
                "sha256:" + "8" * 64,
            ),
            ImmutableReference(
                ReferenceType.EMBEDDING_PROFILE,
                "emp_" + "9" * 48,
                "sha256:" + "9" * 64,
            ),
        ),
        "sha256:" + "a" * 64,
        EffectCapability.CALL_EMBEDDING_PROVIDER,
        _PROFILE,
        DestinationClass.EMBEDDING_PROVIDER,
        "promotion-embed-records-v1",
        RetryClass.RECONCILE_BEFORE_RETRY,
        3,
        "2026-08-22T13:00:00Z",
        tuple(StopCondition),
        _contract("asklegal.embedding-precondition", "b"),
        _contract("asklegal.embedding-postcondition", "c"),
        NoCompensation(),
    )


def _candidate(action: PromotionActionAuthority | None = None) -> RegisteredApprovalCandidate:
    actions = () if action is None else (action,)
    return RegisteredApprovalCandidate(
        _PROPOSAL,
        _APPROVAL,
        _DECISION_FP,
        PromotionApprovalSnapshot(
            _MANIFEST,
            _MANIFEST_FP,
            "srv_" + "d" * 48,
            "srv_" + "e" * 48,
            "2026-08-22T00:00:00Z",
            "2026-08-23T00:00:00Z",
            (("configuration", "1.0.0", "sha256:" + "f" * 64),),
            "1.0.0",
            actions,
        ),
        "act_" + "1" * 48,
        "sha256:" + "1" * 64,
        "evi_" + "2" * 48,
        "sha256:" + "2" * 64,
    )


def _capability() -> CurrentCapabilityEvidence:
    return CurrentCapabilityEvidence(
        profile_ref=_PROFILE,
        owning_application=ApplicationCode.PROMOTION_WORKER,
        capabilities=frozenset({EffectCapability.CALL_EMBEDDING_PROVIDER}),
        active=True,
        valid_from="2026-08-22T11:00:00Z",
        valid_until="2026-08-22T13:00:00Z",
        evidence_ref=_CAPABILITY_EVIDENCE,
    )


def _context() -> RegisteredExecutionBeginContext:
    return RegisteredExecutionBeginContext(
        "2026-08-22T12:00:00Z",
        "2026-08-22T12:05:00Z",
        _LINEAGE,
        _LINEAGE_FP,
        _AUTHORIZATION_FP,
        "act_" + "3" * 48,
        "sha256:" + "3" * 64,
    )


def _service(
    candidates: Candidates,
    capabilities: Capabilities,
    writer: Writer,
) -> RegisteredExecutionBeginService:
    return RegisteredExecutionBeginService(
        candidates,
        capabilities,
        writer,
        SchemaRegistry.from_contracts_root(Path(__file__).parents[3] / "contracts"),
    )


def test_begin_commits_exact_first_action_event_and_intent_atomically() -> None:
    """BEGIN derives its event and first intent only from approved authority."""
    writer = Writer()
    capabilities = Capabilities(_capability())
    result = _service(Candidates(_candidate(_action())), capabilities, writer).begin(
        _PROPOSAL,
        "cmd_" + "4" * 48,
        _context(),
    )

    assert result.result_code == "APPLIED"
    assert result.authoritative_version == 2
    assert capabilities.requests == [(_PROFILE.ref_id, _context().at)]
    assert len(writer.received) == 1
    command = writer.received[0]
    command_document = parse_json_bytes(command.command_bytes, max_bytes=100_000)
    event = parse_json_bytes(command.event_bytes, max_bytes=100_000)
    intent = parse_json_bytes(command.intent_bytes, max_bytes=100_000)
    assert isinstance(command_document, dict)
    assert command_document["action"] == "BEGIN_REGISTERED_PROMOTION_EXECUTION"
    action_authority = command_document["action_authority"]
    capability_evidence_ref = command_document["capability_evidence_ref"]
    assert isinstance(action_authority, dict)
    assert isinstance(capability_evidence_ref, dict)
    assert action_authority["action_id"] == "EMBED_RECORDS"
    assert capability_evidence_ref["ref_id"] == _CAPABILITY_EVIDENCE.ref_id
    assert isinstance(event, dict)
    assert event["from_state"] == "EXECUTION_AUTHORIZED"
    assert event["to_state"] == "EXECUTION_RUNNING"
    assert event["external_effects"] == "DECLARED_MANIFEST_ACTION"
    assert isinstance(intent, dict)
    assert intent["effect_intent_id"] == command.effect_intent_id
    assert intent["effect_type"] == EffectType.EMBEDDING_PROVIDER_CALL.value
    capability_profile_ref = intent["capability_profile_ref"]
    assert isinstance(capability_profile_ref, dict)
    assert capability_profile_ref["fingerprint"] == _PROFILE.fingerprint
    assert intent["input_refs"] == action_authority["input_refs"]
    assert command.effect_deadline == _action().deadline
    assert command.attempt_ceiling == _action().attempt_ceiling


def test_begin_replay_and_lost_ack_do_not_append_a_second_intent() -> None:
    """Exact replay and acknowledgement loss resolve to one durable transaction."""
    writer = Writer()
    command_id = "cmd_" + "5" * 48
    service = _service(Candidates(_candidate(_action())), Capabilities(_capability()), writer)
    first = service.begin(_PROPOSAL, command_id, _context(), simulate_lost_ack=True)
    replay = service.begin(_PROPOSAL, command_id, _context())

    assert first.replayed is True
    assert replay.replayed is True
    assert len(writer.received) == 1


def test_begin_rejects_missing_or_empty_approved_authority() -> None:
    """No Approval or no manifest action can create an Effect Intent."""
    writer = Writer()
    with pytest.raises(RegisteredExecutionBeginError) as missing:
        _service(Candidates(None), Capabilities(_capability()), writer).begin(
            _PROPOSAL,
            "cmd_" + "6" * 48,
            _context(),
        )
    assert missing.value.code is RegisteredExecutionBeginErrorCode.NOT_APPROVED
    with pytest.raises(RegisteredExecutionBeginError) as empty:
        _service(Candidates(_candidate()), Capabilities(_capability()), writer).begin(
            _PROPOSAL,
            "cmd_" + "7" * 48,
            _context(),
        )
    assert empty.value.code is RegisteredExecutionBeginErrorCode.INVALID
    assert not writer.received


def test_begin_rejects_inactive_stale_or_misbound_capability_evidence() -> None:
    """A profile reference alone never substitutes for current exact evidence."""
    inactive = replace(_capability(), active=False)
    stale = replace(_capability(), valid_until=_context().at)
    wrong_profile = replace(
        _capability(),
        profile_ref=replace(_PROFILE, fingerprint="sha256:" + "0" * 64),
    )
    wrong_owner = replace(_capability(), owning_application=ApplicationCode.CONTROL_PLANE)
    missing_capability = replace(_capability(), capabilities=frozenset())
    wrong_evidence_type = replace(
        _capability(),
        evidence_ref=ImmutableReference(
            ReferenceType.CONFIGURATION,
            "cfg_" + "7" * 48,
            "sha256:" + "7" * 64,
        ),
    )
    for evidence in (
        None,
        inactive,
        stale,
        wrong_profile,
        wrong_owner,
        missing_capability,
        wrong_evidence_type,
    ):
        writer = Writer()
        with pytest.raises(RegisteredExecutionBeginError) as raised:
            _service(Candidates(_candidate(_action())), Capabilities(evidence), writer).begin(
                _PROPOSAL,
                "cmd_" + "8" * 48,
                _context(),
            )
        assert raised.value.code is RegisteredExecutionBeginErrorCode.CAPABILITY_INACTIVE
        assert not writer.received


def test_changed_action_cannot_reuse_a_committed_begin_command() -> None:
    """One command ID cannot authorize changed effect-command bytes."""
    writer = Writer()
    command_id = "cmd_" + "9" * 48
    _service(Candidates(_candidate(_action())), Capabilities(_capability()), writer).begin(
        _PROPOSAL,
        command_id,
        _context(),
    )
    changed = replace(_action(), effect_command_fingerprint="sha256:" + "0" * 64)
    with pytest.raises(RuntimeError, match="command fingerprint mismatch"):
        _service(Candidates(_candidate(changed)), Capabilities(_capability()), writer).begin(
            _PROPOSAL,
            command_id,
            _context(),
        )
    assert len(writer.received) == 1


def test_competing_begin_cannot_append_another_first_intent() -> None:
    """The execution aggregate version makes one of two BEGIN commands lose."""
    writer = Writer()
    service = _service(Candidates(_candidate(_action())), Capabilities(_capability()), writer)
    service.begin(_PROPOSAL, "cmd_" + "a" * 48, _context())
    with pytest.raises(RegisteredExecutionBeginError) as raised:
        service.begin(_PROPOSAL, "cmd_" + "b" * 48, _context())
    assert raised.value.code is RegisteredExecutionBeginErrorCode.REJECTED
    assert len(writer.received) == 1


def test_invalid_context_never_reaches_capability_or_register() -> None:
    """Malformed identity or a command window beyond action authority fails closed."""
    writer = Writer()
    capabilities = Capabilities(_capability())
    invalid = replace(_context(), command_expires_at="2026-08-22T14:00:00Z")
    with pytest.raises(RegisteredExecutionBeginError) as raised:
        _service(Candidates(_candidate(_action())), capabilities, writer).begin(
            _PROPOSAL,
            "cmd_" + "c" * 48,
            invalid,
        )
    assert raised.value.code is RegisteredExecutionBeginErrorCode.INVALID
    assert not capabilities.requests
    assert not writer.received
