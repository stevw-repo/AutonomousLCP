# AskLegal Legal Database Pipeline — Delivery Roadmap

Updated: 2026-08-21

## Purpose

This is the durable overall progress plan for turning the accepted pipeline
design into a locally proved and locally operated V1, with separately gated
later cloud deployment. It tracks delivery state and dependency order; it does
not replace the canonical overall design, ADRs, or the exact current handoff in
`WORKING_STATE.md`.

This roadmap contains no delivery-date estimate and grants no implementation
or operational authorization. Each implementation, external integration,
cloud proof, and production action remains separately gated.

## V1 target — single-Ubuntu-host internal POC

V1 is a **strictly internal POC**, not an Azure-hosted deployment:

- development is shifting to the Ubuntu machine — from 2026-08-18 the user
  expects to do significant parts of development there, without retiring the
  Mac — while all five applications run continuously on one Ubuntu 24.04
  x86-64 PC; the Mac is not a runtime dependency;
- SQL Server 2025 Developer, two Durable Task Scheduler emulator instances,
  two Versity Gateway vault instances, secrets, and monitoring run on Ubuntu;
- hosted Pinecone Cloud in a dedicated isolated POC project supplies the
  replaceable vector-serving copy;
- controlled outbound access to admitted official legal-source endpoints is
  allowed;
- controlled outbound calls to separately admitted hosted model and embedding
  APIs are allowed; and
- Azure application hosting is outside V1.

Products and the exact disabled service topology are selected. Static topology
and read-only host-admission policy contracts now pass locally, but exact
tested image versions/digests, Ubuntu package locks and host facts, private
subnets, Pinecone plan/endpoints, credentials, and admission evidence remain
implementation work. Azure M8 is post-V1/deferred. This direction authorizes no
deployment or external effect; explicit authorization is required before the
first real Pinecone write.

## Full Hong Kong local V1 exit checklist

This is the dependency-ordered checklist for the user's 2026-08-21 target: one
working Hong Kong jurisdiction on the local Ubuntu host. “Full Hong Kong” uses
the accepted project scope, not every document produced by every Hong Kong body:

- **Hong Kong Legislation:** the three accepted complete scopes—Ordinances,
  Subsidiary Legislation, and Constitutional and Other Instruments;
- **Hong Kong Cases:** proposition-level coverage for the accepted binding-court
  families and separately accountable accepted historical courts;
- **Hong Kong Regulatory Materials:** current HKEX Main Board and GEM Listing
  Rules, excluding general guidance and policy; and
- **Hong Kong Principles:** only complete publisher-backed scopes with selected
  sources and continuing rights.

If Hong Kong Principles is omitted because no publisher/source/licence is
selected, the result may be called a complete primary-law, binding-cases, and
HKEX V1, but not the complete Hong Kong jurisdiction defined by this design.
Azure application hosting and the Ask.Legal admin portal remain outside this
local V1. The five applications, SQL, schedulers, vault gateways, and monitoring
run locally; approved official sources, Azure model/embedding deployments, and
the isolated Pinecone POC target remain external dependencies.

### HKV1-0 — Freeze scope and source authority — IN PROGRESS

- [x] Preserve the accepted four Hong Kong material families and their existing
  coverage boundaries.
- [x] Retain direct GLD e-Gazette as V1's originating and earliest official
  Gazette publication source; retain HKeL Gazette as backcapture, recovery,
  reconciliation, and gap-detection evidence.
- [x] Preserve the rule that Cloudflare Turnstile, CAPTCHA, and terms gates will
  not be bypassed. Source inclusion is not technical admission.
- [ ] Admit a lawful repeatable GLD acquisition procedure, or an explicitly
  approved bounded manual procedure, with exact artifact, completeness,
  no-change, retry, and failure evidence for every required Gazette class.
- [ ] Prove complete reproducible HKeL inventory coverage for its declared
  recovery/backcapture classes and make every mismatch or missing expected GLD
  artifact a release-blocking gap; do not claim HKeL is the complete current
  Gazette feed.
- [ ] Reconcile ADRs 0025 and 0032, the overall design, source rulebook,
  monitoring cadence, and coverage semantics with the retained GLD primary role
  and HKeL recovery/backcapture role.
- [ ] Freeze one explicit baseline cutoff and earliest supported historical
  boundary for each material family and Release Scope.
- [ ] Freeze every deliberate V1 exclusion and the exact report wording that
  prevents “full Hong Kong” from overstating coverage.

Exit gate: one fingerprinted Hong Kong coverage matrix names every Release
Scope, source role, fact authority, cutoff, owner, admission state, and explicit
exclusion, with an admitted GLD current-publication path and no assumed HKeL
substitution.

### HKV1-1 — Restore trustworthy engineering gates — NOT READY

- [x] Locked Python 3.14.7, Node 24.19.0, uv 0.12.5, workspace packages,
  architecture rules, and ordinary tests exist.
- [x] Current ordinary developer suite passes: 856 passed, 4 skipped on
  2026-08-21.
- [ ] Clear strict Pyright or replace debt with a narrow reviewed exception
  register that cannot grow silently; current result is 856 errors, including
  665 across tracked Python files. The other 191 are ignored local runtime
  files under `var/`.
- [ ] Resolve the 13-file formatting drift without introducing Python 3.14-only
  syntax into Python 3.12 host entrypoints.
- [ ] Make the ordinary shipping command run strict Pyright, Ruff lint, safe
  formatting/grammar checks, architecture/boundary checks, generated-file drift,
  contracts, and the full suite.
- [ ] Add repository CI for the same locked gates; a local green run must not be
  the only release protection.
- [ ] Make `asklegal-local prove --all` safely rerunnable or fail with an explicit
  reset-required result rather than an unhandled `FileExistsError`.
- [ ] Re-run the dedicated SQL Server, Durable Task emulator, package, and image-
  admission proofs in their intended environments.

Exit gate: a clean checkout passes one documented complete shipping command and
CI reproduces it with no unregistered type, lint, format, contract, architecture,
test, package, or image-admission failure.

### HKV1-2 — Close live source-acquisition defects — NOT READY

- [x] Exact versioned direct-HTTP endpoint contracts, TLS validation, byte/media
  limits, hostile-content classification, and immutable vault retention exist.
- [x] HKeL Gazette discovery, session establishment, locator construction,
  inert PDF capture, listing manifest, retry, and 2000–2026 archive have live
  evidence.
- [x] Gazette page-limit exhaustion and an empty intermediate page are explicit
  incomplete results; the worker enumerates the complete bounded listing before
  retaining artifacts or writing its manifest.
- [x] Enforce the redirect limit on the publisher-API `exchange` surface and
  prove a same-host loop stops with `REDIRECT_LIMIT_EXCEEDED`.
- [x] Replace weak template substitution with the exact bounded-locator contract
  everywhere publisher data contributes an artifact path.
- [x] Wire the exact registered complete-inventory procedure into a schedulable
  acquisition activity that derives its required member set, retains or isolates
  every response, writes attempt accounting last, and emits policy-bound coverage.
- [x] Wire ADR 0100's reviewed Patchright discovery into a schedulable activity
  that accepts no URL/policy override, retains only a sanitized request map and
  attempt report, and mechanically denies evidence, completeness, no-change,
  coverage-satisfaction, and processing authority.
