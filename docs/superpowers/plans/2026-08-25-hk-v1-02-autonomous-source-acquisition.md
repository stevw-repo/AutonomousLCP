# Hong Kong V1 Autonomous Source Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admit autonomous, complete, fail-visible acquisition for every GLD, HKeL, Judiciary, and HKEX source role required by the approved V1.

**Architecture:** Keep source contracts and inert response validation in `source-connectors`; keep Patchright browser execution inside the acquisition application. Each source procedure writes artifacts first, an attempt manifest second, and one due-cycle coverage report last. Browser session establishment never becomes legal evidence by itself, and no source failure can collapse into no change.

**Tech Stack:** Python 3.14.7, Patchright 1.62.1 with local Chromium, standard-library HTTPS through the acquisition proxy, immutable evidence-vault ports, Durable Task activities, strict JSON, Pytest.

**Spec:** `docs/design/HK_V1_LIVE_EXECUTION_SPEC.md`

## Global Constraints

- GLD acquisition is fully autonomous and local-only: no manual challenge completion, remote solver, unofficial mirror, or direct browser-to-processing path.
- The browser is limited to exact admitted GLD hosts, paths, methods, request ceilings, and local protected session state.
- HKeL must supply authentic inventories, bilingual XML, schemas/specifications, verified or assisted copies, Editorial Records, past data, and Gazette backcapture required by V1.
- Judiciary must account for every official listing dated on or after 1997-07-01; HKLII is non-controlling.
- HKEX uses exactly five source roles and must account for Main Board and GEM component membership.
- Authentic legal bytes are stored under ignored `var/` vault state, never Git.
- External fetches, consent/terms acceptance, or preserved-permission use require an exact separate authorization at Task 7.

## Dependency and exit contract

Depends on Plan 1's approved Coverage Matrix revision and fingerprint. Produces:

```python
class OfficialSourceProcedure(Protocol):
    def observe(self, request: SourceObservationRequest) -> SourceObservationResult: ...


def acquire_hk_v1_due_cycle(
    instruction: SourceCycleInstruction,
    activities: AcquisitionActivities,
) -> dict[str, object]: ...
```

Plans 3–5 consume only complete source-cycle manifests and addressed immutable evidence references. They must reject direct URLs, unmanifested files, or partial source results.

## File structure

- Modify `packages/source-connectors/src/asklegal_source_connectors/official.py` and the Legislation register — authorization-evidence binding and enabled endpoint contracts.
- Modify `packages/source-connectors/src/asklegal_source_connectors/hk_cases_official.py` and its register — exact Judiciary procedures and 1997 cutoff.
- Create `packages/source-connectors/src/asklegal_source_connectors/gld_gazette.py` — provider-neutral GLD session/enumeration/artifact contract.
- Create `packages/source-connectors/src/asklegal_source_connectors/hkel_legislation.py` — HKeL inventory and artifact procedure.
- Create `packages/source-connectors/src/asklegal_source_connectors/hk_regulatory_official.py` and `hk_regulatory_source_register.json` — five-role HKEX source contract.
- Create `apps/acquisition-worker/src/asklegal_acquisition_worker/gld_session.py` — isolated Patchright GLD session adapter.
- Modify `apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py` — register all procedures and assemble one complete due cycle.
- Modify focused tests under `packages/source-connectors/tests/` and `apps/acquisition-worker/tests/`.

---

### Task 1: Freeze strict GLD and cross-source procedure contracts

**Files:**
- Create: `packages/source-connectors/src/asklegal_source_connectors/gld_gazette.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/official.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/__init__.py`
- Create: `packages/source-connectors/tests/test_gld_gazette.py`

**Interfaces:**
- Consumes: one registered source ID, date window, language, cutoff, and exact admitted endpoint profile.
- Produces: `GldSessionRequest`, `GldSessionGrant`, `GldGazetteEntry`, `GldGazetteWindow`, `GldSessionPort`, and `GldGazetteExchange`.

- [ ] **Step 1: Write the failing contract tests**

