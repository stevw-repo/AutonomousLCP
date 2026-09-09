"""Schema-valid named-human Review decision command proofs."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_application_runtime import (
    HKV1ReviewReadinessProjection,
    HKV1ScopeDispositionProjection,
    LocalAdapterError,
    LocalAdapterErrorCode,
    LocalReviewProjectionStore,
    Principal,
    ProposalDecisionProjection,
    ProposalDetailProjection,
    TokenType,
)
from asklegal_contracts import SchemaRegistry, parse_json_bytes
from asklegal_management_register import (
    RegisteredApprovalTerminalCommand,
    RegisterEventCommand,
    V1CommandResult,
)
from asklegal_management_register_ports import ApprovalError, ApprovalErrorCode
from asklegal_review_api.governance import (
    RegisteredReviewGovernanceConfiguration,
    RegisteredReviewGovernanceService,
    ReviewAuthorityEvidence,
    ReviewCommand,
    ReviewDecisionWindow,
    StaticReviewAuthoritySource,
    SystemReviewDecisionWindowSource,
)
from asklegal_review_api.registered_proposals import (
    ProposalProjectionError,
    freeze_hk_v1_review_readiness,
)

_CONTRACTS = Path(__file__).parents[3] / "contracts"
_COMMAND_ID = "cmd_" + "1" * 48
_ROLES = frozenset({"PipelineAdministrator"})


class DecisionWriter:
    """Restart-safe generic-command fake with one exact winner per manifest."""

    def __init__(self) -> None:
        """Create empty immutable command and winner projections."""
        self.commands: dict[str, tuple[bytes, V1CommandResult]] = {}
        self.winners: dict[str, str] = {}
        self.events: list[RegisterEventCommand] = []
        self.revocations: list[RegisteredApprovalTerminalCommand] = []
        self.approval_winners: set[str] = set()

    def record_event(self, command: RegisterEventCommand) -> V1CommandResult:
        """Apply, exactly replay, or reject one competing decision."""
        prior = self.commands.get(command.command_id)
        if prior is not None:
            if prior[0] != command.command_bytes:
                raise AssertionError
            result = prior[1]
            return V1CommandResult(
                command_id=result.command_id,
                result_code=result.result_code,
                authoritative_version=result.authoritative_version,
                result_bytes=result.result_bytes,
                replayed=True,
            )
        if command.winner_key is not None and command.winner_key in self.winners:
            return V1CommandResult(
                command_id=command.command_id,
                result_code="REJECTED_CONFLICT",
                authoritative_version=1,
                result_bytes=b'{"result_code":"REJECTED_CONFLICT"}',
                replayed=False,
            )
        result = V1CommandResult(
            command_id=command.command_id,
            result_code="APPLIED",
            authoritative_version=1,
            result_bytes=b'{"result_code":"APPLIED"}',
            replayed=False,
        )
        self.commands[command.command_id] = (command.command_bytes, result)
        if command.winner_key is not None:
            self.winners[command.winner_key] = command.command_id
        self.events.append(command)
        return result

    def revoke(
        self,
        command: RegisteredApprovalTerminalCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Apply, exactly replay, or reject one competing revocation."""
        del simulate_lost_ack
        prior = self.commands.get(command.command_id)
        if prior is not None:
            if prior[0] != command.command_bytes:
                raise AssertionError
            return replace(prior[1], replayed=True)
        if command.approval_id in self.approval_winners:
            return V1CommandResult(
                command_id=command.command_id,
                result_code="REJECTED_CONFLICT",
                authoritative_version=2,
                result_bytes=b'{"result_code":"REJECTED_CONFLICT"}',
                replayed=False,
            )
        result = V1CommandResult(
            command_id=command.command_id,
            result_code="APPLIED",
            authoritative_version=2,
            result_bytes=b'{"authoritative_version":2,"result_code":"APPLIED"}',
            replayed=False,
        )
        self.commands[command.command_id] = (command.command_bytes, result)
        self.approval_winners.add(command.approval_id)
        self.revocations.append(command)
        return result


