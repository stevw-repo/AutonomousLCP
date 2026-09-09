# Local Review, Approval, and Real Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user review a complete proposal locally at any time and make one valid Approval automatically start exact, rollback-safe promotion.

**Architecture:** Extend the existing Review/Approval/registered-execution chain rather than replacing it. A SQL wake-up projection makes approved work visible to the Promotion worker; the worker independently re-reads the proposal and current capability evidence before consuming Approval. Real effect handlers use the Plan 6 adapters, perform complete target read-back and backup verification, and atomically change only the Management Register Serving State—never an Ask.Legal route.

**Tech Stack:** Python 3.14.7, FastAPI Review application, pinned Entra delegated-human verifier, Azure SQL stored-procedure boundary, existing corpus/proposal/promotion packages, Azure OpenAI embeddings, Pinecone REST, primary and recovery vault ports, Durable Task worker, Pytest plus opt-in SQL integration tests.

**Spec:** `docs/design/HK_V1_LIVE_EXECUTION_SPEC.md`

## Global Constraints

- The proposal is immutable, whole-package approval only, and may wait while its predicates remain current.
- One named-human Approval is enough; no second command or approval is required.
- Material drift invalidates the waiting proposal before any provider effect.
- Only the Promotion worker can hold embedding, Pinecone, backup, or Serving-State mutation credentials.
- Unapproved or invalidated work cannot call providers.
- Every target record, vector width/fingerprint, and six-field payload is read back before activation.
- The predecessor remains protected; rollback is exact and predecessor-bound.
- V1 has no Ask.Legal route or slot-swap action.
- SQL migration, external provider mutation, backup mutation, and live composition require separate exact authorization.

## Dependency and exit contract

Depends on Plans 1–6: complete ready releases, proposal members, exact profiles, and current capability evidence. Produces:

```python
class RegisteredPromotionRunner(Protocol):
    def run_once(self) -> RegisteredPromotionRunResult: ...


class RegisteredReviewDecisionService(Protocol):
    def approve(
        self, proposal_package_id: str, principal: VerifiedPrincipal, reason: str
    ) -> ProposalDetailProjection: ...
```

Plan 8 supervises the Review and Promotion applications. Plan 9 uses this exact path for baseline, rollback, restoration, and live update.

## File structure

- Modify Review API/client/governance files — complete local report and named-human decision.
- Create migration `000010_approved_promotion_wakeup` — single-use, owner-scoped approved-work dequeue.
- Create migration `000011_serving_state_transition` — compare-and-set current Serving State and exact reversal.
- Modify `packages/promotion` ports/service/builder — Serving State naming and no routing action in V1.
- Create real promotion effect composition under `apps/promotion-worker/src/asklegal_promotion_worker/real_effects.py`.
- Modify registered execution/effect handler/runtime files — automatic approval consumption and next-action handoff.
- Add focused Review, SQL, promotion, read-back, backup, failure, and rollback tests.

---

### Task 1: Show the complete local review report and bind the decision

**Files:**
- Modify: `apps/review-api/src/asklegal_review_api/registered_proposals.py`
- Modify: `apps/review-api/src/asklegal_review_api/api.py`
- Modify: `apps/review-api/src/asklegal_review_api/client/index.html`
- Modify: `apps/review-api/src/asklegal_review_api/client/app.js`
- Modify: `apps/review-api/src/asklegal_review_api/governance.py`
- Test: `apps/review-api/tests/test_registered_proposals.py`
- Test: `apps/review-api/tests/test_registered_governance.py`
- Test: `apps/review-api/tests/test_review_api.py`

**Interfaces:**
- Consumes: all twelve proposal members, verified delegated-human principal, and decision reason.
- Produces: complete `ProposalDetailProjection` and one `APPROVED` or `REJECTED` registered decision.

- [ ] **Step 1: Write failing complete-report and identity tests**

```python
def test_review_detail_contains_every_v1_decision_section() -> None:
    detail = service().detail(PROPOSAL_ID, principal())
    assert set(detail.sections) >= {
        "source_changes",
        "coverage",
        "release_counts",
        "record_changes",
        "quarantine",
        "waiting_room",
        "evaluation",
        "profiles",
        "expected_cost",
        "backup_readiness",
        "rollback_readiness",
    }


def test_approval_requires_verified_delegated_human() -> None:
    with pytest.raises(ApprovalError, match="UNAUTHORIZED_PRINCIPAL"):
        service().approve(PROPOSAL_ID, app_principal(), "approve")
```

