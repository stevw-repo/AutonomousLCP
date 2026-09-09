# Authentic HKEX Main Board and GEM Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build separate complete current Main Board and GEM Listing Rule releases from authentic admitted HKEX products.

**Architecture:** Map the Plan 2 five-role HKEX inventory into a source-faithful component tree, then apply the existing source-neutral inventory, continuity, effective-state, record-boundary, English rendering, partition, coverage, and identity rules. Deterministic code owns board membership and legal consequences; Plan 6 supplies change-gated semantic decisions only when the accepted rules require them.

**Tech Stack:** Python 3.14.7, existing HKEX rulebook 0.14.0 lineage and 284-case conformance suite, strict HTML/PDF/document extraction, `asklegal_corpus`, Management Register identity ports, Pytest.

**Spec:** `docs/design/HK_V1_LIVE_EXECUTION_SPEC.md`

## Global Constraints

- Main Board and GEM remain separate release scopes and applicability branches.
- The exact component universe includes Chapters, rules, notes, appendices, Practice Notes, Regulatory Forms, and Fees Rules.
- The serving record is source-faithful English; Traditional Chinese is discrepancy and compact cross-language evaluation evidence.
- Catalogue pages bound product families but cannot prove component wording or completeness alone.
- Future, transitional, historical, withdrawn, uncertain, and quarantined branches remain accounted for outside ordinary current search.
- No broad HKEX website crawl is allowed.
- This plan performs no model/provider call; Plan 6 composes admitted change-gated semantic work.

## Dependency and exit contract

Depends on Plan 2's complete five-role HKEX source cycle. Produces:

```python
def build_hkex_releases(
    request: HKEXReleaseRequest,
    evidence: HKEXEvidenceReader,
    semantic: HKEXSemanticDecisionReader,
    identities: HKEXIssuedIdentities,
) -> HKEXReleaseResult: ...
```

Plan 6 consumes authentic record shapes and the compact HKEX golden slice. Plan 7 consumes separate Main and GEM `CorpusRelease` objects plus traceability.

## File structure

- Create `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_authentic.py` — five-role evidence-bundle decoder and source tree.
- Create `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_records.py` — board-complete record candidates and traceability seeds.
- Create `apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_regulatory_release.py` — application-owned corpus release and traceability builder.
- Create `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_semantic.py` — change-gated request and strict decision coordinator.
- Modify existing `hk_regulatory_inventory.py`, `hk_regulatory_continuity.py`, `hk_regulatory_effective_state.py`, `hk_regulatory_english.py`, and `hk_regulatory_record_identity.py` only where authentic mapping exposes a missing source-neutral rule.
- Modify `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_pipeline.py` — HKEX processing activity.
- Modify the generated package only through `tools/build_hk_regulatory_rulebook.py` and its attestation builder.

---

### Task 1: Decode complete five-role authentic HKEX evidence

**Files:**
- Create: `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_authentic.py`
- Create: `packages/legal-desks/tests/test_hk_regulatory_authentic.py`

**Interfaces:**
- Consumes: one complete Plan 2 HKEX source-cycle manifest and all addressed artifacts.
- Produces: `HKEXAuthenticEvidenceBundle` through `load_hkex_authentic_bundle()`.

- [ ] **Step 1: Write failing role and board-completeness tests**

```python
def test_bundle_requires_all_five_source_roles() -> None:
    with pytest.raises(HKEXEvidenceError, match="SOURCE_ROLE_MISSING"):
        load_hkex_authentic_bundle(bundle_ref_without("HK-REG-HKEX-FEES-RULES"), reader())


def test_required_english_artifact_cannot_be_replaced_by_chinese_copy() -> None:
    with pytest.raises(HKEXEvidenceError, match="REQUIRED_ENGLISH_ARTIFACT_MISSING"):
        load_hkex_authentic_bundle(chinese_only_main_rulebook_ref(), reader())
```

- [ ] **Step 2: Run and verify the authentic adapter is absent**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_authentic.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement strict evidence bundle loading**