- [x] Keep the sole `CATALOGUE_DISCOVERY` endpoint disabled with its owning
  official Gazette archive explicitly `OUT_OF_SCOPE_V1`.
- [ ] Wire every required browser-session source-evidence procedure for HKeL
  verified/assisted copies, Editorial Records, publication specifications, and
  GLD Gazette, or explicitly remove the corresponding material from V1. Patchright
  discovery cannot satisfy this item.
- [x] Separate `NOT_PUBLISHED`, source unavailability, contract drift, hostile
  response, and incomplete window in durable acquisition outcomes.
- [x] Retain canonical per-source coverage reports for every HKeL Gazette
  terminal result, and provide complete due-source cycle accounting that blocks
  missing or failed `RELEASE_BLOCKING` roles without upgrading `NONBLOCKING`
  discovery roles.
- [x] Wire the cycle report over every due V1 source activity and carry its exact
  references and release-blocking result into the final Coverage Status Manifest
  and release gate.
- [x] Clear the 40 focused connector/acquisition strict-type failures recorded
  after the second slice; the exact Gazette/acquisition/readiness surface now
  passes strict Pyright with zero errors.
- [ ] Complete duplicate-row, moving-`lastPage`, throttling, activity restart,
  lost-acknowledgement, and manifest-adoption proofs. Page 51, redirect-loop,
  bounded-locator, incomplete-window, and partial-publication outcomes are
  already covered.
- [ ] Prove source-specific polite rate, retry, timeout, and outage profiles
  against bounded observations without treating an outage as no change.

Exit gate: every enabled endpoint has one schedulable, bounded, evidence-
preserving procedure; every complete-inventory claim detects partial traversal;
and a full source cycle produces exact durable coverage accounting.

### HKV1-3 — Admit the Hong Kong Legislation package — NOT READY

- [x] Three non-overlapping scopes, 27 offline rules, strict package loader, and
  synthetic baseline/current-update fixtures exist.
- [ ] Complete and admit the exact current/past HKeL inventory/data, verified or
  assisted copy, Editorial Record, publication-specification, Basic Law, Annex
  III, and Instruments & Others evidence paths required by each scope.
- [ ] Complete bilingual XML/PDF identity, language/version matching, structural
  parsing, canonical rendering, official-location splitting, and real tokenizer
  measurement.
- [ ] Implement exact enactment, commencement, partial commencement, amendment,
  repeal/revocation/expiry/revival, correction, and editorial-event handling
  against preserved real evidence.
- [ ] Implement the accepted reconstruction and known-stale analytical fallback
  gates without presenting either as HKeL current official text.
- [ ] Build complete-universe baseline, ordinary update, no-change, quarantine,
  withholding, Waiting Room, identity continuity, disposition, release
  accounting, and Coverage Gap fixtures from adjudicated real reference truth.
- [ ] Freeze source-rulebook, deterministic renderer, semantic profiles/prompts,
  evaluations, owners, attestations, and activation fingerprint.
- [ ] Change all three scopes from `NOT_READY` only after their exact package
  admission checks pass.

Exit gate: all three Hong Kong Legislation Corpus Releases account for every
item at the frozen cutoff, contain only supported operative bilingual records,
and reproduce byte-identically from retained evidence.

### HKV1-4 — Build and admit Hong Kong Cases — NOT STARTED

- [ ] Create an executable Hong Kong Cases package; none exists today.
- [ ] Implement the official Judiciary judgment-listing source register and prove
  complete enumeration for CFA, CA, CFI, Competition Tribunal, and the accepted
  pre-1997 superior/Privy Council historical scopes.
- [ ] Preserve every listing, decision, official artifact, correction/reissue,
  alias, proceeding number, language, and official translation with exact
  accounting; use HKLII only as the accepted non-controlling cross-check.
- [ ] Implement deterministic identity, court/opinion structure, citations,
  passages, dossiers, duplicates, translations, and zero-proposition outcomes.
- [ ] Implement the admitted two-pass Case Proposition workflow and the separate
  later-treatment workflow with exact supporting passages, attribution,
  plurality/dissent handling, uncertainty, challenge, and legal review.
- [ ] Build the current-authority treatment graph, authority-note selection,
  exact retirement/reselection behavior, Quarantine, Coverage Ledger, and
  corpus-wide later-treatment reconciliation.
- [ ] Create protected evaluation suites, reference proposition maps, blinded
  adjudication, multilingual/cross-language retrieval tests, workflow profiles,
  repeated runs, and dual Legal Desk/system-owner attestations.
- [ ] Build and approve the first complete current-authority baseline; every due
  in-scope official listing must have an acquisition and processing disposition,
  even when it creates no Search Record.

Exit gate: every official listing in every promised court/year scope is
accounted for, every searchable proposition is supported by exact judgment
passages and current treatment evidence, and the Cases package is `READY`.

### HKV1-5 — Build and admit HKEX Regulatory Materials — NOT STARTED

- [ ] Create the executable Hong Kong Regulatory Materials package; none exists
  today.
- [ ] Implement and admit the accepted lean five-role HKEX source register and
  source-specific connectors without broad website crawling.
- [ ] Freeze complete Main Board and GEM Rule Component Inventories covering
  Chapters, rules, notes, appendices, Practice Notes, Regulatory Forms, Fees
  Rules, and explicit exclusions.
- [ ] Implement exact branch-level effective state, transitional/future material,
  publication evidence, approval inference, movement/renumbering, structure,
  identity, and component ownership.
- [ ] Implement deterministic English serving records, controlled authority
  notes, source traceability, scope isolation, Quarantine, and complete release
  accounting.
- [ ] Prove Traditional Chinese and cross-language query quality for the selected
  multilingual retrieval/answer workflow even though serving text is English.
- [ ] Freeze evaluations, model/embedding profiles, owners, legal/system
  attestations, and activate both Main Board and GEM scopes.

Exit gate: Main Board and GEM releases each completely account for their frozen
component universe and the Regulatory Materials package is `READY`.

### HKV1-6 — Select, build, and admit Hong Kong Principles — BLOCKED ON SCOPE

- [ ] Select the exact publisher-backed Hong Kong Principles titles and editions
  that define V1 coverage; no executable package or selected source universe
  exists today.
- [ ] Obtain and record continuing licence/rights terms, access method, update
  evidence, currency signals, and freeze-on-expiry behavior for each title.
- [ ] Create source registers/connectors and preserve complete publisher editions
  or rolling states with paragraph identity, moves, splits, merges, corrections,
  and edition continuity.
- [ ] Create the executable source rulebook, deterministic source-faithful
  renderer, complete scopes, fixtures, evaluations, owners, attestations, and
  activation package.
- [ ] Keep Principles separate from case-derived propositions and serve only
  publisher-supported `type: principle` records.

Exit gate: every selected publisher title is completely accounted for under a
current licence and the Hong Kong Principles package is `READY`. If no scope is
selected, rename the V1 claim rather than marking this milestone passed.

### HKV1-7 — Admit model, embedding, and retrieval profiles — NOT READY

- [x] Azure inference, Azure embedding, and the isolated Pinecone POC endpoints
  have passed bounded connectivity calls.
- [ ] Replace all zero/placeholder prompt, package, profile, serving-payload, and
  text fingerprints with exact immutable admitted values.
