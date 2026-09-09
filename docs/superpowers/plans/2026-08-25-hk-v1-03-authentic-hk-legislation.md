# Authentic Hong Kong Legislation Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build complete bilingual current-law releases for all three Hong Kong Legislation scopes from authentic admitted HKeL and Gazette evidence.

**Architecture:** Add an authentic-evidence adapter in the legal-desk package that converts vault-addressed XML/XSD/PDF/specification evidence into the existing source-neutral canonical tree, lifecycle, reconstruction, rendering, and partition contracts. A release builder accounts for every inventory member and emits `CorpusRelease` plus complete traceability; the legal-processing worker orchestrates these pure functions and never reads source URLs directly.

**Tech Stack:** Python 3.14.7, standard-library `xml.etree.ElementTree` behind an inert parser that rejects DTD/entity declarations before parsing, existing legal-desk contracts, `asklegal_corpus`, evidence-vault ports, Pytest, strict Pyright and Ruff.

**Spec:** `docs/design/HK_V1_LIVE_EXECUTION_SPEC.md`

## Global Constraints

- Required authentic input is English and Traditional Chinese XML plus exact schema/publication specification and an official verified or admitted assisted copy.
- Publication never implies commencement; uncertainty goes to Waiting Room, Quarantine, or an explicit withheld disposition.
- One serving record aligns both languages for the same Legal Location, Official Version, and operative state.
- Uncommenced and ceased text is not ordinary current-law search content.
- The three release scopes are complete replacements, not deltas.
- Source-neutral fixtures cannot set a real scope to `READY`.
- No external source or model call is part of this plan; it consumes Plan 2 vault evidence.

## Dependency and exit contract

Depends on Plan 2's complete HKeL, GLD, and HKeL-Gazette evidence manifests. Produces:

```python
def build_hk_legislation_release(
    request: HKLegislationReleaseRequest,
    evidence: AuthenticLegislationEvidenceReader,
    identities: HKLegislationIssuedIdentities,
) -> HKLegislationReleaseResult: ...
```

Plan 6 consumes the emitted `ServingRecord` shape and golden records. Plan 7 consumes the three `CorpusRelease` objects and traceability shards.

## File structure

- Create `packages/legal-desks/src/asklegal_legal_desks/hk_legislation_authentic.py` — strict authentic manifest and XML/XSD/specification adapter.
- Create `packages/legal-desks/src/asklegal_legal_desks/hk_legislation_events.py` — publisher, Gazette, editorial, commencement, cessation, correction, and reconstruction event merger.
- Create `packages/legal-desks/src/asklegal_legal_desks/hk_legislation_records.py` — inventory accounting, record candidates, and infrastructure-neutral traceability seeds.
- Create `apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_legislation_release.py` — map admitted legal-desk candidates into `asklegal_corpus` releases and traceability.
- Modify `packages/legal-desks/src/asklegal_legal_desks/__init__.py` — public API.
- Modify `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_pipeline.py` — legislation activity composition.
- Add focused tests under `packages/legal-desks/tests/` and `apps/legal-processing-worker/tests/`.
- Modify the generated `_hk_legislation_package` through `tools/build_hk_legislation_rulebook.py`; do not hand-edit generated package members.

---

### Task 1: Decode one complete authentic legislation evidence bundle

**Files:**
- Create: `packages/legal-desks/src/asklegal_legal_desks/hk_legislation_authentic.py`
- Create: `packages/legal-desks/tests/test_hk_legislation_authentic.py`

**Interfaces:**
- Consumes: immutable references to the Plan 2 attempt manifest and member bytes.
- Produces: `AuthenticLegislationEvidenceBundle` and `load_authentic_legislation_bundle()`.

- [ ] **Step 1: Write the failing bundle-completeness tests**

