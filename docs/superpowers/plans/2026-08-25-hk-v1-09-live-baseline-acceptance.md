# Complete Hong Kong V1 Baseline and Live Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, approve, activate, roll back, restore, reboot, and autonomously update one complete three-family Hong Kong V1 until the formal result is `V1_ADMITTED`.

**Architecture:** Add one real-V1 admission coordinator that reads the prior eight gates and never repairs missing evidence. Select two authentic complete common cutoffs `T1 < T2`: T1 builds the first complete current Serving State; after reboot, the ordinary scheduler discovers the already published authentic delta through T2, waits for local Approval, and promotes the replacement automatically. Exact rollback to T1 and restoration to T2 prove recovery; subsequent scheduled no-change and healthy-next-cycle evidence close admission.

**Tech Stack:** All repository applications/packages, Ubuntu systemd stack, Azure SQL, official-source connectors, Azure OpenAI, Pinecone, primary/recovery vaults, local Review, Durable Task, Python 3.14.7 admission tooling and Pytest.

**Spec:** `docs/design/HK_V1_LIVE_EXECUTION_SPEC.md`

## Global Constraints

- The admitted scope is exactly three Hong Kong Legislation scopes, post-1-July-1997 binding-case propositions, and Main/GEM Listing Rules.
- Principles and Ask.Legal query/admin integration remain excluded and must be stated in the final limitation text.
- T1 and T2 are authentic complete common cutoffs; T2 contains at least one official source change relative to T1.
- Every due blocking source, source item, release scope, record, traceability entry, provider request, target record, backup, Approval, and transition is completely accounted for.
- Local human Approval is required for both T1 baseline and T2 changed proposal; after Approval, promotion starts automatically.
- No source/model/Pinecone/host/reboot action occurs without its exact current authority.
- Formal admission is impossible with a skipped test, missing read-back, stale profile, orphan process, incomplete telemetry, or unresolved release-blocking gap.
- The final current state is T2 after rollback and restoration; the next scheduled cycle remains healthy.

## Dependency and exit contract

Depends on Gate A–F evidence from Plans 1–8. Produces:

```python
def evaluate_hk_v1_live_admission(
    evidence: HKV1AdmissionEvidence,
) -> HKV1LiveAdmissionReport: ...
```

The only passing terminal result is:

```json
{"admitted": true, "result": "V1_ADMITTED"}
```

## File structure

- Create `tools/hk_v1_live_admission.py` — strict Gate A–G evidence loader/evaluator and CLI.
- Create `tools/hk_v1_live_cycle.py` — exact local baseline/update enqueue CLI that delegates to Control.
- Create `tools/tests/test_hk_v1_live_admission.py` — fail-closed admission tests.
- Modify Control pipeline/service — complete baseline/update orchestration and genuine no-change short circuit.
- Modify reporting — final V1 report and limitation wording.
- Create `docs/runbooks/HK_V1_LOCAL_OPERATOR.md` — local review, status, rollback, recovery, and authorization-bound procedures.
- Modify `.agent/ROADMAP.md`, `.agent/WORKING_STATE.md`, and `.agent/HANDOFF.md` only from observed final evidence.

---

### Task 1: Implement the formal Gate A–G admission evaluator

**Files:**
- Create: `tools/hk_v1_live_admission.py`
- Create: `tools/tests/test_hk_v1_live_admission.py`

**Interfaces:**
- Consumes: immutable refs/fingerprints for Gate A–F plus baseline/update/reboot/schedule evidence for Gate G.
- Produces: canonical `HKV1LiveAdmissionReport` and process exit 0 only for `V1_ADMITTED`.

- [ ] **Step 1: Write failing false-success tests**

```python
@pytest.mark.parametrize(
    "missing_gate",
    ("A", "B", "C", "D", "E", "F", "G"),
)
def test_missing_gate_can_never_report_v1_admitted(missing_gate: str) -> None:
    report = evaluate_hk_v1_live_admission(evidence_without(missing_gate))
    assert report.admitted is False
    assert report.result == "NOT_ADMITTED"


def test_asklegal_routing_receipt_is_not_required() -> None:
    report = evaluate_hk_v1_live_admission(complete_evidence(asklegal_routing_receipt=None))
    assert report.admitted is True
```

