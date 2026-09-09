# Hong Kong Live V1 Execution Specification

Status: written specification approved by the user
Date: 2026-08-25

## 1. Purpose

This specification defines the first continuously operating Hong Kong V1 of
the AskLegal Legal Database Pipeline. It narrows the broader accepted design to
one executable local POC target without changing the five-application trust
model, strict model-output validation, evidence-before-success rule, or
Approval-before-promotion rule.

V1 is not a one-time corpus build. It continuously observes admitted official
sources, prepares complete updates, waits for a local named-human decision, and
automatically promotes an approved replacement Pinecone index.

This specification does not authorize implementation, source access, provider
calls, Pinecone mutation, host mutation, commit, or push. Those actions remain
separately gated.

## 2. Settled V1 product scope

V1 contains:

1. all three accepted Hong Kong Legislation Release Scopes:
   - `HK-LEG-ORDINANCES`;
   - `HK-LEG-SUBSIDIARY`;
   - `HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS`;
2. proposition-level Hong Kong Cases coverage for every official listing in
   the accepted binding-court families from 1 July 1997 onward;
3. current HKEX Main Board and GEM Listing Rules as Hong Kong Regulatory
   Materials; and
4. one complete current-serving Hong Kong Pinecone index containing the exact
   approved composition of those scopes.

V1 excludes:

- Hong Kong Principles. The user will provide reference-publication text after
  V1; that material requires its own later source, rights, identity, rulebook,
  and admission design;
- all Hong Kong Cases before 1 July 1997, including pre-handover superior-court
  and Privy Council material;
- full judgments as searchable records;
- general HKEX guidance and policy outside the accepted Main Board and GEM
  Listing Rule component universe;
- Ask.Legal application routing and query integration;
- Ask.Legal administration-portal integration; and
- Azure application hosting.

The honest V1 label is **complete Hong Kong legislation, post-1-July-1997
binding-case propositions, and HKEX Listing Rules POC**. It is not the broader
four-family complete Hong Kong jurisdiction defined by the initial design
because Principles is deferred.

## 3. Definition of a working live V1

V1 is complete only when all of the following are true:

- the formal admission result is `V1_ADMITTED`;
- the local Ubuntu stack runs continuously under systemd;
- all due official sources are observed on schedule;
- a genuine no-change cycle completes without model, embedding, proposal, or
  Pinecone work;
- a changed cycle autonomously acquires evidence, processes all affected
  scopes, constructs complete releases, and creates one reviewable proposal;
- the proposal may wait safely for the user to review it locally;
- a valid local Approval automatically starts promotion without a second
  command or approval;
- promotion builds a complete replacement Pinecone index, reads back every
  record, verifies backups, and records the new Serving State;
- the previous verified index remains protected for rollback;
- failures never become false no-change or success outcomes;
- the stack survives reboot and resumes schedules and durable work safely; and
- one scheduled no-change cycle and one scheduled changed-and-approved cycle
  pass after reboot.

Because Ask.Legal query integration is excluded, activation means that the
Management Register's current verified Serving State references the approved
complete Pinecone index. It does not mutate an Ask.Legal application route.

## 4. Program architecture and dependency order

V1 follows a hybrid critical-path plan:

1. freeze coverage, authority, cutoffs, and exclusions;
2. admit all required official-source procedures;
3. build the real Legislation, Cases, and HKEX packages as separately testable
   workstreams after their source contracts stabilize;
4. admit exact model, embedding, tokenizer, evaluation, cost, and Pinecone
   profiles;
5. compose the real Approval-bound promotion path;
6. reconcile the continuously operating Ubuntu host; and
7. build, approve, activate, roll back, restore, and update the complete
   baseline.

The three legal-package workstreams may progress independently, but no complete
Hong Kong proposal exists until all required scopes have one valid complete
release or one explicit accepted unavailable-scope disposition.

Every checkpoint must be reviewable and independently testable. A later stage
cannot substitute an enable flag, placeholder fingerprint, or connectivity
result for an earlier admission artifact.

