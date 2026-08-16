# AskLegal Legal Database Pipeline — Working State

Updated: 2026-08-16

## Current objective and status

The architecture and implementation-facing design baseline is accepted through
ADR 0099, including all six D1–D6 protocols. The user decided all seven material
choices individually and then explicitly accepted the reconciled package on
2026-08-16.

The user separately authorized and implementation produced the first bounded
M2 domain-kernel slice: five framework-free lifecycle machines with immutable
versioned state and pure transition results. A 2026-08-16 audit found that this
slice must not yet be called fully proved: the five exact transition catalogues
formerly existed only in Python. The user then authorized and completed the
ordered five-step lifecycle correctness correction. The first bounded M2
lifecycle checkpoint is now accepted: five normative versioned machine
contracts, all six separately approved guard decisions, runtime-exact primitive
validation, independent Python-to-contract equivalence, and one reproducible
ordinary developer bootstrap/test command all pass.
No Command/Result or Effect Intent/Receipt feature implementation, application
runtime, external operation, or production operation is authorized. Decision 7 gives
admitted LLM tasks bounded semantic-decision authority where deterministic code
performs poorly, while checks, tests, validation, final execution, Approval,
and production effects remain deterministic or human-owned.

Decision 1 is settled: match Ask.Legal Backend's provider family by using Azure
OpenAI for both stateless generative proposals and embeddings. The existing
backend's Cloudflare AI endpoint and API-key authentication were observed but
are not inherited by this provider decision; the pipeline retains its private-
Azure and Entra workload-identity security direction.

Decision 2 is settled: use one human `PipelineAdministrator` role assignable
to multiple named people; remove action-specific step-up freshness, an
independent Approval TTL, separate human roles, and absence-cover machinery.
Keep named-human audit evidence, a non-empty reason, single consumption,
revocation, current-role checks, and exact manifest/predicate invalidation.
Technical application and workload identities remain separate. The existing
Approval contract is reconciled at version 1.1.0: it has no `valid_until`
field or `APPROVAL_EXPIRED` lifecycle state. A failed manifest validity
predicate produces `APPROVAL_INVALIDATED`.

Decision 3 is settled: use severity and named administrator assignment, notify
immediately for urgent release-blocking or potentially misleading current-law
issues, permit optional administrator-set due times, and define no fixed review
SLA or periodic overdue engine. Time passing never releases or resolves
material.

Decision 4 is settled: use a separate restricted Ask.Legal App Service
`candidate` slot for one complete production routing generation, validated
manual swap, request-generation pinning, post-cutover verification, and
reverse-swap rollback. The existing development slot remains development-only.
Production admission must prove the plan's slot limit and shared capacity.

Decision 5 is settled: use
`asklegal-<env3>-<jur3>-<YYYYMMDD>-<state12>`, normally 38 characters with an
internal 40-character limit. Enforce lowercase/dash syntax, the current
Pinecone API and actual project-ID hostname limits, and full-fingerprint
collision checks. Names are labels; the complete fingerprint remains authority.

Decision 6 is settled: use one complete immutable Coverage Status Manifest per
routing generation. Bind its exact SHA-256 fingerprint and protected immutable
Azure download reference; retrieve it through authenticated protected storage;
verify and cache it by routing generation; block activation when it is missing,
incomplete, or mismatched; and show a global `coverage status unavailable`
warning when neither valid stored nor cached bytes exist. Do not add a dedicated
coverage-signing identity, key, rotation, or signature-validation lifecycle.
Coverage Status Manifest version 1.1.0 removes `signature_policy_state` and
requires per-scope verification time, exact gap/Quarantine/source-failure
references, and a closed status-matched warning code.

Decision 7 selects LLM-assisted Gazette-event analysis/challenge and
Reconstruction Plan decision/challenge. Every
other unallocated task defaults to `NO_GENERATIVE_LLM` for now, including
Principles transformations and tasks for new jurisdiction/material families.
Together with the earlier Case, later-treatment, and HKEX allocations, the
target design has twelve logical generative stages. No pipeline LLM or
embedding task is runnable today; the foundation marks both provider
capabilities disabled. All legal authority, final source bytes, identity,
release, Approval, and production effects remain deterministic or Legal
Desk/human boundaries regardless of the proposal method.

