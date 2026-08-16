# M2–M7 Build-Readiness Design Audit

Status: audit complete; closure package accepted

Audit date: 2026-08-16

Scope: the complete local pipeline from the M2 domain kernel through the M7
offline synthetic proof. This audit performs no implementation or operation.

## Verdict

The intended system is architecturally coherent. The five-application trust
model, immutable evidence and release model, exact human Approval boundary,
replacement-target promotion model, Python baseline, local-first Docker proofs,
and selected Azure production architecture do not need to be reopened.

The audit originally found that the cross-cutting contracts deliberately
stopped before the command, effect, workflow-run, application-API,
artifact-store, connector, governance-profile, and end-to-end conformance
specifications required by M2–M7. Accepted ADR 0099 and the six protocol
designs below close those gaps. Decision 7's task allocation and bounded LLM
semantic-decision authority are settled.

| Question | Audit answer |
|---|---|
| Is the overall architecture internally coherent? | Yes, subject to the ownership correction below |
| Can the first M2 domain-kernel slice start from the current design alone? | The design prerequisite is satisfied, but implementation still requires separate explicit authorization |
| Is the production provider service boundary selected? | Yes; decision 1 matches Ask.Legal Backend by selecting Azure OpenAI models sold through Microsoft Foundry for both model families, while exact model profiles remain admission evidence |
| Must the full Hong Kong legal corpus be implemented before M7 can prove the platform? | No; M7 uses a test-only synthetic Legal Desk package and makes no Hong Kong readiness claim |
| Does this audit authorize code, Azure, source, model, Pinecone, or deployment work? | No |

## Evidence reviewed

The audit traced:

- the canonical overall design and its system-wide open-decision register;
- ADRs 0001 through 0098, including later amendments and refinements;
- the two existing Hong Kong design audits and the accepted conformance
  catalogues;
- the 54-object cross-cutting contract inventory, six lifecycle machines,
  schemas, catalogues, fixtures, and immutable historical foundation status;
- the Management Register and Durable Task local proofs;
- the five application and thirteen package architecture manifest, including
  all declared dependency and capability edges; and
- every M2–M7 build item and exit gate in the delivery roadmap.

## What is coherent and stays settled

The audit found no reason to reopen these decisions:

1. one modular monorepo with five separately runnable and permissioned
   applications;
2. Python 3.14, FastAPI at the two HTTP boundaries, strict Pyright plus the
   repository boundary checker, and reproducible locked packages;
3. Azure SQL as the Management Register, with stored command procedures and
   append-only facts rather than unrestricted table writes;
4. Durable Task as coordination only, while the Management Register remains
   authoritative for business state and effect authority;
5. immutable primary evidence, separately administered recovery copies, and
   exact content fingerprints;
6. jurisdiction-and-material Legal Desks that decide from preserved evidence
   and cannot approve or deploy;
7. complete Corpus Releases and Desired-State Inventories rather than deltas;
8. one immutable Promotion Manifest, one exact human decision, and pre-effect
   revalidation;
9. replacement serving targets, exact verification, atomic routing-generation
   activation, and separately controlled retirement; and
10. local-first development with Docker-backed real-engine proofs and local
    fakes before any Azure proof.

## Corrections established by this audit

### 1. Manifest preparation belongs outside the privileged executor

The canonical design assigns complete-package assembly to the coordinator and
forbids the promotion worker from changing the approved manifest. The current
architecture spike correctly gives the promotion worker only
`approved_manifest_read`, but the control-plane declaration lacks a pure
manifest-preparation capability and lacks the contract-package dependency
needed to assemble the proposal.

The implementation-facing design must therefore make the split explicit:

- the legal-processing boundary freezes candidate Corpus Releases and their
  exact supporting artifacts;
- the control plane coordinates composition of the Desired-State Inventory,
  candidate Serving State Definition, review report, and proposed Promotion
  Manifest through pure corpus/promotion domain services with no production
  credentials;
