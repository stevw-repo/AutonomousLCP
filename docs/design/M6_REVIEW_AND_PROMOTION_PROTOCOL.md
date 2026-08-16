# M6 Review, Approval, and Promotion Protocol

Status: accepted implementation-facing design

Date: 2026-08-16

Closes: `BR-10` and `BR-11`, provider boundary, index naming, routing
activation, and coverage interface

## 1. Frozen proposal package

The control plane commits one proposal package manifest last after every
referenced artifact passes schema, fingerprint, cross-reference, completeness,
and read-back checks. Canonical roles are:

```text
proposal-manifest.json
corpus-releases/
desired-state-inventories/
serving-state-definition/
record-traceability/
coverage-status/
change-inventory/
validation/
recovery-readiness/
cost-and-capacity/
review-report/
promotion-manifest/
```

The report is a deterministic projection of the same machine artifacts. It is
never a parallel source of authority. Any report field that cannot be derived
links to exact human-authored evidence included before freeze.

One immutable proposal fingerprint covers the complete inventory. After
`REVIEW_READY`, any changed byte, reference, policy profile, target fact,
validation, recovery fact, or base state creates a new package and invalidates
the old one.

## 2. Review projection

The reviewer sees, at minimum:

- observation cutoff, base and candidate Serving States, package validity, and
  exact identities;
- source coverage, failures, Quarantines, Coverage Gaps, carried-forward and
  withheld scopes;
- additions, replacements, unchanged records, and exact retirements by owner;
- before/after legal text and authority-note differences with evidence links;
- rule, model-task, deterministic validation, semantic evaluation, retrieval,
  security, recovery, cost, and capacity results;
- replacement target definitions, routing change, ordered actions, stop
  conditions, rollback state, and invalidation predicates; and
- an explicit no-change result when complete accounting proves no production
  change.

The client verifies every retrieved artifact fingerprint and keeps the viewed
manifest fingerprint visible at decision time. Approval cannot proceed if the
projection is incomplete, stale, or mismatched.

## 3. Governance baseline

One human permission role exists: `PipelineAdministrator`. Multiple named
people may receive it. Through the separately secured Review and Control APIs,
it permits inspection, fingerprint-bound comments, approval, rejection,
revocation, pipeline operation, stop, recovery, and rollback. It does not merge
application identities, database roles, deployment identities, or worker
effect capabilities.

Approval, rejection, and revocation require a non-empty reason, delegated
named-human token, current `PipelineAdministrator` permission, and immutable
audit evidence. Ordinary Entra sign-in and the production MFA baseline apply,
but there is no action-specific step-up or authentication-freshness rule. There
is no separate absence-cover construct; additional named people receive the
same ordinary role. Shared accounts remain forbidden.

Approval becomes valid at decision time and has no independent time-to-live.
Execution must consume it exactly once. Consumption, explicit revocation,
removal of current administrator permission, invalidation of the bound
Promotion Manifest, or failure of any bound evidence, base-state,
configuration, target, or recovery predicate makes it unusable. The manifest's
own evidence-freshness and validity rules still apply. One authorized human
decision is sufficient.

The version 1.1.0 `approval_decision` schema removes the former independent
`valid_until` field while preserving `valid_from` and every validity condition
on the referenced Promotion Manifest. Approval lifecycle version 1.1.0 also
removes the former `APPROVAL_EXPIRED` state; expiry of manifest evidence or a
bound predicate produces `APPROVAL_INVALIDATED`, not a second Approval clock.

## 4. Quarantine and review operations

Every open Quarantine, Coverage Gap, or Source Contract Review records its
severity, created time, affected scopes, evidence, and one or more assigned
named `PipelineAdministrator` users. Urgent release-blocking or potentially
misleading current-law issues notify the assigned administrators immediately.

There are no fixed one-, five-, or ten-business-day deadlines and no required
business-day calendar or periodic overdue-notification engine. An administrator
may set or change an explicit due time when useful. Elapsed time never releases
material or changes legal status: unresolved work remains blocked, safely
withheld, or explicitly carried forward under its evidence rule. Permanent
exclusion requires a Legal Desk Decision and complete release accounting.
Re-entry always creates a new linked work item and repeats every gate.