```python
def test_bundle_requires_matching_bilingual_xml_and_schema() -> None:
    reader = ScriptedEvidenceReader(bundle_members(exclude="TRADITIONAL_CHINESE_XML"))
    with pytest.raises(HKLegislationEvidenceError, match="BILINGUAL_MEMBER_MISSING"):
        load_authentic_legislation_bundle(valid_bundle_ref(), reader)


def test_bundle_reads_back_every_declared_member() -> None:
    reader = ScriptedEvidenceReader(bundle_members())
    bundle = load_authentic_legislation_bundle(valid_bundle_ref(), reader)
    assert reader.read_refs == tuple(member.ref for member in bundle.members)
```

- [ ] **Step 2: Run the tests and verify the module is absent**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_legislation_authentic.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement exact bundle and reader contracts**

```python
@dataclass(frozen=True, slots=True)
class ImmutableEvidenceReference:
    vault: str
    logical_key: str
    version_id: str
    fingerprint: str
    byte_length: int


@dataclass(frozen=True, slots=True)
class EvidenceMember:
    role: str
    reference: ImmutableEvidenceReference


class AuthenticLegislationEvidenceReader(Protocol):
    def read_exact(self, reference: ImmutableEvidenceReference) -> bytes: ...


@dataclass(frozen=True, slots=True)
class AuthenticLegislationEvidenceBundle:
    instrument_id: str
    observation_cutoff: str
    english_xml: EvidenceMember
    traditional_chinese_xml: EvidenceMember
    schemas: tuple[EvidenceMember, ...]
    publication_specifications: tuple[EvidenceMember, ...]
    official_copies: tuple[EvidenceMember, ...]
    editorial_records: tuple[EvidenceMember, ...]
    gazette_events: tuple[EvidenceMember, ...]
    bundle_fingerprint: str
```

Strictly decode the attempt manifest, require exact fingerprints and byte lengths, re-read every member, reject unknown roles, and require matching instrument/version/language facts.

- [ ] **Step 4: Run the authentic-bundle tests**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_legislation_authentic.py -q`

Expected: all tests pass, including tamper, duplicate, missing-member, and wrong-language failures.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/legal-desks/src/asklegal_legal_desks/hk_legislation_authentic.py packages/legal-desks/tests/test_hk_legislation_authentic.py`

Expected: one inert evidence adapter and tests. Commit only with exact user authorization.

### Task 2: Parse authentic XML under the admitted schema/specification profile

**Files:**
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_legislation_authentic.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/hk_canonical_legislation.py`
- Modify: `packages/legal-desks/tests/test_hk_legislation_authentic.py`
- Test: `packages/legal-desks/tests/test_hk_canonical_legislation.py`

**Interfaces:**
- Consumes: `AuthenticLegislationEvidenceBundle`.
- Produces: `AuthenticBilingualInstrument` holding two sealed `CanonicalLanguageTree` objects and one complete `BilingualAlignmentMap`.

- [ ] **Step 1: Write failing namespace, external-entity, and alignment tests**

```python
def test_xml_parser_rejects_external_entities() -> None:
    bundle = valid_bundle(english_xml=XXE_XML)
    with pytest.raises(HKLegislationEvidenceError, match="XML_EXTERNAL_ENTITY_FORBIDDEN"):
        parse_authentic_bilingual_instrument(bundle)


def test_alignment_requires_every_searchable_location_in_both_languages() -> None:
    bundle = valid_bundle(chinese_xml=XML_WITH_MISSING_SECTION_3)
    with pytest.raises(HKLegislationEvidenceError, match="BILINGUAL_ALIGNMENT_INCOMPLETE"):
        parse_authentic_bilingual_instrument(bundle)
```

- [ ] **Step 2: Run the tests and observe the missing parser**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_legislation_authentic.py -q`

Expected: FAIL because `parse_authentic_bilingual_instrument()` is absent.

- [ ] **Step 3: Implement schema-bound inert parsing**

```python
def parse_authentic_bilingual_instrument(
    bundle: AuthenticLegislationEvidenceBundle,
) -> AuthenticBilingualInstrument: ...
```