```python
def test_gld_request_rejects_an_unregistered_endpoint() -> None:
    with pytest.raises(ValueError, match="GLD_ENDPOINT_NOT_ADMITTED"):
        GldSessionRequest(
            source_id="HK-LEG-GLD-EGAZETTE",
            endpoint_id="sep_ffffffffffffffffffffffffffffffffffffffffffffffff",
            start_date="2026-08-24",
            end_date="2026-08-25",
            language="BILINGUAL",
            observation_cutoff="2026-08-25T00:00:00+00:00",
        )


def test_session_grant_has_no_controlling_evidence_authority() -> None:
    field_by_name = {field.name: field for field in fields(GldSessionGrant)}
    assert field_by_name["controlling_evidence"].default is False
```

- [ ] **Step 2: Run the tests and confirm the module is absent**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_gld_gazette.py -q`

Expected: collection fails because the GLD contract module does not exist.

- [ ] **Step 3: Implement the closed contract**

```python
@dataclass(frozen=True, slots=True)
class GldSessionGrant:
    session_id: str
    established_at: str
    expires_at: str
    admitted_host: str
    policy_fingerprint: str
    controlling_evidence: Literal[False] = False


class GldSessionPort(Protocol):
    def establish(self, request: GldSessionRequest) -> GldSessionGrant: ...
    def invalidate(self, session_id: str) -> None: ...


class GldGazetteExchange(Protocol):
    def enumerate_window(
        self, grant: GldSessionGrant, request: GldSessionRequest
    ) -> GldGazetteWindow: ...

    def fetch_artifact(
        self, grant: GldSessionGrant, entry: GldGazetteEntry
    ) -> OfficialTransportResponse: ...
```

Require exact date-window ordering, registered endpoint IDs, allowed languages, sorted unique entries, declared Gazette classes, and a canonical listing fingerprint. The grant contains no cookie, token, header, or raw browser state.

- [ ] **Step 4: Run the contract suite**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_gld_gazette.py packages/source-connectors/tests/test_hk_legislation_official_sources.py -q`

Expected: all tests pass and no existing source role is silently enabled.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/source-connectors/src/asklegal_source_connectors packages/source-connectors/tests/test_gld_gazette.py`

Expected: provider-neutral contracts only. Commit only with exact user authorization.

### Task 2: Build the isolated local GLD browser-session adapter

**Files:**
- Create: `apps/acquisition-worker/src/asklegal_acquisition_worker/gld_session.py`
- Modify: `apps/acquisition-worker/pyproject.toml`
- Create: `apps/acquisition-worker/tests/test_gld_session.py`

**Interfaces:**
- Consumes: `GldSessionRequest`, exact `RenderedBrowserPolicy`, and a protected local session store supplied by the acquisition application.
- Produces: `LocalGldSessionTransport.establish()` and `.invalidate()` implementing `GldSessionPort`.

- [ ] **Step 1: Write failing clean-session and leakage tests**

```python
def test_establish_returns_sanitized_grant_and_keeps_session_secret_private() -> None:
    browser = ScriptedGldBrowser.success(session_secret="secret-cookie")
    store = InMemoryProtectedSessionStore()
    adapter = LocalGldSessionTransport(browser, store, admitted_policy())
    request = valid_gld_request()
    grant = adapter.establish(request)
    assert grant.admitted_host == gld_registered_host(request)
    assert gld_registered_host(request) == "egazette.gld.gov.hk"
    assert "secret-cookie" not in repr(grant)
    assert store.has(grant.session_id)


def test_contract_change_invalidates_session() -> None:
    browser = ScriptedGldBrowser.challenge_shape_changed()
    with pytest.raises(GldSessionError, match="GLD_CHALLENGE_CONTRACT_CHANGED"):
        LocalGldSessionTransport(
            browser, InMemoryProtectedSessionStore(), admitted_policy()
        ).establish(valid_gld_request())