- [ ] **Step 2: Run and verify the real admission evaluator is absent**

Run: `python3 -m pytest tools/tests/test_hk_v1_live_admission.py -q`

Expected: collection fails for the missing tool.

- [ ] **Step 3: Implement exact evidence model and evaluation**

```python
@dataclass(frozen=True, slots=True)
class HKV1GateResult:
    gate: Literal["A", "B", "C", "D", "E", "F", "G"]
    passed: bool
    evidence_refs: tuple[str, ...]
    blocker_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKV1AdmissionEvidence:
    gates: tuple[HKV1GateResult, ...]
    current_serving_state_id: str
    current_target_name: str
    coverage_matrix_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKV1LiveAdmissionReport:
    result: Literal["V1_ADMITTED", "NOT_ADMITTED"]
    admitted: bool
    gate_results: tuple[HKV1GateResult, ...]
    blocker_codes: tuple[str, ...]
    serving_state_id: str
    target_name: str
    coverage_matrix_fingerprint: str
    evidence_fingerprint: str
```

Require exact gate names once, re-read every immutable reference, verify all cross-fingerprints, reject unknown keys, stale profiles, missing counts, mismatched current state/target, and any skipped/assumed result. Sort blockers and make the report canonical.

- [ ] **Step 4: Run admission tests twice**

Run: `python3 -m pytest tools/tests/test_hk_v1_live_admission.py -q`

Run it a second time.

Expected: both runs pass and generated synthetic evidence reports are byte-identical.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- tools/hk_v1_live_admission.py tools/tests/test_hk_v1_live_admission.py`

Expected: fail-closed evaluator only. Commit only with exact user authorization.

### Task 2: Compose complete baseline and update orchestration

**Files:**
- Create: `tools/hk_v1_live_cycle.py`
- Create: `tools/tests/test_hk_v1_live_cycle.py`
- Modify: `apps/control-plane/src/asklegal_control_plane/v1_pipeline.py`
- Modify: `apps/control-plane/src/asklegal_control_plane/v1_service.py`
- Modify: `apps/control-plane/src/asklegal_control_plane/proposal.py`
- Modify: `packages/reporting/src/asklegal_reporting/source_coverage.py`
- Create: `apps/control-plane/tests/test_hk_v1_live_cycle.py`

**Interfaces:**
- Consumes: schedule delivery, common cutoff, Plan 1 matrix, source-cycle result, prior Serving State, three-family processing results, compact evaluation, and proposal builder.
- Produces: `NO_CHANGE`, `PROPOSAL_READY`, or exact failure—never a partial proposal.

- [ ] **Step 1: Write failing no-change and complete-proposal tests**

```python
def test_genuine_no_change_stops_before_model_embedding_and_proposal() -> None:
    result = run_live_cycle(complete_unchanged_source_cycle(), prior_serving_state())
    assert result.state == "NO_CHANGE"
    assert result.model_calls == 0
    assert result.proposal_package_id == ""


def test_changed_cycle_requires_all_five_release_scopes() -> None:
    result = run_live_cycle(changed_cycle_missing("HK-REG-HKEX-GEM"), prior_serving_state())
    assert result.state == "BLOCKED"
    assert result.failure_code == "RELEASE_SCOPE_INCOMPLETE"


def test_live_cycle_cli_defaults_to_preflight() -> None:
    result = run_live_cycle_cli(valid_cli_arguments(mode="preflight"), local_dependencies())
    assert result.enqueued is False