- the Review application reads that frozen proposal and records the human
  decision without altering it; and
- the promotion worker reads only an exact approved manifest and cannot create,
  broaden, or replace it.

The architecture manifest must be revised and re-proved when M3 implementation
is authorized. This audit does not modify that validated checkpoint.

### 2. The M7 platform proof is synthetic, not a Hong Kong readiness claim

M5 describes production legal packages, while M7 asks for one fully runnable
offline flow. Requiring all accepted Hong Kong families before the plumbing can
be proved would couple platform correctness to source rights, real evidence,
model admission, and a large body of jurisdiction work.

M7 will instead use one closed, test-only synthetic jurisdiction/material
package supplied by test utilities. It must exercise the same contracts,
failure paths, evidence rules, Approval boundary, and promotion rules as a real
package, but it:

- is never entered in a production Release Scope Registry;
- grants no source, model, publication, or promotion capability;
- cannot satisfy any Hong Kong Source Rulebook or conformance gate; and
- proves platform orchestration and traceability only, not legal completeness,
  semantic model quality, or production retrieval quality.

Production legal packages retain their own M5 exit gates. A package is enabled
only after its exact source universe, executable rules, fixtures, evaluations,
and attestations are complete.

### 3. Historical foundation status stays historical

`contracts/foundation-status.json` correctly records the state at the ADR 0088
foundation checkpoint and must not be rewritten. ADRs 0089–0099 later selected
the application, infrastructure, provider-family, and implementation-facing
design baseline. Current prose must distinguish that immutable historical fact
from present project decisions; exact deployed model profiles and evidence-
dependent production settings remain admission work.

### 4. Reconstruction is an accepted conditional design path

ADRs 0080–0087 supersede the earlier blanket prohibition. A Legal Status Event
and exact amendment evidence may support a warned deterministic reconstructed
Hong Kong consolidation only through the closed operation registry, complete
plans and reports, exact artifact contract, later-HKeL reconciliation, and an
active attested capability. Project memory must not continue to state that the
pipeline never materializes such a result.

## Required design closure register

All twelve findings are closed at design level. Their machine schemas and code
remain milestone implementation work.