```

- [ ] **Step 2: Run focused tests and observe the missing adapter**

Run: `.venv/bin/python -m pytest apps/acquisition-worker/tests/test_gld_session.py -q`

Expected: collection fails because `gld_session.py` is absent.

- [ ] **Step 3: Implement the Patchright adapter behind a browser protocol**

```python
class GldBrowserRunner(Protocol):
    def establish(
        self, *, start_url: str, allowed_hosts: tuple[str, ...], deadline_seconds: int
    ) -> BrowserSessionMaterial: ...


class ProtectedSessionStore(Protocol):
    def put(self, session_id: str, material: BrowserSessionMaterial, expires_at: str) -> None: ...
    def get(self, session_id: str) -> BrowserSessionMaterial: ...
    def delete(self, session_id: str) -> None: ...
```

Use Patchright only in the concrete runner. Deny downloads to arbitrary paths, popups, extensions, browser credentials, user-supplied URLs, cross-host requests, and session-state logging. Store the minimum material in the acquisition-owned sealed credential location; tests use the in-memory store.

The admitted local experiment order is fixed: ephemeral clean context first;
then a headed Chromium context on the isolated local display; then an origin-
scoped persistent context whose state is sealed and expires. JavaScript and the
publisher's public challenge run only inside that compartment. If none completes
unattended, return `GLD_CHALLENGE_UNRESOLVED`; do not add a manual or remote-
solver fallback.

- [ ] **Step 4: Run browser adapter and architecture tests**

Run: `.venv/bin/python -m pytest apps/acquisition-worker/tests/test_gld_session.py apps/acquisition-worker/tests/test_patchright_discovery.py tools/tests/test_architecture_spike.py -q`

Expected: all tests pass; Patchright remains acquisition-worker-only.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- apps/acquisition-worker`

Expected: one exact-host adapter and tests. No live browser execution occurs. Commit only with exact user authorization.

### Task 3: Complete HKeL evidence procedures

**Files:**
- Create: `packages/source-connectors/src/asklegal_source_connectors/hkel_legislation.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hk_legislation_source_register.json`
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py`
- Create: `packages/source-connectors/tests/test_hkel_legislation.py`
- Create: `apps/acquisition-worker/tests/test_v1_hkel_evidence.py`

**Interfaces:**
- Consumes: existing `OfficialInventoryConnector`, bound endpoint locators, and vault ports.
- Produces: `HkelEvidencePlan` and `capture_hkel_evidence()` with exact member accounting.

- [x] **Step 1: Write the failing complete-member test**

```python
def test_hkel_plan_requires_bilingual_xml_schema_pdf_and_editorial_members() -> None:
    plan = build_hkel_evidence_plan(sample_inventory(), cutoff=UTC_CUTOFF)
    assert {member.role for member in plan.members} == {
        "ENGLISH_XML",
        "TRADITIONAL_CHINESE_XML",
        "XSD",
        "PUBLICATION_SPECIFICATION",
        "OFFICIAL_COPY",
        "EDITORIAL_RECORD",
    }
```

- [x] **Step 2: Run the tests and verify the procedure is absent**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_hkel_legislation.py apps/acquisition-worker/tests/test_v1_hkel_evidence.py -q`

Expected: collection fails for the missing HKeL procedure.

- [x] **Step 3: Implement complete plan-before-fetch behavior**

```python
@dataclass(frozen=True, slots=True)
class HkelEvidencePlan:
    instrument_id: str
    observation_cutoff: str
    members: tuple[HkelEvidenceMember, ...]
    plan_fingerprint: str


def build_hkel_evidence_plan(
    inventory: OfficialInventoryResult, *, cutoff: str
) -> HkelEvidencePlan: ...
```

The acquisition activity must enumerate and validate the whole inventory before fetching addressed artifacts, write each admitted artifact immutably, and write a terminal attempt report only after every required member has a disposition. Missing bilingual partners or schema/specification members produce `PARTIAL_CAPTURE` and release blocking.

- [x] **Step 4: Run HKeL and existing Gazette suites**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_hkel_legislation.py packages/source-connectors/tests/test_hkel_gazette_register.py apps/acquisition-worker/tests/test_v1_hkel_evidence.py apps/acquisition-worker/tests/test_v1_gazette_outcomes.py -q`

Expected: all tests pass, including missing-member and truncated-inventory failures.

- [x] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/source-connectors apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py apps/acquisition-worker/tests/test_v1_hkel_evidence.py`

