# Hong Kong V1 Scope and Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze one executable, fingerprinted definition of the three-family Hong Kong V1 and reconcile every conflicting V1 statement before source work proceeds.

**Architecture:** Add a strict Coverage Matrix owned by the reporting package and consumed by the admission tool. The matrix binds release scopes, source roles, cutoff policy, ownership, cadence, blocking consequences, exclusions, limitation wording, and authorization state without enabling any source. Documentation reconciliation marks older decisions as superseded while retaining their history.

**Tech Stack:** Python 3.14.7, frozen dataclasses, strict JSON decoding, SHA-256 canonical fingerprints, Pytest, Pyright strict mode, Ruff, Markdown.

**Spec:** `docs/design/HK_V1_LIVE_EXECUTION_SPEC.md`

## Global Constraints

- V1 includes all three Hong Kong Legislation scopes, binding-case propositions from 1 July 1997 onward, and current HKEX Main Board and GEM Listing Rules.
- Hong Kong Principles, pre-1-July-1997 Cases, Ask.Legal routing, the Ask.Legal admin portal, and Azure application hosting are excluded.
- GLD is the originating current Gazette source; HKeL Gazette is complementary backcapture and recovery evidence.
- The user's GLD-permission report is not independently verified publisher evidence and cannot enable a connector by itself.
- No implementation step in this plan performs external source access, accepts terms, calls a provider, mutates Pinecone, changes the host, commits, or pushes without the exact separate authority.
- A success result requires complete read-back evidence; absence, silence, or a placeholder fingerprint cannot pass.

## Dependency and exit contract

This is Plan 1 of 9 and has no implementation dependency. It produces:

```python
def load_hk_v1_coverage_matrix(path: Path | None = None) -> HongKongV1CoverageMatrix: ...


def evaluate_hk_v1_scope_gate(
    matrix: HongKongV1CoverageMatrix,
) -> HongKongV1ScopeGateResult: ...
```

Plan 2 consumes the exact matrix fingerprint and may add endpoint evidence only by issuing a new matrix revision. Plans 3–9 must reject a matrix whose scope, exclusions, cutoff, or source-role set differs from the approved revision.

## File structure

- Create `packages/reporting/src/asklegal_reporting/hk_v1_coverage.py` — immutable matrix model, strict loader, canonical fingerprint, and scope-gate evaluator.
- Create `packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json` — repository-owned approved scope and source-role rows.
- Create `packages/reporting/tests/test_hk_v1_coverage.py` — exact scope, cutoff, exclusion, drift, and failure tests.
- Modify `packages/reporting/src/asklegal_reporting/__init__.py` — export the matrix API.
- Modify `tools/v1_poc_admission.py` — expose Gate A without changing the existing synthetic M7 result.
- Modify `tools/tests/test_v1_poc_admission.py` — prove Gate A fails visibly until technical and rights admissions exist.
- Modify the conflicting ADR/design/continuity files named in Task 4 — preserve history and mark superseded V1 statements.

---

### Task 1: Define the strict Coverage Matrix contract

**Files:**
- Create: `packages/reporting/src/asklegal_reporting/hk_v1_coverage.py`
- Create: `packages/reporting/tests/test_hk_v1_coverage.py`

**Interfaces:**
- Consumes: canonical JSON bytes and a filesystem `Path`.
- Produces: `CoverageMatrixRow`, `HongKongV1CoverageMatrix`, `HongKongV1ScopeGateResult`, `load_hk_v1_coverage_matrix()`, and `evaluate_hk_v1_scope_gate()`.

- [ ] **Step 1: Write the failing strict-decoder test**

```python
def test_matrix_rejects_unknown_row_field(tmp_path: Path) -> None:
    document = valid_matrix_document()
    document["rows"][0]["invented"] = True
    path = write_matrix(tmp_path, document)
    with pytest.raises(HongKongV1CoverageError, match="MATRIX_ROW_FIELDS_INVALID"):
        load_hk_v1_coverage_matrix(path)
```

- [ ] **Step 2: Run the single test and observe the missing API failure**

Run: `python3 -m pytest packages/reporting/tests/test_hk_v1_coverage.py::test_matrix_rejects_unknown_row_field -q`

