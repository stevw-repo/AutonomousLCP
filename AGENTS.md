# AskLegal Legal Database Pipeline — Agent Instructions

## Purpose

This repository is the greenfield modular monorepo for Ask.Legal's autonomous
legal-database pipeline. It owns the complete pipeline code while preserving
strict capability, credential, approval, evidence, and deployment boundaries
inside the repository.

The repository is design-first. Its architecture and implementation-facing
design baseline is accepted through ADR 0099, including the six M2–M7 protocol
documents under `docs/design/`. M1 through the complete local/synthetic M7
milestone are implemented and proved. M4 uses deterministic synthetic sources
and filesystem-backed local primary/recovery vault fakes. M5 adds the exact
executable-package/lifecycle/rule engine and one reserved `ZZZ` package. M6
adds immutable corpus/proposal construction, named-human Approval governance,
exact embedding/target/backup/routing boundaries, and a local promotion worker
with deterministic fakes. No real source, cloud storage, model, embedding,
Pinecone, backup, or routing system was accessed. All real external, Azure,
deployment, and production effects remain disabled. M7 completion proves only
the reserved offline synthetic platform and does not authorize M8, external
calls, corpus publication, Pinecone mutation, deployment, or production action.

## Strict repository and memory isolation

This repository has its own project memory. Instructions, decisions,
approvals, priorities, working state, and conversation context from
`Ask.Legal Dataprep`, `Ask.Legal Distillation`, `Ask.Legal Releases`,
`Ask.Legal Pinecone`, or any other workspace do not apply here.

- Read and update only this repository's continuity files for an ordinary
  greenfield task.
- The presence of another workspace root does not authorize reading it,
  importing its context, changing it, or treating its work as a prerequisite.
- Do not copy a legacy requirement, schema, task priority, approval, status, or
  next step into this repository.
- Do not update a legacy repository or its memory as a side effect of work
  here.
- Inspect legacy material only when the user explicitly requests a named
  cross-repository comparison or reference check. Treat the result as
  non-authoritative evidence until the user makes a greenfield decision.
- Even for an explicitly cross-repository task, keep each project's decisions,
  working state, authorization, and handoff files separate. Never create an
  implied approval or shared task queue.

If repository scope is ambiguous, stay within this repository and ask before
crossing the boundary.

## Start every non-trivial task here

Before planning, editing, or running project commands:

1. Read this file completely.
2. Read `docs/agent/CONTEXT.md`, `docs/agent/DECISIONS.md`,
   `docs/agent/ROADMAP.md`, and `docs/agent/WORKING_STATE.md` completely.
3. Read the relevant portions of
   `docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md` and applicable ADRs under
   `docs/adr/`.
4. Inspect repository status and existing files. Preserve unrelated work.
5. Classify the request as design, implementation, diagnosis, or operation.
   Authorization for one class does not imply authorization for another.
6. State assumptions and distinguish settled decisions, recommendations,
   verified facts, and open questions.

Do not create duplicate planning or context documents when an existing file
already serves the purpose.

## Canonical documentation

- `docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md` is the canonical initial
  design of the complete intended system. It is comprehensive but not a final
  specification.
- `docs/adr/` records accepted, hard-to-reverse architecture decisions.
- `docs/agent/CONTEXT.md` defines the project's stable domain language.
- `docs/agent/DECISIONS.md` records settled product and policy decisions.
- `docs/agent/ROADMAP.md` tracks overall delivery progress, proof dependencies,
  milestone exit gates, and the durable work queue.
- `docs/agent/WORKING_STATE.md` records the current objective, blockers,
  validation, changed files, and exact next steps.

Keep these files handoff-ready. Conversation history is temporary and must not
be the only place an important fact or decision exists.

## Greenfield and legacy boundary

The existing local repositories named `Ask.Legal Distillation`,
`Ask.Legal Releases`, and `Ask.Legal Pinecone`, together with the earlier
contents of this repository, are reference material only. They do not define
the target repository layout, contracts, data model, or implementation.