Expected: HKeL source evidence is schedulable but no external endpoint has been called. Commit only with exact user authorization.

### Task 4: Admit the post-1997 Judiciary enumeration contract

**Files:**
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hk_cases_official.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hk_cases_source_register.json`
- Create: `packages/source-connectors/src/asklegal_source_connectors/hk_judiciary.py`
- Create: `packages/source-connectors/tests/test_hk_judiciary.py`
- Test: `packages/source-connectors/tests/test_hk_cases_official_sources.py`

**Interfaces:**
- Consumes: exact official Judiciary listing and artifact endpoint contracts.
- Produces: `JudiciaryListingRequest`, `JudiciaryListingEntry`, `JudiciaryInventory`, and `JudiciaryExchange`.

- [x] **Step 1: Write the failing cutoff and completeness tests**

```python
def test_judiciary_request_has_inclusive_1997_cutoff() -> None:
    request = JudiciaryListingRequest.baseline("2026-08-25T00:00:00+00:00")
    assert request.earliest_decision_date == "1997-07-01"


def test_empty_intermediate_page_is_not_no_change() -> None:
    exchange = ScriptedJudiciaryExchange.pages([page(1), empty_page(2), page(3)])
    with pytest.raises(JudiciarySourceError, match="JUDICIARY_INVENTORY_INCOMPLETE"):
        enumerate_judiciary_inventory(exchange, valid_request())
```

- [x] **Step 2: Run and confirm the concrete enumerator is missing**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_hk_judiciary.py -q`

Expected: collection fails for the missing module.

- [x] **Step 3: Implement listing-first enumeration and artifact identities**

```python
class JudiciaryExchange(Protocol):
    def fetch_listing_page(
        self, request: JudiciaryListingRequest, page: int
    ) -> JudiciaryListingPage: ...

    def fetch_judgment(
        self, entry: JudiciaryListingEntry, artifact: JudiciaryArtifactLocator
    ) -> OfficialTransportResponse: ...
```

Entries must preserve case number, neutral citation, court, decision date, language, opinion/reasons identity, correction/reissue links, translation links, and official locator. Sort by stable official identity, reject page repetition/truncation, and give every listing one terminal capture disposition.

- [x] **Step 4: Run Judiciary, Cases-register, locator, and HTTP suites**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_hk_judiciary.py packages/source-connectors/tests/test_hk_cases_official_sources.py packages/source-connectors/tests/test_endpoint_template_resolution.py packages/source-connectors/tests/test_official_http_connector.py -q`

Expected: all tests pass and HKLII remains non-controlling.

- [x] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/source-connectors`

Expected: exact official contracts, cutoff, and tests; no source bytes in Git. Commit only with exact user authorization.

### Task 5: Add the five-role HKEX source register and inventory procedure

**Files:**
- Create: `packages/source-connectors/src/asklegal_source_connectors/hk_regulatory_official.py`
- Create: `packages/source-connectors/src/asklegal_source_connectors/hk_regulatory_source_register.json`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/__init__.py`
- Create: `packages/source-connectors/tests/test_hk_regulatory_official.py`

**Interfaces:**
- Consumes: the five accepted source IDs from the HKEX source-neutral package.
- Produces: `HongKongRegulatorySourceRegister`, `load_hk_regulatory_source_register()`, and `build_hkex_component_inventory()`.

- [x] **Step 1: Write the failing five-role and board-isolation tests**

```python
def test_hkex_register_has_exactly_five_controlling_roles() -> None:
    register = load_hk_regulatory_source_register()
    assert tuple(source.source_id for source in register.sources) == (
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "HK-REG-HKEX-FEES-RULES",
        "HK-REG-HKEX-REGULATORY-FORMS",
        "HK-REG-HKEX-RULE-UPDATES",
        "HK-REG-HKEX-RULEBOOK-CATALOGUE",
    )