Expected: collection fails because `asklegal_reporting.hk_v1_coverage` does not exist.

- [ ] **Step 3: Implement the immutable contract and exact-key parser**

```python
@dataclass(frozen=True, slots=True)
class CoverageMatrixRow:
    scope_id: str
    material_family: Literal["LEGISLATION", "CASES", "REGULATORY"]
    source_id: str
    fact_authority: str
    owner: Literal["ACQUISITION", "LEGAL_PROCESSING", "CONTROL"]
    earliest_boundary: str
    cutoff_rule: str
    cadence: str
    technical_state: Literal["ADMITTED", "NOT_ADMITTED"]
    rights_state: Literal["ADMITTED", "NOT_ADMITTED"]
    outage_consequence: Literal["RELEASE_BLOCKING", "AFFECTED_WORK_BLOCKING", "NONBLOCKING"]
    exclusion_code: str
    limitation_text: str


@dataclass(frozen=True, slots=True)
class HongKongV1CoverageMatrix:
    revision: str
    effective_date: str
    rows: tuple[CoverageMatrixRow, ...]
    explicit_exclusions: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HongKongV1ScopeGateResult:
    result: Literal["ADMITTED", "NOT_ADMITTED"]
    blocker_codes: tuple[str, ...]
```

Decode with `parse_json_bytes`, require the exact top-level and row key sets, sort rows by `(scope_id, source_id)`, reject duplicates, and compare `sha256(canonicalize(document_without_fingerprint))` with the declared fingerprint.

- [ ] **Step 4: Run the strict-decoder test**

Run: `python3 -m pytest packages/reporting/tests/test_hk_v1_coverage.py::test_matrix_rejects_unknown_row_field -q`

Expected: `1 passed`.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/reporting/src/asklegal_reporting/hk_v1_coverage.py packages/reporting/tests/test_hk_v1_coverage.py`

Expected: only the strict contract and its focused tests. Do not commit unless the user has explicitly authorized this checkpoint commit.

### Task 2: Freeze the approved V1 scope and source-role set

**Files:**
- Create: `packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json`
- Modify: `packages/reporting/src/asklegal_reporting/__init__.py`
- Modify: `packages/reporting/tests/test_hk_v1_coverage.py`

**Interfaces:**
- Consumes: the Plan 1 matrix decoder and the existing Legislation, Cases, and HKEX source-role identifiers.
- Produces: one default matrix revision whose loader fingerprint is stable across two reads.

- [ ] **Step 1: Add the failing approved-scope test**

```python
def test_default_matrix_freezes_the_approved_three_family_scope() -> None:
    matrix = load_hk_v1_coverage_matrix()
    assert {row.material_family for row in matrix.rows} == {"LEGISLATION", "CASES", "REGULATORY"}
    assert {row.scope_id for row in matrix.rows} == {
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-CASE-BINDING-POST-1997",
        "HK-REG-HKEX-MAIN",
        "HK-REG-HKEX-GEM",
    }
    assert all(
        row.earliest_boundary == "1997-07-01"
        for row in matrix.rows
        if row.material_family == "CASES"
    )
```

- [ ] **Step 2: Run it and verify the default data is absent**

Run: `python3 -m pytest packages/reporting/tests/test_hk_v1_coverage.py::test_default_matrix_freezes_the_approved_three_family_scope -q`

Expected: FAIL because the default matrix file does not exist.

- [ ] **Step 3: Add the exact matrix rows**

Populate all six scope IDs. Legislation rows must reference the fourteen existing `HK-LEG-*` source roles; Cases rows must reference the seven existing `HK-CASE-*` roles while marking `HK-CASE-PRIVY-COUNCIL` excluded for this V1; Regulatory rows must reference these five roles for both boards:

```text
HK-REG-HKEX-CONSOLIDATED-RULEBOOKS
HK-REG-HKEX-FEES-RULES
HK-REG-HKEX-REGULATORY-FORMS
HK-REG-HKEX-RULE-UPDATES
HK-REG-HKEX-RULEBOOK-CATALOGUE
```

Freeze explicit exclusions for `HK-PRINCIPLES`, `HK-CASE-PRE-1997`, `FULL_JUDGMENTS_AS_RECORDS`, `HKEX_NON_LISTING_RULE_GUIDANCE`, `ASKLEGAL_ROUTING`, `ASKLEGAL_ADMIN`, and `AZURE_APP_HOSTING`. Compute and insert the canonical fingerprint with a repository-owned helper in the test, then prove the checked-in value matches rather than allowing the runtime to repair it.

- [ ] **Step 4: Run all matrix tests twice**

Run: `python3 -m pytest packages/reporting/tests/test_hk_v1_coverage.py -q`

Run the same command a second time.

Expected: both runs pass with the same reported fingerprint.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/reporting/src/asklegal_reporting`