Approved Decision 7 authority boundary: do not reduce admitted LLM work to
non-consequential advice that a deterministic rule must independently recreate.
For admitted variable-language tasks, the model should decide the bounded
semantic fields and ordinary result, subject to exact evidence binding,
independent challenge, deterministic validation, and human escalation for
unresolved or exceptional cases. Source authenticity, exact source bytes,
identity, coverage arithmetic, contract validity, release, Approval, and
production effects remain outside model authority. Offline evaluation uses
deterministic checks and acceptance calculations against human-adjudicated
reference truth; the earlier model-assisted evaluator selection is superseded.

All seven M1 local checkpoints remain complete. M2 remains in progress only
because its narrow Management Register checkpoint exists. M3 has declarative
application/package boundary skeletons but no runtime behavior. Stop before
further domain, application, external-service, Azure, deployment, or
production work without new explicit implementation or operational
authorization. Design closure grants none.

## Current correctness audit

The overall architecture, trust boundaries, Azure-only direction, Python
choice, five-application isolation, deterministic validation boundary, and
bounded LLM allocation remain coherent with the accepted decisions. The first
M2 lifecycle code is framework-free, immutable, closed-world, type-clean, and
locally green.

The correctness audit is closed. The normative and Python machines now agree on
37 per-machine states and 61 transitions. JSON contracts remain authority for
event names and guard preconditions; this pure kernel implements the structural
state/version boundary and performs no command authorization or effect. The
selected stack and M2-M7 architecture did not need reopening.

A follow-up design-consistency review on 2026-08-16 found and the user
authorized correction of a bounded documentation/contract reconciliation
backlog. The correction is complete: M3 uses only the human
`PipelineAdministrator` role; M6 contains no business-day calendar
contradiction; M2 explicitly defers to and restates the approved normative
machines and guard rules; Approval and Coverage Status are amended at contract
version 1.1.0 with independent positive/negative fixtures; and accepted ADR
0099/canonical-design wording is normalized. The Approval amendment also
removes the obsolete `APPROVAL_EXPIRED` state so no hidden independent TTL
survives.

These are real cleanup items, not missing trust boundaries or unsettled product
choices. Exact regions, capacity, costs, recovery/retention values, source
rights and inventories, deployed-model profiles, and real evaluation results
remain admission evidence rather than architecture gaps. The current Azure
topology is security-heavy and its promised simplicity/affordability is not yet
proved; M8 must measure complete cost and operator burden before production
commitment.

## Build-readiness audit result

`docs/design/M2_M7_BUILD_READINESS_DESIGN_AUDIT.md` records twelve exact gaps.
Accepted ADR 0099 closes them with:

1. D1 — Domain and Register protocol;
2. D2 — Application interfaces;
3. D3 — Acquisition and Evidence protocol;
4. D4 — executable Legal Desk package;
5. D5 — Review and Promotion protocol; and
6. D6 — end-to-end conformance plan.

The audit corrects proposal-package ownership: the control plane coordinates
effect-free preparation through pure corpus/promotion services; the Review API
records the human decision; the promotion worker consumes only the exact
approved manifest. The current architecture spike remains valid checkpoint
evidence, but its manifest must be revised and re-proved before M3 runtime
implementation.

The accepted package makes M7 use one closed test-only synthetic Legal Desk package. That proves the
platform only and cannot satisfy any Hong Kong source, legal, evaluation, or
production-readiness gate. Exact deployed model profiles and measured
operational values remain admission evidence, not design gaps. Admin-portal
integration remains after the stable Review API and pipeline work.

## Architecture checkpoint result

The workspace contains 18 installable members:

- 5 declarative application skeletons: control plane, Review API, acquisition
  worker, legal-processing worker, and promotion worker; and
- 13 shared packages: contracts, domain, Management Register port and adapter,
  durable-task adapter, Evidence Vault, source connectors, legal desks,
  processing, corpus, promotion, reporting, and observability.

`tools/architecture_spike_manifest.json` closes the member set, exact metadata,
permitted internal/external dependencies, roles, 30 capability ports, and
exclusive sensitive-effect owners. `tools/architecture_spike.py` discovers
future members and rejects coverage or metadata drift, undeclared dependencies
or imports, package-to-application dependencies, cycles, declaration drift,
and exclusive-capability drift. The proved graph has 5 applications, 13
packages, 70 direct internal edges, and policy fingerprint
`sha256:b4ec8fd3dc09983460657823664ad6046eca8f573e6dcdcd30dcaf91d93d9475`.

The skeletons contain no FastAPI route, process entry point, worker loop,
configuration loader, credential, provider client, external call, or effect.
Capability declarations are policy assertions, not granted runtime authority.