- [ ] Route only the accepted task allocations to models: deterministic handling
  by default, with separately admitted Gazette/reconstruction and Cases semantic
  workflows.
- [ ] Freeze exact Azure deployment/model versions, API contracts, prompts,
  schemas, tokenizers, budgets, retries, data handling, region, quota, cost, and
  expiry; reject aliases or runtime drift.
- [ ] Build protected legal-semantic evaluation packages and pass every critical,
  language, material, uncertainty, evidence, and adversarial slice.
- [ ] Measure the exact embedding tokenizer and pass English, Traditional Chinese,
  bilingual, cross-language, case-original-language, HKEX, long-record, split-
  record, and authority-note-aware end-to-end retrieval/answer tests.
- [ ] Admit exact Pinecone project/index geometry, metadata schema, backup,
  namespace/index naming, capacity, cost, and outage profiles.

Exit gate: exact fingerprinted model, embedding, and target profiles are
`ADMITTED`, reproducibly evaluated, and the workers refuse any unapproved drift.

### HKV1-8 — Make the real Review and promotion trust chain executable — NOT READY

- [x] The complete M6 release, Approval, desired-state, backup, routing, rollback,
  and retirement behavior passes with deterministic local fakes.
- [x] Six-field serving metadata is now carried in the current source branch.
- [ ] Remove the direct control-plane path that promotes an arbitrary model
  decision or `INSUFFICIENT_EVIDENCE` result.
- [ ] Require immutable Corpus Releases, complete Desired-State Inventory,
  Coverage Status Manifest, Promotion Manifest, named-human Review decision, and
  one exact unconsumed Approval before any embedding or target write.
- [ ] Bind write authority to the approved command/manifest instead of permanent
  `PROMOTION_WRITE_AUTHORIZED=true` deployment state.
- [ ] Carry and compare approved serving/text/profile fingerprints across every
  durable hop; never authenticate a received payload by recomputing its claim.
- [ ] Validate provider upsert acknowledgement, enumerate the complete target,
  and compare every ID, vector fingerprint, and six-field metadata payload.
- [ ] Reconcile ambiguous/lost acknowledgements as `OUTCOME_UNKNOWN` before retry
  or terminal failure.
- [ ] Create and independently verify provider-native and separate recovery
  backups before cutover; keep the predecessor protected.
- [ ] Make Review client authentication, current-role validation, revocation,
  approval invalidation, coverage retrieval/cache, cutover, reverse-swap, and
  exact retirement work against the real local services.

Exit gate: an unapproved payload cannot call embeddings or mutate Pinecone; one
exact approved complete Hong Kong manifest builds a byte/fingerprint-equal
replacement target, verifies backup, cuts over once, and rolls back exactly.

### HKV1-9 — Reconcile and operate the local host — NOT READY

- [x] `asklegal.target`, fourteen services, ten identities, SQL, two schedulers,
  two vault gateways, three egress proxies, and the five applications run under
  systemd on the intended Ubuntu host.
- [ ] Stop and account for `acq-batch` and `cp-test`; no pipeline process may run
  outside the declared supervisor.
- [ ] Rebuild and deliberately deploy all five current application images by
  immutable admitted identifiers; all five running image IDs currently differ
  from the current tags.
- [ ] Rotate every credential exposed through plaintext `var/run/` staging,
  verify sealed/current delivery, remove obsolete duplicates, and prove old
  values fail.
- [ ] Install the five intended timers with exact cadence, overlap, catch-up,
  shutdown, and missed-run behavior; no AskLegal timer exists today.
- [ ] Emit application metrics/traces/audit events, deploy the selected local
  monitoring views and alerts, and prove useful source/provider/workflow/coverage
  failure visibility.
- [ ] Enforce or explicitly accept the residual V1 network risks: proxy bypass,
  broad `asklegal-register` east-west access, shared vault credentials, mutable
  local tags, and Docker-socket authority.
- [ ] Prove local Review authentication, resource ceilings, disk growth,
  retention, vault restore, SQL backup/restore, scheduler replacement, reboot
  survival, clock/time sync, and no-secret logging.
- [ ] Replace the static admission snapshot with evidence that represents the
  live identities, units, images, source profiles, providers, target, and real
  acceptance results.

Exit gate: a reboot returns one current, supervised, observable, scheduled stack
with no orphan process, stale image, plaintext credential duplicate, failed unit,
unexplained admission blocker, or untested recovery path.

### HKV1-10 — Build, approve, and prove the complete baseline — NOT STARTED

- [ ] Freeze one common Hong Kong baseline cutoff and complete source observations
  for every due scope and source role.
- [ ] Preserve exact Primary and Recovery evidence manifests before processing.
- [ ] Build all Legislation, Cases, Regulatory Materials, and Principles Corpus
  Releases; resolve or explicitly disposition every item, zero-record result,
  Quarantine, Waiting Room entry, and Coverage Gap.
- [ ] Compose one complete Hong Kong Desired-State Inventory and traceability map
  with the exact six-field payload and embedding fingerprint for every record.
- [ ] Pass deterministic/legal-semantic validation and English, Traditional
  Chinese, bilingual, cross-language, material-filter, authority-note, stale-law,
  case-treatment, and HKEX retrieval/answer acceptance suites.
- [ ] Review and approve the exact frozen proposal through the named-human Review
  path; any changed input must invalidate it.
- [ ] Build, fully read back, back up, and activate one replacement Hong Kong
  Pinecone generation; verify the coverage manifest and answer path.
- [ ] Prove reverse-swap rollback, restore, lost-ack reconciliation, duplicate,
  restart, source outage, model outage, Pinecone outage, hostile input, and
  partial-scope failure without false success.
- [ ] Run one scheduled no-change cycle and one scheduled controlled-change cycle
  end to end after a reboot.
- [ ] Reconcile README, topology, ADRs, admission files, runbooks, continuity
  files, dependency inventory, credentials, and operator commands to the proved
  system.

Exit gate — working Hong Kong V1: the formal gate says `V1_ADMITTED`; every
promised scope has complete current coverage or an exact visible non-overstating
limitation; the local stack autonomously rebuilds and reports; Ask.Legal's POC
route serves only the exact approved generation; and an independently verified
rollback can restore the predecessor without data loss or broad deletion.

## Honest progress summary

