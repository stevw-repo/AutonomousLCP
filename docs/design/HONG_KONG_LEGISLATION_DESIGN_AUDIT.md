# Hong Kong Legislation Design Audit

Status: complete policy audit, amended by ADRs 0079 through 0087

Audit date: 2026-08-12
Scope: Hong Kong Legislation only; no implementation or production operation

## Plain-language conclusion

The Hong Kong Legislation design is internally coherent after the corrections
recorded below. It is complete enough at the **policy-architecture level** for
the Ordinances and subsidiary-legislation scopes: the design says what is
covered, which evidence proves which facts, how current records are built, how
uncertainty is handled, and what must be tested.

That does **not** mean the software is ready to build or operate. The exact
machine schemas, synthetic fixture files, validators, source connectors,
authority-note templates, operational values, and cross-system contracts still need
to be produced. The constitutional-and-other-instruments scope is also
deliberately not policy-complete because the user deferred a full review of
HKeL's Instruments & Others and its row-level disposition registry.

In short:

| Question | Audit answer |
|---|---|
| Is the Hong Kong policy architecture coherent? | Yes, after the documented corrections |
| Are Ordinances and subsidiary legislation policy-complete? | Yes, subject to executable specification and implementation |
| Is the constitutional-and-other-instruments scope complete? | No; it is correctly marked `NOT_READY` pending the deferred review |
| Is the complete pipeline implementation-ready? | No |
| Did the audit invent a new legal-policy choice? | No |

## What the audit checked

The audit traced the Hong Kong design from source discovery to release
eligibility:

1. coverage and Release Scope ownership;
2. Registered Sources, source roles, monitoring, freshness, and outages;
3. HKeL bilingual XML and matching verified or assisted official HKeL copies;
4. Gazette events, HKeL consolidation, past data, Editorial Records, and
   excluded LegCo material;
5. first-baseline and ordinary-update rules;
6. legal status, Waiting Room, evidence-only, historical, Quarantine, and
   Coverage Gap behavior;
7. bilingual text, authority notes, splitting, identity, lineage, and traceability;
8. complete release accounting and the boundary before promotion;
9. conceptual fixtures, strict fixture packages, rulebook packaging,
   readiness, and conformance attestation; and
10. generative-LLM, deterministic, Legal Desk, and human authority boundaries.

The original audit compared the canonical design, ADRs 0018 through 0044, and
all three agent continuity files. ADRs 0079 and 0081 later kept warned latest
applicable official HKeL text
searchable during a consolidation gap. ADR 0080 then superseded the audit's
reconstruction prohibition and made exact warned reconstruction the preferred
result, with ADR 0079 as fallback. ADR 0082 fixes the closed deterministic
operation registry, and ADRs 0083, 0086, and 0087 freeze its current 63-case and
35-pair conformance extension. ADR 0084 fixes the strict Plan and Execution Report contracts. The
ADR 0085 fixes the immutable bilingual artifact, derivation-map, coverage-proof,
and ordinary-renderer boundary. ADR 0086 fixes later-HKeL monitoring,
comparison, replacement, mismatch attribution, suspension, and restart. ADR
0087 fixes the capability-attestation, activation, and promotion boundary. The
frozen 121-case suite remains the executable pre-reconstruction baseline and
does not by itself prove this new capability.

## Corrections made by the audit

### 1. Final LLM allocation now uses a bounded hybrid boundary

Some documents treated two case-law model tasks as finally enabled and Hong
Kong Legislation as permanently non-generative. The user's later direction was
to decide the exact deterministic-versus-LLM split later, including Gazette
and Legal Desk support.

ADR 0043 originally made those task names candidates rather than
implementation authority. Decision 7 now admits Gazette-event and
Reconstruction Plan semantic decision/challenge stages while retaining the
sole model gateway, deterministic checks, human handling of unresolved cases,
and complete task-admission requirements. No provider capability is enabled.

### 2. Result types are no longer mixed together

ADR 0033 used the word “outcome” for several different concepts. ADR 0044 now
keeps them separate:

- processing: `PASS`, `BLOCK`, or `QUARANTINE`;
- legal disposition: current, Waiting Room, evidence-only, historical, or
  Quarantine, when that gate actually decides it;