```python
@dataclass(frozen=True, slots=True)
class HKEXEvidenceMember:
    reference: str
    fingerprint: str
    byte_length: int
    role: str
    board: str


class HKEXEvidenceReader(Protocol):
    def read_exact(self, member: HKEXEvidenceMember) -> bytes: ...


@dataclass(frozen=True, slots=True)
class HKEXAuthenticEvidenceBundle:
    observation_cutoff: str
    catalogue: HKEXEvidenceMember
    consolidated_rulebooks: tuple[HKEXEvidenceMember, ...]
    fees_rules: tuple[HKEXEvidenceMember, ...]
    regulatory_forms: tuple[HKEXEvidenceMember, ...]
    final_updates: tuple[HKEXEvidenceMember, ...]
    bundle_fingerprint: str
```

Re-read every artifact, validate role/board/language/media type/fingerprint, reject unknown roles and hostile content, and require every declared inventory member to appear exactly once.

- [ ] **Step 4: Run authentic and source-decision tests**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_authentic.py packages/legal-desks/tests/test_hk_regulatory_conformance_source.py -q`

Expected: all tests pass with complete source role and board accounting.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_authentic.py packages/legal-desks/tests/test_hk_regulatory_authentic.py`

Expected: an inert, exact evidence adapter. Commit only with exact user authorization.

### Task 2: Construct the authentic board-isolated component tree

**Files:**
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_authentic.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_inventory.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_continuity.py`
- Modify: `packages/legal-desks/tests/test_hk_regulatory_authentic.py`
- Test: `packages/legal-desks/tests/test_hk_regulatory_inventory.py`
- Test: `packages/legal-desks/tests/test_hk_regulatory_continuity.py`

**Interfaces:**
- Consumes: `HKEXAuthenticEvidenceBundle`.
- Produces: separate `HKEXBoardSourceTree` values and continuity decisions against the prior approved tree.

- [ ] **Step 1: Write failing structure and continuity tests**

```python
def test_authentic_tree_accounts_for_every_required_component_kind() -> None:
    trees = build_hkex_source_trees(valid_bundle())
    assert {node.kind for tree in trees for node in tree.nodes} >= {
        "CHAPTER",
        "RULE",
        "NOTE",
        "APPENDIX",
        "PRACTICE_NOTE",
        "FORM",
        "FEES_RULE",
    }


def test_title_similarity_cannot_move_component_between_boards() -> None:
    decision = decide_hkex_component_continuity(main_component(), similar_gem_component())
    assert decision.result == "NO_CONTINUITY"
```

- [ ] **Step 2: Run and observe authentic tree construction is missing**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_authentic.py packages/legal-desks/tests/test_hk_regulatory_continuity.py -q`

Expected: the new tests fail.

- [ ] **Step 3: Implement source-faithful tree mapping**

```python
@dataclass(frozen=True, slots=True)
class HKEXBoardSourceTree:
    board: Literal["MAIN", "GEM"]
    components: tuple[HKEXAuthenticComponent, ...]
    source_inventory_fingerprint: str
    tree_fingerprint: str


def build_hkex_source_trees(
    bundle: HKEXAuthenticEvidenceBundle,
) -> tuple[HKEXBoardSourceTree, HKEXBoardSourceTree]: ...
```

Preserve official labels, parent/child order, cross-references, tables, fee cells, Form fields, update mappings, applicability facts, and English/Chinese counterpart refs. Continuity requires official identity/evidence, never text similarity alone.

- [ ] **Step 4: Run inventory and continuity suites**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_authentic.py packages/legal-desks/tests/test_hk_regulatory_inventory.py packages/legal-desks/tests/test_hk_regulatory_continuity.py -q`

Expected: all tests pass for exact membership, missing child, board isolation, split, merge, and re-identification cases.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_authentic.py packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_inventory.py packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_continuity.py packages/legal-desks/tests`

Expected: authentic mapping plus narrowly required source-neutral corrections. Commit only with exact user authorization.

### Task 3: Decide prevailing applicability state and transitions

**Files:**
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_effective_state.py`
- Create: `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_semantic.py`
- Create: `packages/legal-desks/tests/test_hk_regulatory_authentic_state.py`

**Interfaces:**
- Consumes: board source tree, final-update evidence, cutoff, prior approved state, and optional admitted semantic decision.
- Produces: one `HKEXComponentStateDecision` per applicability branch.

- [ ] **Step 1: Write failing future, transitional, and uncertainty tests**

```python
def test_future_branch_stays_waiting_before_effective_date() -> None:
    decision = decide_authentic_hkex_state(future_update(), cutoff="2026-08-25")
    assert decision.state == "WAITING_ROOM"