| ID | Gate | Gap | Required closure artifact |
|---|---|---|---|
| `BR-01` | **BLOCKS M2** | The 54-object foundation has no normative command envelope, command result, effect intent, effect receipt, or general idempotent-operation contract | Domain protocol specification with exact IDs, canonical fingerprint bases, causation/correlation, expected-version checks, idempotency semantics, accepted/rejected result algebra, and effect authorization/receipt rules |
| `BR-02` | **BLOCKS M2** | Aggregate ownership and transactional behavior are proved only for a narrow Approval/Serving State spike | Management Register aggregate and command catalogue mapping each command to owning application, procedure, input state, appended facts, outbox entries, concurrency token, replay result, ambiguous-commit resolution, projections, and recovery export |
| `BR-03` | **BLOCKS M2** | There is no normative pipeline-run/work-item lifecycle spanning schedule, acquisition, legal processing, package preparation, review, and promotion | Run/work lifecycle specification with observation cutoff, immutable input/configuration/contract/build references, retry and cancellation rules, terminal outcomes, overlap policy, workflow-version binding, and Management Register versus Durable Task ownership |
| `BR-04` | **BLOCKS M2** | The shared two-state bounded-review machine is too small to express Quarantine assignment, severity, optional due time, notification, resolution disposition, re-entry, and recurrence without ambiguity | Entity-specific Source Contract Review, Coverage Gap, and Quarantine resolution contracts. Keep immutable closed records, represent recurrence as a new linked record, and define exact release-blocking and re-entry effects |
| `BR-05` | Before M3 | The two APIs and three worker processes lack versioned operation contracts and runtime behavior | Application interface specification covering Control and Review operations, stable error envelope, pagination and immutable snapshot binding, idempotency, authorization matrix, health/readiness, configuration validation, graceful shutdown, worker leasing/fencing, and no-ingress rules |
| `BR-06` | Before M3 | Proposal-package preparation ownership is inconsistent between prose and the architecture manifest | Revised dependency/capability manifest and tests giving the control plane an effect-free preparation path while retaining `approved_manifest_read` as the promotion worker's only manifest input |
| `BR-07` | Before M4 | The Evidence Vault design names storage guarantees but not the complete write/read protocol | Evidence artifact protocol defining canonical logical keys, media-type and byte validation, conditional create, partial-upload isolation, manifest-last commit, exact-version readback, corruption handling, primary-to-recovery receipt, retention/hold metadata, and local fake behavior |
| `BR-08` | Before M4 | Watcher and Scraper responsibilities are clear, but their executable boundary is not | Connector protocol with observation request/result, cutoff and source-contract binding, pagination/completeness proof, supported no-change evidence, retries/throttling, changed-source capture, hostile-byte isolation, stable failure classes, and coverage consequences |
| `BR-09` | Before M5 | The legal-policy designs and conceptual catalogues are not executable package contracts | Source Rulebook package specification covering layout, schema and code locks, source-universe inventory, rule traces, fixtures, deterministic outputs, semantic evaluation isolation, admission attestations, activation/suspension, and per-scope readiness |
| `BR-10` | Before M6 | Corpus, traceability, review, report, and promotion objects exist, but their multi-artifact sealing and provider-neutral execution ports are not complete | Corpus/promotion package protocol defining canonical file layouts and order, manifest-last sealing, review projection, report schemas, embedding request/receipt/cache key, replacement-target inventory, backup and routing compare-and-swap, verification, rollback, and exact retirement interfaces |
| `BR-11` | Before M6 | Approval and Quarantine schemas can say policy is configured but no policy-profile contract supplies the actual values | Versioned governance profile schemas. Decision 2 fixes one human `PipelineAdministrator` role, no action-specific step-up, no independent Approval TTL, single consumption, and no absence-cover construct; decision 3 fixes severity, named assignment, immediate urgent notification, optional due times, and no fixed SLA |
| `BR-12` | Before M7 | Roadmap scenarios are prose and do not form one auditable end-to-end acceptance package | M7 conformance matrix mapping every invariant and adverse scenario to exact fixtures, expected artifacts, expected register state, expected effects, restart point, report result, and reproducibility command |

## Six closure packets

The gaps above should be resolved as six focused design artifacts rather than
as one oversized specification:

| Packet | Covers | Exit condition |
|---|---|---|
| **D1 — Domain and Register protocol** | `BR-01`–`BR-04` | Every command, aggregate, lifecycle, concurrency outcome, and effect boundary needed by M2 has one exact normative definition |
| **D2 — Application interfaces** | `BR-05`–`BR-06` | Both APIs and all workers have exact startup/runtime contracts and the manifest-preparation ownership is mechanically enforceable |
| **D3 — Acquisition and Evidence protocol** | `BR-07`–`BR-08` | A synthetic connector can prove complete observation and immutable two-vault evidence behavior without external access |
| **D4 — Executable Legal Desk package** | `BR-09` plus the synthetic-package boundary | One test-only package proves the package mechanism; production packages remain independently gated |
| **D5 — Review and Promotion protocol** | `BR-10`–`BR-11` | A frozen proposal can be reviewed and executed against provider-neutral local fakes with exact invalidation, recovery, and rollback |
| **D6 — End-to-end conformance plan** | `BR-12` | The complete M7 flow and every required adverse path have exact reproducible expected results |

D1 through D6 are accepted by ADR 0099. They are:

- [`M2_DOMAIN_AND_REGISTER_PROTOCOL.md`](M2_DOMAIN_AND_REGISTER_PROTOCOL.md);
- [`M3_APPLICATION_INTERFACE_PROTOCOL.md`](M3_APPLICATION_INTERFACE_PROTOCOL.md);
- [`M4_ACQUISITION_AND_EVIDENCE_PROTOCOL.md`](M4_ACQUISITION_AND_EVIDENCE_PROTOCOL.md);
- [`M5_EXECUTABLE_LEGAL_DESK_PACKAGE_PROTOCOL.md`](M5_EXECUTABLE_LEGAL_DESK_PACKAGE_PROTOCOL.md);
- [`M6_REVIEW_AND_PROMOTION_PROTOCOL.md`](M6_REVIEW_AND_PROMOTION_PROTOCOL.md);
  and
- [`M7_END_TO_END_CONFORMANCE_PLAN.md`](M7_END_TO_END_CONFORMANCE_PLAN.md).

## Accepted closure package

Decision 1 selected Azure OpenAI for both generative proposals and embeddings
to match Ask.Legal Backend. Decision 2 selected one human
`PipelineAdministrator` role, no action-specific step-up, no independent
Approval TTL, single consumption, and no absence-cover construct. Decision 3
selects severity, named assignment, immediate urgent notification, optional
administrator-set due times, and no fixed review SLA.

Decision 4 selects a separate restricted production-candidate App Service slot,
manual validated swap, request-generation pinning, and reverse-swap rollback;
the existing development slot remains development-only.

Decision 5 selects
`asklegal-<env3>-<jur3>-<YYYYMMDD>-<state12>` with an internal 40-character
limit, full-fingerprint collision checks, and validation against Pinecone's
live API and project-ID hostname constraints.

Decision 6 selects one complete immutable, fingerprint-bound Coverage Status
Manifest per routing generation, protected authenticated retrieval, verified
caching, activation blocking for missing/incomplete/mismatched coverage, and a
global fail-visible warning when neither stored nor cached bytes are valid. It
does not add a dedicated signing identity or signing-key lifecycle.

Decision 7 selects LLM-assisted Gazette-event analysis/challenge and
Reconstruction Plan decision/challenge. Offline evaluation is deterministic
against human-adjudicated reference truth, and every other otherwise-
unallocated task defaults to `NO_GENERATIVE_LLM` for now.

All seven material choices and the complete package are accepted. This closes
the design prerequisite only and grants no implementation or operational
authority.

## Admission data that is not an open design gap

Exact deployed model versions, measured thresholds, regions, capacity,
retention, recovery objectives, service levels, alert thresholds, source
inventories, source rights, named role assignments, and real evaluation sets
remain required before their capabilities activate. The accepted protocols
define candidate profile/evidence contracts and fail-closed behavior. These
values are not floating architecture choices and receive no implicit defaults.

## External prerequisites that block real packages, not the platform proof

- source-specific rights, contracts, and legal-compliance approval;
- complete production source registers and endpoint inventories;
- preserved real evidence and adjudicated evaluation sets;
- source- and jurisdiction-specific operational owners; and
- provider accounts, quotas, credentials, and non-production environments.

None may be replaced with synthetic evidence in a production readiness claim.

## Milestone readiness after the audit

| Milestone | Readiness verdict |
|---|---|
| M2 | Design-ready; implementation remains separately unauthorized |
| M3 | Design-ready; architecture manifest correction must be implemented and re-proved |
| M4 | Design-ready; connector and vault implementations remain |
| M5 | Package mechanism design-ready; every real package retains its own evidence gates |
| M6 | Design-ready; provider and production effects remain disabled |
| M7 | Conformance plan complete; genuine proof waits for implemented M2–M6 local capabilities |

## Authorization boundary

This audit changes documentation only. It does not authorize domain or
application implementation, source access, legal-data acquisition, model or
embedding calls, Azure resources, Pinecone access, backup or routing mutation,
deployment, publication, commit, push, or any other remote action.