## Package and lock checkpoint after expansion

The root uv workspace and exact lock now cover all 18 members. The complete
network-disabled package proof produced 18 byte-identical wheels across two
path-distinct builds and passed 18 separate clean non-editable installations;
each installation exposed only its declared transitive workspace closure and
no development tools. Current artifacts:

- lock SHA-256:
  `8acc9a0215fbd26e2903e2d905710e4b1ad5bd38c4429bcc752ce49f89ffb7a9`;
- deterministic container-input bundle SHA-256:
  `4acad3d6f49a419b32946e711ca8d805f864ef37524f0b4f8b4c94ca96adc455`.

The earlier contract, type, real SQL Server, Durable Task SDK/emulator, and
synthetic image-admission proof results remain unchanged. SQL Server and
Durable Task emulator integrations were not rerun for this checkpoint.

## Validation performed

First bounded M2 domain-lifecycle checkpoint on 2026-08-16:

- implemented five framework-free immutable lifecycle machines with 37 closed
  states and 60 exact transitions;
- proved every declared transition and every unlisted state pair, exact version
  increments, stale-version rejection, cancel-after-promotion prohibition,
  retry return, mitigated-gap resolution, terminal closure, and linked
  recurrence using 15 focused tests;
- Ruff repository check: pass;
- strict Pyright 1.1.413: 0 diagnostics;
- Python boundary policy: 48 files and 8 exact reviewed exceptions pass;
- architecture tests: 5 passed;
- ordinary suite with local loopback permission: 97 passed and 4 opt-in
  integrations deselected;
- complete offline package proof: 18 reproducible wheels and 18 isolated
  installs; domain wheel SHA-256
  `2f53da3d296ea03069771db2b3bd34e93c42b4eb2b4d6154ec527ef81af38da3`;
- contract/document validator and `git diff --check`: pass.

Correctness audit on 2026-08-16:

- confirmed no versioned machine contract or lifecycle catalogue under
  `contracts/` contains any of the five new lifecycle state families;
- confirmed the focused exhaustive test derives allowed and forbidden cases
  from the Python machine tables themselves rather than an independent
  normative contract;
- confirmed D1 fixes state families and key semantic rules but does not
  enumerate all 60 chosen edges or their guard predicates;
- reproduced runtime acceptance of `version=True` and `version=1.5`, including
  applied transitions to versions `2` and `2.5` respectively;
- confirmed the checked-in package test command's current `.venv` cannot import
  `asklegal_domain`; host plugin isolation is already documented, and an
  explicit `PYTHONPATH` was needed for this focused audit run;
- fresh focused validation with explicit workspace source paths: 40 passed;
- focused Ruff check: pass; strict Pyright: 0 diagnostics; and
- `git diff --check`: pass.

Ordered lifecycle correction step 1 on 2026-08-16:

- added versioned closed-world Pipeline Run, Work Item, Source Contract Review,
  Coverage Gap, and Quarantine machine contracts containing the current 37
  per-machine states and 60 implementation-selected structural edges;
- added 33 unique state codes to the global lifecycle catalogue;
- changed the existing Source Contract Review, Coverage Gap, and Quarantine
  boundary schema enums from the historical generic review states to their
  entity-specific states and corrected their inventory machine references;
- regenerated the exact contract package manifest;
- contract, catalogue, state-machine, inventory, fixture, documentation,
  package, and reproducibility validation: pass;
- package-manifest fingerprint:
  `sha256:af3c55bffd476a9a1a1067040a7e623fdce203c1e2cd00d69a3540ece213e1d6`;
  and
- `git diff --check`: pass.

At the end of step 1 these files were normative contract candidates and
acceptance remained pending. The following recorded decisions and completed
steps 3-5 resolved that temporary state; the checkpoint is now accepted.

Ordered correction step-2 decision 1 is accepted. The normative Pipeline Run
contract now forbids `RUN_PROMOTING → RUN_BLOCKED`: unknown outcomes remain in
`RUN_PROMOTING` under fencing and reconciliation, then resolve only to verified
success, verified rollback, or proved final failure. The normative five-machine
set therefore has 59 transitions while the Python implementation still has 60;
that temporary, explicit mismatch will be corrected before the independent
equivalence proof in step 4.