Named administrator assignments are versioned governance-profile data and
production cannot start with the required assignments unset. Optional due
times are recorded on the affected item when an administrator chooses one; no
business-day calendar exists.

## 5. Embedding boundary

Embeddings use Azure OpenAI models sold by Azure through Microsoft Foundry.
The promotion worker is the exclusive caller. Production uses stateless
embedding inference, an exact admitted deployment/model version, and a
user-assigned managed identity after the non-production Entra proof passes;
static API keys are not the accepted baseline.

An Embedding Request binds:

- Search Record ID and serving-payload fingerprint;
- exact `metadata.text` bytes only;
- tokenizer and token count;
- provider resource/geography class, deployment, model ID/version, API
  contract, dimensions, encoding, normalization, and metric;
- batch membership and position; and
- idempotency/cache key.

The cache key is SHA-256 over the exact text fingerprint plus the complete
embedding-profile fingerprint. Authority notes, operational traceability, and
unapproved fields are not embedded. Empty, oversized, mismatched, partial, or
non-finite vectors fail. A receipt records provider request ID, vector count,
dimension, normalized vector-byte fingerprint, usage, latency, and result—not
raw vectors in the Management Register.

Exact model and dimension are selected by the admitted retrieval evaluation
profile, not hard-coded into architecture. Changing either creates new vectors,
index configuration, Serving State, Promotion Manifest, and Approval.

## 6. Replacement target and exact retirement

The target adapter can create, describe, upsert into, enumerate, query, back
up, and delete only through manifest-bound commands. It cannot mutate the
active target in place.

Build order:

1. revalidate Approval, base state, recovery, configuration, and cost limit;
2. create the exact replacement index;
3. embed/upsert the complete Desired-State Inventory in bounded batches;
4. reconcile every receipt and enumerate the complete remote inventory;
5. compare IDs, fingerprints, counts, index configuration, namespaces, and
   metadata to the DSI;
6. run deterministic query-path and retrieval gates;
7. create Pinecone-native backup and verify separately administered recovery
   material;
8. mark the candidate Serving State `VERIFIED`;
9. activate the complete routing generation;
10. perform pinned-generation post-cutover checks; and
11. retain the predecessor for rollback. Retirement is a later exact manifest.

Unknown or unowned remote records block. Broad metadata deletion, wildcard
delete, delete-all, prefix-derived deletion, and runtime-derived retirement are
not represented by any port.

## 7. Pinecone index naming

Decision 5 fixes the final name as:

`asklegal-<env3>-<jur3>-<YYYYMMDD>-<state12>`

Rules:

- `env3` is one of `dev`, `stg`, or `prd`;
- `jur3` is the registered lowercase ISO-derived three-character project code;
- the date is the UTC Serving State freeze date;
- `state12` is the first twelve hexadecimal characters of the immutable
  Serving State Definition SHA-256 after collision checking;
- only lowercase ASCII letters, digits, and dashes are permitted;
- the name is at most 40 characters and, with the actual Pinecone project ID
  and separating dash, must be at most 52 characters; and
- a collision with different full fingerprints is a hard failure that requires
  a newly registered disambiguation token in a new definition—never overwrite
  or reuse.

`latest`, mutable aliases, sequence-only names, and date-only names are
forbidden.

## 8. Ask.Legal routing activation

Ask.Legal uses one complete routing generation, serialized as an immutable
configuration artifact and referenced by one non-sticky App Service setting.
It maps every served jurisdiction to an exact index host/name, Serving State,
Query Contract, embedding profile, and coverage manifest fingerprint.

Decision 4 fixes production activation as a restricted `candidate` App Service
deployment slot, distinct from the existing development slot, and a manually
authorized standard slot swap:

1. deploy the already admitted Ask.Legal application build when a build change
   is required; otherwise use the exact production-compatible build;