Disable DTDs, external entities, network resolution, XInclude, and executable content. Validate namespace/schema/profile fingerprints before mapping source nodes to the existing canonical tree draft. Seal each language tree with `seal_canonical_language_tree()`, then validate the alignment map with `parse_bilingual_alignment_map()`.

- [ ] **Step 4: Run parser and canonical-renderer suites**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_legislation_authentic.py packages/legal-desks/tests/test_hk_canonical_legislation.py -q`

Expected: all tests pass, including tables, schedules, formulae, footnotes, images, and bilingual mismatch failures represented by the admitted small fixtures.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/legal-desks/src/asklegal_legal_desks/hk_legislation_authentic.py packages/legal-desks/src/asklegal_legal_desks/hk_canonical_legislation.py packages/legal-desks/tests`

Expected: authentic mapping delegates canonical validation to the existing source-neutral contract. Commit only with exact user authorization.

### Task 3: Merge legal events without inferring legal effect

**Files:**
- Create: `packages/legal-desks/src/asklegal_legal_desks/hk_legislation_events.py`
- Create: `packages/legal-desks/tests/test_hk_legislation_events.py`

**Interfaces:**
- Consumes: parsed publisher state, GLD/HKeL Gazette events, Editorial Records, and accepted reconstruction results.
- Produces: `HKLegislationEventTimeline` and `decide_hk_legislation_state()`.

- [ ] **Step 1: Write failing event-authority tests**

```python
def test_publication_without_commencement_stays_waiting() -> None:
    result = decide_hk_legislation_state(events(publication_only=True), CUTOFF)
    assert result.state == "WAITING_ROOM"
    assert result.reason_code == "COMMENCEMENT_NOT_PROVED"


def test_conflicting_gazette_and_editorial_facts_are_quarantined() -> None:
    result = decide_hk_legislation_state(conflicting_events(), CUTOFF)
    assert result.state == "QUARANTINE"
    assert result.reason_code == "OFFICIAL_EVENT_CONFLICT"
```

- [ ] **Step 2: Run and confirm event merger is absent**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_legislation_events.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement ordered event authority and closed outcomes**

```python
@dataclass(frozen=True, slots=True)
class HKLegislationEventDecision:
    legal_location_id: str
    state: Literal["CURRENT", "WAITING_ROOM", "HISTORY", "QUARANTINE"]
    reason_code: str
    controlling_event_refs: tuple[str, ...]
    unresolved_fact_codes: tuple[str, ...]


def decide_hk_legislation_state(
    timeline: HKLegislationEventTimeline, cutoff: str
) -> HKLegislationEventDecision: ...
```

Apply the accepted commencement, cessation/revival, amendment, correction, editorial-event, reconstruction, and known-stale rules. Use model output only as an evidence-bound decision input through Plan 6; never treat confidence as legal effect.

- [ ] **Step 4: Run event and reconstruction suites**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_legislation_events.py packages/legal-desks/tests/test_hk_reconstruction_execution.py -q`

Expected: all deterministic event cases pass; no provider is called.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/legal-desks/src/asklegal_legal_desks/hk_legislation_events.py packages/legal-desks/tests/test_hk_legislation_events.py`

Expected: pure state decisions and complete evidence references. Commit only with exact user authorization.

### Task 4: Build record candidates, complete releases, and traceability for all three scopes

**Files:**
- Create: `packages/legal-desks/src/asklegal_legal_desks/hk_legislation_records.py`
- Create: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_legislation_release.py`
- Modify: `packages/legal-desks/src/asklegal_legal_desks/__init__.py`
- Create: `packages/legal-desks/tests/test_hk_legislation_records.py`
- Create: `apps/legal-processing-worker/tests/test_hk_legislation_release.py`
- Test: `packages/corpus/tests/test_traceability_lookup.py`

**Interfaces:**
- Consumes: authenticated instruments, legal-state decisions, existing canonical rendering/partitioning, and register-issued identities.
- Produces: infrastructure-neutral `HKLegislationRecordCandidate` values from the legal desk, then an application-owned `HKLegislationReleaseResult` containing one `CorpusRelease` and complete `TraceabilityEntry` values for a single scope.

- [ ] **Step 1: Write the failing full-accounting tests**

```python
def test_release_accounts_for_every_inventory_member() -> None:
    result = build_hk_legislation_release(
        valid_release_request(), evidence_reader(), issued_identities()
    )
    assert result.accounted_source_item_count == result.source_inventory_count
    assert result.unaccounted_source_item_ids == ()