class ApprovedSource:
    """Exact approved-detail fake reconstructed after a decision."""

    def __init__(self, detail: ProposalDetailProjection) -> None:
        """Freeze one approved detail."""
        self.detail = detail

    def approved(self, approval_id: str) -> ProposalDetailProjection | None:
        """Return only the exact Approval identity."""
        decision = self.detail.decision
        if decision is None or decision.approval_id != approval_id:
            return None
        return self.detail


def _authority() -> tuple[StaticReviewAuthoritySource, ReviewAuthorityEvidence]:
    evidence = ReviewAuthorityEvidence(
        "person-local-1",
        _ROLES,
        "act_" + "1" * 48,
        "sha256:" + "a" * 64,
        "evi_" + "2" * 48,
        "sha256:" + "b" * 64,
    )
    return StaticReviewAuthoritySource({evidence.subject: evidence}), evidence


def _principal(*, token_type: TokenType = TokenType.DELEGATED_HUMAN) -> Principal:
    return Principal(
        "person-local-1",
        "api://asklegal-review",
        "asklegal-review-client",
        _ROLES,
        token_type,
    )


def _service(
    writer: DecisionWriter,
    authority: StaticReviewAuthoritySource,
    approved: ApprovedSource | None = None,
    window: ReviewDecisionWindow | None = None,
) -> tuple[RegisteredReviewGovernanceService, LocalReviewProjectionStore]:
    proposals = LocalReviewProjectionStore()
    return (
        RegisteredReviewGovernanceService(
            writer,
            proposals,
            authority,
            SchemaRegistry.from_contracts_root(_CONTRACTS),
            RegisteredReviewGovernanceConfiguration(
                window or ReviewDecisionWindow("2026-08-16T00:00:00Z", "2026-08-16T00:05:00Z"),
                approved,
                writer if approved is not None else None,
            ),
        ),
        proposals,
    )


def test_system_review_window_is_fresh_and_expired_proposal_cannot_be_approved() -> None:
    """A long-running local Review process never stamps every decision with fixture time."""
    moments = iter(
        (
            datetime(2026, 9, 8, 1, 2, 3, tzinfo=UTC),
            datetime(2026, 9, 8, 1, 7, 3, tzinfo=UTC),
        )
    )
    source = SystemReviewDecisionWindowSource(lambda: next(moments), timedelta(minutes=5))
    assert source.current() == ReviewDecisionWindow("2026-09-08T01:02:03Z", "2026-09-08T01:07:03Z")
    assert source.current() == ReviewDecisionWindow("2026-09-08T01:07:03Z", "2026-09-08T01:12:03Z")

    writer = DecisionWriter()
    authority, _evidence = _authority()
    service, proposals = _service(
        writer,
        authority,
        window=ReviewDecisionWindow("2026-08-18T00:00:00Z", "2026-08-18T00:05:00Z"),
    )
    with pytest.raises(LocalAdapterError) as expired:
        service.submit(_command(proposals))
    assert expired.value.code is LocalAdapterErrorCode.STALE_VERSION
    assert writer.events == []


def _command(
    proposals: LocalReviewProjectionStore,
    *,
    action: str = "APPROVE",
    command_id: str = _COMMAND_ID,
    expected_version: int = 0,
) -> ReviewCommand:
    detail = proposals.detail("proposal-1")
    assert detail is not None
    return ReviewCommand(
        command_id,
        "proposal-1",
        expected_version,
        {
            "action": action,
            "manifest_fingerprint": detail.proposal.manifest_fingerprint,
            "reason": "Reviewed the complete immutable proposal",
        },
        _principal(),
    )


