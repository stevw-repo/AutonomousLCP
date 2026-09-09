"""Registered Approval revalidation and single-use consumption proofs."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import SchemaRegistry, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_corpus import ProposalPackageInput, freeze_proposal_package
from asklegal_evidence_vault import LocalImmutableVault, RetentionProfile, VaultName
from asklegal_management_register import (
    ApprovedPromotionClaim,
    RegisteredApprovalConsumptionCommand,
    RegisteredApprovalTerminalCommand,
    ReviewReadyProposalRow,
    V1CommandResult,
)
from asklegal_promotion import (
    PromotionApprovalSnapshot,
    ProposalMemberReceipt,
    StoredProposalPackage,
    TraceabilityShardReceipt,
    proposal_receipt_document,
    proposal_receipt_fingerprint,
    stored_proposal_package_from_bytes,
)
from asklegal_promotion_worker.registered_approval import (
    ApprovalConsumptionContext,
    ApprovedPromotionQueue,
    CurrentReviewerAuthority,
    RegisteredApprovalCandidate,
    RegisteredApprovalConsumptionService,
    RegisteredApprovalError,
    RegisteredApprovalErrorCode,
    RegisteredApprovalSourceError,
    RegisteredPromotionApprovalSource,
)

from tools.tests.proposal_member_fixture import semantic_proposal_fixture

_PROPOSAL = "ppk_" + "1" * 48
_APPROVAL = "apr_" + "2" * 48
_MANIFEST = "pmn_" + "3" * 48
_MANIFEST_FP = "sha256:" + "3" * 64
_DECISION_FP = "sha256:" + "4" * 64
_REVIEWER = "act_" + "5" * 48
_REVIEWER_FP = "sha256:" + "5" * 64
_AUTHORITY = "evi_" + "6" * 48
_AUTHORITY_FP = "sha256:" + "6" * 64
_VALIDATION = "evi_" + "7" * 48
_VALIDATION_FP = "sha256:" + "7" * 64
_LINEAGE = "exe_" + "8" * 48
_LINEAGE_FP = "sha256:" + "8" * 64
_WORKER = "act_" + "9" * 48
_WORKER_FP = "sha256:" + "9" * 64
_PREDICATES = (("configuration", "1.0.0", "sha256:" + "a" * 64),)


def test_approved_promotion_queue_protocol_is_only_a_lease_and_acknowledgement_boundary() -> None:
    """The worker-side type exposes no consume, authorize, begin, or provider action."""
    claim = ApprovedPromotionClaim(
        _PROPOSAL,
        _APPROVAL,
        _DECISION_FP,
        _MANIFEST,
        _MANIFEST_FP,
        "pwr_" + "a" * 48,
        "2026-08-27T12:05:00Z",
        1,
        1,
    )
    queue: ApprovedPromotionQueue = Queue(claim)

    observed = queue.claim_next(claim.claimant_worker_id, claim.claimed_until)
    assert observed == claim
    queue.acknowledge_started(claim, _LINEAGE)


class Candidates:
    """Mutable complete-reread fake."""

    def __init__(self, candidate: RegisteredApprovalCandidate | None) -> None:
        """Set the candidate returned by every read."""
        self.candidate = candidate

    def approved(self, proposal_package_id: str) -> RegisteredApprovalCandidate | None:
        """Return only the configured proposal candidate."""
        if self.candidate is None or self.candidate.proposal_package_id != proposal_package_id:
            return None
        return self.candidate


class Rows:
    """Immutable least-privilege SQL projection fake."""

    def __init__(self, rows: tuple[ReviewReadyProposalRow, ...]) -> None:
        """Freeze the rows returned after every restart."""
        self.rows = rows

    def review_ready_proposals(self) -> tuple[ReviewReadyProposalRow, ...]:
        """Return the configured exact generation."""
        return self.rows


class Queue:
    """Provider-disabled handoff fake with no execution methods."""

    def __init__(self, claim: ApprovedPromotionClaim) -> None:
        """Bind one pre-existing queue lease."""
        self.claim = claim
        self.acknowledgements: list[tuple[ApprovedPromotionClaim, str]] = []

    def claim_next(self, worker_id: str, claimed_until: str) -> ApprovedPromotionClaim | None:
        """Return the supplied lease only for its exact claimant and expiry."""
        if (worker_id, claimed_until) != (
            self.claim.claimant_worker_id,
            self.claim.claimed_until,
        ):
            return None
        return self.claim

    def acknowledge_started(self, claim: ApprovedPromotionClaim, execution_lineage_id: str) -> None:
        """Record a caller-visible handoff without consuming any Approval."""
        self.acknowledgements.append((claim, execution_lineage_id))


class Authority:
    """Mutable current reviewer assignment fake."""

    def __init__(self, current: CurrentReviewerAuthority | None) -> None:
        """Set the current assignment."""
        self.value = current

    def current(self, reviewer_identity_id: str) -> CurrentReviewerAuthority | None:
        """Return the assignment only for its stable reviewer identity."""
        if self.value is None or self.value.reviewer_identity_id != reviewer_identity_id:
            return None
        return self.value


class Writer:
    """Atomic command/winner fake preserved across service restarts."""

    def __init__(self) -> None:
        """Create an empty command and Approval winner register."""
        self.commands: dict[str, tuple[str, V1CommandResult]] = {}
        self.winners: dict[str, str] = {}
        self.received: list[RegisteredApprovalConsumptionCommand] = []
        self.invalidations: list[RegisteredApprovalTerminalCommand] = []
        self.lost_ack_flags: list[bool] = []

    def consume(
        self,
        command: RegisteredApprovalConsumptionCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Apply, replay, or reject one competing Approval consumption."""
        command_fp = "sha256:" + sha256(command.command_bytes).hexdigest()
        prior = self.commands.get(command.command_id)
        if prior is not None:
            if prior[0] != command_fp:
                message = "command fingerprint mismatch"
                raise RuntimeError(message)
            result = prior[1]
            return replace(result, replayed=True)
        if command.approval_id in self.winners:
            return V1CommandResult(
                command_id=command.command_id,
                result_code="REJECTED_CONFLICT",
                authoritative_version=None,
                result_bytes=b'{"result_code":"REJECTED_CONFLICT"}',
                replayed=False,
            )
        result = V1CommandResult(
            command_id=command.command_id,
            result_code="APPLIED",
            authoritative_version=1,
            result_bytes=b'{"authoritative_version":1,"result_code":"APPLIED"}',
            replayed=False,
        )
        self.commands[command.command_id] = (command_fp, result)
        self.winners[command.approval_id] = command.command_id
        self.received.append(command)
        self.lost_ack_flags.append(simulate_lost_ack)
        return result

    def invalidate(
        self,
        command: RegisteredApprovalTerminalCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Apply, replay, or reject one competing objective invalidation."""
        command_fp = "sha256:" + sha256(command.command_bytes).hexdigest()
        prior = self.commands.get(command.command_id)
        if prior is not None:
            if prior[0] != command_fp:
                message = "command fingerprint mismatch"
                raise RuntimeError(message)
            return replace(prior[1], replayed=True)
        if command.approval_id in self.winners:
            return V1CommandResult(
                command_id=command.command_id,
                result_code="REJECTED_CONFLICT",
                authoritative_version=None,
                result_bytes=b'{"result_code":"REJECTED_CONFLICT"}',
                replayed=False,
            )
        result = V1CommandResult(
            command_id=command.command_id,
            result_code="APPLIED",
            authoritative_version=1,
            result_bytes=b'{"authoritative_version":1,"result_code":"APPLIED"}',
            replayed=False,
        )
        self.commands[command.command_id] = (command_fp, result)
        self.winners[command.approval_id] = command.command_id
        self.invalidations.append(command)
        self.lost_ack_flags.append(simulate_lost_ack)
        return result


def _candidate() -> RegisteredApprovalCandidate:
    return RegisteredApprovalCandidate(
        _PROPOSAL,
        _APPROVAL,
        _DECISION_FP,
        PromotionApprovalSnapshot(
            _MANIFEST,
            _MANIFEST_FP,
            "srv_" + "b" * 48,
            "srv_" + "c" * 48,
            "2026-08-22T00:00:00Z",
            "2026-08-23T00:00:00Z",
            _PREDICATES,
            "1.0.0",
            (),
        ),
        _REVIEWER,
        _REVIEWER_FP,
        _AUTHORITY,
        _AUTHORITY_FP,
    )


def _authority() -> CurrentReviewerAuthority:
    return CurrentReviewerAuthority(
        _REVIEWER,
        _REVIEWER_FP,
        frozenset({"PipelineAdministrator"}),
        _AUTHORITY,
        _AUTHORITY_FP,
    )


def _context() -> ApprovalConsumptionContext:
    return ApprovalConsumptionContext(
        "2026-08-22T12:00:00Z",
        "2026-08-22T12:05:00Z",
        "srv_" + "b" * 48,
        _PREDICATES,
        _LINEAGE,
        _LINEAGE_FP,
        _VALIDATION,
        _VALIDATION_FP,
        _WORKER,
        _WORKER_FP,
    )


def _schemas() -> SchemaRegistry:
    return SchemaRegistry.from_contracts_root(Path(__file__).parents[3] / "contracts")


def _service(
    candidates: Candidates,
    authority: Authority,
    writer: Writer,
) -> RegisteredApprovalConsumptionService:
    return RegisteredApprovalConsumptionService(candidates, authority, writer, writer, _schemas())


def _stored_approved_row(
    tmp_path: Path,
) -> tuple[ReviewReadyProposalRow, LocalImmutableVault]:
    """Freeze one real 11-member package and schema-valid approved decision."""
    fixture = semantic_proposal_fixture(
        observation_cutoff="2026-08-22T00:00:00Z",
        valid_until="2026-08-23T00:00:00Z",
        base_serving_state_id="srv_" + "b" * 48,
        candidate_serving_state_id="srv_" + "c" * 48,
        candidate_serving_state_fingerprint="sha256:" + "c" * 64,
        embedding_profile_fingerprint="sha256:" + "f" * 64,
        validity_predicates=_PREDICATES,
    )
    manifest_fingerprint = fixture.bindings.promotion_manifest_fingerprint
    manifest_id = fixture.bindings.promotion_manifest_id
    contents = fixture.contents
    package = freeze_proposal_package(
        contents,
        ProposalPackageInput(
            "2026-08-22T00:00:00Z",
            manifest_id,
            manifest_fingerprint,
            "srv_" + "b" * 48,
            "sha256:" + "b" * 64,
            "srv_" + "c" * 48,
            "sha256:" + "c" * 64,
        ),
        fixture.traceability_shards,
    )
    vault = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    retention = RetentionProfile("proposal-v1", "2036-01-01T00:00:00Z")
    members = tuple(
        ProposalMemberReceipt(
            artifact.role,
            artifact.path,
            vault.conditional_create(
                f"proposal-packages/{package.package_id}/members/{artifact.path}",
                artifact.content,
                retention,
            ).reference,
        )
        for artifact in package.artifacts
    )
    traceability_shards = tuple(
        TraceabilityShardReceipt(
            path,
            vault.conditional_create(
                f"proposal-packages/{package.package_id}/traceability/{path}",
                fixture.traceability_shards[path],
                retention,
            ).reference,
        )
        for path in sorted(fixture.traceability_shards)
    )
    manifest_reference = vault.conditional_create(
        f"proposal-packages/{package.package_id}/proposal-manifest.json",
        package.manifest_bytes,
        retention,
    ).reference
    provisional = StoredProposalPackage(
        package.package_id,
        package.fingerprint,
        manifest_id,
        manifest_fingerprint,
        members,
        traceability_shards,
        manifest_reference,
        "",
    )
    receipt = replace(provisional, receipt_fingerprint=proposal_receipt_fingerprint(provisional))
    receipt_bytes = canonicalize(checked_json_value(proposal_receipt_document(receipt)))
    approval_id = (
        "apr_"
        + sha256(
            chr(31).join((manifest_id, manifest_fingerprint, "APPROVED")).encode()
        ).hexdigest()[:48]
    )
    decision_bytes = canonicalize(
        checked_json_value(
            {
                "approval_id": approval_id,
                "authority_evidence_ref": {
                    "fingerprint": _AUTHORITY_FP,
                    "ref_id": _AUTHORITY,
                    "ref_type": "EVIDENCE",
                },
                "decision": "APPROVED",
                "decision_time": "2026-08-22T00:01:00Z",
                "expected_base_serving_state_ref": {
                    "fingerprint": "sha256:" + "b" * 64,
                    "ref_id": "srv_" + "b" * 48,
                    "ref_type": "SERVING_STATE",
                },
                "governance_policy_state": "CONFIGURED",
                "immutable": True,
                "promotion_manifest_ref": {
                    "fingerprint": manifest_fingerprint,
                    "ref_id": manifest_id,
                    "ref_type": "PROMOTION_MANIFEST",
                },
                "reason": "Reviewed complete package",
                "reviewer_identity_ref": {
                    "fingerprint": _REVIEWER_FP,
                    "ref_id": _REVIEWER,
                    "ref_type": "ACTOR",
                },
                "schema_id": "asklegal.approval-decision",
                "schema_version": "1.1.0",
                "valid_from": "2026-08-22T00:00:00Z",
                "validity_condition_refs": [
                    {
                        "contract_id": _PREDICATES[0][0],
                        "fingerprint": _PREDICATES[0][2],
                        "version": _PREDICATES[0][1],
                    }
                ],
            }
        )
    )
    return (
        ReviewReadyProposalRow(
            package.package_id,
            receipt_bytes,
            sha256(receipt_bytes).digest(),
            1,
            "2026-08-22T00:00:00",
            decision_bytes,
            sha256(decision_bytes).digest(),
            1,
            "PROPOSAL_APPROVED",
            "2026-08-22T00:01:00",
        ),
        vault,
    )


def test_promotion_source_reconstructs_exact_approval_after_restart(tmp_path: Path) -> None:
    """A fresh Promotion process re-reads SQL, all 12 vault objects, and decision bytes."""
    row, vault = _stored_approved_row(tmp_path)
    first = RegisteredPromotionApprovalSource(Rows((row,)), vault, _schemas()).approved(
        row.proposal_package_id
    )
    restarted = RegisteredPromotionApprovalSource(Rows((row,)), vault, _schemas()).approved(
        row.proposal_package_id
    )
    assert first is not None
    assert restarted == first
    assert first.approval_id.startswith("apr_")
    assert first.manifest.fingerprint.startswith("sha256:")
    assert first.manifest.validity_predicates == _PREDICATES
    assert first.reviewer_identity_id == _REVIEWER
    assert first.authority_evidence_id == _AUTHORITY


def test_promotion_source_rejects_tamper_and_never_admits_rejection(tmp_path: Path) -> None:
    """Changed decision bytes fail closed; a rejected projection is not consumable."""
    row, vault = _stored_approved_row(tmp_path)
    assert row.decision_bytes is not None
    tampered_document = parse_json_bytes(row.decision_bytes, max_bytes=10_000)
    assert isinstance(tampered_document, dict)
    manifest_ref = tampered_document["promotion_manifest_ref"]
    assert isinstance(manifest_ref, dict)
    manifest_ref["fingerprint"] = "sha256:" + "0" * 64
    tampered_bytes = canonicalize(tampered_document)
    tampered = replace(
        row,
        decision_bytes=tampered_bytes,
        decision_fingerprint=sha256(tampered_bytes).digest(),
    )
    with pytest.raises(RegisteredApprovalSourceError):
        RegisteredPromotionApprovalSource(Rows((tampered,)), vault, _schemas()).approved(
            row.proposal_package_id
        )
    rejected = replace(row, decision_event_type="PROPOSAL_REJECTED")
    assert (
        RegisteredPromotionApprovalSource(Rows((rejected,)), vault, _schemas()).approved(
            row.proposal_package_id
        )
        is None
    )


def test_promotion_source_independently_rereads_traceability_shards(tmp_path: Path) -> None:
    """Promotion refuses a valid Approval when one declared lookup shard is corrupt."""
    row, vault = _stored_approved_row(tmp_path)
    receipt = stored_proposal_package_from_bytes(row.receipt_bytes)
    vault.inject_corruption(receipt.traceability_shards[0].reference, b"changed")

    with pytest.raises(RegisteredApprovalSourceError):
        RegisteredPromotionApprovalSource(Rows((row,)), vault, _schemas()).approved(
            row.proposal_package_id
        )


def test_registered_approval_consumes_once_without_provider_effect() -> None:
    """Bind the complete approval, lineage, authority, and validity evidence."""
    writer = Writer()
    result = _service(Candidates(_candidate()), Authority(_authority()), writer).consume(
        _PROPOSAL,
        "cmd_" + "a" * 48,
        _context(),
        simulate_lost_ack=True,
    )
    assert result.result_code == "APPLIED"
    assert result.authoritative_version == 1
    assert writer.lost_ack_flags == [True]
    command = writer.received[0]
    command_document = parse_json_bytes(command.command_bytes, max_bytes=10_000)
    event = parse_json_bytes(command.event_bytes, max_bytes=10_000)
    assert isinstance(command_document, dict)
    assert command_document["action"] == "CONSUME_REGISTERED_APPROVAL"
    assert "effect" not in command_document
    assert isinstance(event, dict)
    assert event["from_state"] == "APPROVAL_APPROVED"
    assert event["to_state"] == "APPROVAL_CONSUMED"
    assert event["event_type"] == "CONSUME_FOR_ONE_EXECUTION_LINEAGE"
    evidence_refs = event["evidence_refs"]
    assert isinstance(evidence_refs, list)
    assert len(evidence_refs) == 2
    assert "effect" not in event


def test_registered_approval_restart_replays_and_competing_lineage_loses() -> None:
    """A fresh service exactly replays one command and rejects another winner."""
    candidates = Candidates(_candidate())
    authority = Authority(_authority())
    writer = Writer()
    command_id = "cmd_" + "b" * 48
    original = _service(candidates, authority, writer).consume(_PROPOSAL, command_id, _context())
    replay = _service(candidates, authority, writer).consume(_PROPOSAL, command_id, _context())
    assert original.replayed is False
    assert replay.replayed is True
    competing_context = replace(
        _context(),
        execution_lineage_id="exe_" + "c" * 48,
        execution_lineage_fingerprint="sha256:" + "c" * 64,
    )
    with pytest.raises(RegisteredApprovalError) as raised:
        _service(candidates, authority, writer).consume(
            _PROPOSAL,
            "cmd_" + "c" * 48,
            competing_context,
        )
    assert raised.value.code is RegisteredApprovalErrorCode.ALREADY_CONSUMED


def test_registered_approval_requires_approved_decision_and_current_authority() -> None:
    """Missing decision, removed role, or reviewer-identity drift blocks consumption."""
    writer = Writer()
    with pytest.raises(RegisteredApprovalError) as missing:
        _service(Candidates(None), Authority(_authority()), writer).consume(
            _PROPOSAL, "cmd_" + "d" * 48, _context()
        )
    assert missing.value.code is RegisteredApprovalErrorCode.NOT_APPROVED
    removed = replace(_authority(), roles=frozenset())
    with pytest.raises(RegisteredApprovalError) as role:
        _service(Candidates(_candidate()), Authority(removed), writer).consume(
            _PROPOSAL, "cmd_" + "e" * 48, _context()
        )
    assert role.value.code is RegisteredApprovalErrorCode.AUTHORITY_REMOVED
    drifted = replace(_authority(), reviewer_identity_fingerprint="sha256:" + "d" * 64)
    with pytest.raises(RegisteredApprovalError) as identity:
        _service(Candidates(_candidate()), Authority(drifted), Writer()).consume(
            _PROPOSAL, "cmd_" + "f" * 48, _context()
        )
    assert identity.value.code is RegisteredApprovalErrorCode.AUTHORITY_REMOVED


def test_objective_drift_persists_one_no_effect_invalidation_before_failure() -> None:
    """A changed bound predicate terminally invalidates before consumption can retry."""
    writer = Writer()
    drifted = replace(
        _context(),
        current_predicates=(("configuration", "1.0.1", "sha256:" + "a" * 64),),
    )
    service = _service(Candidates(_candidate()), Authority(_authority()), writer)
    with pytest.raises(RegisteredApprovalError) as first:
        service.consume(_PROPOSAL, "cmd_" + "0" * 48, drifted)
    with pytest.raises(RegisteredApprovalError) as replay:
        _service(Candidates(_candidate()), Authority(_authority()), writer).consume(
            _PROPOSAL,
            "cmd_" + "0" * 48,
            drifted,
        )
    assert first.value.code is RegisteredApprovalErrorCode.INVALID
    assert replay.value.code is RegisteredApprovalErrorCode.INVALID
    assert len(writer.invalidations) == 1
    command = writer.invalidations[0]
    command_document = parse_json_bytes(command.command_bytes, max_bytes=10_000)
    event = parse_json_bytes(command.event_bytes, max_bytes=10_000)
    assert isinstance(command_document, dict)
    assert command_document["action"] == "INVALIDATE_REGISTERED_APPROVAL"
    assert command_document["reason_code"] == "VALIDITY_PREDICATE_DRIFT"
    assert "effect" not in command_document
    assert isinstance(event, dict)
    assert event["to_state"] == "APPROVAL_INVALIDATED"
    assert event["event_type"] == "INVALIDATE"
    assert event["execution_lineage_refs"] == []
    assert "effect" not in event

    with pytest.raises(RegisteredApprovalError) as terminal:
        service.consume(_PROPOSAL, "cmd_" + "2" * 48, _context())
    assert terminal.value.code is RegisteredApprovalErrorCode.ALREADY_CONSUMED


@pytest.mark.parametrize(
    "context",
    [
        replace(_context(), at="2026-08-21T23:59:59Z"),
        replace(_context(), at="2026-08-23T00:00:01Z"),
        replace(_context(), command_expires_at="2026-08-22T11:59:59Z"),
        replace(_context(), current_base_serving_state_id="srv_" + "d" * 48),
        replace(_context(), current_predicates=(("configuration", "1.0.1", "sha256:" + "a" * 64),)),
    ],
)
def test_registered_approval_rejects_manifest_validity_drift(
    context: ApprovalConsumptionContext,
) -> None:
    """Time, base-state, predicate, or command-window drift invalidates consumption."""
    with pytest.raises(RegisteredApprovalError) as raised:
        _service(Candidates(_candidate()), Authority(_authority()), Writer()).consume(
            _PROPOSAL,
            "cmd_" + "1" * 48,
            context,
        )
    assert raised.value.code is RegisteredApprovalErrorCode.INVALID