The project is **advanced in design with the local synthetic platform complete
and the first real-package source-access checkpoint implemented, but external
admission and platform operation incomplete**. The architecture and Hong Kong legal-policy model
are extensive. The normative
cross-cutting contract package plus the Python contract, type, durability,
package, synthetic image-admission, and architecture boundaries are locally
proved. M2 is complete: its domain kernel, typed Management Register boundary,
deterministic fake, and complete common SQL substrate are proved, including on
a fresh real local SQL Server. M3 is complete with five independently runnable
local boundaries and fail-closed local adapters. M4 is complete with exact
evidence/acquisition contracts, synthetic connectors, two local vault fakes,
and explicit observation outcomes. M5 is complete for the executable package
engine, local lifecycle, bounded semantic boundary, processing worker, and one
reserved synthetic package. A frozen Hong Kong Legislation package now records
all three scopes and their exact blockers and proves the ordered offline
`HKLEG-BASE-OBS-001` → `HKLEG-BASE-INV-001` → `HKLEG-BASE-EVID-001` →
`HKLEG-BASE-STATE-001` → `HKLEG-BASE-LIMIT-001` → `HKLEG-BASE-ID-001` →
`HKLEG-BASE-DISP-001` → `HKLEG-BASE-REC-001` → `HKLEG-BASE-REL-001` path,
the bounded `REVIEW-001` → `HIST-001` branch, and the orthogonal
`CHANGE-001` cutoff guard, the three ordinary current-observation outcomes,
four ordinary evidence rules, two observable-difference rules, and two
evidence-bound cause rules against 97 exact synthetic cases without
fabricated real-source proof;
every real scope remains `NOT_READY`. The repository now also has a strict
fourteen-role official-source register and bounded HTTPS connector. The legal
team has cleared all fourteen roles. Current executable `main` records five
configured roles, five partially configured, one blocked, and three outside V1;
GLD remains one of the partial roles because it is retained for V1 but its
Turnstile-gated acquisition procedure is not technically admitted. Legal
clearance has not been converted into false technical readiness.
M6 is complete with local corpus/proposal construction, Review-backed Approval,
and a fully checked fake replacement-target promotion and rollback. M7 is
complete: all 32 accepted offline scenarios connect the real local boundaries
through one stable CLI and produce a byte-identical report in two path-distinct
runs. There is no Azure environment and no production activation. The other
four are no longer hypothetical: on 2026-08-19 and 2026-08-20 real Hong Kong
sources, the Azure inference and embedding deployments, and Pinecone writes were
each exercised from inside their owning worker through its own egress proxy, and
one document ran the whole chain to a verified record in `testing-index-1`. None
of that is admission. The composite gate still reports `V1_POC_NOT_ADMITTED`,
and a working call is not a deployment profile or an evaluation.

| Area | Current state | Evidence or remaining gap |
|---|---|---|
| Overall design and architecture | **DESIGN ACCEPTED** | Architecture and implementation-facing design are accepted through ADR 0099, including all six M2–M7 protocols |
| Hong Kong legal-policy design | Complete ordinary offline path and expanding official-source boundary implemented; real scopes `NOT_READY` | The package binds 14 source roles and all three scopes; 27 offline rules cover first-baseline, ordinary current update through complete release accounting, and missing-consolidation event routing in 127 exact synthetic cases. The strict source register binds 79 endpoints and records legal-team clearance for all roles; five roles are configured, five partially configured, one is technically blocked, and three are outside V1 scope. Technical reporting accounts for all roles, item URL binding is implemented, bilingual inventories are atomic, and bounded direct plus isolated Patchright discovery is proved. Inert evidence, catalogue, physical, direct-search, adjudicated-evaluation, complete-universe, and activation evidence remain |
| Normative machine contracts | Foundation through M6 contracts complete | Repository-owned Draft 2020-12 package 1.5.0 covers 74 shared objects and 27 cross-cutting fixtures, adding proposal-package and exact embedding profile/request/receipt contracts |
| Python and Management Register foundations | All seven M1 checkpoints complete | Python 3.14.7 contract/type/package/architecture gates, synthetic image admission, the independent Node oracle, and separate real SQL Server and Durable Task emulator proofs pass |
| Domain kernel and Management Register | **M2 COMPLETE** | Five lifecycle machines, operation objects, re-entry, typed store/fake, exact SQL prefix, procedures, ledger, recovery, and conformance proofs pass |
| Five applications and shared runtime packages | **M3 COMPLETE** | Two strict independent FastAPI APIs, one replaceable Review client, three no-ingress workers, and one framework-free application-runtime package pass local boundary proofs; all external effects remain disabled |
| Evidence and acquisition | **M4 COMPLETE** | Deterministic Registered Source/endpoint, Watcher, Scraper, hostile-input, coverage-accounting, manifest-last primary/recovery vault, exact receipt, corruption, retention, restart, and acquisition-outcome proofs pass using synthetic bytes only |
| Legal processing and executable packages | **M5 COMPLETE (LOCAL/SYNTHETIC); HK READINESS IN PROGRESS** | The loader now admits honest non-executable `NOT_READY` inventories; the frozen HK Legislation checkpoint selects Ordinances first while all real scopes remain blocked and no real jurisdiction or model is admitted |
| Review, Approval, corpus, and promotion | **M6 COMPLETE (LOCAL/SYNTHETIC)** | Exact releases/desired state/coverage/proposals, real local Review governance, single-use Approval, replacement target, embedding, backup, routing, rollback, coverage cache, and retirement-denial proofs pass; all remote adapters remain disabled |
| Local end-to-end pipeline | **M7 COMPLETE (LOCAL/SYNTHETIC)** | Stable reset/named/all CLI; 32 expected-result scenarios; golden acquisition-to-recovery flow; failure/retry/restart/hostility/Approval/promotion/recovery/deletion proofs; network denial; and path-distinct reproducibility pass |
| V1 operating environment | **RUNNING UNDER SYSTEMD ON THE TARGET HOST; ADMISSION NOT READY** | Fourteen services are running, all five application logs report ready, ten host identities and the owned storage paths exist, and installed generated units match the repository. The five running application images are older than the current local tags/source; `acq-batch` and `cp-test` run outside systemd; no recurring timers are installed; application telemetry and Prometheus/Grafana are absent; and the composite gate still reports `V1_POC_NOT_ADMITTED`. Its 14 blockers are a fail-closed static baseline and do not yet model the live host/provider evidence. |
| Azure infrastructure and delivery | Post-V1/deferred unless separately restored to V1 scope | Azure SQL, Container Apps, Scheduler, Blob, ACR, Application Gateway, Azure Pipelines, and Azure Monitor remain accepted future architecture, but no Bicep, pipelines, or cloud resources exist |
| Real-source, model, embedding, and Pinecone operation | **ALL FOUR PATHS EXERCISED LIVE; FORMAL ADMISSION NOT STARTED** | Legal admission is clear for all 14 roles. The current source report accounts for 79 endpoints, 56 enabled, with five roles configured, five partially configured, one blocked, and three outside V1 scope. Azure embeddings, Azure `gpt-5.4` inference, Pinecone writes to `testing-index-1`, and live Hong Kong source capture have each been exercised, and 7,274 gazette PDFs for 2000–2026 are retained under Object Lock. `MODEL_AND_EMBEDDING_ADMISSION` and `PINECONE_ADMISSION` remain `NOT_STARTED` in the static admission gate because deployment profiles, evaluation, exact approval/read-back, recovery, and rollback evidence are missing. No production activation occurred. |
| Production admission and activation | Not started | Security, recovery, quality, operational, and human-approval proofs remain |
| Ask.Legal admin-portal integration | Intentionally deferred | M7 now satisfies the complete-pipeline prerequisite, but integration remains deferred by explicit direction |

Numerical percentage is deliberately omitted: counting accepted documents and
implemented production capabilities as equivalent units would overstate
progress.

Publisher and archive enquiries are deferred by user direction and are not a
V1 prerequisite. Any source that cannot be completed through independently
verified official interfaces remains an explicit coverage limitation rather
than blocking unrelated V1 construction.

## Status legend

- **COMPLETE** — required artifact and its stated validation exist.
- **IN PROGRESS** — at least one required implementation checkpoint is complete
  but the milestone exit gate is not.