- [ ] **Step 2: Run focused Review tests and observe missing sections**

Run: `python3 -m pytest apps/review-api/tests/test_registered_proposals.py apps/review-api/tests/test_registered_governance.py apps/review-api/tests/test_review_api.py -q`

Expected: at least the complete-report test fails.

- [ ] **Step 3: Extend strict projection and local UI**

Decode each authoritative proposal member independently, render counts/failures/sample outputs without treating the report as authority, and POST only the exact package ID, whole-package decision, and non-empty reason. Keep bearer tokens in memory and require the existing pinned Entra tenant/client/key/role profile.

- [ ] **Step 4: Run Review and proposal-member tests**

Run: `python3 -m pytest apps/review-api/tests packages/contracts/tests/test_proposal_members.py packages/corpus/tests/test_m6_corpus.py -q`

Expected: all Review, governance, and proposal trust-chain tests pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- apps/review-api`

Expected: complete local display and exact whole-package decisions only. Commit only with exact user authorization.

### Task 2: Add automatic single-use approved-work wake-up

**Files:**
- Create: `packages/management-register-adapter/migrations/000010_approved_promotion_wakeup/001_approved_promotion_wakeup.sql`
- Create: `packages/management-register-adapter/migrations/000010_approved_promotion_wakeup/manifest.json`
- Modify: `packages/management-register-adapter/src/asklegal_management_register/store.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/registered_approval.py`
- Create: `packages/management-register-adapter/tests/test_approved_promotion_wakeup.py`
- Test: `apps/promotion-worker/tests/test_registered_approval.py`

**Interfaces:**
- Consumes: terminal registered proposal decision rows.
- Produces: `ApprovedPromotionQueue.claim_next(worker_id, lease_until) -> ApprovedPromotionClaim | None`.

- [ ] **Step 1: Write failing claim/replay/concurrency tests**

```python
def test_approved_proposal_becomes_claimable_without_second_command(sql_store) -> None:
    approve(sql_store, PROPOSAL_ID)
    claim = sql_store.claim_next_approved_promotion(WORKER_ID, LEASE_UNTIL)
    assert claim.proposal_package_id == PROPOSAL_ID


def test_two_workers_cannot_claim_the_same_approval(sql_store) -> None:
    approve(sql_store, PROPOSAL_ID)
    claims = concurrently_claim(sql_store, workers=("worker-a", "worker-b"))
    assert sum(claim is not None for claim in claims) == 1
```

- [ ] **Step 2: Run the opt-in SQL test and observe the missing procedure**

Run: `ASKLEGAL_RUN_SQL_INTEGRATION=1 python3 -m pytest packages/management-register-adapter/tests/test_approved_promotion_wakeup.py -q`

Expected: FAIL because migration/procedure/adapter methods are absent. Use only the repository's disposable SQL proof instance; do not apply to live SQL.

- [ ] **Step 3: Implement owner-scoped claim and acknowledgement**

```python
class ApprovedPromotionQueue(Protocol):
    def claim_next(self, worker_id: str, claimed_until: str) -> ApprovedPromotionClaim | None: ...
    def acknowledge_started(
        self, claim: ApprovedPromotionClaim, execution_lineage_id: str
    ) -> None: ...
```

The stored procedure selects one `APPROVED`, unconsumed, unrevoked, uninvalidated proposal, acquires a lease/fence, and returns its exact row. Promotion independently performs existing consume/authorize/begin commands; the queue claim is not authorization.

- [ ] **Step 4: Run fresh migration and least-privilege proofs**

Run: `ASKLEGAL_RUN_SQL_INTEGRATION=1 python3 -m pytest packages/management-register-adapter/tests/test_migration_package.py packages/management-register-adapter/tests/test_approved_promotion_wakeup.py packages/management-register-adapter/tests/test_sql_server_integration.py -q`

Expected: fresh database proof passes; only the Promotion role can claim and acknowledge approved work.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/management-register-adapter apps/promotion-worker/src/asklegal_promotion_worker/registered_approval.py apps/promotion-worker/tests/test_registered_approval.py`

Expected: one owner-scoped wake-up migration and adapter. Live migration requires separate authority. Commit only with exact user authorization.