Expected: one strict loader, one approved data file, and public exports. Commit only after exact user authorization; suggested message: `feat(reporting): freeze Hong Kong V1 coverage matrix`.

### Task 3: Make Gate A executable and fail-visible

**Files:**
- Modify: `tools/v1_poc_admission.py`
- Modify: `tools/tests/test_v1_poc_admission.py`

**Interfaces:**
- Consumes: `evaluate_hk_v1_scope_gate(matrix)`.
- Produces: a `scope_authority` section in the V1 admission report with `result`, `matrix_revision`, `matrix_fingerprint`, and exact blocker codes.

- [ ] **Step 1: Write the failing admission-report test**

```python
def test_v1_report_exposes_scope_authority_blockers() -> None:
    report = build_v1_admission_report()
    gate = report["scope_authority"]
    assert gate["result"] == "NOT_ADMITTED"
    assert "SOURCE_TECHNICAL_ADMISSION_MISSING" in gate["blocker_codes"]
    assert "SOURCE_RIGHTS_ADMISSION_MISSING" in gate["blocker_codes"]
    assert gate["matrix_fingerprint"].startswith("sha256:")
```

- [ ] **Step 2: Run the test and confirm the missing report member**

Run: `python3 -m pytest tools/tests/test_v1_poc_admission.py::test_v1_report_exposes_scope_authority_blockers -q`

Expected: FAIL with a missing `scope_authority` key.

- [ ] **Step 3: Add the scope gate without changing synthetic M7 admission**

```python
def _scope_authority_section() -> dict[str, object]:
    matrix = load_hk_v1_coverage_matrix()
    gate = evaluate_hk_v1_scope_gate(matrix)
    return {
        "blocker_codes": list(gate.blocker_codes),
        "matrix_fingerprint": matrix.fingerprint,
        "matrix_revision": matrix.revision,
        "result": gate.result,
    }
```

Keep `local synthetic platform proved` semantically separate. The new section must not turn the real V1 result into admitted while any row is unadmitted.

- [ ] **Step 4: Run focused admission tests**

Run: `python3 -m pytest tools/tests/test_v1_poc_admission.py -q`

Expected: all tests pass and the real V1 remains `NOT_ADMITTED`.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `python3 -m tools.v1_poc_admission`

Expected: a deterministic report that preserves synthetic M7 success while showing Gate A blockers. Commit only with exact user authorization.

### Task 4: Reconcile superseded V1 documentation without deleting history

**Files:**
- Modify: `docs/adr/0046-limit-ordinary-hong-kong-case-coverage-to-binding-courts.md`
- Modify: `docs/adr/0049-establish-the-first-hong-kong-cases-current-authority-baseline.md`
- Modify: `docs/adr/0077-admit-hkex-multilingual-retrieval-and-downstream-answer-behavior-separately.md`
- Modify: `docs/adr/0100-isolate-patchright-to-non-controlling-source-discovery.md`
- Modify: `docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md`
- Modify: `docs/design/HONG_KONG_CASE_TREATMENT_DESIGN_AUDIT.md`
- Modify: `.agent/CONTEXT.md`
- Modify: `.agent/DECISIONS.md`
- Modify: `.agent/ROADMAP.md`
- Modify: `.agent/HANDOFF.md`
- Modify: `.agent/WORKING_STATE.md`
- Create: `tools/tests/test_hk_v1_documentation.py`