Ordered correction step-2 decision 2 is accepted. Every applicable
pre-promotion state retains guarded terminal edges to `RUN_BLOCKED`,
`RUN_CANCELLED`, and `RUN_FAILED`. Blocked means potentially correctable but
requires a new linked/rebased run; cancellation requires a named
`PipelineAdministrator` and no irreversible checkpoint; failed means
non-retryable or permitted attempts exhausted. `RUN_REJECTED` remains
human-rejection-only.

Ordered correction step-2 decision 3 is accepted. Operator-facing Work Item
classification is reduced to Completed (`WORK_SUCCEEDED`, `WORK_NO_CHANGE`),
Needs follow-up (`WORK_BLOCKED`, `WORK_QUARANTINED`), Stopped
(`WORK_CANCELLED`, `WORK_FAILED_FINAL`), and non-terminal Retrying
(`WORK_RETRY_WAIT`). Detailed states remain normative for automation and audit.
Terminal work never reopens; only retry wait retains identity and inputs.

Ordered correction step-2 decision 4 is accepted. The same unresolved Coverage
Gap may switch directly between carry-forward and withholding mitigation when
its identity and affected scope are unchanged. Each switch requires a new
authenticated administrator decision and exact evidence. The normative
five-machine set now has 61 transitions; Python remains intentionally
unchanged until the later implementation/conformance steps.

Ordered correction step-2 decision 5 is accepted. Source Contract Reviews,
Coverage Gaps, and Quarantines share one recurrence/supersession rule: terminal
records never reopen; material subject/scope/definition change supersedes only
a non-terminal record and creates one new linked `OPEN` replacement; recurrence
after terminal closure creates a new linked `OPEN` record without mutating the
predecessor.

Ordered correction step-2 decision 6 is accepted. A retry counts only after
processing starts. Delivery retries retain `WORK_DISPATCHED`, reuse one stable
dispatch identity, and consume no work-attempt allowance. Only a retryable
failure from `WORK_RUNNING` may enter `WORK_RETRY_WAIT`; the direct
`WORK_DISPATCHED → WORK_RETRY_WAIT` edge is explicitly forbidden. All identified
step-2 ambiguities are now settled.

Ordered lifecycle correction steps 3-5 completed on 2026-08-16:

- exact runtime validation rejects non-string identities, raw-string states,
  Boolean or fractional versions, malformed events, and inconsistent results;
- Python implements the final approved 37 states and 61 transitions;
- a repository-level independent test reads the five JSON machine contracts
  and proves exact machine ID, version, entity type, complete states, initial
  state, terminal states, and structural transition equality;
- `python3 -m tools.dev_test --uv <uv-0.12.5> --node <node-24.19.0>` performs
  one frozen all-member sync, verifies Python 3.14.7, isolates host pytest
  plugins and workspace sources, supplies the exact Node oracle, and runs the
  ordinary suite;
- exact one-command proof: 103 passed and 4 opt-in integrations skipped;
- repository Ruff: pass; strict Pyright 1.1.413: 0 diagnostics; Python boundary
  policy: 48 files and 8 exact reviewed exceptions; contract/document/package
  validator and architecture tests: pass;
- current contract package-manifest fingerprint:
  `sha256:ff8a84ed971b62bb1b27451a61b0d43620c51ec55700ca492b562b4f901df594`;
- complete offline package proof: 18 byte-identical wheels across two builds
  and 18 isolated installs; domain wheel SHA-256
  `0a53d10bfffaf3ff5a61a4272f6d032cbfefc78b298f85c3e66a213ed6849ced`;
- lock SHA-256 remains
  `8acc9a0215fbd26e2903e2d905710e4b1ad5bd38c4429bcc752ce49f89ffb7a9`;
- container-input bundle SHA-256 is
  `4acad3d6f49a419b32946e711ca8d805f864ef37524f0b4f8b4c94ca96adc455`;
  and
- `git diff --check`: pass.

Bounded accepted-design reconciliation completed on 2026-08-16:

- M3's Control API authority table now uses only the named human
  `PipelineAdministrator` role while preserving technical application,
  capability, evidence, and aggregate checks;
- M6 contains no business-day calendar requirement, M2 explicitly binds its
  readable lifecycle summary to the five normative machines and six approved
  guard decisions, and ADR 0099/canonical-design wording reflects acceptance;
- cross-cutting contract package 1.1.0 removes independent Approval expiry and
  `APPROVAL_EXPIRED`, adds exact Coverage Status per-scope verification,
  evidence, and status-matched warning fields, and corrects effect-free
  Promotion Manifest preparation ownership to the control plane;