def test_required_bilingual_location_cannot_emit_one_language() -> None:
    with pytest.raises(HKLegislationReleaseError, match="BILINGUAL_RECORD_INCOMPLETE"):
        build_hk_legislation_release(
            request_with_missing_chinese_location(), evidence_reader(), issued_identities()
        )
```

- [ ] **Step 2: Run and verify the release builder is absent**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_legislation_records.py apps/legal-processing-worker/tests/test_hk_legislation_release.py -q`

Expected: collection fails for the missing module.

- [ ] **Step 3: Implement the release builder**

```python
@dataclass(frozen=True, slots=True)
class HKLegislationReleaseRequest:
    scope_id: str
    observation_cutoff: str
    source_inventory_item_ids: tuple[str, ...]
    prior_release_id: str


@dataclass(frozen=True, slots=True)
class HKLegislationRecordCandidate:
    record_id: str
    text: str
    source: str
    authority_note: str
    evidence_refs: tuple[str, ...]
    legal_item_id: str
    official_version_ids: tuple[str, ...]
    legal_location_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKLegislationReleaseResult:
    release: CorpusRelease
    traceability_entries: tuple[TraceabilityEntry, ...]
    source_inventory_count: int
    accounted_source_item_count: int
    unaccounted_source_item_ids: tuple[str, ...]
    waiting_room_item_ids: tuple[str, ...]
    history_item_ids: tuple[str, ...]
    quarantine_item_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKLegislationIssuedIdentities:
    legal_item_ids: tuple[tuple[str, str], ...]
    official_version_ids: tuple[tuple[str, str], ...]
    legal_location_ids: tuple[tuple[str, str], ...]
    search_record_ids: tuple[tuple[str, str], ...]
```

The legal-desk function uses `render_canonical_bilingual_location()` and the exact-limit partitioner, accepts only already issued identities, and returns record candidates without importing `asklegal_corpus`. The application module maps candidates to `ServingRecord`, calls `serving_payload_fingerprint()` and `build_corpus_release()`, and constructs complete traceability. Reuse an existing ID only when exact identity and payload continuity pass; the processing application requests any required forward successor through the Management Register before retrying the pure candidate builder.

- [ ] **Step 4: Run legislation release, corpus, and traceability tests**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_legislation_records.py apps/legal-processing-worker/tests/test_hk_legislation_release.py packages/corpus/tests/test_m6_corpus.py packages/corpus/tests/test_traceability_lookup.py -q`

Expected: all tests pass for complete, zero-record, waiting, quarantine, successor, and unchanged-reuse cases.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/legal-desks apps/legal-processing-worker/src/asklegal_legal_processing_worker/hk_legislation_release.py apps/legal-processing-worker/tests/test_hk_legislation_release.py packages/corpus/tests/test_traceability_lookup.py`

Expected: one complete-snapshot builder with no direct infrastructure dependency. Commit only with exact user authorization.

### Task 5: Compose the legal-processing activity and restart behavior

**Files:**
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_pipeline.py`
- Modify: `apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_infrastructure.py`
- Create: `apps/legal-processing-worker/tests/test_v1_legislation_pipeline.py`

**Interfaces:**
- Consumes: complete source-cycle binding, immutable evidence references, identity/register ports, and optional admitted semantic decisions.
- Produces: three immutable release artifacts plus a processing attempt report written last.

- [ ] **Step 1: Write the failing three-scope activity test**

```python
def test_legislation_activity_builds_exactly_three_scopes_manifest_last() -> None:
    vault = RecordingVault()
    result = process_hk_legislation(
        activity_context(), complete_instruction(), infrastructure(vault)
    )
    assert tuple(item.scope_id for item in result.releases) == (
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
    )
    assert vault.write_roles[-1] == "LEGAL_PROCESSING_ATTEMPT_REPORT"