**Interfaces:**
- Consumes: the approved master spec and matrix fingerprint.
- Produces: historically honest documentation with current V1 amendments and no ambiguous activation claim.

- [ ] **Step 1: Add a stale-statement scan test**

Create `tools/tests/test_hk_v1_documentation.py` with a helper that extracts only
the current V1 sections:

```python
CURRENT_SECTION_MARKERS = ("## Current V1 position", "## V1 position", "## Current goal")


def load_current_v1_sections() -> str:
    paths = (Path(".agent/CONTEXT.md"), Path(".agent/HANDOFF.md"), Path(".agent/WORKING_STATE.md"))
    sections: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for marker in CURRENT_SECTION_MARKERS:
            if marker in text:
                sections.append(text.split(marker, 1)[1].split("\n## ", 1)[0])
    return "\n".join(sections)


def test_current_v1_sections_do_not_assert_superseded_scope() -> None:
    current_sections = load_current_v1_sections()
    forbidden = (
        "Principles still needs publisher/title/licence selection",
        "Turnstile acceptance path is still a technical admission blocker and must not be bypassed",
        "bounded manual acquisition procedure",
        "Ask.Legal route is the V1 activation boundary",
    )
    assert not any(text in current_sections for text in forbidden)
```

The helper intentionally inspects current-status sections, not historical decision text.

- [ ] **Step 2: Run the scan and record every stale current statement**

Run: `python3 -m pytest tools/tests/test_hk_v1_documentation.py -q`

Expected: FAIL and list the remaining stale current sections.

- [ ] **Step 3: Add dated amendment blocks and update current sections**

Every older decision remains present. Add a 2026-08-25 amendment stating exactly which V1 statement it supersedes and link `docs/design/HK_V1_LIVE_EXECUTION_SPEC.md`. Keep the overall four-family target in the initial design, but label it as broader than the approved three-family V1. State that V1 activation is the Management Register Serving State transition, not Ask.Legal routing.

- [ ] **Step 4: Run the stale scan and Markdown/link checks**

Run: `python3 -m pytest tools/tests/test_hk_v1_documentation.py -q`

Expected: PASS while historical superseded text remains discoverable.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- docs/adr docs/design .agent tools/tests/test_hk_v1_documentation.py`

Expected: dated amendments, current-state corrections, and the documentation test only. Commit only with exact user authorization; suggested message: `docs: reconcile approved Hong Kong V1 scope`.

### Task 5: Prove Gate A and hand its fingerprint to Plan 2

**Files:**
- Modify: `.agent/WORKING_STATE.md`
- Modify: `.agent/ROADMAP.md`

**Interfaces:**
- Consumes: all Plan 1 files.
- Produces: one recorded matrix revision/fingerprint, Gate A result, remaining admission blockers, and the exact Plan 2 input.

- [ ] **Step 1: Run focused Plan 1 tests**

Run: `.venv/bin/python -m pytest packages/reporting/tests/test_hk_v1_coverage.py tools/tests/test_v1_poc_admission.py tools/tests/test_hk_v1_documentation.py -q`

Expected: all Plan 1 tests pass.

- [ ] **Step 2: Run the complete shipping gate**

Run: `python3 -m tools.dev_test --uv /home/docpro/.local/bin/uv --node /home/docpro/.local/bin/node`

Expected: Pyright 0, Ruff clean, architecture and contract checks pass, generated packages reproduce, and the full Pytest suite passes except the documented intentional opt-in skips.

- [ ] **Step 3: Capture the deterministic Gate A output twice**

Run: `python3 -m tools.v1_poc_admission`

Run the same command again.

Expected: identical matrix revision, fingerprint, scope set, exclusions, and blocker codes.

- [ ] **Step 4: Rewrite current continuity state**

Record the exact commands and observed results in `.agent/WORKING_STATE.md`; advance HKV1-0 in `.agent/ROADMAP.md` only for the scope/authority contract, not source admission.

- [ ] **Step 5: Stop at the authorization gate**

Run: `git status --short --branch`

Expected: the exact Plan 1 changes are visible. Request explicit commit authorization before committing. Request separate external-source authorization only when Plan 2 reaches its preserved-evidence checkpoint.