- the independent Node oracle and Python implementation agree on 19 synthetic
  fixtures, including positive and negative cases for both amendments;
- exact developer command: 105 passed and 4 opt-in integrations skipped;
- repository Ruff: pass; strict Pyright 1.1.413: 0 diagnostics; Python boundary
  policy: 48 files and 8 exact reviewed exceptions; contract/document/package
  validator and `git diff --check`: pass;
- contract package-manifest fingerprint:
  `sha256:ff8a84ed971b62bb1b27451a61b0d43620c51ec55700ca492b562b4f901df594`;
- complete offline package proof: 18 byte-identical wheels across two builds
  and 18 isolated installs; `asklegal-contracts` wheel SHA-256
  `01563033af1288e384551b38351d47d5b2d55b13f4df132584739eccc2e82f99`;
- lock SHA-256 remains
  `8acc9a0215fbd26e2903e2d905710e4b1ad5bd38c4429bcc752ce49f89ffb7a9`;
  and container-input bundle SHA-256 remains
  `4acad3d6f49a419b32946e711ca8d805f864ef37524f0b4f8b4c94ca96adc455`.

Design closure accepted on 2026-08-16:

- recorded explicit user acceptance of ADR 0099 and D1–D6 after all seven
  material decisions were settled;
- changed the ADR, protocol, audit, canonical design, roadmap, README, agent
  instructions, decision log, stack recommendation, and handoff from proposed
  closure to accepted design baseline;
- retained separate implementation, external-call, deployment, and production
  authorization gates;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  links and reproducibility.

Decision 7 finalized on 2026-08-16:

- selected change-gated LLM analysis/challenge for Gazette events;
- selected LLM decision/challenge for structured Reconstruction Plans while
  preserving deterministic closed-operation execution and authentic final
  text;
- gave admitted model tasks authority over only their exact bounded semantic
  fields after independent challenge and deterministic validation;
- replaced model-assisted offline evaluation with deterministic checks and
  acceptance calculations against human-adjudicated reference truth;
- fixed `NO_GENERATIVE_LLM` as the current default for every other unallocated
  task, including Principles transformations and new material families; and
- reconciled ADR 0099, M5, the canonical design, audit, stack recommendation,
  roadmap, decisions, context, README, agent instructions, and this handoff;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  links and reproducibility.

Decision 7 allocation inventory on 2026-08-16:

- traced the LLM boundary and allocation through ADRs 0039, 0043, 0053,
  0065–0068, 0076, 0080, 0082, 0087, M5, the canonical design, contract
  inventory, and foundation capability status;
- distinguished actual runtime state (no admitted or runnable model task) from
  accepted target-design allocations;
- corrected the canonical overview to include ADR 0076's four HKEX Regulatory
  tasks and recorded the open Gazette, reconstruction-plan, and optional
  evaluator choices; and
- deferred decision 7 pending the user's review instead of recording a blanket
  default;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  links and reproducibility.

Decision 6 reconciliation on 2026-08-16:

- selected one complete immutable, fingerprint-bound Coverage Status Manifest
  per routing generation with authenticated protected retrieval and verified
  caching;
- retained activation blocking and fail-visible unavailability while removing
  the proposed signing identity, keys, rotation, expiry, and signature checks;
- recorded the required later versioned amendment to the current normative
  Coverage Status Manifest schema without changing the contract during design
  work; and
- reconciled ADRs 0079 and 0099, M6, the canonical design, audit, stack
  recommendation, Hong Kong audit, roadmap, decisions, context, README, agent
  instructions, and this handoff;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  links and reproducibility.

Decision 5 reconciliation on 2026-08-16:

- fixed `asklegal-<env3>-<jur3>-<YYYYMMDD>-<state12>` as the exact name;
- retained the internal 40-character limit, current Pinecone API and actual
  project-ID hostname checks, full-fingerprint collision hard failure, and ban
  on mutable/date-only names; and
- reconciled ADR 0099, M6, the canonical design, audit, stack recommendation,
  Hong Kong audit, roadmap, decisions, context, README, agent instructions, and
  handoff;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  links and reproducibility.

Decision 4 reconciliation on 2026-08-16:

- selected a separate restricted production-candidate App Service slot and
  kept the existing development slot development-only;
- fixed validated manual swap, per-request routing-generation pinning,
  post-cutover verification, and reverse-swap rollback;