- **DESIGN CLOSURE IN REVIEW** — a complete proposal exists, but material
  choices or final acceptance remain with the user.
- **DESIGN ACCEPTED** — direction is settled, but implementation proof does not
  yet exist.
- **NOT STARTED** — no authorized implementation checkpoint is complete.
- **DEFERRED** — intentionally paused by an explicit decision.
- **BLOCKED** — cannot advance because a required external choice or artifact
  is unavailable. No milestone is currently classified as blocked.

## Delivery map

```mermaid
flowchart TD
    M0["M0 — Overall design baseline<br/>DESIGN ACCEPTED"]
    M1["M1 — Engineering foundation<br/>COMPLETE"]
    M2["M2 — Domain kernel and Management Register<br/>COMPLETE"]
    M3["M3 — Five local application boundaries<br/>COMPLETE"]
    M4["M4 — Evidence and acquisition<br/>COMPLETE"]
    M5["M5 — Legal processing and executable rulebooks<br/>COMPLETE — LOCAL/SYNTHETIC"]
    M6["M6 — Review, Approval, corpus, and promotion<br/>COMPLETE — LOCAL/SYNTHETIC"]
    M7["M7 — Complete local synthetic pipeline<br/>COMPLETE — LOCAL/SYNTHETIC"]
    M8["M8 — Azure non-production platform<br/>NOT STARTED"]
    M9["M9 — External and production admission<br/>NOT STARTED"]
    M10["M10 — Controlled production activation<br/>NOT STARTED"]
    M11["M11 — Ask.Legal admin-portal integration<br/>DEFERRED"]

    M0 --> M1 --> M2 --> M3
    M3 --> M4
    M3 --> M5
    M3 --> M6
    M4 --> M7
    M5 --> M7
    M6 --> M7
    M7 --> M8 --> M9 --> M10 --> M11
```

The diagram shows proof dependencies, not a promise that all work must be
serial. Executable legal packages, exact policy values, and local adapters may
advance in parallel once their own prerequisites and authorization gates are
met.

For the M5-to-M7 dependency, M7 requires the Legal Desk package mechanism and
one closed test-only synthetic package, not completion of every production
Hong Kong package. Production packages remain `NOT_READY` until their own
complete source, rulebook, fixture, evaluation, owner, and attestation gates
pass. Their external admission evidence is tracked under M9 and exact package
gates. An M7 success therefore proves that the local platform works; it does
not mark an unfinished real legal package complete.

## Milestones and exit gates

### M0 — Overall design baseline — DESIGN ACCEPTED

Delivered:

- greenfield modular-monorepo and five separately permissioned applications;
- evidence, Management Register, corpus, Approval, replacement-serving-target,
  recovery, and audit boundaries;
- detailed Hong Kong legislation, reconstruction, case proposition, case
  treatment, and HKEX Regulatory design-level rules and catalogues; and
- accepted production stack through ADR 0098.

Exit gate:

- accepted system-wide design exists and unresolved matters are explicitly
  listed instead of receiving implied defaults.

The 2026-08-16 full M2–M7 build-readiness audit is closed by accepted ADR 0099
and six accepted protocols:
Domain/Register, Application interfaces, Acquisition/Evidence, executable
Legal Desk, Review/Promotion, and end-to-end conformance. All seven material
decisions, including Decision 7's bounded semantic-decision authority, are
settled and the user explicitly accepted the reconciled package.

After design acceptance, exact source registers/rulebooks, deployed model
profiles, regions, capacity, security assignments, recovery/retention/service-
level values, budgets, and evaluations remain implementation artifacts or
admission evidence. Their absence keeps capabilities disabled.

### M1 — Engineering foundation — COMPLETE

Delivered:

- implementation-neutral normative `contracts/` package and validator; and
- completed Python 3.14.7 contract-boundary spike under `packages/contracts/`;
  and
- completed repository-wide type-boundary spike using official Pyright strict,
  automatic source discovery, a closed exception register, and 15 focused
  synthetic policy tests; and
- completed narrow Management Register spike with exact migrations, typed
  `mssql-python` adapter, stored procedures, least privilege, ledger,
  concurrency, retry, and lost-ack recovery proofs on real local SQL Server;
  and
- completed local durability spike with the standalone Microsoft Python SDK,
  deterministic fresh-worker replay, buffered stale and duplicate human
  events, fake-register reconstruction, and one effect across a lost-ack retry
  on both the always-on SDK backend and digest-pinned Docker emulator; and
- completed package spike with complete workspace-member coverage, two
  byte-identical offline wheel builds, member-specific clean locked installs,
  independent import isolation, and byte-identical container-input bundles;
  and
- completed local image-admission spike with two reproducible network-disabled
  OCI builds, normalized SPDX/provenance/scanner evidence, fail-closed
  vulnerability and licence policy, exact ORAS graph copy and recovery,
  isolated test-only signing, and locked-down runtime proof; and
- completed local architecture policy covering all five applications,
  14 shared packages, exact direct dependencies, internal imports, cycles,
  declarations, and exclusive capability ownership, followed by the complete
  offline package proof for the expanded 19-member workspace.

Next checkpoints, in recommended order:

1. **Type-boundary spike — COMPLETE** — reject unapproved `Any`, unknown types,
   unparameterized collections, unchecked casts, ignored errors,
   infrastructure imports, and framework leakage.
2. **Management Register spike — COMPLETE** — real SQL Server proves exact migrations,
   least-privilege procedures, JCS bytes, idempotency, concurrency, outbox and
   inbox behavior, ledger checks, deadlock handling, and ambiguous commits.
3. **Durability spike — COMPLETE** — prove deterministic restart, duplicated human events,
   stale fingerprints, idempotent activities, and fake-register recovery.
4. **Package spike — COMPLETE** — exact network-disabled installation,
   independent imports, reproducible wheels, and reproducible container inputs.
5. **Image-admission spike — COMPLETE** — prove reproducible synthetic
   OCI graphs, SBOM, provenance, vulnerability and licence policies, test
   signing, exact graph copy, and fail-closed rejection without Azure.
6. **Architecture spike — COMPLETE** — enforce allowed application/package
   imports and capability surfaces.

Exit gate:

- all seven local proofs, including the completed contract spike, pass from
  exact locks with synthetic inputs and local fakes;
- architecture tests enforce the monorepo dependency and capability rules; and
- no external service is required for the ordinary test suite.

M1 through M7 are complete locally. M8 is the next separately authorized
capability milestone. The disposable SQL Server and Durable
Task emulator containers have been removed; their digest-pinned images may
remain cached.

### M2 — Domain kernel and Management Register — COMPLETE

Delivered:

- the framework-free immutable lifecycle kernel for Pipeline Runs, Work Items,
  Source Contract Reviews, Coverage Gaps, and Quarantines: 37 closed states,
  61 contract-authoritative transitions, optimistic-version rejection,
  runtime-exact primitive validation, recurrence identities, exhaustive
  allowed/forbidden tests, independent contract-to-code equivalence, and one
  exact ordinary developer bootstrap/test command; and
- contract package 1.2.0 plus framework-free immutable Command Envelope,
  Command Result, Effect Intent, and Effect Receipt objects, with closed
  submission resolution, owner/capability/destination bindings, strict runtime
  validation, 27 independent fixtures, and contract-to-code equivalence; and