```

- [ ] **Step 2: Run and observe no real three-family coordinator**

Run: `python3 -m pytest apps/control-plane/tests/test_hk_v1_live_cycle.py tools/tests/test_hk_v1_live_cycle.py -q`

Expected: collection fails or tests fail because current composition is synthetic/partial.

- [ ] **Step 3: Implement the exact durable sequence**

```text
observe all due sources
verify complete source cycle
compare controlling source fingerprints with current Serving State
if unchanged: write NO_CHANGE report and stop
if changed: process Legislation, Cases, Main, GEM
verify all five complete Release Scopes and traceability
run compact evaluation under current profiles
build complete desired state, coverage, recovery readiness, report, manifest
write proposal manifest last
register proposal for Review
```

Every step uses stable command/work-item identity from cycle ID and cutoff and replays exact completed output after restart.

The CLI accepts only `BASELINE` or `UPDATE`, a frozen cutoff document/key, the
matrix path, and `preflight` or `enqueue`. Preflight re-reads all inputs and
performs no register write.

- [ ] **Step 4: Run Control, acquisition, processing, corpus, and proposal integration tests**

Run: `python3 -m pytest apps/control-plane/tests/test_hk_v1_live_cycle.py tools/tests/test_hk_v1_live_cycle.py apps/acquisition-worker/tests/test_v1_source_cycle.py apps/legal-processing-worker/tests packages/corpus/tests apps/control-plane/tests/test_m6_proposal.py -q`

Expected: changed/no-change/failure/restart cases pass with local fakes.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- apps/control-plane packages/reporting`

Expected: one complete cycle coordinator. Commit only with exact user authorization.

### Task 3: Select and freeze authentic complete cutoffs T1 and T2

**Files:**
- Create: `tools/hk_v1_select_acceptance_cutoffs.py`
- Create: `tools/tests/test_hk_v1_select_acceptance_cutoffs.py`
- Modify: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: admitted source observation manifests already preserved under `var/`.
- Produces: `HKV1AcceptanceCutoffs` with `baseline_cutoff`, `changed_cutoff`, exact source-manifest refs, and proved delta.

- [ ] **Step 1: Write failing authentic-delta tests**

```python
def test_cutoff_pair_requires_complete_sources_at_both_cutoffs() -> None:
    with pytest.raises(CutoffSelectionError, match="COMMON_CUTOFF_INCOMPLETE"):
        select_acceptance_cutoffs(observations_with_incomplete_hkex_at_t1())


def test_t2_requires_at_least_one_controlling_official_change() -> None:
    with pytest.raises(CutoffSelectionError, match="AUTHENTIC_CHANGE_NOT_FOUND"):
        select_acceptance_cutoffs(two_identical_complete_cutoffs())
```

- [ ] **Step 2: Run and verify cutoff selector is absent**

Run: `python3 -m pytest tools/tests/test_hk_v1_select_acceptance_cutoffs.py -q`

Expected: collection fails for the missing tool.

- [ ] **Step 3: Implement deterministic selection**

Choose the latest pair `T1 < T2 <= now` for which every blocking source has complete manifests at both cutoffs and at least one controlling source artifact/inventory fingerprint changes. Bind exact source refs and delta IDs. Do not manufacture a source change or use a synthetic fixture for live acceptance.

- [ ] **Step 4: Run selection in read-only mode**

Run: `python3 -m tools.hk_v1_select_acceptance_cutoffs --source-root var/hk-v1/vault --output var/hk-v1/acceptance/cutoffs.json`

Expected: one authentic complete pair or exact `AUTHENTIC_CHANGE_NOT_FOUND`. If no pair exists, continue scheduled observation until one exists; do not weaken the gate.

- [ ] **Step 5: Freeze and review the cutoff evidence**

Read back the output and every referenced source manifest. Record T1/T2, source fingerprints, and changed source IDs in `.agent/WORKING_STATE.md`. This is read-only and performs no external call.

### Task 4: Build, review, and automatically promote the T1 baseline

**Files:**
- Runtime evidence only under: `var/hk-v1/acceptance/t1/`
- Modify after observed result: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: frozen T1 cutoff, current admitted source/model/target profiles, and exact external action authority.
- Produces: first approved complete T1 Serving State and protected index.

- [ ] **Step 1: Stop and confirm exact live action authority**

Confirm source access, model calls, embeddings, the exact Pinecone project/index prefix, backup writes, local SQL writes/migrations, and Serving-State activation are authorized for the bounded T1 run. Confirm the maximum expected provider cost from preflight.

- [ ] **Step 2: Enqueue the T1 common-cutoff baseline and wait for `PROPOSAL_READY`**

Run:

`python3 -m tools.hk_v1_live_cycle --kind BASELINE --cutoff-file var/hk-v1/acceptance/cutoffs.json --cutoff-key baseline_cutoff --matrix packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json --mode preflight`

