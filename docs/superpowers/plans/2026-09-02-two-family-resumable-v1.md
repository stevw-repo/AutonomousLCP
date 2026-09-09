# Two-Family Resumable Hong Kong V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the smallest honest V1 containing complete Hong Kong Legislation and post-1-July-1997 binding-court Case propositions, with resumable acquisition, Azure model and embedding work, Pinecone serving, retained local human Approval, and continuous local operation.

**Architecture:** Replace family-sized serial capture attempts with one hash-chained local acquisition journal, deterministic work-item identities, and a per-host worker pool capped at four active requests. Reuse verified HKeL and Judiciary evidence without redownload, complete Legislation and Cases through separate resumable stages, then reconcile the existing model, embedding, Pinecone, Review, Approval, promotion, and Ubuntu acceptance surfaces to exactly two included families.

**Tech Stack:** Python 3.14, frozen dataclasses and strict JSON contracts, filesystem-backed immutable local state, `concurrent.futures`, existing official-source connectors, Azure OpenAI profile adapters, Pinecone promotion adapters, pytest, Ruff, Pyright, repository boundary and architecture checks.

**Spec:** `docs/superpowers/specs/2026-09-02-two-family-resumable-acquisition-design.md`

## Global Constraints

- V1 includes only all three accepted Hong Kong Legislation scopes and `HK-CASE-BINDING-POST-1997`.
- HKEX remains preserved but is excluded from V1 scheduling, admission, proposals, promotion composition, and acceptance.
- Authority 808 and its interrupted HKEX output remain dormant and must not be resumed, reinterpreted, or deleted by this plan.
- At most four requests may be active concurrently per official host.
- Successful work survives interruption and isolated retryable outages; incomplete work is never reported as complete or no-change.
- Every newly captured body is content-addressed and read back before `CAPTURED_VERIFIED` is recorded.
- Existing verified HKeL archives and Judiciary pages are imported by exact report/object binding and are not copied or redownloaded merely to seed the journal.
- Azure model output remains strictly schema-validated; embeddings, Pinecone mutation, promotion, and routing remain fail-closed behind their existing exact capability and retained Approval boundaries.
- Routine tasks use focused tests. The complete repository gate runs only after Tasks 6, 8, and 10 unless a focused gate identifies a cross-cutting regression.
- Do not accept terms, enter credentials or personal data, delete Pinecone state, deploy, commit, or push under this plan. Repository checkpoints remain uncommitted unless the user separately requests a commit.

## File structure

- `apps/acquisition-worker/src/asklegal_acquisition_worker/acquisition_journal.py` owns strict journal types, hash chaining, local persistence, replay, and derived checkpoints.
- `apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py` owns deterministic scheduling, four-per-host concurrency, retry availability, and cycle result projection.
- `apps/acquisition-worker/src/asklegal_acquisition_worker/retained_evidence_import.py` owns offline migration of verified historical reports and objects into journal entries.
- `apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py` owns the HKeL/GLD Legislation work graph.
- `apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py` owns year/page enumeration, artifact discovery, and incremental Judiciary work.
- Existing `v1_pipeline.py`, `v1_service.py`, and `hk_v1_due_cycle.py` compose those focused modules; they do not absorb their implementations.
- Existing legal-desk and legal-processing modules consume verified batch manifests and remain the authority for legal interpretation.
- Existing processing, promotion, Review, and Approval modules remain in place; only two-family composition and missing real adapters are changed.

---

### Task 1: Reconcile the canonical V1 scope to Legislation and Cases

**Files:**
- Modify: `packages/reporting/src/asklegal_reporting/hk_v1_coverage.py`
- Modify: `packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json`
- Modify: `packages/reporting/src/asklegal_reporting/hk_v1_due_cycle.py`
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py`
- Modify: `apps/control-plane/src/asklegal_control_plane/v1_pipeline.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/package.json`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/_hk_cases_package/package.json`
- Modify: `contracts/package-manifest.json`
- Test: `packages/reporting/tests/test_hk_v1_coverage.py`
- Test: `packages/reporting/tests/test_hk_v1_due_cycle.py`
- Test: `apps/acquisition-worker/tests/test_v1_due_register_integration.py`
- Test: `apps/control-plane/tests/test_v1_due_cycle_control.py`