Do not introduce a production dependency on legacy code or artifacts merely
because they already exist. Reuse requires an explicit decision, a current
contract, focused tests, and evidence that the component fits the greenfield
design.

## Modular monorepo boundary

The planned repository contains several separately runnable and separately
permissioned applications:

- **control plane** — scheduling, workflow state, source registry, coordination,
  coverage status, and reports;
- **review application** — human inspection, approval, rejection, and
  revocation;
- **acquisition worker** — source watchers, scrapers, and immutable evidence
  capture;
- **legal-processing worker** — parsing, jurisdiction-and-material rules,
  distillation, and evidence-bound AI work; and
- **promotion worker** — embeddings, backups, replacement serving targets,
  verification, cutover, and exact approved retirement.

Shared packages hold domain objects, versioned contracts, management-register
and evidence-vault interfaces, source connectors, legal desks, corpus
construction, promotion rules, reporting, observability, and test utilities.

One Git repository does not mean one process, database role, credential set, or
deployment. Security boundaries are enforced through separate applications,
identities, secrets, networks, deployment jobs, and authorization checks.

## Dependency rules

- Applications may depend on packages; packages must not depend on applications.
- Domain and contract packages must not depend on infrastructure adapters.
- Source connectors capture source facts; they do not decide legal status.
- Legal desks interpret preserved evidence; they do not approve or deploy.
- Processing creates candidate records; it does not publish or promote them.
- Corpus construction creates immutable releases and desired-state inventories;
  it does not authorize production.
- The promotion worker consumes only an exact valid approval bound to one
  frozen promotion manifest.
- Only the promotion worker may receive production embedding, backup, Pinecone,
  or Ask.Legal routing credentials.
- Forbidden imports and dependency directions must be enforced by automated
  architecture tests.

## Data and artifact rules

Git contains code, schemas, prompts, small test fixtures, evaluation
definitions, infrastructure configuration, and documentation only.

Do not place full legal corpora, source snapshots, immutable releases,
embedding caches, reports containing operational data, backups, credentials,
or production runtime state in Git. Local development may use an ignored
`var/` tree that imitates external stores.

Pinecone is a replaceable serving copy. The management register records what
the system believes and is doing; the evidence vault preserves what proves and
reproduces it.

## Authorization boundaries

- Documentation and design work does not authorize implementation.
- Implementation work does not authorize external source access, AI or
  embedding-provider calls, release publication, backup mutation, Pinecone
  access, pruning, deletion, deployment, or Ask.Legal routing changes.
- A successful capability does not authorize the next capability.
- One complete human approval covers the exact frozen promotion package.
- Any material change to evidence, records, settings, targets, recovery
  readiness, or fingerprints invalidates approval.
- Broad or inferred deletion is forbidden.
- Do not commit, push, open a pull request, publish, deploy, or send an external
  message unless the user requests that exact action.

Read-only inspection and local validation are allowed when relevant.

## Design rules

- Design the intended complete pipeline as a whole.
- Do not place pilot scope, staged product versions, rollout plans, estimates,
  temporary operating arrangements, or migration sequencing in the overall
  design.
- Use simple language first and define unavoidable specialist terms.
- Preserve the distinction between case-derived propositions and each
  jurisdiction's publisher-derived Principles.
- Preserve approved Regulatory Materials as a separate family; do not relabel
  non-statutory regulatory rules as legislation or mix unincorporated guidance
  into rule records.
- Keep uncommenced legislation outside ordinary current-law search.
- Never describe uncertain legal status as automatically resolved.
- Make destructive behavior exact, owned, evidence-backed, reversible, and
  independently verifiable.
- Prefer diagrams and tables when they materially clarify ownership, state,
  sequence, or trust boundaries.
- Record unresolved choices explicitly rather than inventing a decision.

## Implementation rules