### Task 3: Replace routing semantics with Management Register Serving State

**Files:**
- Modify: `packages/promotion/src/asklegal_promotion/ports.py`
- Modify: `packages/promotion/src/asklegal_promotion/local.py`
- Modify: `packages/promotion/src/asklegal_promotion/builder.py`
- Modify: `packages/promotion/src/asklegal_promotion/model.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/service.py`
- Create: `packages/management-register-adapter/migrations/000011_serving_state_transition/001_serving_state_transition.sql`
- Create: `packages/management-register-adapter/migrations/000011_serving_state_transition/manifest.json`
- Create: `packages/promotion/tests/test_serving_state.py`
- Create: `packages/management-register-adapter/tests/test_serving_state_transition.py`

**Interfaces:**
- Consumes: expected base Serving State, approved candidate state, coverage fingerprint, target name, and predecessor.
- Produces: `ServingStatePort.activate()` and `.rollback()` with compare-and-set receipts.

- [ ] **Step 1: Write failing no-routing and compare-and-set tests**

```python
def test_v1_manifest_has_no_asklegal_routing_action() -> None:
    manifest = build_v1_manifest(valid_inputs())
    assert EffectType.ROUTING_ACTIVATION not in tuple(
        action.effect_type for action in manifest.actions
    )
    assert EffectType.RELEASE_PUBLICATION in tuple(
        action.effect_type for action in manifest.actions
    )


def test_serving_state_activation_loses_on_base_drift(store) -> None:
    with pytest.raises(PromotionError, match="BASE_STATE_DRIFT"):
        store.activate(expected_base="srv_old", candidate=candidate_bound_to("srv_other"))
```

- [ ] **Step 2: Run and observe current `RoutingPort` behavior**

Run: `python3 -m pytest packages/promotion/tests/test_serving_state.py packages/management-register-adapter/tests/test_serving_state_transition.py -q`

Expected: tests fail until the V1 path stops requiring `ROUTING_ACTIVATION`.

- [ ] **Step 3: Implement exact Serving State port and migration**

```python
class ServingStatePort(Protocol):
    active_state_id: str

    def activate(self, expected_base: str, candidate: ServingStateCandidate) -> str: ...
    def verify(self, candidate_state_id: str) -> None: ...
    def rollback(self, candidate_state_id: str, predecessor_state_id: str) -> str: ...
```

Store candidate target name, inventory fingerprint, coverage fingerprint, profile refs, approval/execution lineage, predecessor, and activation receipt. Compare and set under one transaction. Preserve the generic future routing contract outside the V1 manifest, but do not call it.

- [ ] **Step 4: Run promotion and fresh SQL suites**

Run: `python3 -m pytest packages/promotion/tests/test_serving_state.py apps/promotion-worker/tests/test_m6_promotion.py -q`

Run: `ASKLEGAL_RUN_SQL_INTEGRATION=1 python3 -m pytest packages/management-register-adapter/tests/test_serving_state_transition.py packages/management-register-adapter/tests/test_migration_package.py -q`

Expected: local promotion and disposable SQL compare-and-set/reverse-state tests pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/promotion packages/management-register-adapter apps/promotion-worker/src/asklegal_promotion_worker/service.py`

Expected: V1 activation names and mutates only Serving State. Commit only with exact user authorization.

### Task 4: Compose current capability, authority, and state readers

**Files:**
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/registered_execution_begin.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/v1_infrastructure.py`
- Create: `apps/promotion-worker/src/asklegal_promotion_worker/current_evidence.py`
- Create: `apps/promotion-worker/tests/test_current_evidence.py`

**Interfaces:**
- Consumes: exact profile/evidence refs from Plan 6, current app identity/role, current Serving State, and manifest predicates.
- Produces: concrete `CurrentCapabilityEvidenceSource`, `CurrentAuthoritySource`, and `CurrentServingStateSource` implementations.

- [ ] **Step 1: Write failing stale-capability and identity tests**

```python
def test_expired_capability_is_not_current() -> None:
    assert evidence_source(expired_capability()).current(PROFILE_ID, NOW) is None


def test_wrong_worker_identity_cannot_begin_execution() -> None:
    with pytest.raises(RegisteredExecutionBeginError, match="INVALID"):
        begin_service(wrong_worker_identity()).begin(candidate(), context())
```