After the preflight passes and the exact action authority is current, run the
same command with `--mode enqueue`. Expected: complete source read-back, five
releases, traceability, compact evaluation, desired state, recovery readiness,
and one manifest-last proposal. Any blocker stops before Review.

- [ ] **Step 3: Present the proposal and wait for local user Approval**

Open the loopback Review application, verify all report sections and profiles/cost/rollback readiness, and let the proposal wait without a second command. The user approves or rejects the whole package. Rejection ends this attempt; drift creates a new proposal.

- [ ] **Step 4: Observe automatic promotion and full read-back**

Expected after Approval: Promotion claims the approved row, consumes Approval, embeds, builds the complete T1 index, enumerates every record, compares every vector/payload, verifies both backups, and activates the T1 Serving State. No manual promotion command is issued.

- [ ] **Step 5: Capture T1 evidence and pre-reboot health**

Run: `python3 -m tools.hk_v1_live_admission --evidence-root var/hk-v1/acceptance --output var/hk-v1/acceptance/pre-reboot-report.json`

Expected: `NOT_ADMITTED` only because T2 rollback/reboot/scheduled-cycle evidence is absent. Record T1 release/inventory/index/state/approval/execution/backup fingerprints and external effects in `.agent/WORKING_STATE.md`.

### Task 5: Reboot with T1 current and run the scheduled T2 changed cycle

**Files:**
- Runtime evidence only under: `var/hk-v1/acceptance/t2/`
- Modify after observed result: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: current T1 state, frozen T2 cutoff, installed timers, and reboot/external-action authority.
- Produces: post-reboot healthy T1 stack and a scheduled T2 proposal waiting for Approval.

- [ ] **Step 1: Stop and confirm exact reboot authority**

Confirm reboot of this Ubuntu machine and continued authorized source/provider operations. Verify no promotion or source work is actively mutating state before reboot.

- [ ] **Step 2: Reboot and verify T1 continuity**

After boot, require systemd target, five applications, SQL, both schedulers, vaults, proxies, telemetry, Review authentication, timers, current T1 Serving State, protected T1 index, and durable queue health. No manual replay command should be necessary.

- [ ] **Step 3: Let the ordinary observation timer enqueue T2**

Use the installed timer path, not a direct pipeline command. The scheduled cycle must autonomously discover the authentic T1-to-T2 source delta, build complete replacements for affected scopes, reuse exact unchanged releases, pass compact evaluation, and register one proposal.

- [ ] **Step 4: Verify the proposal waits safely**

Leave it unapproved across at least one Promotion-worker poll and one application restart. Expected: zero embedding/Pinecone calls while waiting, proposal remains visible, and current state remains T1. If any validity predicate drifts, the proposal invalidates and the scheduler builds a fresh one.

- [ ] **Step 5: Approve T2 locally and observe automatic promotion**

The user reviews and approves the whole T2 proposal. Expected: no second command; Promotion builds/read-backs/backups the complete T2 index and activates T2. Record schedule invocation, wait duration, Approval, execution, target, backup, and state-transition evidence.

### Task 6: Prove exact rollback to T1 and restoration to T2

**Files:**
- Runtime evidence only under: `var/hk-v1/acceptance/rollback/`
- Modify after observed result: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: exact T2 manifest, predecessor T1 state, protected T1/T2 targets/backups, and rollback authority.
- Produces: verified T1 rollback followed by verified T2 restoration.

- [ ] **Step 1: Stop and confirm exact rollback/restoration authority**

Confirm mutation of only the Management Register Serving State from T2 to declared predecessor T1 and back to T2. No index deletion, broad selector, Ask.Legal routing, or source/provider call is needed.

- [ ] **Step 2: Execute manifest-declared reverse-state operation**

Expected: compare-and-set succeeds only from exact T2; current state becomes T1; coverage and target refs match T1; complete T1 index remains readable.

- [ ] **Step 3: Verify rollback read-back**

Enumerate current Serving State and protected target inventory, compare fingerprints/counts, retrieve compact golden records, and read recovery evidence. Any mismatch fails rollback proof.

- [ ] **Step 4: Restore exact T2**