def test_named_human_approval_is_schema_valid_no_effect_and_restart_safe() -> None:
    """The event is exact Approval 1.1.0 and replay never creates another fact."""
    writer = DecisionWriter()
    authority, evidence = _authority()
    service, proposals = _service(writer, authority)

    first = service.submit(_command(proposals))
    restarted, restarted_proposals = _service(writer, authority)
    replay = restarted.submit(_command(restarted_proposals))

    assert first.result_code == "APPROVED"
    assert first.authoritative_version == 1
    assert replay.resolution == "EXACT_REPLAY"
    assert replay.result_ref == first.result_ref
    assert len(writer.events) == 1
    event = writer.events[0]
    assert event.owning_application == "REVIEW_APPLICATION"
    assert event.event_type == "PROPOSAL_APPROVED"
    assert b"effect" not in event.command_bytes.lower()
    assert b"effect" not in event.event_bytes.lower()
    assert event.winner_key is not None
    assert event.winner_key.startswith("proposal-decision:pmn_")
    document = parse_json_bytes(event.event_bytes, max_bytes=1_000_000)
    assert isinstance(document, dict)
    assert document["schema_id"] == "asklegal.approval-decision"
    assert document["schema_version"] == "1.1.0"
    assert document["decision"] == "APPROVED"
    assert document["authority_evidence_ref"] == {
        "fingerprint": evidence.authority_evidence_fingerprint,
        "ref_id": evidence.authority_evidence_id,
        "ref_type": "EVIDENCE",
    }
    assert document["validity_condition_refs"] == [
        {
            "contract_id": "configuration",
            "fingerprint": "sha256:" + "e" * 64,
            "version": "1.0.0",
        }
    ]
    assert event.event_id == "evt_" + sha256(event.event_bytes).hexdigest()[:48]


def _hk_v1_readiness(manifest_fingerprint: str) -> HKV1ReviewReadinessProjection:
    scopes = (
        "HK-CASE-BINDING-POST-1997",
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
    )
    zero_scopes = (
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-SUBSIDIARY",
    )
    return freeze_hk_v1_review_readiness(
        tuple(
            HKV1ScopeDispositionProjection(
                scope,
                "NO_CHANGE" if scope in zero_scopes else "COMPLETE",
                0,
            )
            for scope in scopes
        ),
        ("Cases begin on 1997-07-01.", "HKEX Regulatory Materials are post-V1."),
        "evaluation/model.json",
        "evaluation/retrieval.json",
        "sha256:" + "6" * 64,
        "sha256:" + "7" * 64,
        "sha256:" + "8" * 64,
        "synthetic-v1",
        "sha256:" + "3" * 64,
        (
            ("rec_" + "1" * 48, "HK-CASE-BINDING-POST-1997", "CASES"),
            ("rec_" + "2" * 48, "HK-LEG-ORDINANCES", "LEGISLATION"),
        ),
        zero_scopes,
        "asklegal-local-hkg-20260906-candidate001",
        "backup/native.json",
        "backup/recovery.json",
        "srv_" + "8" * 48,
        manifest_fingerprint,
    )


def test_hk_v1_readiness_rejects_scope_results_inconsistent_with_membership() -> None:
    """A zero-record scope cannot be displayed as a completed populated scope."""
    scopes = (
        "HK-CASE-BINDING-POST-1997",
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
    )
    with pytest.raises(ProposalProjectionError):
        freeze_hk_v1_review_readiness(
            tuple(HKV1ScopeDispositionProjection(scope, "COMPLETE", 0) for scope in scopes),
            ("HKEX is outside V1.",),
            "evaluation/model.json",
            "evaluation/retrieval.json",
            "sha256:" + "6" * 64,
            "sha256:" + "7" * 64,
            "sha256:" + "8" * 64,
            "synthetic-v1",
            "sha256:" + "3" * 64,
            (
                ("rec_" + "1" * 48, scopes[0], "CASES"),
                ("rec_" + "2" * 48, scopes[2], "LEGISLATION"),
            ),
            (scopes[1], scopes[3]),
            "asklegal-local-hkg-20260906-candidate001",
            "backup/native.json",
            "backup/recovery.json",
            "srv_" + "8" * 48,
            "sha256:" + "4" * 64,
        )