- [ ] **Step 2: Run and observe real readers are absent**

Run: `python3 -m pytest apps/promotion-worker/tests/test_current_evidence.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement reread-and-verify readers**

Every `current()` call reads the exact immutable evidence bytes, validates hash/expiry/environment/application/effect/profile, and compares them with manifest references. Current Serving State comes from the Management Register stored procedure, not an environment variable.

- [ ] **Step 4: Run current-evidence and execution-begin suites**

Run: `python3 -m pytest apps/promotion-worker/tests/test_current_evidence.py apps/promotion-worker/tests/test_registered_execution_begin.py apps/promotion-worker/tests/test_registered_execution.py -q`

Expected: all current, stale, tampered, wrong-owner, and drift tests pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- apps/promotion-worker/src/asklegal_promotion_worker/current_evidence.py apps/promotion-worker/src/asklegal_promotion_worker/registered_execution_begin.py apps/promotion-worker/src/asklegal_promotion_worker/v1_infrastructure.py apps/promotion-worker/tests/test_current_evidence.py`

Expected: exact readers and fail-closed infrastructure composition. Commit only with exact user authorization.

### Task 5: Implement real fenced effect handlers and complete read-back

**Files:**
- Create: `apps/promotion-worker/src/asklegal_promotion_worker/real_effects.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/registered_effect_handler.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/runtime.py`
- Create: `apps/promotion-worker/tests/test_real_effects.py`
- Test: `apps/promotion-worker/tests/test_registered_effect_handler.py`
- Test: `apps/promotion-worker/tests/test_v1_serving_payload.py`

**Interfaces:**
- Consumes: claimed fenced intent bytes, exact current capability evidence, embedding/target/backup/Serving-State ports.
- Produces: `RegisteredEffectOutcome` for embedding, Pinecone, backup, release publication, and exact rollback effects.

- [ ] **Step 1: Write failing unapproved, lost-ack, and payload tests**

```python
def test_handler_refuses_intent_not_bound_to_current_capability() -> None:
    with pytest.raises(RegisteredEffectHandlerError, match="CAPABILITY_EVIDENCE_MISMATCH"):
        effect_port(stale_capability()).perform(valid_intent_bytes(), fencing_token=7)


def test_unknown_upsert_ack_is_reconciled_by_full_readback() -> None:
    outcome = effect_port(target=lost_ack_but_complete_target()).perform(upsert_intent(), 7)
    assert outcome.result == "SUCCEEDED_AFTER_READBACK"


def test_target_readback_requires_exact_six_field_payload() -> None:
    with pytest.raises(PromotionError, match="INVENTORY_MISMATCH"):
        verify_complete_target(expected(), actual_missing_authority_note())
```

- [ ] **Step 2: Run and observe only disabled effect composition exists**

Run: `python3 -m pytest apps/promotion-worker/tests/test_real_effects.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement effect dispatch by exact manifest action**

```python
class RealPromotionEffectPort:
    def perform(self, intent_bytes: bytes, fencing_token: int) -> RegisteredEffectOutcome:
        authority = decode_and_validate_intent(intent_bytes, fencing_token)
        handler = self._handlers[authority.action.effect_type]
        return handler(authority)
```

There is no default handler. Each handler revalidates capability, destination, idempotency, input refs, fencing, precondition, and attempt ceiling. Pinecone verification enumerates and compares every record ID, vector fingerprint/width, content fingerprint, and six-field payload.

- [ ] **Step 4: Run handler, payload, and remote-adapter suites**

Run: `python3 -m pytest apps/promotion-worker/tests/test_real_effects.py apps/promotion-worker/tests/test_registered_effect_handler.py apps/promotion-worker/tests/test_v1_serving_payload.py packages/promotion/tests/test_remote_adapters.py -q`

Expected: all exact-effect, replay, fence, lost-ack, read-back, and payload tests pass with scripted providers.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- apps/promotion-worker packages/promotion`

Expected: explicit handlers remain disabled unless exact real infrastructure loads. Commit only with exact user authorization.

### Task 6: Implement provider-native and independent recovery verification

**Files:**
- Create: `packages/promotion/src/asklegal_promotion/backup.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/real_effects.py`
- Create: `packages/promotion/tests/test_backup.py`
- Modify: `apps/promotion-worker/tests/test_real_effects.py`