**Interfaces:**
- Consumes: current issued Coverage Matrix, Legislation register, Cases register, and due-cycle contracts.
- Produces: `included_material_families == ("CASES", "LEGISLATION")`, four required scopes, and explicit `HKEX_REGULATORY_POST_V1` exclusion facts.

- [ ] **Step 1: Add strict failing two-family matrix tests**

```python
def test_v1_matrix_includes_only_legislation_and_cases() -> None:
    matrix = load_hk_v1_coverage_matrix()
    assert tuple(
        sorted({row.material_family for row in matrix.rows if row.technical_state == "ADMITTED"})
    ) == (
        "CASES",
        "LEGISLATION",
    )
    assert "HKEX_REGULATORY_POST_V1" in matrix.explicit_exclusions
```

- [ ] **Step 2: Run the exact RED selection**

Run: `.venv/bin/python -m pytest packages/reporting/tests/test_hk_v1_coverage.py packages/reporting/tests/test_hk_v1_due_cycle.py apps/acquisition-worker/tests/test_v1_due_register_integration.py apps/control-plane/tests/test_v1_due_cycle_control.py -q`

Expected: FAIL because the current matrix and due cycle still require Regulatory/HKEX.

- [ ] **Step 3: Replace required-family constants and matrix rows atomically**

Use exact closed values:

```python
_V1_INCLUDED_MATERIAL_FAMILIES = frozenset({"LEGISLATION", "CASES"})
_V1_REQUIRED_SCOPE_IDS = frozenset(
    {
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-CASE-BINDING-POST-1997",
    }
)
_V1_POSTPONED_EXCLUSIONS = frozenset({"HKEX_REGULATORY_POST_V1"})
```

Keep Regulatory vocabulary parseable for historical reports, but reject it as a current included-family input.

- [ ] **Step 4: Regenerate only derived package and contract fingerprints**

Run these repository-owned generators in order; do not regenerate or delete the preserved HKEX package:

```bash
.venv/bin/python -m tools.build_hk_legislation_rulebook
.venv/bin/python -m tools.build_hk_cases_rulebook
node tools/validate-contracts.mjs --write-manifest
node tools/validate-contracts.mjs
```

- [ ] **Step 5: Run the focused scope gate**

Run: `.venv/bin/python -m pytest packages/reporting/tests/test_hk_v1_coverage.py packages/reporting/tests/test_hk_v1_due_cycle.py apps/acquisition-worker/tests/test_v1_due_register_integration.py apps/control-plane/tests/test_v1_due_cycle_control.py packages/legal-desks/tests/test_rulebook_package.py -q`

Expected: PASS with exactly two included material families and no HKEX due work.

### Task 2: Add the immutable acquisition journal and replayable checkpoint

**Files:**
- Create: `apps/acquisition-worker/src/asklegal_acquisition_worker/acquisition_journal.py`
- Create: `apps/acquisition-worker/tests/test_acquisition_journal.py`
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/v1_infrastructure.py`
- Modify: `apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py`
- Modify: `tools/python_boundary_check.py`

**Interfaces:**
- Consumes: an explicit absolute cycle-state root from `V1AcquisitionInfrastructure`.
- Produces: `WorkItemIdentity`, `JournalTransition`, `AcquisitionJournalEntry`, `AcquisitionCheckpoint`, `LocalAcquisitionJournal.append()`, `LocalAcquisitionJournal.replay()`, and `LocalAcquisitionJournal.write_checkpoint()`.

- [ ] **Step 1: Write failing construction and canonical-ID tests**

```python
def test_work_item_identity_is_stable_and_rejects_fact_drift() -> None:
    item = WorkItemIdentity.issue(
        source_family="CASES",
        source_role="HK-CASE-JUDICIARY-LRS-INVENTORY",
        cycle_id="cyc_20260902_cases",
        observation_cutoff="2026-09-02T10:33:42+08:00",
        procedure_version="JUDICIARY_RESULT_1.0.12",
        locator="https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?page=364",
        stage="LISTING_PAGE",
        parent_id="year-2011",
        media_type="text/html",
        max_bytes=16_777_216,
    )
    assert item.work_item_id.startswith("awi_")
    assert WorkItemIdentity.from_json(item.to_json()) == item