def test_unresolved_transition_does_not_replace_current_branch() -> None:
    decision = decide_authentic_hkex_state(conflicting_transition(), cutoff="2026-08-25")
    assert decision.state == "QUARANTINE"
    assert decision.keep_prior_current is True
```

- [ ] **Step 2: Run and observe missing authentic-state coordinator**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_authentic_state.py -q`

Expected: collection fails for the new test module's imports.

- [ ] **Step 3: Implement deterministic-first state coordination**

```python
@dataclass(frozen=True, slots=True)
class HKEXFinalUpdate:
    update_id: str
    board: Literal["MAIN", "GEM"]
    effective_date: str
    condition_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKEXPriorComponentState:
    component_id: str
    branch_id: str
    state: str
    decision_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXComponentStateDecision:
    component_id: str
    branch_id: str
    state: Literal["CURRENT", "WAITING_ROOM", "HISTORY", "QUARANTINE"]
    keep_prior_current: bool
    reason_code: str
    evidence_refs: tuple[str, ...]


def decide_authentic_hkex_state(
    component: HKEXAuthenticComponent,
    updates: tuple[HKEXFinalUpdate, ...],
    prior: HKEXPriorComponentState | None,
    *,
    cutoff: str,
    semantic_decision: AdmittedSemanticDecision | None = None,
) -> HKEXComponentStateDecision: ...
```

Use semantic analysis only when the accepted change gate says deterministic facts cannot resolve wording, conditions, or mappings. Unknown, malformed, or absent semantic output remains unresolved; it never selects a prevailing branch.

- [ ] **Step 4: Run state and source-neutral conformance suites**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_authentic_state.py packages/legal-desks/tests/test_hk_regulatory_effective_state.py packages/legal-desks/tests/test_hk_regulatory_conformance_state.py -q`

Expected: all tests pass with provider execution disabled.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_effective_state.py packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_semantic.py packages/legal-desks/tests/test_hk_regulatory_authentic_state.py`

Expected: exact state consequences and a disabled semantic boundary. Commit only with exact user authorization.

### Task 4: Render and partition authentic English records

**Files:**
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_english.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_record_identity.py`
- Create: `packages/legal-desks/tests/test_hk_regulatory_authentic_rendering.py`

**Interfaces:**
- Consumes: current component branches, governing ancestors/definitions, tables, fees, Forms, and source measurements.
- Produces: canonical English record candidates with exact source-element closure and identity consequences.

- [ ] **Step 1: Write failing completeness and language tests**

```python
def test_table_record_preserves_every_cell_and_governing_label() -> None:
    record = render_authentic_hkex_record(table_component())
    assert set(record.source_element_ids) == set(table_component().all_source_element_ids)
    assert "Table 2" in record.text


def test_chinese_text_cannot_become_serving_text() -> None:
    with pytest.raises(HKEXRenderingError, match="SERVING_LANGUAGE_NOT_ENGLISH"):
        render_authentic_hkex_record(chinese_component())
```

- [ ] **Step 2: Run and observe missing authentic rendering entry point**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_authentic_rendering.py -q`

Expected: collection fails or the new entry point is absent.

- [ ] **Step 3: Implement authentic rendering through existing canonical rules**

```python
@dataclass(frozen=True, slots=True)
class HKEXGoverningContext:
    ancestor_component_ids: tuple[str, ...]
    definition_component_ids: tuple[str, ...]
    cross_reference_ids: tuple[str, ...]


def render_authentic_hkex_record(
    component: HKEXAuthenticComponent,
    context: HKEXGoverningContext,
) -> HKEXEnglishRecordResult: ...
```

Retain minimum governing context and exact referring words; keep authority note outside text and embedding input. Partition only at accepted official child boundaries after measuring the actual English labels and six-field metadata. Quarantine a unit that cannot fit without an arbitrary cut.

- [ ] **Step 4: Run rendering, partition, and identity suites**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_authentic_rendering.py packages/legal-desks/tests/test_hk_regulatory_english.py packages/legal-desks/tests/test_hk_regulatory_conformance_rendering.py packages/legal-desks/tests/test_hk_regulatory_conformance_partition.py packages/legal-desks/tests/test_hk_regulatory_record_identity.py -q`

Expected: all rendering/partition/identity tests pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_english.py packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_record_identity.py packages/legal-desks/tests/test_hk_regulatory_authentic_rendering.py`

Expected: source-faithful English output only. Commit only with exact user authorization.

### Task 5: Build separate complete Main and GEM releases