def test_component_inventory_does_not_merge_main_and_gem() -> None:
    result = build_hkex_component_inventory(scripted_products(), cutoff=UTC_CUTOFF)
    assert set(result.board_ids) == {"MAIN", "GEM"}
    assert not set(result.main_component_ids) & set(result.gem_component_ids)
```

- [x] **Step 2: Run and observe missing register code**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_hk_regulatory_official.py -q`

Expected: collection fails for the missing module.

- [x] **Step 3: Implement strict register loading and component inventory**

```python
@dataclass(frozen=True, slots=True)
class HKEXProductObservation:
    source_id: str
    board: Literal["MAIN", "GEM"]
    component_kind: str
    official_locator: str
    artifact_fingerprint: str


@dataclass(frozen=True, slots=True)
class HKEXComponentInventory:
    board_ids: tuple[str, ...]
    main_component_ids: tuple[str, ...]
    gem_component_ids: tuple[str, ...]
    inventory_fingerprint: str


def load_hk_regulatory_source_register(
    path: Path | None = None,
) -> HongKongRegulatorySourceRegister: ...


def build_hkex_component_inventory(
    products: tuple[HKEXProductObservation, ...], *, cutoff: str
) -> HKEXComponentInventory: ...
```

Require Chapters, rules, notes, appendices, Practice Notes, Regulatory Forms, and Fees Rules to have a board owner and terminal disposition. The catalogue bounds product families but cannot prove artifact content or complete component membership alone.

- [x] **Step 4: Run the new register and existing HKEX source-decision suites**

Run: `.venv/bin/python -m pytest packages/source-connectors/tests/test_hk_regulatory_official.py packages/legal-desks/tests/test_hk_regulatory_conformance_source.py -q`

Expected: all tests pass with the exact five-role fingerprint.

- [x] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- packages/source-connectors`

Expected: one strict five-role register, inventory procedure, exports, and tests. Commit only with exact user authorization.

### Task 6: Assemble one complete V1 due-source cycle

**Files:**
- Modify: `apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py`
- Modify: `apps/control-plane/src/asklegal_control_plane/v1_pipeline.py`
- Modify: `packages/reporting/src/asklegal_reporting/source_coverage.py`
- Test: `apps/acquisition-worker/tests/test_v1_source_cycle.py`
- Test: `apps/control-plane/tests/test_v1_observation_pipeline.py`
- Test: `packages/reporting/tests/test_source_coverage.py`

**Interfaces:**
- Consumes: all four source procedure results plus Plan 1 matrix fingerprint.
- Produces: one canonical `SourceCoverageCycleBinding` whose `accounting_complete` is true only when every due blocking role is terminal and complete.

- [ ] **Step 1: Write the failing all-source cycle test**

```python
def test_due_cycle_requires_all_four_source_families() -> None:
    result = run_due_cycle(scripted_complete_results(exclude="HKEX"))
    assert result["accounting_complete"] is False
    assert result["missing_source_ids"] == [
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "HK-REG-HKEX-FEES-RULES",
        "HK-REG-HKEX-REGULATORY-FORMS",
        "HK-REG-HKEX-RULE-UPDATES",
        "HK-REG-HKEX-RULEBOOK-CATALOGUE",
    ]
    assert result["disposition"] == "PARTIAL_CAPTURE"
```

- [ ] **Step 2: Run and observe current Legislation-only accounting**

Run: `.venv/bin/python -m pytest apps/acquisition-worker/tests/test_v1_source_cycle.py::test_due_cycle_requires_all_four_source_families -q`

Expected: FAIL because the current scheduler does not assemble every V1 source family.

- [ ] **Step 3: Register the procedures and aggregate manifest-last**

```python
def acquire_hk_v1_due_cycle(
    instruction: SourceCycleInstruction,
    activities: AcquisitionActivities,
) -> dict[str, object]:
    results = activities.capture_every_due_source(instruction)
    return activities.write_complete_cycle_report(instruction, results)