2. place the candidate complete routing generation on the candidate slot as a
   swappable setting; secrets, identities, networking, diagnostics, and other
   environment facts remain slot-specific;
3. warm the slot and verify exact target connectivity, query compatibility,
   coverage retrieval, and generation pinning;
4. compare the complete source/target slot configuration and prove every
   setting's sticky/non-sticky classification matches the manifest;
5. execute the standard swap through the manifest-bound Azure operation; App
   Service applies target slot-specific settings to the candidate instances,
   restarts and warms them, and must abort the swap if readiness fails;
6. append activation only after the production endpoint reports the candidate
   generation and passes post-cutover checks.

Every request snapshots one routing-generation ID before its first retrieval
and uses it for all jurisdictions. Direct edits to production routing settings,
auto-swap, percentage traffic mixing between generations, and using the
development slot as a production candidate are forbidden. Rollback is the
manifest-declared reverse swap to the retained predecessor followed by exact
verification.

Production admission must prove that the Ask.Legal App Service plan supports
the additional slot and has adequate shared capacity. If it does not, activation
remains disabled until capacity is provided or a later design decision selects
another complete-generation mechanism; the development slot is not silently
repurposed.

## 9. Coverage-status interface

Each Serving State contains one complete immutable Coverage Status Manifest
with every expected Release Scope, status, last verified time, open
gap/quarantine/source-failure references, and user-facing warning code. The
routing generation binds its exact SHA-256 fingerprint and protected immutable
Azure download reference. No dedicated coverage-signing identity, signing key,
rotation, or signature-validation lifecycle is required.

Ask.Legal retrieves the manifest through authenticated protected storage,
verifies the exact bytes against the bound fingerprint, caches the verified
copy by routing generation, and exposes coverage warnings alongside
search/answer behavior. It never interprets absence of a record as proof that
no law exists.

Activation blocks if the candidate manifest is missing, incomplete, has the
wrong fingerprint, or does not account for every expected scope. After
activation, a temporary manifest-store failure may use only the matching
verified cached copy. If neither a valid stored nor cached copy exists,
Ask.Legal shows a global `coverage status unavailable` warning and records an
incident; it does not silently claim complete coverage.

Coverage Status Manifest version 1.1.0 removes `signature_policy_state` and
requires each scope to carry `last_verified_at`, exact gap, Quarantine, and
source-failure references, plus the closed warning code matching its status.
The serving/routing package still binds the complete manifest reference and
fingerprint; protected storage resolves that immutable reference without
placing credentials in the manifest.

## 10. Reports and rollback

Before, no-change, approval, execution, after, incident, and recovery reports
are immutable typed artifacts. Each includes run/package/state refs, counts,
gaps, decisions, effect receipts, verification, elapsed time, costs, and exact
unresolved work. Reports contain references to sensitive evidence rather than
copying it.

Rollback activates only the exact retained predecessor. It does not undo
evidence, decisions, or audit facts. Recovery and rollback append new events
and reports. A failed rollback becomes an incident and leaves broad cleanup
disabled.

## 11. Required M6 proof

Local tests must prove stale/revoked/consumed Approval, administrator-role
removal, manifest invalidation, manifest drift, base-state drift, overlapping execution,
partial batch, lost acknowledgement, vector mismatch, unknown remote record,
  quota/cost stop, backup failure, routing compare-and-set loss, swap preflight
  or platform warm-up abort,
post-cutover failure, rollback, coverage-fingerprint mismatch,
coverage-unavailable behavior, and exact retirement denial.

This design uses current official constraints documented by Microsoft for
[Azure OpenAI embeddings](https://learn.microsoft.com/en-us/azure/foundry/openai/tutorials/embeddings),
[Azure App Service deployment-slot swaps](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots),
and Pinecone for
[index-name restrictions](https://docs.pinecone.io/troubleshooting/restrictions-on-index-names).

This document is design authority only and grants no model, embedding,
Pinecone, backup, routing, Azure, or production authorization.