def test_hk_v1_approval_requires_the_complete_displayed_review_surface() -> None:
    """A named approval cannot outlive retryable or hidden Task 8 review facts."""
    writer = DecisionWriter()
    authority, _evidence = _authority()
    service, proposals = _service(writer, authority)
    detail = proposals.detail("proposal-1")
    assert detail is not None
    readiness = _hk_v1_readiness(detail.proposal.manifest_fingerprint)
    predicates = tuple(
        sorted(
            (
                *detail.validity_predicates,
                (
                    "HK_V1_TWO_FAMILY_PROPOSAL",
                    "1.0.0",
                    detail.proposal.manifest_fingerprint,
                ),
            )
        )
    )
    proposals.details = tuple(
        replace(item, hk_v1_readiness=readiness, validity_predicates=predicates)
        if item.proposal.proposal_id == "proposal-1"
        else item
        for item in proposals.details
    )

    result = service.submit(_command(proposals))

    assert result.result_code == "APPROVED"
    assert readiness.retryable_count == 0
    assert len(readiness.scope_dispositions) == 4
    assert readiness.model_evaluation_ref
    assert readiness.retrieval_evaluation_ref
    assert readiness.native_backup_ref
    assert readiness.recovery_backup_ref
    assert readiness.rollback_state_id
    document = parse_json_bytes(writer.events[0].event_bytes, max_bytes=1_000_000)
    assert isinstance(document, dict)
    assert document["review_readiness_fingerprint"] == readiness.fingerprint


def test_two_family_approval_without_registered_readiness_is_refused() -> None:
    """A two-family predicate cannot bypass the retained Task 8 review surface."""
    writer = DecisionWriter()
    authority, _evidence = _authority()
    service, proposals = _service(writer, authority)
    detail = proposals.detail("proposal-1")
    assert detail is not None
    predicates = tuple(
        sorted(
            (
                *detail.validity_predicates,
                (
                    "HK_V1_TWO_FAMILY_PROPOSAL",
                    "1.0.0",
                    detail.proposal.manifest_fingerprint,
                ),
            )
        )
    )
    proposals.details = tuple(
        replace(item, validity_predicates=predicates)
        if item.proposal.proposal_id == "proposal-1"
        else item
        for item in proposals.details
    )

    with pytest.raises(LocalAdapterError) as failure:
        service.submit(_command(proposals))

    assert failure.value.code is LocalAdapterErrorCode.DISABLED
    assert writer.events == []


def test_hk_v1_review_drift_blocks_approval_before_register_write() -> None:
    """Changing a displayed fact after freeze invalidates the whole local approval."""
    writer = DecisionWriter()
    authority, _evidence = _authority()
    service, proposals = _service(writer, authority)
    detail = proposals.detail("proposal-1")
    assert detail is not None
    readiness = _hk_v1_readiness(detail.proposal.manifest_fingerprint)
    drifted = replace(readiness, retryable_count=1)
    proposals.details = tuple(
        replace(item, hk_v1_readiness=drifted)
        if item.proposal.proposal_id == "proposal-1"
        else item
        for item in proposals.details
    )

    with pytest.raises(LocalAdapterError) as failure:
        service.submit(_command(proposals))

    assert failure.value.code is LocalAdapterErrorCode.DISABLED
    assert writer.events == []


def test_rejection_is_a_terminal_decision_fact_not_an_approval_effect() -> None:
    """The same exact command path records rejection without creating an effect."""
    writer = DecisionWriter()
    authority, _evidence = _authority()
    service, proposals = _service(writer, authority)

    result = service.submit(_command(proposals, action="REJECT"))

    assert result.result_code == "REJECTED"
    assert writer.events[0].event_type == "PROPOSAL_REJECTED"
    assert b"effect" not in writer.events[0].event_bytes.lower()


def test_decision_requires_delegated_token_and_current_external_assignment() -> None:
    """A token role cannot substitute for a current evidenced assignment."""
    writer = DecisionWriter()
    authority, _evidence = _authority()
    service, proposals = _service(writer, authority)
    application = _command(proposals)
    application = ReviewCommand(
        application.command_id,
        application.target,
        application.expected_version,
        application.body,
        _principal(token_type=TokenType.APPLICATION),
    )

    with pytest.raises(ApprovalError) as wrong_token:
        service.submit(application)
    assert wrong_token.value.code is ApprovalErrorCode.UNAUTHORIZED_PRINCIPAL

    authority.remove("person-local-1")
    with pytest.raises(ApprovalError) as removed:
        service.submit(_command(proposals))
    assert removed.value.code is ApprovalErrorCode.UNAUTHORIZED_PRINCIPAL
    assert writer.events == []