Execute the approved exact forward state operation from T1 to the already verified/protected T2 candidate, then repeat state, inventory, retrieval, coverage, and backup verification.

- [ ] **Step 5: Preserve rollback/restoration receipts**

Record exact T1/T2 state IDs, compare-and-set receipts, read-back counts/fingerprints, and no-routing/no-deletion evidence in `.agent/WORKING_STATE.md`.

### Task 7: Prove scheduled no change and next-cycle health

**Files:**
- Runtime evidence only under: `var/hk-v1/acceptance/schedules/`
- Modify after observed result: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: current T2 Serving State and installed ordinary timer.
- Produces: one genuine scheduled no-change result and one following healthy schedule result.

- [ ] **Step 1: Let the next due timer run with no controlling source delta**

Expected: complete source observation and read-back pass; fingerprints equal T2; cycle returns `NO_CHANGE`; model calls, embeddings, proposal creation, and Pinecone mutations are all zero.

- [ ] **Step 2: Verify no-change accounting**

Read the cycle report and assert every due source has a complete terminal outcome, no missing/gap blocking sources exist, and the report explicitly binds current T2 state and source policy.

- [ ] **Step 3: Observe the following scheduler invocation**

Expected: timer remains active, durable command is accepted or exact-replayed, no stuck lease exists, telemetry is fresh, disk/resource bounds are healthy, and the current T2 state remains verified.

- [ ] **Step 4: Run host and recovery checks**

Run the host collector/admission and scheduled recovery proof. Expected: Gate F remains passing after real baseline/update activity.

- [ ] **Step 5: Preserve scheduled-cycle evidence**

Record timer invocation IDs, due source counts, no-change proof, zero external provider mutations, next-cycle status, host admission fingerprint, and recovery proof in `.agent/WORKING_STATE.md`.

### Task 8: Issue `V1_ADMITTED`, write the operator runbook, and stop

**Files:**
- Create: `docs/runbooks/HK_V1_LOCAL_OPERATOR.md`
- Modify: `.agent/ROADMAP.md`
- Modify: `.agent/WORKING_STATE.md`
- Modify: `.agent/HANDOFF.md`

**Interfaces:**
- Consumes: complete immutable Gate A–G evidence.
- Produces: final admission report, operator runbook, and handoff-ready project state.

- [ ] **Step 1: Run all focused acceptance tests and complete shipping gate**

Run: `python3 -m pytest tools/tests/test_hk_v1_live_admission.py apps/control-plane/tests/test_hk_v1_live_cycle.py -q`

Expected: all acceptance tests pass.

Run: `python3 -m tools.dev_test --uv /home/docpro/.local/bin/uv --node /home/docpro/.local/bin/node`

Expected: Pyright 0, Ruff clean, architecture/contracts/reproducibility pass, and the complete suite passes except documented intentional opt-in skips.

- [ ] **Step 2: Evaluate real immutable evidence**

Run: `python3 -m tools.hk_v1_live_admission --evidence-root var/hk-v1/acceptance --output var/hk-v1/acceptance/final-report.json`

Expected: exit 0 and exact terminal result `V1_ADMITTED`.

- [ ] **Step 3: Write the concise local operator runbook**

Document how to view health, wait for/review/approve/reject a proposal, recognize invalidation, verify current Serving State/index, inspect source failures, run read-only admission, perform authorization-bound rollback/restoration, recover SQL/vault/scheduler, rotate credentials, and identify the exact actions that still require explicit authority. State the V1 scope and exclusions prominently.

- [ ] **Step 4: Update canonical continuity from observed evidence**

Mark Gates A–G and HKV1-0 through HKV1-10 complete only if the final report passes. Record exact current state/index/cutoff/profile/evaluation/backup/rollback/host/report fingerprints, verification commands/results, external actions, and remaining post-V1 work. Keep Principles deferred.

- [ ] **Step 5: Stop at the final checkpoint gate**

Run: `git status --short --branch`

Expected: only planned code/docs/continuity changes; authentic corpora, secrets, runtime reports, and backups remain ignored under `var/`. Request explicit commit and push authorization separately. Do not claim V1 complete unless the observed final report is exactly `V1_ADMITTED`.