```

Control supplies only cycle identity, cutoff, and matrix fingerprint. Acquisition derives sources and endpoints from admitted registers. The report must include missing, duplicate, gap, failed, and complete source IDs and must be the final vault write.

- [ ] **Step 4: Run cross-application cycle tests**

Run: `.venv/bin/python -m pytest apps/acquisition-worker/tests/test_v1_source_cycle.py apps/control-plane/tests/test_v1_observation_pipeline.py packages/reporting/tests/test_source_coverage.py -q`

Expected: all synthetic complete/failure/restart/no-change cases pass.

- [ ] **Step 5: Prepare the reviewer checkpoint**

Run: `git diff -- apps/acquisition-worker apps/control-plane packages/reporting`

Expected: one due-cycle path with complete source accounting. No real source procedure is enabled yet. Commit only with exact user authorization.

### Task 7: Preserve authorization evidence and execute the external admission proof

**Files:**
- Create: `tools/hk_v1_source_admission.py`
- Create: `tools/tests/test_hk_v1_source_admission.py`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hk_legislation_source_register.json`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hk_cases_source_register.json`
- Modify: `packages/source-connectors/src/asklegal_source_connectors/hk_regulatory_source_register.json`
- Modify: `packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json`
- Modify: `.agent/WORKING_STATE.md`

**Interfaces:**
- Consumes: user-identified GLD authorization evidence and exact external-source authority for this checkpoint.
- Produces: admitted source-profile fingerprints and repeated authentic source-cycle evidence under ignored `var/` vault storage.

- [ ] **Step 1: Stop and verify the exact authority**

Before any network call, confirm in current user instructions:

```text
authorized source hosts
authorized public procedures
permission-evidence reference
permitted observation window
whether terms or consent presentation is expected
```

If a terms/consent screen appears, stop, preserve its text for review, and obtain explicit acceptance authority before interaction.

Add a disabled-by-default CLI whose preflight performs no network call:

`python3 -m tools.hk_v1_source_admission --matrix packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json --mode preflight --output-root var/hk-v1/source-admission`

- [ ] **Step 2: Run clean-session, renewal, expiry, restart, drift, and no-change GLD probes**

Run: `python3 -m tools.hk_v1_source_admission --matrix packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json --mode execute --source-id HK-LEG-GLD-EGAZETTE --output-root var/hk-v1/source-admission/gld`

Expected: repeated unattended clean-session, renewal, expiry, restart, drift, and no-change scenarios complete; sanitized session evidence, complete Gazette-class enumeration, inert artifacts, and manifest-last accounting are preserved. A challenge-contract change produces `SOURCE_CONTRACT_CHANGED`.

- [ ] **Step 3: Run authentic HKeL, Judiciary, and HKEX baseline-window probes**

Run:

`python3 -m tools.hk_v1_source_admission --matrix packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json --mode execute --source-family HKEL --output-root var/hk-v1/source-admission/hkel`

Run:

`python3 -m tools.hk_v1_source_admission --matrix packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json --mode execute --source-family JUDICIARY --output-root var/hk-v1/source-admission/judiciary`

Run:

`python3 -m tools.hk_v1_source_admission --matrix packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json --mode execute --source-family HKEX --output-root var/hk-v1/source-admission/hkex`

Expected: every source role returns a complete terminal result or an exact blocking failure. Preserve response bytes, request facts, locator bindings, hashes, timestamps, and attempt reports in the primary vault and read every retained object back.

- [ ] **Step 4: Run the repeated due-cycle proof**

Run one changed cycle, one genuine no-change cycle, one forced truncated traversal, one source outage, and one worker restart. Expected: only the genuine no-change cycle reports no change; every other case remains distinct and fail-visible.

- [ ] **Step 5: Freeze admitted evidence and run the complete shipping gate**

Update only evidence references, register states, revisions, and fingerprints; never commit authentic corpus bytes. Run:

`python3 -m tools.dev_test --uv /home/docpro/.local/bin/uv --node /home/docpro/.local/bin/node`

Expected: complete shipping gate passes. Record exact external hosts accessed and outcomes in `.agent/WORKING_STATE.md`. Request explicit commit authority before creating the Plan 2 checkpoint.