- explicit quarantine release-to-new-linked-Work-Item re-entry; and
- a typed framework-free `ManagementRegisterStore` port and deterministic
  thread-safe fake covering exact replay/conflict, versions, winners, events,
  effect intents, leases, fencing, attempts, receipts, policy states,
  projections, digest failure, and recovery replay; and
- the narrow local Management Register adapter and exact two-migration prefix,
  including the nine-batch common M2 SQL substrate, five procedure-only
  application roles, recovery views, and real SQL Server conformance proof.

Design prerequisite: **ACCEPTED** in
`docs/design/M2_DOMAIN_AND_REGISTER_PROTOCOL.md`.

Implemented:

- framework-free immutable domain objects, IDs, fingerprints, state machines,
  commands, events, effect intents, results, and policy states;
- typed `ManagementRegisterStore` port and fake implementation;
- exact forward-only SQL Server migration packages and narrow runner;
- command procedures, least-privilege views and roles, event/inbox/outbox
  persistence, projections, ledger verification, and recovery exports; and
- property, concurrency, replay, failure, and migration tests.

Exit gate:

- every normative lifecycle has executable transition tests;
- duplicate, concurrent, stale, and ambiguous operations reach one exact
  result; and
- a fresh local SQL Server can be built and verified only from fingerprinted
  migrations.

Exit result: **PASS**. Every M2 transition is tested exhaustively; replay,
conflict, stale, concurrency, expiry, fencing, deadlock, ambiguous commit,
lost acknowledgement, projection rebuild, digest failure, recovery, overlap,
cancellation, recurrence, and re-entry have explicit proof. The fresh SQL
Server proof applied only the exact `000001`/`000002` prefix and verified its
ledger. Azure recovery operations and production settings remain M8–M10
admission work rather than an unfinished M2 implementation default.

### M3 — Five local application boundaries — COMPLETE

Delivered:

- independently startable control-plane and Review FastAPI applications with
  distinct `/api/v1` OpenAPI, audiences, origins, routes, health checks, exact
  raw-body boundaries, errors, ETags, idempotency, and optimistic versions;
- snapshot/filter/sort/caller/expiry-bound Review pagination, exact manifest
  decisions, audited evidence streaming, and a replaceable PKCE browser client
  that keeps bearer tokens in memory only;
- independently startable acquisition, legal-processing, and promotion
  workers with no HTTP ingress, exact revision configuration, separate local
  task hubs, generation fencing, cooperative shutdown, and fail-closed effect
  adapters;
- a framework-free application-runtime package holding exact configuration,
  local identity, register, pagination, projection, task, lease, and disabled-
  effect adapters; and
- evolved architecture and package policies for 5 applications, 14 packages,
  80 internal edges, 31 capability ports, and exclusive control-plane proposal
  preparation.

Design prerequisite: **ACCEPTED and implemented** in
`docs/design/M3_APPLICATION_INTERFACE_PROTOCOL.md`.

Exit gate:

- each application starts and tests independently;
- forbidden imports and capabilities fail automatically;
- workers have no accidental HTTP, UI, Approval, or production credentials;
  and
- later admin-portal integration depends only on the versioned Review API.

Exit gate: **PASS**. M3 performs no source, model, embedding, serving, backup,
routing, recovery, Azure, deployment, or production effect.

### M4 — Evidence and acquisition — COMPLETE

Design prerequisite: **ACCEPTED** in
`docs/design/M4_ACQUISITION_AND_EVIDENCE_PROTOCOL.md`.

Delivered:

- source registry, watcher, scraper, source-snapshot, evidence-vault, recovery-
  copy, content-addressing, hostile-content isolation, and coverage-accounting
  packages;
- deterministic synthetic source connectors and complete failure cases; and
- local primary/recovery vault fakes with conditional-create, exact-version,
  read-back, manifest, retention, and recovery tests.

Contract package 1.3.0 now governs Connector Request, Watcher Result, Scraper
Result, Vault Object Receipt, Evidence Object, Evidence Package, and
Acquisition Outcome. The acquisition worker uses a two-phase boundary: it can
commit primary evidence, but only an independently supplied exact recovery
receipt can make a Source Snapshot `PRESERVED` and legal-processing eligible.
Recovery copying remains owned by the promotion-worker boundary.

Exit gate:

- every registered synthetic source observation has one explicit outcome;
- complete evidence is preserved before processing;
- missing, changed, contradictory, or hostile inputs fail closed or enter the
  exact Quarantine/Source Contract Review path; and
- no change signal can silently create model, embedding, or promotion work.

Exit gate: **PASS** using only synthetic responses and filesystem-backed local
vaults. Missing/unavailable work creates Coverage Gap, source-contract drift
creates Source Contract Review, hostile content creates Quarantine, stable
full capture creates one preserved Source Snapshot, and admitted no-change
authorizes no downstream work. No real source, Azure, model, embedding,
serving, backup, routing, deployment, or production effect was performed.

### M5 — Legal processing and executable rulebooks — COMPLETE (LOCAL/SYNTHETIC)

Design prerequisite: **ACCEPTED** in
`docs/design/M5_EXECUTABLE_LEGAL_DESK_PACKAGE_PROTOCOL.md`. The M7 platform
proof uses one test-only synthetic package and satisfies no production Hong
Kong package gate.

Delivered locally:

- contract package 1.4.0 for executable package roots, exact scope activation,
  Rule Execution Results, bounded Semantic Task Request/Decision, and candidate
  artifacts;
- a canonical-layout loader that rejects missing/extra files, drift, path or
  code violations, contract mismatch, overlapping scopes, incomplete sources,
  leakage, floating or expired profiles, stale activation, and environment
  misuse;
- a deterministic closed rule engine that blocks zero matches as
  `RULEBOOK_NON_TOTAL`, blocks multiple matches as `RULEBOOK_AMBIGUOUS`, and
  emits byte-identical evidence-bound outcomes and candidate bytes;
- the sole provider-neutral semantic gate with a contract-equal twelve-stage
  catalogue, six exact primary/secondary pairings, distinct profiles/prompts,
  evidence budgets, preserved-reference validation, expiry, and deterministic
  reconciliation; only an exact local fake is implemented and the default
  runner is disabled; and
- reserved package `ZZZ` / `LOCAL_SYNTHETIC` / `TEST_LEGAL_MATERIAL`, rejected
  in every other environment and carrying no real locator, credential, legal
  authority, or production scope.

Real package admission remains outstanding for the accepted Hong Kong
families:

- executable Hong Kong Legislation Source Rulebook, schemas, exact fixtures,
  current-baseline/update behavior, and reconstruction capability;
- executable Hong Kong Cases source register, proposition coverage ledger,
  treatment graph, renderers, exact fixtures, evaluation packages, and
  workflow-admission profiles;
- executable HKEX Regulatory source inventory, rules, schemas, complete
  conformance artifacts, and multilingual retrieval/answer admission; and
- Principles and any additional jurisdiction/material package only after its
  own source, rights, coverage, and rulebook decisions exist.

