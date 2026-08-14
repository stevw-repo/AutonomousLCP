---
status: accepted
date: 2026-08-10
amended_by: 0016
refined_by:
  - "0078"
---

# Separate the Serving State definition from its lifecycle

One **Serving State Definition** is a sealed immutable description of the
complete search state that Ask.Legal may serve. Its identity and fingerprint
are fixed before Approval. It contains:

- its schema version, stable identity, content fingerprint, and environment;
- its predecessor Serving State and exact rollback Serving State, except for an
  explicitly approved initial bootstrap;
- the complete Routing Configuration identity and fingerprint;
- every jurisdiction's exact Pinecone Index Generation, immutable index
  configuration, and Desired-State Inventory;
- all serving-record profile schemas and the complete internal Record
  Traceability Lookup;
- the query, filter, grouping, citation, authority-note, text-building, embedding
  provider, model, dimensions, and distance-metric contracts;
- the exact coverage-status manifest;
- the required inventory, retrieval, query-path compatibility, recovery, and
  post-cutover verification definitions; and
- immutable recovery references and every non-secret runtime setting that can
  change legal search results.

The fingerprint covers that canonical definition and every referenced
immutable identity and fingerprint. It does not cover Approval, execution
receipts, activation time, mutable status, transient monitoring observations,
secret values, or an incidental Ask.Legal application build.

The Promotion Manifest binds the candidate Serving State Definition. The
definition does not refer back to the manifest, avoiding a circular
fingerprint. Creating the definition does not mean its indexes exist, have
passed verification, or are active. It becomes an eligible **Serving State**
only when the manifest-authorized build and verification events prove that the
real targets match the definition.

What happened to a Serving State is recorded through separate immutable,
append-only lifecycle events. Event types cover build results, verification,
activation, post-cutover verification, failure, rollback activation, recovery
protection, and exact retirement. Each event identifies the environment,
Serving State, time, responsible identity, applicable Promotion Manifest,
Approval and execution lineage, predecessor event, remote-operation receipts,
and evidence fingerprints.

Lifecycle events never rewrite the Serving State Definition. The management
register may present a convenient current-status view, but that view is derived
from the event history and is not the source of truth.

Only an activation or rollback-activation event changes the active state for an
environment. It must use an atomic compare-and-set condition proving that the
approved base state is still active. Events are serialized so exactly one
Serving State is active per environment. Reactivating a retained predecessor
during rollback creates a new event pointing to the same immutable state; it
does not clone or modify that state.

The complete Azure routing generation carries both the exact jurisdiction
index mapping and the Serving State identity. Each answer-producing request
pins one activation event and Serving State for its entire lifetime. The answer
audit record contains the Serving State ID and activation-event ID. The exact
Ask.Legal build remains in the operational request log so incidents can still
be reconstructed without making routine app deployments part of the corpus
identity.

## Considered options

- put activation time, Approval, and execution results inside the Serving State
  fingerprint — rejected because those facts exist only after the candidate
  must be frozen and would change its identity;
- let the Serving State and Promotion Manifest fingerprint each other —
  rejected because that creates a circular identity dependency;
- store one mutable `status` field — rejected because activation, rollback, and
  retirement would overwrite history and make concurrent transitions unsafe;
- treat the Azure index-name settings alone as the Serving State — rejected
  because they do not prove inventories, contracts, coverage, authority notes,
  verification, or recovery; and
- create a new Serving State identity when rolling back — rejected because
  rollback reactivates an already verified immutable state.

## Consequences

The management register needs versioned schemas and canonical fingerprinting
for both Serving State Definitions and lifecycle events, plus a serialized
per-environment activation ledger with atomic base-state comparison. Azure's
complete routing generation must expose the Serving State ID alongside the
index mapping. Ask.Legal must pin and record that state for every answer.

The exact Azure activation mechanism, event storage technology, canonical
serialization algorithm, production bootstrap procedure, recovery retention
period, and retirement policy remain to be specified before implementation.