## 5. Coverage and cutoff contract

One fingerprinted V1 Coverage Matrix must name every:

- Release Scope;
- source role and exact fact authority;
- owner;
- baseline cutoff;
- earliest supported boundary;
- monitoring cadence;
- technical and rights admission state;
- release-blocking consequence; and
- explicit exclusion and public-facing limitation wording.

The first baseline uses one common observation cutoff selected and frozen when
the admitted baseline run begins. Ordinary cycles use their own durable cycle
cutoff and compare against the last approved Serving State.

Cases use 1 July 1997 as the inclusive earliest V1 decision date. The official
listing boundary still requires every entry from that date onward to receive
one acquisition and processing disposition. A valid zero-proposition judgment
is a complete accounted outcome.

Legislation search contains supported operative current law at the cycle
cutoff. Uncommenced material remains in the Waiting Room; past and ceased
versions remain evidence and history rather than ordinary current-law records.

HKEX search contains the supported prevailing Main Board and GEM branches at
the cycle cutoff. Future, transitional, withdrawn, uncertain, and historical
branches remain separately accounted for.

## 6. Autonomous official-source acquisition

Every source procedure must have a registered endpoint contract, bounded
locator policy, schedule, completeness rule, retry and timeout profile, no-
change rule, immutable evidence flow, and explicit failure consequence.

### 6.1 GLD e-Gazette

GLD remains the originating and generally earliest official current Gazette
source. HKeL Gazette remains complementary backcapture, recovery,
reconciliation, and gap-detection evidence and cannot silently replace GLD.

The user reports that the Hong Kong Government granted the project permission
for the required automated use, including locally overcoming the public
Cloudflare/Turnstile access gate. No official API, allowlist, credential, or
other technical route is supplied. The actual authorization evidence must be
preserved and bound to the source admission before the connector is enabled;
the register must distinguish the user's report from independently verified
publisher authorization evidence.

The V1 GLD path must be fully autonomous and local-only:

- no manual download or challenge completion;
- no paid or remote CAPTCHA-solving service;
- no unofficial mirror as the current-publication authority;
- one isolated local Chromium/Patchright compartment owned by acquisition;
- only exact registered GLD hosts, methods, and paths;
- minimum protected session state required for unattended renewal;
- browser discovery/session establishment separated from preserved inert
  artifact capture wherever the public interface permits; and
- fail-closed source-contract review when the challenge or endpoint behavior
  changes.

Admission requires repeated unattended clean-session, renewal, expiry,
challenge-change, complete enumeration, artifact capture, retry, no-change,
restart, and failure tests for every required Gazette class. Inability to
traverse the public access flow blocks that due cycle.

### 6.2 HKeL

HKeL acquisition must preserve authentic:

- complete current inventory;
- English and Traditional Chinese XML;
- XSD/schema and publication-specification bundles;
- verified or assisted official copies;
- Editorial Records;
- required past inventory/data for reconciliation; and
- Gazette backcapture inventories and artifacts.

Synthetic ADR 0040 and reconstruction fixtures cannot admit real parsing.
Authentic XML/XSD/PDF/specification bytes must lead the parser, renderer, and
evaluation work.

### 6.3 Judiciary Cases

The official Judiciary procedure must enumerate and account for every in-scope
official listing from 1 July 1997. It preserves judgments, opinions,
corrections, reissues, languages, official translations, aliases, proceeding
identifiers, and exact source inventory evidence.

HKLII remains non-controlling discovery and discrepancy evidence. It cannot
prove official completeness or replace a missing required Judiciary artifact.

### 6.4 HKEX

HKEX uses the accepted lean five-role source register and exact declared
official products. Broad website crawling is excluded. The source inventory
must completely account for Chapters, rules, notes, appendices, Practice
Notes, Regulatory Forms, Fees Rules, and explicit exclusions for both boards.

### 6.5 Shared cycle completion