The first eleven local Hong Kong package checkpoints are complete. The frozen Hong
Kong Legislation package records all 14 accepted stable source roles and all
three non-overlapping scopes, selects `HK-LEG-ORDINANCES` as the current target,
and executes only the offline ordered `HKLEG-BASE-OBS-001` →
`HKLEG-BASE-INV-001` → `HKLEG-BASE-EVID-001` → `HKLEG-BASE-STATE-001` →
`HKLEG-BASE-LIMIT-001` → `HKLEG-BASE-ID-001` → `HKLEG-BASE-DISP-001` →
`HKLEG-BASE-REC-001` → `HKLEG-BASE-REL-001` conformance path. Five observation fixtures cover frozen,
missing-source, mixed-cutoff, lock-drift, and post-cutoff-change branches; four
inventory fixtures cover accounted, unaccounted, duplicate-owned, and
misassigned branches. Five evidence fixtures cover verified and assisted
bilingual success, missing-language blocking, conflict quarantine, and
forbidden historical substitution. Seven state fixtures cover clear operative success, missing
signals, partial-status ambiguity, source conflict, unknown semantics, unproved
operative effect, and missing rulebook support. Five limit fixtures cover a
present-state-only success and blocks for unsupported historical events,
effective dates, identity or continuity relationships, and complete historical
event chains. Five identity fixtures cover fresh register allocation, legacy
aliases, blocked source/legacy identity reuse, blocked unproved lineage, and
quarantined similarity-based ambiguity. The package still declares
Seven disposition fixtures cover all five primary dispositions, a visible
operative-event consolidation gap, and rejection of single-signal shortcuts.
Six record fixtures cover exact candidate creation, non-searchable exclusion,
legacy identity rejection, incomplete bilingual content, non-canonical
rendering, and unapproved authority notes.
Seven release-accounting fixtures cover a complete initial release, missing and
duplicate inventory, inconsistent outputs, a false predecessor, missing
references, and unresolved completeness.
Five targeted-review fixtures cover one bounded investigation and reject no-
question, whole-history, unregistered-source, and fact-scope-mismatch requests.
The package still declares
incomplete rule and fixture universes plus exact source, rights, bytes, evaluation, semantic-
profile, owner, and attestation blockers. It remains non-activatable and
`NOT_READY`; this is progress toward its gate, not satisfaction of it.

Azure OpenAI models sold by Azure through Microsoft Foundry are the selected
service boundary. Exact deployed models remain disabled until their immutable
evaluation/admission profiles pass. This does not block deterministic
contracts, rulebooks, renderers, fakes, or evaluation-package construction.

Exit gate:

- each enabled jurisdiction/material package accounts for its complete frozen
  source universe;
- exact deterministic and semantic gates pass without evaluation leakage;
- uncertainty never becomes guessed legal status or searchable text; and
- only an exact admitted workflow may make a model-assisted proposal.

Exit gate: **PASS for the only enabled package, the reserved local-synthetic
scope.** Its complete invented source universe, deterministic fixtures, sealed
evaluation references, exact local profiles, owner/test attestation, activation,
rule execution, semantic challenge, quarantine, withholding, candidate, and
reproducibility paths pass. No production Hong Kong package is enabled; all
remain `NOT_READY`, so this result makes no Hong Kong legal-readiness claim.

### M6 — Review, Approval, corpus, and promotion — COMPLETE (LOCAL/SYNTHETIC)

Design prerequisite: **ACCEPTED** in
`docs/design/M6_REVIEW_AND_PROMOTION_PROTOCOL.md`.

Delivered locally:

- contract package 1.5.0 adds frozen proposal-package manifests and exact
  embedding profile, request, and receipt objects with independent runtime
  equivalence and schema-conformance proofs;
- deterministic Corpus Release, Desired-State Inventory, complete Coverage
  Status Manifest, Promotion Manifest, and manifest-last Proposal Package
  construction, including exact role, byte, reference, and read-back checks;
- the Review API writes fingerprint-bound comments, decisions, and revocations
  to the named-human `PipelineAdministrator` Approval register with optimistic
  versions, exact command replay, current-role revalidation, and atomic
  single-lineage consumption;
- provider-neutral embedding, replacement-target, backup, routing, coverage,
  rollback, and exact-retirement ports with no-network local fakes; and
- the promotion worker revalidates manifest/profile/cost/base/coverage facts,
  reconciles lost acknowledgements, proves exact vector and metadata inventory,
  verifies retrieval and backup, performs one compare-and-set cutover, and
  reverse-swaps only to the retained predecessor.

Exit gate:

- one human decision binds one exact frozen package and execution lineage;
- any material change invalidates Approval;
- a synthetic replacement serving target exactly matches the desired state
  before simulated cutover;
- exact rollback and recovery are independently verified; and
- broad or inferred deletion is impossible.

Exit gate: **PASS with local synthetic records and fakes only.** The required
stale/revoked/consumed Approval, role removal, invalidation, drift, overlap,
partial batch, lost acknowledgement, vector mismatch, unknown record, cost,
backup, routing, warm-up, post-cutover, rollback, coverage, and retirement
failures are exercised. No model, embedding provider, Pinecone, backup service,
Ask.Legal slot, Azure resource, corpus publication, or production route was
called or changed.

### M7 — Complete local synthetic pipeline — COMPLETE (LOCAL/SYNTHETIC)

Design prerequisite: **ACCEPTED** in
`docs/design/M7_END_TO_END_CONFORMANCE_PLAN.md`.

Delivered locally:

1. schedule and observe a synthetic source;
2. preserve exact evidence;
3. apply one executable Legal Desk rulebook;
4. create candidate records and complete coverage accounting;
5. freeze a Corpus Release, Desired-State Inventory, and Promotion Manifest;
6. inspect and approve through the Review API/client;
7. embed and build a replacement fake serving target;
8. verify, cut over, report, recover, and roll back; and
9. repeat failure, retry, duplicate, restart, stale-approval, overlap, hostile-
   input, and no-change cases.

Exit evidence:

- `uv run --frozen --all-packages asklegal-local reset --exact-test-state`,
  named scenario, and `prove --all` semantics are implemented and documented;
- all 32 scenarios pass twice in clean path-distinct roots with byte-identical
  complete reports and full generated-artifact inventories;
- the golden flow uses the local M3–M6 application/service boundaries from
  source observation through Review HTTP Approval, cutover, rollback, and
  exact recovery;
- every scenario is checked against a frozen expected result/fact/effect entry;
  and
- DNS/socket access is denied while every provider/system remains a local fake.

Exit gate: **PASS.** The report fingerprint from the final stable CLI proof is
`sha256:1371eca6e75e380f8a754e665850e3839aa7e2ff9de4b86e18c5061ae026d8ae`
and its statement is exactly `local synthetic platform proved`. This is the
point at which the local pipeline first genuinely works. No real legal package,
provider, Azure resource, Pinecone target, Ask.Legal route, deployment, or
production effect was accessed or admitted. Admin-portal integration remains
deferred.

### M8 — Azure non-production platform — NOT STARTED

Build under separate authorization:

- repository-owned Bicep, policy, identities, role assignments, networks,
  private DNS, Azure SQL, Container Apps, Scheduler, Blob/Confidential Ledger,
  ACR/Artifact Signing, Application Gateway, Azure Monitor, audit archives,
  and Azure Pipelines/Managed DevOps Pools;
- exact Deployment Change Packages, what-if review, operational approval,
  image admission, migration, deployment, evidence, drift, rollback, and
  retirement jobs; and