```

- [ ] **Step 2: Run and observe the activity is absent**

Run: `python3 -m pytest apps/legal-processing-worker/tests/test_v1_legislation_pipeline.py -q`

Expected: collection fails for the missing activity.

- [ ] **Step 3: Add the restart-safe processing activity**

```python
def process_hk_legislation(
    context: ActivityContext,
    payload: object,
    infrastructure: V1LegalProcessingInfrastructure,
) -> object: ...
```

The payload contains only cycle ID, cutoff, matrix fingerprint, and source-cycle reference. The worker re-reads and validates the cycle, derives all evidence members, requests identities through the register port, and treats exact prior artifact versions as replay. A partial write without the terminal report remains incomplete and rerunnable.

- [ ] **Step 4: Run legal-worker and architecture suites**

Run: `python3 -m pytest apps/legal-processing-worker/tests/test_v1_legislation_pipeline.py apps/legal-processing-worker/tests/test_m5_processing.py tools/tests/test_architecture_spike.py -q`

Expected: all tests pass; source connector and application boundaries remain closed.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- apps/legal-processing-worker`

Expected: one registered activity and focused tests. Commit only with exact user authorization.

### Task 6: Replace `NOT_READY` only after authentic baseline proof

**Files:**
- Modify through generator: `packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/`
- Modify: `tools/build_hk_legislation_rulebook.py`
- Modify: `.agent/WORKING_STATE.md`
- Create: `packages/legal-desks/tests/test_hk_legislation_package.py`

**Interfaces:**
- Consumes: three authentic release results at one common cutoff and their deterministic compact evaluation results.
- Produces: package readiness evidence and Gate C Legislation status `READY`.

- [ ] **Step 1: Add the failing authentic-readiness test**

```python
def test_legislation_package_ready_requires_three_authentic_complete_releases() -> None:
    package = load_hk_legislation_rulebook()
    assert package.readiness.state == "READY"
    assert set(package.readiness.release_scope_ids) == {
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
    }
    assert package.readiness.authentic_evidence_fingerprints
```

- [ ] **Step 2: Run and confirm the package remains honestly not ready**

Run: `python3 -m pytest packages/legal-desks/tests/test_hk_legislation_package.py::test_legislation_package_ready_requires_three_authentic_complete_releases -q`

Expected: FAIL because the current package has `NOT_READY` attestations.

- [ ] **Step 3: Generate readiness from observed evidence, never hard-coded success**

Extend `tools/build_hk_legislation_rulebook.py` to accept a canonical admission-result file under ignored `var/`, verify the three releases and evaluation references, emit immutable readiness members, and add `--check` to compare generated bytes without rewriting them. If any referenced object cannot be read back or any scope is incomplete, retain `NOT_READY` with exact blockers.

- [ ] **Step 4: Rebuild twice and run the complete legislation sweep**

Run: `python3 -m tools.build_hk_legislation_rulebook --check`

Run it a second time.

Expected: byte-identical package trees.

Run: `python3 -m pytest packages/legal-desks/tests -k 'legislation or reconstruction' -q`

Expected: all Legislation and reconstruction tests pass.

- [ ] **Step 5: Run the complete shipping gate and stop**

Run: `python3 -m tools.dev_test --uv /home/docpro/.local/bin/uv --node /home/docpro/.local/bin/node`

Expected: complete shipping gate passes. Record the authentic cutoff, three release IDs/fingerprints, readiness fingerprint, and exact commands in `.agent/WORKING_STATE.md`. Request explicit commit authorization before creating the Plan 3 checkpoint.