A source cycle succeeds only when every due release-blocking role has one
complete terminal outcome. Missing pages, truncated traversal, expired
sessions, contract drift, language mismatch, hostile content, ambiguous not-
published results, or absent required artifacts stay distinct and cannot be
collapsed into no change.

## 7. Real legal-package behavior

### 7.1 Legislation

The real package produces complete releases for all three accepted scopes. One
searchable record contains aligned English and Traditional Chinese content for
the same Legal Location, Official Version, and operative state.

The package applies the already accepted publication, commencement,
cessation/revival, amendment, correction, editorial-event, reconstruction,
known-stale, canonical rendering, partition, identity, and release-accounting
rules to authentic evidence.

It never infers commencement from publication alone, constructs consolidated
text from an amending instruction without the accepted reconstruction path, or
serves a required bilingual location with one missing or mismatched language.

### 7.2 Cases

The real package accounts for every in-scope official listing but indexes only
supported proposition-level legal analysis. Full judgments remain evidence.

The authoritative judgment passages and exact locators are always preserved.
The proposition wording may be faithfully summarized or distilled where that
improves legal analysis. Exact quotation is required only when the legal meaning
depends on the precise wording. A distilled proposition must preserve the
court, opinion path, authority role, qualifications, exceptions, result,
meaning, and exact support and must not broaden, omit, or manufacture the
court's reasoning.

The package completes proposition extraction, zero-proposition accounting,
corrections, later-treatment discovery and classification, current-authority
treatment graph construction, authority-note selection, immutable
retirement/reselection, and complete release accounting.

### 7.3 HKEX

The real package creates separate complete Main Board and GEM releases. It
decides prevailing state per exact applicability branch, preserves component
continuity, constructs source-faithful English records, retains minimum
governing context, and accounts for tables, fees, Forms, cross-references,
Waiting Room, history, uncertainty, and Quarantine.

Traditional Chinese is used for discrepancy detection and compact cross-
language retrieval evaluation. The serving record remains English.

### 7.4 Shared release behavior

- unchanged scopes reuse the exact previous release;
- changed scopes create complete replacements, not deltas;
- every source item has one disposition;
- register-issued identity and exact payload continuity govern reuse and
  lineage;
- uncertainty is visible and cannot become retirement or a false zero;
- complete Record Traceability Lookup shards bind every selected record to its
  evidence, legal decisions, rendering, identity, scope, and release; and
- no package becomes `READY` from source-neutral fixtures alone.

## 8. Models and compact V1 evaluation

Deterministic handling remains the default. Models are used only for the
accepted Gazette, reconstruction, Case proposition, Case treatment, and change-
gated HKEX semantic tasks.

Every admitted model call binds one exact deployment/model version, prompt,
schema, evidence budget, tokenizer, retry/timeout rule, quota, cost limit, data-
handling profile, and expiry. Model output is strictly decoded; extra, missing,
unknown, unsupported, or malformed content is rejected rather than repaired.

V1 evaluation is intentionally compact:

- one fixed representative golden set for Legislation, Gazette, Cases, and
  HKEX;
- English, Traditional Chinese, bilingual, and a small cross-language query
  slice;
- exact pass/fail checks for schema, evidence, citation, attribution,
  qualifications, and forbidden broadening;
- one simple top-results retrieval check for each golden query;
- a short local report containing failures and sample outputs; and
- one clean repeat run to expose unstable behavior.

V1 does not require a research-grade benchmark, complex statistical scoring,
large blinded-review program, or dual-attestation ceremony.

The following remain zero-tolerance admission failures:

- invented or unsupported evidence or citation;
- malformed output;
- wrong court, opinion, or authority attribution;
- materially broadened or incomplete legal meaning;
- incomplete bilingual legislation;
- cross-case/reference leakage; and
- unapproved model, prompt, tokenizer, embedding, or target drift.

The exact embedding and Pinecone profiles must cover the six-field serving
payload, dimension, metric, project/index naming, capacity, cost, timeout,
outage, backup, and complete read-back behavior.