- recorded the App Service plan slot-limit and shared-capacity proof as a
  production-admission prerequisite; and
- reconciled ADR 0099, M6, the canonical design, audit, stack recommendation,
  Hong Kong audit, roadmap, decisions, context, README, agent instructions, and
  handoff;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  links and reproducibility.

Decision 3 reconciliation on 2026-08-16:

- removed fixed one-, five-, and ten-business-day review SLAs, the required
  business-day calendar, and periodic overdue-notification machinery;
- retained severity, named administrator assignment, immediate urgent
  notification, optional administrator-set due times, and the invariant that
  elapsed time never releases or resolves material; and
- reconciled the domain, M6, M7, Hong Kong, canonical, ADR, audit, roadmap,
  decisions, context, README, and handoff language;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  links and reproducibility.

Decision 2 reconciliation on 2026-08-16:

- replaced the proposed six-role human catalogue with one
  `PipelineAdministrator` role assignable to multiple named people;
- removed action-specific step-up freshness, independent Approval TTL, and
  absence-cover machinery while retaining reasons, named-human audit,
  revocation, current-role checks, manifest/predicate invalidation, and exact
  single consumption;
- preserved separate application, workload, database, deployment, and effect
  identities;
- recorded that the current normative `approval_decision.valid_until` field
  requires a later versioned contract amendment rather than silently changing
  implementation during design work; and
- reconciled ADRs 0007 and 0096, proposed ADR 0099, D2/D5/D6, the canonical
  design, audit, stack recommendation, roadmap, decisions, context, and handoff;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  links and reproducibility.

Decision 1 verification on 2026-08-16:

- read-only inspection of Ask.Legal Backend verified Azure OpenAI-configured
  clients for both chat/generative requests and embeddings, followed by
  Pinecone vector queries;
- observed its Cloudflare AI endpoint and Azure OpenAI API-key transport but
  did not copy either into the pipeline decision;
- reconciled the selected provider family across ADR 0099, the audit,
  canonical design, stack recommendation, roadmap, context, README, agent
  instructions, decisions, and this handoff;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  links and reproducibility.

Decision-status correction on 2026-08-16:

- changed ADR 0099 and D1–D6 from accepted to proposed;
- removed stale design-complete and selected-choice claims from the canonical
  design, roadmap, context, stack recommendation, audits, README, and agent
  instructions;
- recorded the original seven user decisions and the requirement to present
  them one at a time before final package acceptance;
- `git diff --check`: pass; and
- the repository documentation/contract validator passes, including local
  Markdown links, headings, fenced blocks, and reproducibility.

Proposed design-closure-package validation on 2026-08-16:

- mapped all twelve audit findings to proposed D1–D6 protocol sections;
- drafted recommendations for the Azure OpenAI/Foundry stateless provider
  boundary, exact Pinecone naming rule, candidate-slot validated manual-swap
  routing, the then-proposed signed coverage interface, reviewer roles/timing,
  and Quarantine deadlines; decisions 1 through 6 later settled the provider,
  simplified human governance, simplified review timing, candidate-slot
  routing, naming, and the simpler fingerprint-bound coverage mechanism;
- reconciled the draft package across the canonical design, ADR 0099, audit,
  roadmap, decisions, context, and handoff; the later correction restores the
  material D1–D6 choices to open status;
- checked current official Microsoft and Pinecone constraints used by the
  provider, routing, and naming decisions; and
- validated Markdown links, ADR references, headings, trailing whitespace,
  and design-versus-admission/authorization language.

Design-audit validation on 2026-08-16:

- traced all M2–M7 roadmap build items and exit gates against the canonical
  design, ADR inventory, 54 cross-cutting objects, six lifecycle machines, and
  the five-application/13-package capability graph;
- confirmed the foundation has no normative general command/effect or
  pipeline-run contracts and that the shared bounded-review lifecycle has only
  `REVIEW_OPEN` and `REVIEW_RESOLVED`;
- confirmed the control plane lacks the pure promotion-package dependency and
  proposal-preparation capability even though the promotion worker correctly
  has only `approved_manifest_read`;
- corrected stale prose that treated all production infrastructure as open and
  stale project memory that prohibited the accepted conditional Hong Kong
  reconstruction path; and
- validated Markdown whitespace, internal document links, absence of trailing
  whitespace, and continuity consistency after the edits.

Final local validation on 2026-08-16:

- exact uv 0.12.5 offline lock check: 72 packages resolved;
- architecture proof: 5 applications, 13 packages, 70 dependency edges, and
  30 capability ports;