**Files:**
- Create: `packages/legal-desks/src/asklegal_legal_desks/hk_regulatory_records.py`
- Create: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_regulatory_release.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/__init__.py`
- Create: `packages/legal-desks/tests/test_hk_regulatory_records.py`
- Create: `apps/legal-processing-worker/tests/test_hk_regulatory_release.py`

**Interfaces:**
- Consumes: authentic component trees, state decisions, rendered records, prior releases, and register-issued identities.
- Produces: infrastructure-neutral `HKEXRecordCandidate` values and component accounting from the legal desk, then an application-owned `HKEXReleaseResult` with Main/GEM `CorpusRelease` objects and traceability.

- [ ] **Step 1: Write failing board and component-accounting tests**

```python
def test_release_builder_emits_exactly_main_and_gem() -> None:
    result = build_hkex_releases(valid_request(), evidence(), semantic(), issued_hkex_identities())
    assert tuple(release.scope_id for release in result.releases) == (
        "HK-REG-HKEX-GEM",
        "HK-REG-HKEX-MAIN",
    )


def test_every_source_component_has_one_terminal_disposition() -> None:
    result = build_hkex_releases(valid_request(), evidence(), semantic(), issued_hkex_identities())
    assert result.component_count == result.disposition_count
    assert result.unaccounted_component_ids == ()
```

- [ ] **Step 2: Run and verify the release builder is absent**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_records.py apps/legal-processing-worker/tests/test_hk_regulatory_release.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement complete per-board release construction**

```python
@dataclass(frozen=True, slots=True)
class HKEXReleaseRequest:
    observation_cutoff: str
    source_inventory_fingerprint: str
    prior_main_release_id: str
    prior_gem_release_id: str


class HKEXSemanticDecisionReader(Protocol):
    def state_decision(self, component_id: str) -> AdmittedSemanticDecision | None: ...


@dataclass(frozen=True, slots=True)
class HKEXRecordCandidate:
    record_id: str
    board: Literal["MAIN", "GEM"]
    text: str
    source: str
    authority_note: str
    source_element_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKEXReleaseResult:
    releases: tuple[CorpusRelease, CorpusRelease]
    traceability_entries: tuple[TraceabilityEntry, ...]
    component_count: int
    disposition_count: int
    unaccounted_component_ids: tuple[str, ...]
    waiting_component_ids: tuple[str, ...]
    historical_component_ids: tuple[str, ...]
    quarantine_component_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKEXIssuedIdentities:
    component_ids: tuple[tuple[str, str], ...]
    legal_location_ids: tuple[tuple[str, str], ...]
    search_record_ids: tuple[tuple[str, str], ...]
    successor_record_ids: tuple[tuple[str, str], ...]
```

The legal desk requires separate board ownership, complete source closure, exact state, identity continuity, and already issued identities while returning candidates without importing `asklegal_corpus`. The application maps candidates to six-field `ServingRecord` values, computes payload fingerprints, and builds releases/traceability. Reuse unchanged releases or records only under exact continuity; the processing application obtains required successor IDs from the Management Register and changes create complete replacements.

- [ ] **Step 4: Run release, coverage, identity, and corpus suites**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_records.py apps/legal-processing-worker/tests/test_hk_regulatory_release.py packages/legal-desks/tests/test_hk_regulatory_conformance_coverage.py packages/legal-desks/tests/test_hk_regulatory_conformance_identity.py packages/corpus/tests/test_m6_corpus.py -q`

Expected: all tests pass for complete, empty, blocked-board, unchanged, changed, waiting, and quarantine cases.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/legal-desks apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_regulatory_release.py apps/legal-processing-worker/tests/test_hk_regulatory_release.py packages/corpus/tests/test_m6_corpus.py`

Expected: exactly two complete release outputs and traceability. Commit only with exact user authorization.

### Task 6: Compose restart-safe HKEX processing with semantic calls disabled

**Files:**
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_pipeline.py`
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_infrastructure.py`
- Create: `apps/legal-processing-worker/tests/test_v1_hkex_pipeline.py`

**Interfaces:**
- Consumes: source-cycle ref, cutoff, prior approved releases, identity ports, and disabled/admitted semantic runner selected by Plan 6.
- Produces: immutable tree/state/render/release artifacts and one terminal report.

- [ ] **Step 1: Write failing change-gate and replay tests**

```python
def test_unchanged_hkex_cycle_makes_no_semantic_request() -> None:
    infrastructure = recording_infrastructure()
    result = process_hkex(context(), unchanged_instruction(), infrastructure)
    assert result.reused_release_count == 2
    assert infrastructure.semantic_requests == ()