The currently selected production baseline is Python 3.14, the FastAPI and
strict Python boundary toolchain, Azure SQL for the Management Register,
Azure Container Apps with one workload-profiles environment per application,
the standalone Python Durable Task SDK with managed Scheduler, and separately
administered Azure Blob primary and recovery vaults with Azure Confidential
Ledger for database digests, and one private Premium Azure Container Registry
with ABAC repositories and attested image admission, plus one Application
Gateway WAF_v2 with a public Review listener, a private control listener, and
separate Entra API authorization boundaries, plus repository-owned Bicep and
Azure Pipelines with workload-federated identities, fresh Microsoft-hosted
control-plane agents, and separate stateless Managed DevOps Pools for private
ACR and Azure SQL work, plus Azure Monitor and immutable operational-audit
archives; see accepted ADRs 0089 through 0098. Decision 1 of the ADR 0099
review selects stateless Azure OpenAI models sold by Azure through Microsoft
Foundry for admitted generative semantic tasks and embeddings, matching Ask.Legal
Backend's provider family. Decision 4 selects a separate restricted Ask.Legal
App Service candidate slot for validated manual production swap and reverse-
swap rollback; the development slot remains development-only. ADR 0099
includes the decision-5 environment/jurisdiction/date/state Pinecone
naming contract. Decision 6 selects one complete immutable, fingerprint-bound
Coverage Status Manifest with protected retrieval, per-routing-generation
verified caching, activation blocking, and fail-visible unavailability; it
deliberately adds no coverage-signing identity or key lifecycle. Decision 7
selects LLM-assisted Gazette-event analysis/challenge and Reconstruction Plan
decision/challenge, while deterministic checks and human-adjudicated reference
truth govern evaluation and every other unallocated task defaults to
deterministic handling for now.
The completed local foundation spikes
pin Python 3.14.7 and its exact development locks, enforce repository-wide
strict Pyright plus the repository-owned boundary checker, prove the selected
SQL and durability adapters locally, and prove locked offline package
installation and reproducible package/container inputs.
The local image-admission proof additionally pins its Linux amd64 toolchain and
fresh Grype database, proves reproducible synthetic OCI and evidence graphs,
closed vulnerability/licence rules, test-only signing, exact recovery, and a
locked-down runtime without granting production signing or registry authority.
The evolved local architecture proof governs all five runnable local
application boundaries and 14 shared packages with a closed dependency,
import, cycle, declaration, and capability-ownership policy. M3 adds only local
interfaces and fail-closed adapters; it grants no external runtime capability.
M2 supplies the complete framework-free lifecycle and operation domain,
quarantine re-entry, a typed Management Register port and deterministic fake,
and two exact forward-only SQL migrations with real SQL Server proof for
command/replay/version/concurrency, event and intent atomicity, effect leases,
fencing, receipts, projections, recovery rows, ledger verification, and five
procedure-only application roles. Replay and transport resolution remain
separate from durable Command Results; Effect Intents bind a closed type,
exclusive owner, capability, and sanitized destination before any effect.
M2 performs no external effect. M7 adds the stable repository-owned
`asklegal-local` reset/prove interface, a closed 32-scenario expected-result
catalogue, network denial, two path-distinct executions, and one deterministic
report that says only `local synthetic platform proved`. It composes the real
local M3–M6 boundaries without adding a sixth deployable application or any
remote capability. Exact deployed model versions and measured
values outside those spikes,
capacity, security assignments, retention, recovery, and operational settings
remain admission profiles/evidence and have no implicit defaults. When
implementation is explicitly authorized:

- begin from domain objects, state transitions, and versioned contracts;
- keep legal-status rules jurisdiction- and material-specific;
- make jobs retryable, idempotent, fingerprint-bound, and auditable;
- validate complete inputs before any external call;
- quarantine uncertainty and incomplete work instead of guessing or silently
  skipping it;
- isolate source text from tools, code execution, secrets, and approval state;
- apply least privilege to every application;
- test failure, restart, stale approval, overlap, recovery, and malicious input;
  and
- preserve exact evidence before any production mutation.

## Reporting

At the end of a task, report:

- files inspected and changed;
- decisions made and questions left open;
- validation performed;
- authorization gates reached;
- external or remote actions performed, or explicitly state that none occurred;
  and
- continuity files updated.