- architecture negative tests: undeclared member, forbidden import,
  package-to-app dependency, cycle, and capability drift all rejected;
- complete package proof: 18 reproducible wheels and 18 isolated installs;
- Ruff format/check: 171 files pass;
- strict Pyright 1.1.413: 0 diagnostics;
- repository boundary checker: 46 files and 8 exact reviewed exceptions pass;
- ordinary suite: 82 passed and 4 opt-in integrations skipped;
- independent Node contract-oracle tests pass within the ordinary suite; and
- `git diff --check`: pass.

The sandboxed ordinary-suite run could not create its two required IPv6
loopback sockets and reported 80 passed, 4 skipped, and 2 permission failures.
The unchanged suite was rerun with local socket permission and passed. Because
the host exposes unrelated pytest plugins built for another Python version,
use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q`.

## Authorization and external effects

Authorized and completed: the seven M1 local checkpoints, acceptance of ADR
0099 and D1–D6, the first bounded M2 lifecycle checkpoint including its
ordered correctness correction, and the bounded accepted-design/contract
reconciliation. The user also explicitly authorized committing and pushing the
reviewed accumulated repository checkpoint to the configured `origin`.

Still unauthorized:

- command/effect domain contracts and further domain-kernel or Management
  Register implementation;
- runnable application scaffolding, routes, workers, or a complete pipeline;
- source access, legal corpus work, model or embedding calls, Pinecone,
  backups, routing, or any provider effect;
- Azure resources, Bicep apply, pipeline execution, registry/signing,
  deployment, or production mutation; and
- pull request, publication, deployment, or any external message other than
  the explicitly authorized Git push.

This M2 checkpoint retrieved only public PyPI metadata and the exact pinned uv
0.12.5 Linux wheel into `/tmp/asklegal-m2-tools` to rerun the offline package
proof. Its SHA-256 matched the previously recorded
`3e195ccf1ed60c8bb24a6447ce306441a4181d54b602407e09bc56e963911c15`.
All wheel builds and isolated installs then ran offline. No source system,
model, embedding provider, Azure resource, Pinecone service, registry,
deployment, or production system was accessed.

The lifecycle correction again retrieved that exact public uv 0.12.5 Linux
wheel solely to validate the new one-command developer workflow. Its SHA-256
matched
`3e195ccf1ed60c8bb24a6447ce306441a4181d54b602407e09bc56e963911c15`.
The exact temporary `/tmp/asklegal-lifecycle-uv` tree (approximately 81 MB) was
removed after proof. Node.js 24.19.0 came from the existing local bundled
workspace runtime. No source system, model provider, Azure resource, Pinecone,
registry, deployment, or production system was accessed.

The bounded reconciliation retrieved the same exact public uv 0.12.5 Linux
wheel solely for the final offline package and documented developer-command
proof. Its SHA-256 again matched
`3e195ccf1ed60c8bb24a6447ce306441a4181d54b602407e09bc56e963911c15`.
The exact task-created `/tmp/asklegal-design-cleanup-uv` tree (approximately 80
MB) and downloaded metadata were removed after validation. No source system,
model provider, Azure resource, Pinecone service, registry, deployment, or
production system was accessed.

Host-environment diagnosis and repair on 2026-08-16 verified the failure mode
reported by the user: a prior temporary uv installation left a durable
shell-startup entry for `/tmp/asklegal-contract-tools/env`, which no longer
exists. The screenshot shows that reference in `.profile` at the time of
failure; the current `.profile` was already clean, and the surviving reference
was removed from `.zshrc`. The original `.zshrc` is recoverable at
`/home/stevw-s14/.zshrc.asklegal-backup`. The exact task-created temporary
directories `/tmp/asklegal-m2-tools` and `/tmp/asklegal-m2-uv-cache` were also
removed (approximately 292 MB combined). `.profile`, `.zshrc`, and `.bashrc`
now contain no matching temporary-env reference, and a Bash login-shell check
passes without the warning. The account's configured shell is Bash; `zsh` is
not installed, so a zsh-process check was not applicable. Future temporary
tools must be invoked directly and must never modify shell startup files.

This design-closure task used read-only official Microsoft Learn documentation
for Azure OpenAI/Foundry and App Service slot behavior and official Pinecone
documentation for current index-name constraints. It performed no external
write or operational action.

Decision 1 used read-only local inspection of the explicitly named
`Ask.Legal Core/AskLegal-Backend` code. It verified Azure OpenAI for both chat
and embeddings, a Cloudflare AI endpoint, API-key authentication, and separate
Pinecone queries. No legacy memory was read and no file outside this repository
was changed.

Decision 4 used read-only current Microsoft Learn documentation to verify that
deployment slots are live apps, standard swaps can be reversed, slots have no
separate charge, and supported slot counts vary by App Service plan tier. No
Azure resource or external system was changed.

Decision 5 preparation used read-only current Pinecone documentation to verify
the 45-character index-name API limit, allowed lowercase characters/dashes, and
the additional combined index-name/project-ID hostname constraint. No Pinecone
resource was accessed or changed.

Earlier architecture-checkpoint external activity was limited to approved
retrieval of public PyPI metadata and the exact uv 0.12.5 Linux wheel into
`/tmp/asklegal-architecture-tools`; its SHA-256 was verified as
`3e195ccf1ed60c8bb24a6447ce306441a4181d54b602407e09bc56e963911c15`.
All builds and installs then ran offline. No Azure resource, source system,
model provider, embedding provider, Pinecone service, registry, deployment, or
production system was accessed.

## Exact next step

Present the next bounded M2 feature checkpoint—immutable Command
Envelope/Result and Effect Intent/Receipt contracts plus pure domain
objects—for separate authorization. Do not start that implementation without
explicit authorization.

Ask.Legal admin-portal integration remains deferred until the complete local
pipeline and stable Review API work.

## Files changed by this checkpoint

First bounded M2 lifecycle checkpoint:

- `packages/domain/src/asklegal_domain/lifecycles.py` and public exports;
- `packages/domain/tests/test_lifecycles.py` with exhaustive closed-world
  transition coverage;
- five normative `contracts/transitions/*.json` machine files, lifecycle codes,
  entity-specific state schemas and inventory links, and the regenerated exact
  package manifest;
- `tools/tests/test_lifecycle_contract_equivalence.py` as the independent
  cross-package oracle;
- `tools/dev_test.py` and its README/tool-policy integration for one exact
  bootstrap/test command;
- root Ruff policy for the domain test file; and
- `AGENTS.md`, `README.md`, and all four continuity files.

Bounded accepted-design reconciliation:

- `docs/design/M2_DOMAIN_AND_REGISTER_PROTOCOL.md`,
  `docs/design/M3_APPLICATION_INTERFACE_PROTOCOL.md`,
  `docs/design/M6_REVIEW_AND_PROMOTION_PROTOCOL.md`, accepted ADR 0099, and the
  canonical design;
- Approval and Coverage Status schemas, Approval lifecycle/catalogue,
  cross-cutting inventory/package version, four independent fixtures, and the
  regenerated package manifest;
- Python schema/fixture/reproducibility tests and the package-manifest oracle;
  and
- `AGENTS.md`, `README.md`, and all four continuity files.

Design-closure changes:

- new `docs/design/M2_M7_BUILD_READINESS_DESIGN_AUDIT.md`;
- new D1–D6 protocol specifications under `docs/design/`;
- accepted ADR 0099 containing the implementation-facing design baseline;
- corrected and linked `docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md`;
- drafted reconciliations across the production stack recommendation and both
  prior Hong Kong design audits, with the final accepted decisions preserved;
- updated `docs/agent/CONTEXT.md`, `docs/agent/DECISIONS.md`,
  `docs/agent/ROADMAP.md`, and this handoff; and
- updated `AGENTS.md` and the continuity files; and
- no application, package, contract, migration, lock, or runtime file changed.

Earlier architecture-checkpoint changes still present in the worktree:

- root `pyproject.toml` and `uv.lock`;
- five new `apps/*` members and ten new canonical package-role skeletons;
- existing contract, Durable Task, and Management Register adapter boundary
  declarations, plus the new Management Register port dependency;
- `tools/architecture_spike.py`,
  `tools/architecture_spike_manifest.json`, and
  `tools/tests/test_architecture_spike.py`;
- expanded `tools/package_spike_manifest.json`, package proof/test handling,
  and package tests for all 18 members; and
- `AGENTS.md`, `README.md`, the technical stack proof checklist, and all four
  continuity files.

The reviewed checkpoint contains all earlier accumulated design and local
implementation work plus this reconciliation. The user explicitly authorized
one commit and push of that complete checkpoint; no other publication or
operation is authorized.
