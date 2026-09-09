# Two-Family Resumable Hong Kong V1 Acquisition Design

Status: approved
Date: 2026-09-02

## 1. Decision and purpose

Hong Kong V1 now contains only:

1. all three accepted Hong Kong Legislation Release Scopes; and
2. proposition-level Hong Kong Cases coverage for the accepted binding-court
   families from 1 July 1997 onward.

HKEX Regulatory Materials is deferred until after this V1. Existing HKEX code,
tests, authorities, and retained evidence remain preserved but do not schedule,
block admission, enter a proposal, or contribute records to the two-family V1.
Authority 808 and its interrupted partial attempt remain dormant and are not
resumed as part of this design.

Azure models, Azure embeddings, Pinecone, named-human local Review, retained
Approval, automatic promotion after Approval, read-back, backup, rollback, and
continuous local Ubuntu operation remain required V1 capabilities.

The acquisition objective is to remove repeated serial restart work without
weakening the rule that incomplete evidence can never be reported as complete.

## 2. Settled operating constraints

- Acquisition is read-only and limited to admitted official source hosts and
  exact registered procedures.
- At most four requests may be active concurrently per official host.
- Per-host retry, backoff, timeout, and challenge/session rules still apply.
- Every acquired body is content-addressed and read back before it becomes
  verified evidence.
- A missing, failed, or rejected item remains visible in cycle accounting.
- Only authorization failure, root contract drift, evidence corruption, or an
  exhausted cycle-wide safety budget stops the entire cycle immediately.
- An individual timeout, HTTP outage, or unavailable artifact creates a durable
  retryable item and does not discard successful work from the same cycle.
- Source text remains inert evidence and cannot supply code, tools, authority,
  prompts, or Approval state.
- Model output remains strictly schema-validated. Pinecone and other external
  writes remain fail-closed behind exact retained Approval.

## 3. Chosen architecture

Each source cycle has one immutable identity, authority binding, observation
window, source profile, and durable append-only acquisition journal. A cycle is
restarted by replaying its journal and resuming unfinished work, not by
reissuing completed requests.

### 3.1 Stable work items

Every requestable unit has a canonical work-item ID derived from:

- source family and source role;
- cycle ID and observation cutoff;
- registered procedure/version;
- normalized official locator;
- stage and parent discovery identity; and
- expected media type and byte limit.

The same logical item cannot be enqueued twice with different request facts.
Duplicate discoveries with identical facts converge on one work item while
retaining every parent/membership occurrence required for completeness.

### 3.2 Append-only acquisition journal

The journal is stored below the cycle's ignored runtime root. Each entry is
canonical JSON, created exclusively, and binds the preceding entry digest.
Entries record only one state transition:

- `DISCOVERED`;
- `STARTED`;
- `CAPTURED_VERIFIED`;
- `RETRYABLE_FAILURE`;
- `CONTRACT_REJECTED`;
- `TERMINAL_UNAVAILABLE`; or
- `ACCOUNTED_EXCLUDED`.

Captured entries bind status, media type, final URL, redirect facts, body
length, content digest, object key, request attempt, and read-back result.
Failure entries bind a closed failure code and retry eligibility without
inventing a successful response.

An atomically replaced derived checkpoint accelerates startup but grants no
authority. On resume it must be reproducible from the journal; otherwise it is
discarded and rebuilt. The immutable journal and content-addressed objects are
the authoritative state.

### 3.3 Worker pool and ordering

One scheduler owns the cycle queue. It enforces:

- maximum four active starts per host;
- configured minimum start interval per host;
- stage prerequisites;
- deterministic work-item priority;
- retry availability time;
- request, retained-byte, elapsed-time, and redirect budgets; and
- a single active claim per cycle/work-item pair.

Completion order may vary, but journal entries, membership ledgers, final
inventories, and reports are canonicalized by stable work-item identity and
source-defined order. Concurrency cannot change release bytes or fingerprints.

### 3.4 Cycle results

The final report uses a closed result set:

- `COMPLETE`: every required item has one complete accounted disposition;
- `NO_CHANGE`: the complete cycle proves byte/fingerprint equality to the last
  approved source state;
- `INCOMPLETE_RETRYABLE`: all successful work is retained, but at least one
  required item remains retryable;
- `SOURCE_CONTRACT_CHANGED`: a root or identity contract no longer parses or
  reconciles safely;
- `EVIDENCE_INTEGRITY_FAILURE`: retained bytes, hashes, objects, or journal
  lineage fail read-back; or
- `BUDGET_EXHAUSTED`: the cycle reached an admitted safety ceiling.

Only `COMPLETE` or a fully proved `NO_CHANGE` may advance to processing or
release construction. `INCOMPLETE_RETRYABLE` is progress, never success.

## 4. Legislation acquisition

### 4.1 Baseline

The already retained HKeL data archives are the primary bulk baseline input.
The system imports their existing verified object references and retained
archive/member fingerprints into the journal without copying or redownloading
their bodies.

Independent archives may be parsed concurrently. Each archive is opened under
the existing bounded ZIP/XML security contract. Member identities, English and
Traditional-Chinese pairing, XSD/specification bindings, structural profiles,
and known review issues are checkpointed so an unchanged archive is not parsed
again during an ordinary source cycle.

Verified or assisted official copies, Editorial Records, Basic Law materials,
Annex III, and Instruments and Others remain separate required work-item
classes. HKeL XML does not silently prove a missing required copy.