def test_unresolved_changed_component_fails_when_semantic_capability_disabled() -> None:
    with pytest.raises(ProcessingError, match="SEMANTIC_CAPABILITY_DISABLED"):
        process_hkex(context(), unresolved_change_instruction(), disabled_infrastructure())
```

- [ ] **Step 2: Run and observe the HKEX activity is absent**

Run: `python3 -m pytest apps/legal-processing-worker/tests/test_v1_hkex_pipeline.py -q`

Expected: collection fails or lacks `process_hkex()`.

- [ ] **Step 3: Implement change-gated orchestration**

```python
def process_hkex(
    context: ActivityContext,
    payload: object,
    infrastructure: V1LegalProcessingInfrastructure,
) -> object: ...
```

Reuse both prior releases on complete no change. For changed products, parse the complete affected board tree, create semantic work only for unresolved accepted task kinds, re-read all results, and build a complete board replacement. Partial writes remain incomplete and replay-safe.

- [ ] **Step 4: Run worker, HKEX, and architecture suites**

Run: `python3 -m pytest apps/legal-processing-worker/tests/test_v1_hkex_pipeline.py packages/legal-desks/tests -k 'hk_regulatory' -q`

Expected: all focused tests pass with provider composition disabled.

Run: `python3 -m pytest tools/tests/test_architecture_spike.py -q`

Expected: package/application boundaries pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- apps/legal-processing-worker`

Expected: restart-safe, change-gated HKEX activity. Commit only with exact user authorization.

### Task 7: Generate source-ready HKEX admission evidence

**Files:**
- Modify: `tools/build_hk_regulatory_rulebook.py`
- Modify: `tools/build_hk_regulatory_attestation.py`
- Modify through generators: `packages/legal-desks/src/asklegal_legal_desks/_hk_regulatory_package/`
- Create: `packages/legal-desks/tests/test_hk_regulatory_source_readiness.py`
- Modify: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: authentic complete component inventories/trees, all 284 source-neutral cases, build-compatibility attestation, and compact golden slice.
- Produces: `SOURCE_READY_PENDING_MODEL_ADMISSION` for both boards with exact model/baseline blockers.

- [ ] **Step 1: Write the failing source-readiness test**

```python
def test_hkex_package_is_source_ready_for_both_boards() -> None:
    package = load_hk_regulatory_rulebook()
    assert package.readiness.state == "SOURCE_READY_PENDING_MODEL_ADMISSION"
    assert set(package.readiness.scope_ids) == {"HK-REG-HKEX-MAIN", "HK-REG-HKEX-GEM"}
    assert package.readiness.authentic_component_inventory_refs
    assert package.readiness.blocker_codes == (
        "MODEL_PROFILE_NOT_ADMITTED",
        "BASELINE_RELEASES_INCOMPLETE",
    )
```

- [ ] **Step 2: Run and confirm current authentic readiness is false**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_regulatory_source_readiness.py -q`

Expected: FAIL because the current package has no authentic HKEX tree.

- [ ] **Step 3: Generate readiness from verified admission input**

Read one canonical ignored `var/` admission result, re-read all exact evidence refs, validate both board inventories and the existing external build attestation, emit only hashes/counts/refs, and add `--check` for read-only generated-byte comparison. Keep `NOT_READY` if any authentic member or board is incomplete.

- [ ] **Step 4: Rebuild twice and run the complete HKEX sweep**

Run: `python3 -m tools.build_hk_regulatory_rulebook --check`

Run it a second time.

Expected: byte-identical generated trees.

Run: `python3 -m pytest packages/legal-desks/tests -k 'hk_regulatory' -q`

Expected: all HKEX source-neutral, authentic, release, package, and attestation tests pass.

- [ ] **Step 5: Run the complete shipping gate and stop**

Run: `python3 -m tools.dev_test --uv /home/docpro/.local/bin/uv --node /home/docpro/.local/bin/node`

Expected: complete shipping gate passes. Record source cutoff, both inventory/release-readiness fingerprints, and remaining Plan 6 blockers in `.agent/WORKING_STATE.md`. Request explicit commit authorization before creating the Plan 5 checkpoint.