**Interfaces:**
- Consumes: exact target definition/inventory fingerprint and separately administered primary/recovery vault ports.
- Produces: `BackupVerification` with independently read-back native and recovery receipts.

- [ ] **Step 1: Write failing independent-verification tests**

```python
def test_same_receipt_cannot_satisfy_native_and_recovery_verification() -> None:
    with pytest.raises(PromotionError, match="BACKUP_FAILED"):
        create_and_verify_backup(target(), same_receipt_backends())


def test_unreadable_recovery_copy_blocks_activation() -> None:
    with pytest.raises(PromotionError, match="BACKUP_FAILED"):
        create_and_verify_backup(target(), unreadable_recovery_backend())
```

- [ ] **Step 2: Run and observe real backup adapter is absent**

Run: `python3 -m pytest packages/promotion/tests/test_backup.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement exact backup and read-back**

Write provider-native backup request/receipt evidence and a separate recovery inventory package containing target definition, desired inventory, vectors or provider-supported export refs, and six-field payloads. Read both back through separate ports and compare exact fingerprints before returning `native_verified=True` and `recovery_verified=True`.

- [ ] **Step 4: Run backup and promotion service tests**

Run: `python3 -m pytest packages/promotion/tests/test_backup.py apps/promotion-worker/tests/test_real_effects.py apps/promotion-worker/tests/test_m6_promotion.py -q`

Expected: all backup success/failure/replay cases pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/promotion/src/asklegal_promotion/backup.py packages/promotion/tests/test_backup.py apps/promotion-worker/src/asklegal_promotion_worker/real_effects.py`

Expected: two independently verified recovery paths. Commit only with exact user authorization.

### Task 7: Prove automatic Approval-to-promotion and exact rollback locally

**Files:**
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/v1_pipeline.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py`
- Create: `apps/promotion-worker/tests/test_v1_approval_to_promotion.py`
- Modify: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: approved proposal claim, current evidence readers, registered command writers, and scripted or authorized real ports.
- Produces: one terminal execution result with current Serving State or exact rollback state.

- [ ] **Step 1: Write the failing end-to-end local lifecycle test**

```python
def test_approval_automatically_promotes_without_second_command() -> None:
    system = local_registered_system()
    system.review.approve(PROPOSAL_ID, human_principal(), "reviewed")
    result = system.promotion.run_once()
    assert result.state == "EXECUTION_SUCCEEDED"
    assert system.serving_state.active_state_id == CANDIDATE_STATE_ID


def test_drift_invalidates_waiting_approval_before_provider_call() -> None:
    system = local_registered_system(predicates=drifted_predicates())
    system.review.approve(PROPOSAL_ID, human_principal(), "reviewed")
    result = system.promotion.run_once()
    assert result.state == "APPROVAL_INVALIDATED"
    assert system.provider_calls == ()
```

- [ ] **Step 2: Run and observe automatic lifecycle is incomplete**

Run: `python3 -m pytest apps/promotion-worker/tests/test_v1_approval_to_promotion.py -q`

Expected: new tests fail until wake-up, current readers, effects, and Serving State are composed.

- [ ] **Step 3: Implement one `run_once()` chain**

Claim approved work, re-read proposal, consume Approval, authorize execution, begin action 1, handle/receipt each exact action with durable handoff, verify complete target/backups, activate Serving State, and acknowledge queue start/result. On post-activation verification failure, execute only the manifest-declared reverse-state operation.

- [ ] **Step 4: Run full Review/Promotion/SQL proof and shipping gate**

Run: `python3 -m pytest apps/review-api/tests apps/promotion-worker/tests packages/promotion/tests -q`

Expected: all local lifecycle tests pass.

Run the opt-in migrations against a fresh disposable SQL database, then run:

`python3 -m tools.dev_test --uv /home/docpro/.local/bin/uv --node /home/docpro/.local/bin/node`

Expected: fresh SQL proof and complete shipping gate pass.

- [ ] **Step 5: Stop before live mutation**

Record migration proof, lifecycle evidence, and no-routing result in `.agent/WORKING_STATE.md`. Do not apply migrations to live SQL, load real provider handlers, mutate Pinecone, or change Serving State without exact separate authority. Request explicit commit authorization before creating the Plan 7 checkpoint.
