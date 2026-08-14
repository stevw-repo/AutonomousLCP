---
status: accepted
date: 2026-08-10
refined_by:
  - "0087"
---

# Make the Promotion Manifest the sole execution envelope

The Promotion Manifest is one sealed immutable machine-readable package. It is
the only object a human approves and the only production plan the promotion
worker may execute.

The manifest binds by exact identifier and fingerprint:

- its schema version, identity, creation time, observation cutoff, and validity
  window;
- the base Serving State and complete current Routing Configuration;
- the exact candidate Serving State Definition;
- every candidate Desired-State Inventory and referenced Corpus Release;
- the old and proposed Pinecone Index identities and configurations;
- code, build, contract, search-schema, embedding-model, dimension, metric,
  text-building, cache, and non-secret runtime setting identities;
- exact additions, replacements, carried-forward records, withholdings,
  retirements, unchanged records, and aggregate counts;
- source, legal-status, Quarantine, and Coverage Gap evidence;
- pre-change recovery evidence and the exact rollback Serving State;
- validation, retrieval, capacity, quota, and recovery-readiness results;
- expected cost and hard cost limits;
- the ordered actions, preconditions, verification checkpoints, stop
  conditions, post-cutover checks, and rollback action; and
- every evidence, freshness, target, configuration, recovery, time, or
  fingerprint condition that invalidates the package.

The manifest references immutable evidence and payload artifacts rather than
duplicating the full legal corpus. It contains no credentials, tokens, private
keys, vector values, or secret settings. Approval, execution checkpoints,
remote-operation receipts, and final results are separate append-only records
that refer to the manifest fingerprint and never mutate it.

The promotion worker cannot choose a different target, derive a new record
list, substitute a model or setting, broaden a retry, skip a checkpoint, invent
a compensating action, or use a different rollback state. A retry remains bound
to the same inputs and permitted checkpoint. Any material difference requires a
new Promotion Manifest and new Approval.

## Considered options

- approve each Corpus Release or Pinecone Index separately — rejected because
  the human would not approve one complete resulting Serving State;
- approve a human-readable report while the worker derives the executable plan
  later — rejected because the executed target could differ from the reviewed
  target;
- allow the worker to select current targets or settings at runtime — rejected
  because implicit `latest` choices defeat fingerprint-bound Approval; and
- embed credentials or the complete corpus in the manifest — rejected because
  secrets and large payloads belong in their bounded stores and can be bound by
  exact references and fingerprints.

## Consequences

The system needs a versioned Promotion Manifest schema, canonical serialization
and fingerprinting, immutable artifact references, deterministic diffing,
explicit action and rollback contracts, and objective invalidation predicates.
Human review may use a concise report, but that report is a view of this exact
machine-readable manifest rather than a separate source of authority.

ADR 0007 defines how one authorized human decision binds to the manifest and
remains objectively valid until execution.

ADR 0009 defines the candidate Serving State Definition that the manifest
binds. The definition does not refer back to this manifest; execution and
activation results are append-only lifecycle events, avoiding circular or
mutable fingerprints.