- measured configuration values for region, capacity, service levels,
  retention, recovery, security, observability, and cost.

Exit gate:

- a non-production environment is reproducible from reviewed source and exact
  immutable inputs;
- private paths, least privilege, workload federation, policy denial, audit
  sealing, and independent recovery evidence are proved; and
- no reusable Azure deployment credential is present.

### M9 — External and production admission — NOT STARTED

Prove separately authorized real integrations without granting production
mutation merely because an integration works:

- official/publisher source rights, authorization, completeness, rate, outage,
  hostile-input, and change-detection behavior;
- exact Azure OpenAI/Foundry generative and embedding deployment profiles,
  SDK/API, identity, network, data-location, retention, abuse-monitoring,
  quota, cost, outage, evaluation, and admission evidence;
- Pinecone replacement-index, backup, desired-state, search-quality,
  generation-pinning, and rollback behavior;
- Entra, Conditional Access, WAF, audit export, alerting, incident, recovery,
  restore, and regional replacement drills; and
- complete security, privacy, legal, quality, operational, and cost sign-off.

Exit gate:

- every production dependency has current evidence and an admitted exact
  profile;
- source, model, embedding, retrieval, recovery, security, and operational
  gates all pass; and
- a frozen production-candidate package is ready for human approval without
  making any production change.

### M10 — Controlled production activation — NOT STARTED

Perform only under exact operational and legal Promotion approvals:

- deploy the admitted application and infrastructure digests;
- build and verify the complete production-candidate serving state;
- warm and test the separate Ask.Legal production-candidate routing path;
- activate one exact generation, observe it, and preserve all receipts;
- demonstrate bounded rollback and recovery; and
- establish routine reconciliation, quality, security, recovery, cost,
  incident, and audit operations.

Exit gate:

- every question in the canonical design's definition of success can be
  answered from preserved evidence and reports; and
- Ask.Legal serves only the exact verified and approved state.

### M11 — Ask.Legal admin-portal integration — DEFERRED

After M7 proves the pipeline and the Review API contract is stable:

- admit the existing Ask.Legal admin portal as a separate Review API client;
- reproduce reviewer evidence, comparison, rejection, revocation, approval,
  single-role authorization, accessibility, and audit behavior inside the portal;
- retain Review API authorization and Management Register write boundaries;
  and
- retire or retain the standalone browser shell through an explicit product
  decision.

Exit gate:

- portal integration changes only the reviewer experience, not pipeline,
  Approval, evidence, or promotion correctness.

## Cross-cutting gates that apply to every milestone

- **Authorization:** success at one capability never authorizes the next.
- **Contracts:** normative schemas and exact fingerprints lead implementation.
- **Evidence:** preserve inputs and receipts before consequential effects.
- **Least privilege:** each application, job, identity, role, subnet, and
  credential receives only its owned capability.
- **Determinism and idempotency:** retry, duplicate, restart, overlap, and
  ambiguous outcomes have exact tested results.
- **Uncertainty:** block, quarantine, or request review; never guess or skip.
- **Quality:** contract validity does not replace legal, semantic, retrieval,
  security, recovery, or operational admission.
- **Reversibility:** production mutation requires exact recovery evidence and
  independently verified rollback.
- **Handoff:** update `CONTEXT.md`, `DECISIONS.md`, `WORKING_STATE.md`, and this
  roadmap when a milestone status or dependency materially changes.

## Immediate decision and work queue

1. **M1–M7 local platform — COMPLETE:** the engineering foundation, domain and
   register, five application boundaries, acquisition/evidence, executable ZZZ
   processing, Review/Approval/promotion, and all 32 end-to-end scenarios pass.
2. **V1 POC topology — PROVISIONED AND RUNNING; RELEASE SAFETY AND ADMISSION
   OUTSTANDING:** the host, identities, networks, sealed systemd credentials,
   certificates, storage, and fourteen services are present. The current work is
   not routine plumbing: (a) freeze the unsafe direct promotion path; (b) reconcile
   five stale running application images and two orphan containers; (c) rotate
   every credential copied through plaintext staging; (d) install the intended
   timers and observable health/telemetry; and (e) replace the static admission
   snapshot with evidence that represents the live host and provider profiles.
   The egress proxy remains a convention rather than an enforced boundary and the
   composite gate remains `V1_POC_NOT_ADMITTED`. Preserve the exact
   `LOGICALLY_SEPARATE_POC_RECOVERY` limitation.
   The implementation baseline and incremental proof plan are in
   `docs/design/V1_POC_UBUNTU_TOPOLOGY.md`.

2b. **Superseded static-contract summary — STATIC CONTRACTS COMPLETE:** the
   exact disabled service/network/vault/scheduler/authority inventory, complete
   12-artifact-to-16-service mapping, read-only Ubuntu host-facts policy, five-
   image build-input inventory, five-application runtime-input inventory, and
   process-side file credential loader pass locally. The disabled credential-interface
   proof plan also binds all three credential-gated product services to six
   exact steps and seven inspection surfaces. The composite admission gate now
   revalidates all eight static contracts and reports the single authoritative
   verdict `V1_POC_NOT_ADMITTED`: 14 ordered components, eight static contracts
   validated, 14 blockers, and no admission or effect
   authority. Preserve the exact
   `LOGICALLY_SEPARATE_POC_RECOVERY` limitation. Next resolve tested artifact
   and Ubuntu package pins, collision-free private subnets, remaining adapter
   and readiness composition, host credential delivery, SQL Server and vault
   certificate trust, and the file-only SQL/Versity credential-interface gate
   before any service can be enabled.
   The implementation baseline and incremental proof plan are in
   `docs/design/V1_POC_UBUNTU_TOPOLOGY.md`.
3. **Full Hong Kong package work:** execute HKV1-0 through HKV1-10 above in
   dependency order. First admit the retained GLD current-publication path and
   prove the complementary HKeL backcapture/recovery role without treating it
   as an upstream substitute. The stable
   Hong Kong Legislation baseline/current-update checkpoints exist but all three
   scopes remain `NOT_READY`. Hong Kong Cases, HKEX Regulatory Materials, and
   Hong Kong Principles have no executable real package; the Principles scope
   additionally needs publisher/source/licence selection before “full Hong Kong
   jurisdiction” is an honest release claim.
4. **V1 admission work:** first close the live promotion trust-chain defects and
   enforce the documented type/lint shipping gates. Then admit the exact real
   source package, model and embedding profiles, Pinecone serving target,
   recovery, and application dependencies. Prior successful calls prove
   connectivity only; they do not supply frozen profiles, evaluation, approval,
   full read-back, recovery, or rollback evidence.
5. **Azure M8 — POST-V1/DEFERRED:** retain the accepted cloud design, but do not
   treat Azure resource creation as a V1 prerequisite without a new decision.
6. **External-effect gate:** Pinecone belongs to the POC design, but credentials,
   plan purchase, project/index creation, writes, and routing remain gated until
   explicitly authorized. Azure application hosting, Entra/WAF, and other cloud
   production dependencies remain post-V1.
7. **Admin portal — DEFERRED:** integration may now be planned against the
   stable Review API, but remains after the pipeline proof by explicit user
   direction and is not part of M8 authority.

No completed local gate authorizes external access, Azure creation, deployment,
production mutation, commit, or push.