- coverage: exact Coverage Gap or none;
- Source Contract Review: required or not;
- record output: exact records or none; and
- workflow or reason code: what happened and what path follows.

This prevents mistakes such as treating `PASS` as “searchable current law,”
treating a Coverage Gap as legal status, or treating
`SUPPORTED_NO_CHANGE` as another legal disposition.

### 3. Observation-failure test coverage is complete

`HKLEG-CURRENT-OBS-003` had two defined branches but no direct conformance
case. ADR 0044 adds:

- `HKLEG-CURRENT-CASE-017` — a release-blocking current inventory or Gazette
  Observation remains unavailable after retries; and
- `HKLEG-CURRENT-CASE-018` — one item-specific source fails while independent
  affected work remains complete.

The frozen pre-reconstruction package binds 89 reconciliation fixtures, 18
ordinary-update cases, and 14 baseline cases: **121 exact tests**. ADR 0080's
extension remains to be frozen.

### 4. Stale “still open” wording is classified accurately

Older ADR consequences still called splitting, rule IDs, conformance design,
and package architecture open even though ADRs 0033 through 0042 settled them.
Those statements now distinguish settled design from exact implementation
artifacts and deliberately deferred decisions.

## Settled Hong Kong Legislation design

| Area | Settled design |
|---|---|
| Coverage | Three non-overlapping Release Scopes; legal-nature routing prevents HKeL categories or A-numbers from creating duplicate ownership |
| Ordinary serving unit | One Search Record per supported Legal Location, containing both authentic English and Traditional Chinese in `metadata.text` |
| Authority-note channel | Required English-only `metadata.authority_note`; exact `"None"` when no note applies; controlled warning clauses precede any material support clauses; the note is not embedded |
| Evidence | Matching bilingual HKeL XML constructs the record; matching official bilingual verified or assisted HKeL copies support applicable text and version under ADR 0081; a newer complete assisted version need not wait for an older verified one |
| Gazette | Exact event evidence proves an event; it does not become consolidated serving text |
| Reconstruction | ADR 0080 permits exact deterministic bilingual reconstruction from a complete applicable HKeL base supported by verified or assisted copies and a proved operative amendment chain; ADR 0082 limits execution to eight closed source-backed operation classes with atomic bilingual failure; ADRs 0084 and 0085 fix immutable Plan, Report, final artifact, derivation, and rendering-input contracts; ADR 0086 fixes later-HKeL replacement, comparison, mismatch suspension, and restart; ADR 0087 requires exact capability attestation and candidate-processing activation without bypassing promotion Approval; the record uses ordinary legislation serving behavior with the mandatory warning, and ADR 0079 is the fallback |
| History | HKeL past data is on-demand evidence for a named question, not routine replay; the first baseline proves present state without inventing complete history |
| Editorial changes | HKeL Editorial Records prove their assigned official editorial events but do not replace current bilingual evidence |
| LegCo | Bills and proceedings are excluded from automated ingestion and serving; optional human research is non-controlling |
| Monitoring | Daily lightweight current-law signals, weekly supporting sources, monthly/event cross-checks, and on-demand large or historical artifacts |
| Current update | Stable ordered rules cover observation, evidence, difference, cause, event-before-consolidation, disposition, record construction, and complete release accounting |
| First baseline | Complete current inventory at one cutoff; clear present state may pass without replaying history; uncertainty opens a bounded investigation |
| Status | Current, Waiting Room, evidence-only, historical, and Quarantine are distinct; a Coverage Gap is separate |
| Identity | Opaque register-issued Legal Item, Official Version, Legal Location, and Search Record identities; source labels are aliases; serving changes create lineage rather than overwrite |
| Splitting | Official bilingual structure, recursive fit checks, dependency closure, canonical grouping, and exact source-unit coverage; no arbitrary token or sentence chopping |
| Conformance | 89 strict hashed reconciliation packages, 18 ordinary-update cases, and 14 first-baseline cases form the 121-case ordinary baseline; ADRs 0083, 0086, and 0087 add 63 direct reconstruction cases and 35 controlled pairs, making 184 direct cases for a reconstruction-enabled profile |
| Rulebook | One immutable `hk-legislation` policy package with per-scope readiness, exact locks, validation, activation lineage, impact declaration, and build attestation |
| Production boundary | Processing creates candidates only; it cannot approve, embed, mutate Pinecone, or deploy |