## 9. Local Review and Approval

The Review interface runs locally on the Ubuntu host. A changed valid cycle
automatically prepares one immutable proposal and report showing:

- source changes and completeness;
- additions, replacements, carry-forwards, withholdings, and retirements;
- Quarantine, Waiting Room, and Coverage Gaps;
- per-scope release and record counts;
- compact model/retrieval evaluation results;
- exact model, embedding, and Pinecone profiles;
- expected provider cost; and
- backup and rollback readiness.

The proposal may wait indefinitely for the user, subject to its manifest
validity predicates. The user approves or rejects the whole proposal locally.
Partial approval is excluded.

Approval automatically wakes the Promotion worker. Promotion first re-reads
the complete immutable package and current authority/capability evidence. A
material source, profile, base-index, evidence, recovery, manifest, or authority
change invalidates the waiting proposal and causes a new proposal rather than
promotion of stale work.

No second command or second approval is required after a valid Approval.

## 10. Approval-bound promotion

After valid Approval, the Promotion worker autonomously:

1. consumes the exact Approval for one execution lineage;
2. validates every manifest action and current capability profile;
3. obtains embeddings;
4. creates a complete replacement Pinecone index;
5. writes the exact Desired-State Inventory;
6. reconciles ambiguous acknowledgements through full read-back;
7. enumerates and compares every ID, vector, and six-field payload;
8. creates and independently verifies provider-native and separate recovery
   evidence;
9. records the new current Serving State; and
10. protects the predecessor for rollback.

An unapproved or invalidated proposal cannot call embeddings or mutate
Pinecone. Before current-state change, every failure leaves the predecessor
current. A failure after state change follows the exact approved reverse-state
operation and preserves complete receipts.

Because Ask.Legal routing is excluded, the V1 Promotion Manifest contains no
Ask.Legal application-setting or slot-swap action. The local Serving State
transition is the complete-index activation boundary.

## 11. Continuous Ubuntu operation

The five applications, SQL Server, two Durable Task scheduler instances, two
vault gateways, three egress proxies, and telemetry collector run under the
declared systemd target.

V1 host admission requires:

- no `acq-batch`, `cp-test`, or other unsupervised pipeline container;
- all five current application images deployed by immutable identity;
- rotated sealed credentials with obsolete plaintext staging removed and old
  values proved unusable;
- the five declared timers installed for ordinary observation, full
  reconciliation, audit archive, recovery verification, and telemetry
  retention;
- daily ordinary source observation;
- weekly full reconciliation and health reporting;
- exact non-overlap, catch-up, shutdown, and missed-run behavior;
- basic local metrics, traces, audit events, dashboards, and alerts for source,
  workflow, coverage, model, provider, storage, and promotion failures;
- bounded CPU, memory, disk, log, and evidence-retention behavior;
- SQL and vault backup/restore proof;
- independent scheduler replacement proof;
- local Review authentication;
- no-secret logging; and
- successful full-stack reboot recovery.

The Ubuntu implementation plan owns the exact `OnCalendar` times and may set
them only once source rate policies, expected cycle duration, backup windows,
and local capacity observations are recorded. The frequencies and non-overlap
requirements above are fixed by this specification.

## 12. Failure and recovery rules

The system must keep these outcomes distinct:

- genuine no change;
- not published;
- source unavailable;
- source-contract drift;
- incomplete inventory/window;
- hostile or unsupported content;
- legal uncertainty;
- model/provider outage;
- malformed or unsupported model result;
- embedding or Pinecone acknowledgement unknown;
- target mismatch;
- backup/recovery failure;
- stale or invalid Approval; and
- post-activation verification failure.

No timeout, empty page, silence, aggregate count, model confidence, or remote
acknowledgement proves completeness by itself.

The previous verified Serving State remains current unless an exact approved
replacement passes all pre-state-change checks. Recovery and rollback are
exact, predecessor-bound, independently verified, and never use broad deletion.