def test_stale_manifest_version_and_competing_decision_fail_closed() -> None:
    """Neither stale input nor a second winner can append another decision."""
    writer = DecisionWriter()
    authority, _evidence = _authority()
    service, proposals = _service(writer, authority)

    stale = _command(proposals, expected_version=1)
    with pytest.raises(LocalAdapterError) as stale_error:
        service.submit(stale)
    assert stale_error.value.code is LocalAdapterErrorCode.STALE_VERSION

    detail = proposals.detail("proposal-1")
    assert detail is not None
    drifted = ReviewCommand(
        "cmd_" + "2" * 48,
        "proposal-1",
        0,
        {
            "action": "APPROVE",
            "manifest_fingerprint": "sha256:" + "0" * 64,
            "reason": "Wrong manifest",
        },
        _principal(),
    )
    with pytest.raises(LocalAdapterError) as manifest_error:
        service.submit(drifted)
    assert manifest_error.value.code is LocalAdapterErrorCode.STALE_VERSION

    service.submit(_command(proposals))
    competing = _command(
        proposals,
        action="REJECT",
        command_id="cmd_" + "3" * 48,
    )
    with pytest.raises(LocalAdapterError) as conflict:
        service.submit(competing)
    assert conflict.value.code is LocalAdapterErrorCode.STALE_VERSION
    assert len(writer.events) == 1


def test_registered_revocation_is_schema_valid_single_winner_and_restart_safe() -> None:
    """A current named human can append one no-effect terminal revocation."""
    writer = DecisionWriter()
    authority, evidence = _authority()
    decision_service, proposals = _service(writer, authority)
    decision_result = decision_service.submit(_command(proposals))
    base_detail = proposals.detail("proposal-1")
    assert base_detail is not None
    approved_detail = replace(
        base_detail,
        proposal=replace(base_detail.proposal, status="APPROVED", review_version=1),
        decision=ProposalDecisionProjection(
            decision_result.result_ref,
            "APPROVED",
            "2026-08-16T00:00:00Z",
            evidence.reviewer_identity_id,
            evidence.reviewer_identity_fingerprint,
            evidence.authority_evidence_id,
            evidence.authority_evidence_fingerprint,
            "Reviewed the complete immutable proposal",
            "sha256:" + sha256(writer.events[0].event_bytes).hexdigest(),
        ),
    )
    approved = ApprovedSource(approved_detail)
    service, _unused = _service(writer, authority, approved)
    command = ReviewCommand(
        "cmd_" + "4" * 48,
        decision_result.result_ref,
        1,
        {
            "action": "REVOKE",
            "approval_ref": decision_result.result_ref,
            "manifest_fingerprint": approved_detail.proposal.manifest_fingerprint,
            "reason": "Withdraw before execution",
        },
        _principal(),
    )
    first = service.submit(command)
    replay, _unused = _service(writer, authority, approved)
    replayed = replay.submit(command)
    assert first.result_code == "REVOKED"
    assert first.authoritative_version == 2
    assert replayed.resolution == "EXACT_REPLAY"
    assert len(writer.revocations) == 1
    terminal = writer.revocations[0]
    command_document = parse_json_bytes(terminal.command_bytes, max_bytes=10_000)
    event = parse_json_bytes(terminal.event_bytes, max_bytes=10_000)
    assert isinstance(command_document, dict)
    assert command_document["action"] == "REVOKE_REGISTERED_APPROVAL"
    assert command_document["reason"] == "Withdraw before execution"
    assert "effect" not in command_document
    assert isinstance(event, dict)
    assert event["event_type"] == "REVOKE"
    assert event["to_state"] == "APPROVAL_REVOKED"
    assert event["execution_lineage_refs"] == []
    assert "effect" not in event

    competing = replace(command, command_id="cmd_" + "5" * 48)
    with pytest.raises(LocalAdapterError) as conflict:
        service.submit(competing)
    assert conflict.value.code is LocalAdapterErrorCode.STALE_VERSION