## Work still required before implementation can be claimed ready

These are specification or implementation artifacts, not missing policy
choices:

- strict machine-readable schemas for the rulebook, rule objects, code
  catalogues, decisions, traceability, fixtures, expected results, and the now-
  specified Reconstruction Plan and Execution Report contracts;
- the actual 121 pre-reconstruction synthetic test packages and their byte-
  level expected artifacts, plus executable packages, fixture bytes, and
  expected artifacts for ADR 0083's frozen reconstruction catalogue;
- semantic validators, deterministic renderers, XML/PDF reconciliation,
  bilingual alignment, status mapping, partitioning, and coverage-proof code;
- exact controlled-English authority-note templates and stable reason-code entries
  that implement the accepted meanings;
- source connectors, endpoint discovery, health checks, bounded retries,
  clock times, backoff, timeouts, and provider-throttling values;
- the pinned multilingual embedding model, tokenizer, token ceiling, metadata
  byte ceiling, and canonical serialization;
- the exact six-field Serving Record Contract values and the internal Record
  Traceability Lookup encoding; and
- a processing build plus a successful Rulebook Conformance Attestation.

Producing these artifacts requires explicit implementation authorization. The
current design-only authorization does not permit it.

## Closed exclusions and admission gates

These items no longer leave the current engineering design open:

| Item | Closed current behavior |
|---|---|
| Full HKeL Instruments & Others review and row-level Instrument Disposition Registry | Constitutional-and-other-instruments stays disabled and `NOT_READY`; enabling it requires a later package decision and complete registry |
| Unallocated generative tasks | Proposed default is `NO_GENERATIVE_LLM`; user decision remains required before this is closed |
| Query-facing dates and recency search | Excluded from the current product design; no serving date field or temporal ranking behavior |
| HKLII registration | ADR 0045 registers it as non-controlling Hong Kong Cases discovery evidence; it is not controlling Hong Kong Legislation evidence |
| Production Azure routing and final index-name contract | Decision 4 selects separate candidate-slot routing and decision 5 fixes the index-name format; neither is a Hong Kong legal-rulebook choice |
| Source-specific legal-compliance controls | Required package admission evidence owned by the legal team; missing evidence keeps the source disabled |

## Cross-cutting admission dependencies, not Hong Kong design defects

Hong Kong candidates can be specified and tested against the proposed ADR 0099
protocols, but those protocols require user acceptance and production cannot
be called ready until the relevant profiles
and evidence below are populated and proved:

- Ask.Legal's implemented and proved fingerprint-bound coverage consumption;
- implemented production Serving Record and traceability encodings;
- named assignments and end-to-end proof for the single human
  `PipelineAdministrator` role;
- named Quarantine assignments and the optional-due-time/re-entry policy;
- backup isolation, key recovery, retention, restore targets, and drills;
- anomaly, cost, capacity, security, service-level, and deletion policies; and
- measured Azure production-candidate activation and complete routing-
  generation proof under an accepted ADR 0099 mechanism.

## Readiness verdict by Release Scope

| Release Scope | Policy architecture | Rulebook decision readiness today | Reason |
|---|---|---|---|
| `HK-LEG-ORDINANCES` | Complete | Can become `DECISION_READY` only after executable artifacts and conformance attestation exist | No unresolved Hong Kong policy choice found by this audit |
| `HK-LEG-SUBSIDIARY` | Complete | Can become `DECISION_READY` only after executable artifacts and conformance attestation exist | No unresolved Hong Kong policy choice found by this audit |
| `HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS` | Incomplete by explicit deferral | `NOT_READY` | Mandatory Instruments & Others review and row-level registry work remain open |

## Audit boundary

This audit changes documentation only. It performed no source access, model or
embedding call, dependency installation, release publication, Pinecone or
backup mutation, deployment, Azure change, routing change, commit, push, or
other remote action.