## 13. Verification and acceptance gates

### Gate A — coverage

The fingerprinted Coverage Matrix matches this specification and every V1
source, scope, cutoff, owner, exclusion, and limitation.

### Gate B — official sources

GLD, HKeL, Judiciary, and HKEX each complete repeated unattended acquisition,
no-change, retry, restart, incomplete, and contract-drift proofs with authentic
preserved evidence.

### Gate C — legal packages

All three Legislation scopes, every in-scope Case listing, and both HKEX boards
produce complete release accounting from authentic evidence. Every required
package is `READY`.

### Gate D — models and retrieval

The compact golden evaluation passes twice under exact immutable model,
embedding, tokenizer, prompt, cost, quota, and Pinecone profiles.

### Gate E — Review and promotion

A proposal can wait, become invalid when its facts drift, or be approved later.
Valid Approval automatically starts promotion. Complete read-back, backup,
current-state transition, failure stop, and rollback pass.

### Gate F — host

The supervised, current, credential-rotated, scheduled, observable stack passes
resource, backup/restore, scheduler replacement, local Review authentication,
and reboot proof with no orphan process.

### Gate G — complete live baseline

One common-cutoff baseline is acquired, processed, reviewed, approved, embedded,
fully read back, backed up, and recorded as current. The predecessor rollback
and restoration pass. After reboot, one scheduled no-change cycle and one
scheduled changed cycle that waits for later local Approval both complete, and
the next scheduled cycle remains healthy.

## 14. Plan decomposition

Following the user's written-spec approval, this design is implemented through nine dependency-
linked plans:

The executable plan index is
[`docs/superpowers/plans/2026-08-25-hk-v1-plan-index.md`](../superpowers/plans/2026-08-25-hk-v1-plan-index.md).

1. scope, authority, and documentation reconciliation;
2. autonomous official-source acquisition;
3. authentic Hong Kong Legislation admission;
4. post-1-July-1997 Hong Kong Cases admission;
5. authentic HKEX Main Board and GEM admission;
6. compact model, embedding, retrieval, and Pinecone admission;
7. local Review and Approval-bound real promotion;
8. continuous Ubuntu host reconciliation and operation; and
9. complete baseline, rollback, reboot, and scheduled live acceptance.

Plans 3, 4, and 5 may execute independently after Plan 2 freezes their source
contracts. Plan 6 consumes the real record and evaluation shapes from those
packages. Plans 7 and 8 may prepare disabled local composition but cannot enable
provider effects until Plan 6 passes. Plan 9 consumes every prior gate.

Each plan must name exact files, interfaces, tests, commands, artifacts,
authorization gates, checkpoint commits, and exit evidence. It must use failing
tests before implementation and the complete shipping gate before claiming its
checkpoint complete.

## 15. Authorization gates

This specification records product intent but does not grant the following
actions:

- external official-source access;
- accepting external terms or consent;
- model or embedding calls;
- Pinecone reads or writes;
- live SQL migrations;
- stopping or replacing current services;
- credential rotation;
- host deployment or reboot;
- commit, push, or remote change.

Each such action requires the exact authority applicable to its implementation
checkpoint. The reported GLD permission still requires preserved evidence and
source admission before technical enablement.

## 16. Documentation reconciliation required by Plan 1

Plan 1 must reconcile every older statement that conflicts with this approved
scope, including:

- Principles as a V1 blocker;
- pre-1997 Case families as V1 requirements;
- Ask.Legal routing as the V1 activation boundary;
- manual GLD as an acceptable V1 procedure;
- the earlier prohibition on any GLD Turnstile traversal, superseded by the
  user's later reported government permission and fully autonomous requirement;
- research-grade or dual-attestation evaluation ceremony beyond the compact V1
  gate;
- stale test/file counts and migration descriptions; and
- static host descriptions that do not distinguish the currently running but
  non-admitted stack.

Superseded decisions must remain historically visible and be marked as such;
they must not be silently deleted.