```

- [ ] **Step 2: Define the closed transition and result enums**

```python
class JournalTransition(StrEnum):
    DISCOVERED = "DISCOVERED"
    STARTED = "STARTED"
    CAPTURED_VERIFIED = "CAPTURED_VERIFIED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    CONTRACT_REJECTED = "CONTRACT_REJECTED"
    TERMINAL_UNAVAILABLE = "TERMINAL_UNAVAILABLE"
    ACCOUNTED_EXCLUDED = "ACCOUNTED_EXCLUDED"


class AcquisitionCycleResult(StrEnum):
    COMPLETE = "COMPLETE"
    NO_CHANGE = "NO_CHANGE"
    INCOMPLETE_RETRYABLE = "INCOMPLETE_RETRYABLE"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    EVIDENCE_INTEGRITY_FAILURE = "EVIDENCE_INTEGRITY_FAILURE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
```

- [ ] **Step 3: Implement hash-chained exclusive journal entries**

Each entry body must include `sequence`, `previous_entry_fingerprint`, `work_item`, `transition`, exact transition payload, and its own `fingerprint`. Write with create-exclusive/no-follow semantics, fsync the file and directory, reopen, parse, and compare before returning.

- [ ] **Step 4: Add hostile replay tests**

Cover sequence gaps, predecessor-digest drift, unknown fields, invalid transitions, body/object mismatch, duplicate terminal disposition, symlinked roots, non-regular entries, checkpoint drift, and a checkpoint that omits a journal item.

- [ ] **Step 5: Implement a derived atomic checkpoint**

```python
@dataclass(frozen=True, slots=True)
class AcquisitionCheckpoint:
    cycle_id: str
    through_sequence: int
    journal_head_fingerprint: str
    items: tuple[CheckpointItem, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class CheckpointItem:
    work_item_id: str
    latest_sequence: int
    transition: JournalTransition
    attempt_count: int
    object_ref: str | None
    retry_not_before: str | None
```

`load_checkpoint()` must replay the journal and discard/rebuild any checkpoint whose bytes, head, item states, or fingerprint do not match replay.

- [ ] **Step 6: Run the journal gate**

Run: `.venv/bin/python -m pytest apps/acquisition-worker/tests/test_acquisition_journal.py apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py -q`

Expected: PASS, including interruption after arbitrary sequence numbers and exact replay.

### Task 3: Add the deterministic four-per-host resumable worker pool

**Files:**
- Create: `apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py`
- Create: `apps/acquisition-worker/tests/test_resumable_acquisition.py`
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py`
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/v1_service.py`
- Modify: `apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py`

**Interfaces:**
- Consumes: `LocalAcquisitionJournal`, immutable `ScheduledWorkItem` values, an injected read-only `CaptureTransport`, clock, sleeper, and `CycleBudget`.
- Produces: `ResumableAcquisitionRunner.run() -> AcquisitionCycleReport` with canonical item ordering independent of completion order.

- [ ] **Step 1: Write the exact concurrency RED**

```python
def test_one_host_never_exceeds_four_active_requests() -> None:
    transport = BlockingCountingTransport(item_count=12)
    report = run_items(transport, per_host_limit=4)
    assert transport.maximum_active_by_host == {"legalref.judiciary.hk": 4}
    assert report.result is AcquisitionCycleResult.COMPLETE
```

- [ ] **Step 2: Define scheduler values and protocol**

```python
@dataclass(frozen=True, slots=True)
class ScheduledWorkItem:
    identity: WorkItemIdentity
    priority: tuple[int, int, str]
    host: str
    not_before_monotonic_ns: int


class CaptureTransport(Protocol):
    def capture(self, item: WorkItemIdentity) -> CaptureOutcome: ...


@dataclass(frozen=True, slots=True)
class CaptureOutcome:
    transition: JournalTransition
    status_code: int | None
    media_type: str | None
    final_url: str | None
    body_length: int
    body_fingerprint: str | None
    object_ref: str | None
    failure_code: str | None
    retry_not_before: str | None


@dataclass(frozen=True, slots=True)
class CycleBudget:
    maximum_starts: int
    maximum_retained_bytes: int
    maximum_elapsed_seconds: int
    maximum_redirects: int


@dataclass(frozen=True, slots=True)
class AcquisitionCycleReport:
    cycle_id: str
    result: AcquisitionCycleResult
    item_dispositions: tuple[CheckpointItem, ...]
    request_starts: int
    retained_bytes: int
    journal_head_fingerprint: str
    fingerprint: str
```

- [ ] **Step 3: Implement one queue owner with per-host gates**

Use `ThreadPoolExecutor`; maintain one semaphore and one locked next-start time per exact host. Never let worker completion mutate report order. The scheduler appends `STARTED` before calling transport and appends one closed outcome transition after read-back.

- [ ] **Step 4: Implement retry and cycle-stop projection**

`RETRYABLE_FAILURE` re-enters the queue only when its exact retry policy permits it. Root identity drift, journal/object corruption, authorization failure, and cycle-budget exhaustion stop new dispatch. An isolated outage leaves unrelated queued items runnable and projects `INCOMPLETE_RETRYABLE` if retries remain.

- [ ] **Step 5: Add deterministic-order and interruption tests**

Run the same 20 items with forward, reverse, and random completion timing; require byte-identical report JSON. Interrupt after 7 verified items, replay, and prove those 7 cause zero second-run transport calls.

- [ ] **Step 6: Run the worker gate**

Run: `.venv/bin/python -m pytest apps/acquisition-worker/tests/test_resumable_acquisition.py apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py -q`

Expected: PASS with maximum active count exactly four, deterministic output, and preserved progress.

### Task 4: Import existing verified evidence without network or duplication

**Files:**
- Create: `apps/acquisition-worker/src/asklegal_acquisition_worker/retained_evidence_import.py`
- Create: `apps/acquisition-worker/tests/test_retained_evidence_import.py`
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py`
- Test: `packages/legal-desks/tests/test_hk_legislation_retained.py`
- Test: `tools/tests/test_hk_v1_source_execution.py`

**Interfaces:**
- Consumes: canonical retained source report path, expected report SHA-256, expected authority/binding facts, and a `WorkItemProjection` callback.
- Produces: `RetainedImportReceipt` containing imported count, reused object bytes, journal head, and source report fingerprint.

```python
class WorkItemProjection(Protocol):
    def __call__(self, retained_record: JsonValue) -> WorkItemIdentity: ...


@dataclass(frozen=True, slots=True)
class RetainedImportReceipt:
    source_family: str
    source_report_fingerprint: str
    imported_item_count: int
    reused_object_bytes: int
    journal_head_fingerprint: str
    archive_pairs: int | None
    last_listing: tuple[int, int] | None
```

- [ ] **Step 1: Write an exploding-network import RED**

```python
def test_imports_retained_hkel_and_judiciary_without_transport(tmp_path: Path) -> None:
    transport = ExplodingTransport()
    receipts = import_known_v1_retained_evidence(tmp_path, transport=transport)
    assert transport.calls == []
    assert receipts.hkel.archive_pairs == 3_157
    assert receipts.judiciary.last_listing == (2011, 363)
```

- [ ] **Step 2: Validate the complete retained source graph before journal writes**

Require canonical report bytes, exact stored report hash, authority and execution binding, every referenced object as regular/non-symlink, exact object length/hash, and no logical identity collision. Do not infer facts from directory names.

- [ ] **Step 3: Project verified captures to stable work items**

Emit `DISCOVERED` then `CAPTURED_VERIFIED` entries that bind the original report/object identity and an `imported_from_retained_report` field. Do not copy object bytes; keep the original immutable object reference.

- [ ] **Step 4: Add tamper and idempotence coverage**

Mutate report hash, object hash, object length, authority binding, projection URL, and a prior journal entry. Require pre-write failure. Re-run an exact import and require no new entries and the same receipt.

- [ ] **Step 5: Run the offline import gate**

Run: `.venv/bin/python -m pytest apps/acquisition-worker/tests/test_retained_evidence_import.py packages/legal-desks/tests/test_hk_legislation_retained.py tools/tests/test_hk_v1_source_execution.py -q -k 'retained or import or replay'`

Expected: PASS with zero network effects and no retained-evidence mutation.

### Task 5: Finish resumable Legislation acquisition and authentic release input

**Files:**
- Create: `apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py`
- Create: `apps/acquisition-worker/tests/test_hk_legislation_acquisition.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hkel_legislation.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/gld_gazette.py`
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/gld_session.py`
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_legislation_authentic.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_legislation_events.py`
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_legislation_release.py`
- Test: `packages/legal-desks/tests/test_hk_legislation_authentic.py`
- Test: `packages/legal-desks/tests/test_hk_legislation_events.py`
- Test: `apps/legal-processing-worker/tests/test_hk_legislation_release.py`

**Interfaces:**
- Consumes: verified HKeL journal items, GLD event/artifact items, Basic Law items, publication specifications, and retained structural review issues.
- Produces: `LegislationAcquisitionManifest` and three complete release-scope inputs; no legal-effect inference occurs in acquisition.

- [ ] **Step 1: Write the Legislation work-graph RED**

Require one deterministic graph containing HKeL inventory/archive/spec roles, GLD issue/event artifacts, Editorial Records, verified/assisted copy dispositions, Basic Law/Annex III, and Instruments and Others.

- [ ] **Step 2: Import and reuse unchanged HKeL archives**

Bind the known retained profile (`56` endpoints, `12,858` members, `3,157` bilingual pairs, `7` specs) to journal items. Reparse only archives whose exact archive/spec fingerprint changed.

- [ ] **Step 3: Route GLD discovery and artifacts through the shared runner**

The isolated GLD session emits only admitted discoveries. Artifact captures become normal work items. Session/challenge failure becomes a visible retryable or contract result and cannot erase completed HKeL work.

- [ ] **Step 4: Build strict complete-input projection**

```python
@dataclass(frozen=True, slots=True)
class LegislationAcquisitionManifest:
    cycle_id: str
    observation_cutoff: str
    scope_dispositions: tuple[LegislationScopeDisposition, ...]
    verified_item_refs: tuple[str, ...]
    review_issue_refs: tuple[str, ...]
    journal_head_fingerprint: str
    result: AcquisitionCycleResult
    fingerprint: str


@dataclass(frozen=True, slots=True)
class LegislationScopeDisposition:
    scope_id: str
    required_item_count: int
    verified_item_count: int
    retryable_item_count: int
    rejected_item_count: int
    result: AcquisitionCycleResult
```

The legal-processing worker accepts this manifest only when all three required scopes are complete.

- [ ] **Step 5: Prove incremental change and no-change behavior**

Fixture cycle A imports the retained baseline; fixture cycle B changes one Gazette artifact and one HKeL archive fingerprint; fixture cycle C changes nothing. B must process only changed inputs. C must cause zero model, embedding, proposal, or Pinecone effects.

- [ ] **Step 6: Run the Legislation exit gate**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_hkel_legislation.py packages/source-connectors/tests/test_gld_gazette.py apps/acquisition-worker/tests/test_gld_session.py apps/acquisition-worker/tests/test_hk_legislation_acquisition.py packages/legal-desks/tests/test_hk_legislation_retained.py packages/legal-desks/tests/test_hk_legislation_retained_structure.py packages/legal-desks/tests/test_hk_legislation_authentic.py packages/legal-desks/tests/test_hk_legislation_events.py packages/legal-desks/tests/test_hk_legislation_records.py apps/legal-processing-worker/tests/test_hk_legislation_release.py -q`

Expected: PASS, followed by the complete repository gate because this task completes one family boundary.

### Task 6: Finish resumable Cases enumeration and artifact acquisition

**Files:**
- Create: `apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py`
- Create: `apps/acquisition-worker/tests/test_hk_cases_acquisition.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hk_judiciary.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hk_judiciary_authentic.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hk_cases_source_register.json`
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_case_judgment.py`
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_case_workflow.py`
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_case_release.py`
- Test: `packages/source-connectors/tests/test_hk_judiciary.py`
- Test: `packages/source-connectors/tests/test_hk_judiciary_authentic.py`
- Test: `packages/legal-desks/tests/test_hk_case_judgment.py`
- Test: `apps/legal-processing-worker/tests/test_v1_cases_pipeline.py`

**Interfaces:**
- Consumes: the retained Judiciary listing prefix through 2011/page363, current official year/page grammar, discovered artifact locators, and non-controlling HKLII discrepancy hints.
- Produces: `CasesAcquisitionManifest` containing complete year-shard inventories and verified judgment/artifact references from 1997-07-01 through cutoff.

- [ ] **Step 1: Write year-shard and retained-prefix REDs**

```python
def test_cases_baseline_resumes_after_2011_page_363() -> None:
    plan = build_cases_baseline_plan(retained_prefix=verified_w_prefix())
    assert plan.first_network_item.identity.stage == "LISTING_PAGE"
    assert plan.first_network_item.identity.parent_id == "year-2011"
    assert "page=364" in plan.first_network_item.identity.locator
```

- [ ] **Step 2: Partition the baseline into deterministic year shards**

Each year owns ordered listing pages and exact completion facts. The global runner may interleave years, but a year page cannot skip its required predecessor page and report ordering remains year/page canonical.

- [ ] **Step 3: Create artifact work immediately from verified listing rows**

Generate canonical judgment, correction/reissue, language, translation, alias, and proceeding-identity items. Deduplicate identical captures by locator identity while preserving every listing occurrence.

- [ ] **Step 4: Keep enumeration and artifact workers independent**

One retryable artifact must not stop listing enumeration; one retryable listing page blocks only that year’s completeness. Root/session/result grammar drift stops unsafe descendants before transport.

- [ ] **Step 5: Add current-list and RSS incremental discovery**

Bind exact registered new-judgment/RSS procedures to frequent incremental cycles, plus a periodic full year/listing reconciliation. RSS can discover work but can never prove complete no-change alone.

- [ ] **Step 6: Project complete Case inputs**

```python
@dataclass(frozen=True, slots=True)
class CasesAcquisitionManifest:
    cycle_id: str
    earliest_decision_date: str
    observation_cutoff: str
    year_dispositions: tuple[YearShardDisposition, ...]
    judgment_bundle_refs: tuple[str, ...]
    discrepancy_refs: tuple[str, ...]
    journal_head_fingerprint: str
    result: AcquisitionCycleResult
    fingerprint: str


@dataclass(frozen=True, slots=True)
class YearShardDisposition:
    year: int
    first_in_scope_date: str
    final_page: int
    verified_listing_pages: int
    discovered_judgments: int
    verified_judgments: int
    retryable_items: int
    result: AcquisitionCycleResult
```

- [ ] **Step 7: Run the Cases exit gate**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_hk_judiciary.py packages/source-connectors/tests/test_hk_judiciary_authentic.py apps/acquisition-worker/tests/test_hk_cases_acquisition.py packages/legal-desks/tests/test_hk_case_judgment.py packages/legal-desks/tests/test_hk_case_proposition.py packages/legal-desks/tests/test_hk_case_treatment.py packages/legal-desks/tests/test_hk_case_authority_graph.py packages/legal-desks/tests/test_hk_case_records.py apps/legal-processing-worker/tests/test_v1_cases_pipeline.py apps/legal-processing-worker/tests/test_hk_case_release.py -q`

Expected: PASS, followed by the complete repository gate because both source families are now structurally complete.

### Task 7: Compose complete two-family processing and proposal readiness

**Files:**
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_pipeline.py`
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_infrastructure.py`
- Modify: `apps/control-plane/src/asklegal_control_plane/v1_pipeline.py`
- Modify: `apps/control-plane/src/asklegal_control_plane/proposal.py`
- Modify: `packages/reporting/src/asklegal_reporting/hk_v1_coverage.py`
- Modify: `packages/reporting/src/asklegal_reporting/hk_v1_due_cycle.py`
- Test: `apps/legal-processing-worker/tests/test_v1_legislation_pipeline.py`
- Test: `apps/legal-processing-worker/tests/test_v1_cases_pipeline.py`
- Test: `apps/control-plane/tests/test_hk_v1_live_cycle.py`

**Interfaces:**
- Consumes: complete `LegislationAcquisitionManifest`, complete `CasesAcquisitionManifest`, exact semantic profiles, and immutable evidence refs.
- Produces: one frozen two-family proposal manifest whose completeness fingerprint excludes HKEX and includes all four required scopes.

- [ ] **Step 1: Add a failing partial-family proposal test**

Require proposal construction to reject Legislation-only, Cases-only, incomplete-retryable, stale journal-head, and mismatched cutoff inputs before model or embedding effects.

- [ ] **Step 2: Pipeline verified batches without granting release completeness**

Allow deterministic parsing and model-request preparation for verified batches. Store batch outputs under exact evidence/profile fingerprints. Keep release construction closed until both complete manifests reconcile to one accepted cutoff.

- [ ] **Step 3: Bind the two-family coverage report**

The report must list all three Legislation scopes, one Cases scope, exact exclusions, acquisition journal heads, retryable counts, review issues, and model/embedding capability evidence.

- [ ] **Step 4: Run the proposal-readiness gate**

Run: `.venv/bin/python -m pytest apps/legal-processing-worker/tests/test_v1_legislation_pipeline.py apps/legal-processing-worker/tests/test_v1_cases_pipeline.py apps/control-plane/tests/test_hk_v1_live_cycle.py packages/reporting/tests/test_hk_v1_coverage.py packages/reporting/tests/test_hk_v1_due_cycle.py -q`

Expected: PASS with no proposal from partial acquisition and one exact proposal from complete two-family inputs.

### Task 8: Retain Azure models, embeddings, Pinecone, Review, and Approval

**Files:**
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_pipeline.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/v1_infrastructure.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/real_effects.py`
- Modify: `apps/promotion-worker/src/asklegal_promotion_worker/service.py`
- Modify: `apps/review-api/src/asklegal_review_api/registered_proposals.py`
- Modify: `apps/review-api/src/asklegal_review_api/api.py`
- Modify: `packages/promotion/src/asklegal_promotion/model.py`
- Modify: `packages/promotion/src/asklegal_promotion/remote.py`
- Test: `apps/legal-processing-worker/tests/test_v1_model_profiles.py`
- Test: `apps/promotion-worker/tests/test_v1_serving_profiles.py`
- Test: `apps/promotion-worker/tests/test_v1_approval_to_promotion.py`
- Test: `apps/review-api/tests/test_registered_governance.py`
- Test: `packages/promotion/tests/test_remote_adapters.py`

**Interfaces:**
- Consumes: one frozen complete two-family proposal, admitted Azure semantic and embedding profiles, retained named-human Approval, and an admitted Pinecone target profile.
- Produces: strict model outputs, exact-token embedding receipts, immutable backup, replacement Pinecone target, verified Serving State transition, and rollback receipt.

- [ ] **Step 1: Add a two-family target composition RED**

Require exact proposal members for Legislation and Cases, reject any current HKEX member, and preserve historical HKEX vocabulary only outside the promoted member set.

- [ ] **Step 2: Complete admitted Azure adapter composition**

Use the existing immutable semantic profiles, exact tokenizer, integer budget preflight, strict request/response schemas, and capability receipts. No fallback model, repaired output, or profile drift is accepted.

- [ ] **Step 3: Complete exact embedding and Pinecone replacement effects**

Count exact tokens before Approval consumption or provider effect. Require provider usage equality, target read-back, independent backup verification, and one replacement target. Never delete an existing Pinecone target without the separate deletion authority.

- [ ] **Step 4: Preserve retained local human Approval**

The Review UI shows the four exact scope dispositions, limitations, retryable count zero, model evaluation, retrieval evaluation, target, backup, rollback, and proposal fingerprint. Approval is named, retained, single-use, and invalidated by any input drift.

- [ ] **Step 5: Run the model/promotion exit gate**

Run: `.venv/bin/python -m pytest packages/processing/tests packages/promotion/tests apps/legal-processing-worker/tests/test_v1_model_profiles.py apps/promotion-worker/tests apps/review-api/tests -q`

Expected: PASS, followed by the complete repository gate. No real provider or Pinecone call occurs in this test gate.

### Task 9: Compose continuous Ubuntu operation and live acceptance

**Files:**
- Modify: `tools/hk_v1_live_cycle.py`
- Modify: `tools/hk_v1_live_admission.py`
- Modify: `tools/v1_poc_systemd_units.py`
- Modify: `apps/control-plane/src/asklegal_control_plane/v1_service.py`
- Modify: `packages/observability/src/asklegal_observability/status.py`
- Create: `docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md`
- Test: `tools/tests/test_hk_v1_live_cycle.py`
- Test: `tools/tests/test_hk_v1_live_admission.py`
- Test: `tools/tests/test_v1_poc_systemd_units.py`
- Test: `apps/control-plane/tests/test_v1_schedules.py`
- Test: `packages/observability/tests/test_status.py`

**Interfaces:**
- Consumes: complete source cycles, proposal and Approval state, promotion receipts, due-cycle schedule, and recovery proof.
- Produces: continuous local source/update operation and formal two-family Gate A–G acceptance.

- [ ] **Step 1: Add schedule tests for resumable cycles**

Require an interrupted cycle to resume its exact cycle ID and journal rather than start a competing baseline. Require no HKEX timer or source instruction.

- [ ] **Step 2: Update Gate A–G arithmetic to four scopes/two families**

Keep source completeness, model capability, review, Approval, backup, replacement target, read-back, rollback, restart, and no-change gates. Remove only HKEX as a required V1 member.

- [ ] **Step 3: Add operator-visible progress**

Expose per-family discovered, verified, retryable, rejected, terminal, active, queued, retained-byte, journal-head, and last-progress facts. Status must say `INCOMPLETE_RETRYABLE` rather than a percent-based success claim.

- [ ] **Step 4: Run the operational gate**

Run: `.venv/bin/python -m pytest tools/tests/test_hk_v1_live_cycle.py tools/tests/test_hk_v1_live_admission.py tools/tests/test_v1_poc_systemd_units.py apps/control-plane/tests/test_v1_schedules.py packages/observability/tests/test_status.py -q`

Expected: PASS with exact resume after interruption and no HKEX scheduling.

### Task 10: Prove one complete two-family baseline, update, promotion, rollback, and cleanup

**Files:**
- Modify: `.agent/CONTEXT.md`
- Modify: `.agent/DECISIONS.md`
- Modify: `.agent/ROADMAP.md`
- Modify: `.agent/WORKING_STATE.md`
- Modify: `.agent/HANDOFF.md`
- Modify: `docs/runbooks/HK_V1_TWO_FAMILY_LOCAL_OPERATOR.md`
- Test: complete repository test and static gates

**Interfaces:**
- Consumes: separately authorized source/provider/target actions, one retained local human Approval, and the completed Tasks 1–9.
- Produces: truthful `V1_ADMITTED` only after exact baseline, changed update, no-change, promotion, reboot, rollback, and restoration proofs.

- [ ] **Step 1: Run a fresh authorized Legislation and Cases baseline**

Reuse imported evidence, resume outstanding work, and preserve every successful item. Do not start HKEX. Do not claim completeness while any required item is retryable or rejected.

- [ ] **Step 2: Freeze the complete two-family proposal and obtain retained Approval**

The user reviews the exact local proposal. Only the retained Approval may wake the real promotion worker.

- [ ] **Step 3: Promote, read back, back up, and record Serving State**

Require exact Azure/model/embedding receipts, replacement Pinecone target verification, independent backup verification, and current Serving State bound to the approved proposal.

- [ ] **Step 4: Prove changed update, no-change, reboot recovery, rollback, and restore**

Run one changed cycle, one no-change cycle with zero provider/Pinecone effects, reboot recovery, exact rollback to the first target, and restoration to the second.

- [ ] **Step 5: Archive only verified superseded local evidence and reproducible output**

Create a manifest of candidate paths, sizes, SHA-256 values, modes, and mtimes; copy to the approved secondary disk; verify the destination recursively; then remove only the exact approved source paths. Keep the latest resumable journal, current baseline, required regression fixtures, and all Approval/promotion evidence on the SSD.

- [ ] **Step 6: Run final verification**

Run, in order:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
node_modules/.bin/pyright
.venv/bin/python tools/python_boundary_check.py
.venv/bin/python -m pytest tools/tests/test_architecture_spike.py tools/tests/test_python_boundary_check.py -q
.venv/bin/python -m pytest -q
git diff --check
```

Expected: every command exits `0`; the full suite contains no source, provider, or Pinecone effect unless the exact live acceptance step separately authorized it.

- [ ] **Step 7: Issue the terminal handoff**

Record exact report, proposal, Approval, target, backup, rollback, journal-head, scope, test, and retained-evidence fingerprints. State external effects exactly. Mark `V1_ADMITTED` only if every accepted two-family gate is proved.

## Execution order and review gates

1. Tasks 1–4 establish the shared, offline resumable foundation.
2. Task 5 completes Legislation independently.
3. Task 6 completes Cases independently.
4. Task 7 freezes two-family proposal readiness.
5. Task 8 closes Azure models, embeddings, Pinecone, Review, Approval, and promotion.
6. Tasks 9–10 close continuous local operation and live acceptance.

Each task requires its own strict RED-to-GREEN cycle, focused static checks, diff check, and fresh review before its dependent task begins. No task may convert retryable or missing work into success to save time.