### 4.2 Gazette events and updates

GLD e-Gazette remains the originating publication/event authority. Its local
session/challenge compartment discovers issued artifacts and event facts;
artifact downloads enter the same durable queue. HKeL Gazette material remains
backcapture, recovery, reconciliation, and gap evidence rather than a silent
replacement for GLD.

An ordinary update first compares current inventory/archive fingerprints. Only
new or changed archives and newly discovered Gazette/editorial artifacts are
downloaded or parsed. Unchanged archives reuse their verified journal/object
state.

## 5. Cases acquisition

### 5.1 Baseline enumeration

The 1-July-1997-to-cutoff range is partitioned into independent year shards.
Each year owns a deterministic page queue and complete page/listing inventory.
Year shards may run concurrently within the four-per-host limit; pages within a
year follow the publisher's required pagination order.

The existing verified Judiciary listing pages through 2011 page 363 are
imported into the new journal by exact object/report binding. They are not
redownloaded solely to populate the new checkpoint model.

Every discovered official listing immediately creates durable judgment,
correction/reissue, language, translation, alias, and proceeding-identity work
items. Enumeration does not wait for judgment downloads, and downloads do not
erase or obscure incomplete enumeration.

### 5.2 Artifact download and incremental updates

Judgment/artifact workers consume the durable queue concurrently under the
same host limit. Existing verified bodies are reused by content/object binding.
Timeouts and source outages become retryable items while unrelated artifacts
continue.

After the complete baseline, the registered new-judgment and RSS procedures
drive frequent incremental discovery. A periodic bounded reconciliation still
checks the complete official listing universe so RSS omissions cannot become
false no-change.

HKLII remains non-controlling discovery and discrepancy evidence. It cannot
complete an official Judiciary work item.

## 6. Processing, models, and promotion

Verified acquisition batches may enter local deterministic parsing and model
preparation before the whole baseline completes. This improves utilization but
does not permit partial release or promotion.

- Legislation batches produce candidate canonical bilingual trees, legal-event
  dossiers, and explicit review issues.
- Cases batches produce candidate judgment structure, passages, propositions,
  and later-treatment dossiers through the admitted two-pass workflows.
- Azure model and embedding calls remain bound to exact immutable profiles,
  token budgets, prompts, evidence objects, and strict output schemas.
- Candidate embeddings may be staged locally or in an explicitly admitted
  disposable target, but the complete Pinecone Serving State changes only from
  one approved complete two-family proposal.
- The named local human reviews one frozen proposal whose coverage report lists
  every required Legislation and Cases scope. Approval is retained, single-use,
  drift-invalidated, and automatically wakes promotion.

## 7. Scope and plan reconciliation

The canonical V1 specification, Coverage Matrix, due-cycle counts, registers,
package manifests, reporting labels, acceptance gates, and operator docs must
be advanced coherently from three included families to two.

- HKEX scopes and sources become explicit post-V1 exclusions rather than
  deleted vocabulary.
- HKEX is absent from V1 scheduling, source admission, package readiness,
  proposal completeness, Pinecone composition, and `V1_ADMITTED` evaluation.
- Plans 3 and 4 become the only authentic legal-package prerequisites.
- Plan 5 is preserved as deferred work.
- Plans 6 through 9 continue, but their release/proposal/target arithmetic binds
  only Legislation and Cases.
- The honest product label becomes **complete Hong Kong legislation and
  post-1-July-1997 binding-case propositions V1**.

## 8. Storage and migration

Existing immutable evidence is not duplicated. Migration records bind old
report/object identities into new journal entries and prove read-back before
reuse.

Superseded test output, caches, and reproducible basetemp remain deletable.
Historical source attempts needed only for audit or regression may be moved to
the approved secondary archive after a manifest/hash/metadata verification.
The latest active baseline, journal, required regression fixtures, and objects
needed for resume remain on the SSD.

## 9. Verification strategy

Routine changes use focused tests for journal transitions, resume, concurrency,
source adapters, exact accounting, and false-success prevention. The complete
repository gate runs at plan exits rather than after every source-shape fix.

Required integration proofs include:

1. interruption after arbitrary successful items, restart, and exact resume
   without repeating those requests;
2. four active requests on one host never becoming five;
3. deterministic final bytes under different completion orders;
4. one retryable outage not stopping unrelated work;
5. root contract drift stopping before unsafe child requests;
6. journal/checkpoint/object tamper failing closed;
7. retained HKeL and Judiciary evidence importing without network access;
8. a complete baseline followed by a small incremental changed cycle;
9. a complete no-change cycle producing no model, embedding, proposal, or
   Pinecone effects; and
10. one approved changed cycle producing the exact complete two-family target,
    read-back, backup, Serving State transition, and rollback proof.

## 10. Authorization and non-goals

The user approved this architecture, including the written specification and
bounded four-per-host read-only source concurrency, on 2026-09-02. This
approval does not authorize accepting new
publisher terms, entering credentials or personal data, destructive evidence
deletion, Pinecone deletion, deployment, commit, or push.

This design does not weaken strict model-output parsing, source-rights
boundaries, evidence read-back before success, or Approval before external
writes. It does not add HKEX, Principles, pre-1-July-1997 Cases, full judgments
as searchable records, Ask.Legal routing, or Azure application hosting to V1.
